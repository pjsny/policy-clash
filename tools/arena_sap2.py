"""The `sap2-v1` arena: discover bots, play a round robin, rewrite the board.

Discovers every `bots/sap2/*/bot.py`, plays every unordered pair in both
seatings over a fixed seed range, fits a rating, and rewrites
`bots/sap2/LEADERBOARD.md`. See `bots/README.md` for the submission interface
and the rules.

The protocol is fixed so that two runs of the board agree: seeds from
`ARENA_SEED_BASE`, both seatings for each seed and pair, and a Bradley-Terry
fit with a prior.

A bot receives an `Observation` and nothing else - no env handle, no seat
index, no seed. That is enforced here by construction rather than by review:
`act()` takes one argument, so a bot has nothing else to reach for. A bot
marked `"class": "reference"` in its `meta.json` may break that rule on
purpose, and never ranks.

Usage:

    envs/.venv/bin/python tools/arena_sap2.py
    envs/.venv/bin/python tools/arena_sap2.py --matches 120
    envs/.venv/bin/python tools/arena_sap2.py --only greedy,ppo_mlx
    envs/.venv/bin/python tools/arena_sap2.py --reference
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sys
import time
from datetime import date
from itertools import combinations
from pathlib import Path

try:
    from policyclash_envs import make
    from policyclash_envs.base import Outcome, Termination
except ImportError:
    sys.exit("Run this with envs/.venv/bin/python - policyclash_envs lives there.")

ENV_ID = "sap2-v1"
ROOT = Path(__file__).resolve().parent.parent
BOTS_DIR = ROOT / "bots" / "sap2"
BOARD = BOTS_DIR / "LEADERBOARD.md"

ARENA_SEED_BASE = 900_000  # disjoint from tools/train_ppo_sap2.py's training range
TIME_BUDGET_MS = 20.0

IGNORED = 0


class Entry:
    """One discovered submission: its metadata, its factory, and its stats."""

    def __init__(self, slug: str, meta: dict, factory) -> None:
        self.slug = slug
        self.meta = meta
        self.factory = factory
        self.ranked = meta.get("class", "ranked") == "ranked"
        self.act_times: list[float] = []
        self.forfeits = 0

    def build(self, seed: int):
        return self.factory(seed)


def load_bot(slug: str):
    """Import `bots/sap2/<slug>/bot.py` and return its `make_bot` factory.

    Shared with `tools/train_ppo_sap2.py`, which draws its opponent pool from
    the same directory the arena ranks. One loader means a bot cannot behave
    one way in training and another way on the board.
    """
    bot_file = BOTS_DIR / slug / "bot.py"
    spec = importlib.util.spec_from_file_location(f"bots_sap2_{slug}", bot_file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.make_bot


def discover(only: set[str] | None, include_reference: bool) -> tuple[list[Entry], list[str]]:
    """Load every bot. Returns the loaded entries and the slugs that failed.

    The failures matter as much as the successes. A bot whose dependency is
    missing on this machine - `mlx` on a machine that is not an Apple
    silicon Mac, for one - must not quietly vanish from a board that then
    replaces the committed one.
    """
    entries: list[Entry] = []
    skipped: list[str] = []
    for bot_file in sorted(BOTS_DIR.glob("*/bot.py")):
        slug = bot_file.parent.name
        if only and slug not in only:
            continue

        meta_file = bot_file.parent / "meta.json"
        meta = json.loads(meta_file.read_text()) if meta_file.exists() else {}
        if meta.get("class", "ranked") == "reference" and not include_reference:
            continue

        spec = importlib.util.spec_from_file_location(f"bots_sap2_{slug}", bot_file)
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception as exc:  # a missing dependency must be loud, not silent
            deps = ", ".join(meta.get("deps", [])) or "none declared"
            print(f"  skipping {slug}: import failed ({exc.__class__.__name__}: {exc}); deps: {deps}")
            skipped.append(slug)
            continue
        if not hasattr(module, "make_bot"):
            print(f"  skipping {slug}: no make_bot(seed)")
            skipped.append(slug)
            continue

        entries.append(Entry(slug, meta, module.make_bot))
    return entries, skipped


def play(first: Entry, second: Entry, seed: int) -> tuple[Outcome, Termination]:
    """One match. Seat 0 is `first`.

    Each bot is rebuilt for every match from a seed derived from the match
    seed, so no state leaks between matches and the whole run is reproducible.
    """
    env = make(ENV_ID)
    bots = (first.build(seed * 7919 + 1), second.build(seed * 7919 + 2))
    owners = (first, second)

    result = env.reset(seed=seed)
    while not result.done:
        actions = [IGNORED, IGNORED]
        for s in (0, 1):
            obs = result.observations[s]
            if obs is None:
                continue
            t0 = time.perf_counter()
            # A ranked bot only ever gets `act(obs)`. A reference bot may
            # declare `act_privileged(env, seat, obs)` and reach the env
            # itself, which is the whole reason it cannot rank.
            bot = bots[s]
            if owners[s].ranked or not hasattr(bot, "act_privileged"):
                actions[s] = int(bot.act(obs))
            else:
                actions[s] = int(bot.act_privileged(env, s, obs))
            owners[s].act_times.append((time.perf_counter() - t0) * 1000.0)
        result = env.step(*actions)

    if result.termination == Termination.ILLEGAL_ACTION:
        # An out-of-range action forfeits. Charge it to whichever bot lost, and
        # report it: a bot that forfeits is broken, not merely weak.
        loser = second if result.outcome == Outcome.PLAYER_0 else first
        loser.forfeits += 1

    return result.outcome, result.termination


def bradley_terry(wins: dict[tuple[str, str], float], names: list[str], prior: float = 1.0) -> dict[str, float]:
    """Maximum likelihood strengths on the Elo scale, field mean 1500.

    A round robin has no meaningful match order, so an order-dependent Elo
    update would report the order as much as the strength. `prior` adds that
    many drawn games between every pair: a bot that wins every game has no
    finite maximum likelihood strength, and a clean sweep is a normal result
    here, so without it a rating reports only how long the iteration ran. Each
    rating is therefore a conservative bound on the true separation.
    """
    if len(names) < 2:
        return {n: 1500.0 for n in names}

    strength = {n: 1.0 for n in names}
    played = {
        (a, b): wins.get((a, b), 0.0) + wins.get((b, a), 0.0) + prior
        for a in names
        for b in names
        if a != b
    }
    scored = {n: sum(wins.get((n, b), 0.0) + prior / 2 for b in names if b != n) for n in names}

    for _ in range(5000):
        updated = {}
        for a in names:
            denom = sum(played[(a, b)] / (strength[a] + strength[b]) for b in names if a != b)
            updated[a] = scored[a] / denom if denom > 0 else strength[a]
        total = sum(updated.values())
        strength = {n: v * len(names) / total for n, v in updated.items()}

    scale = 400.0 / math.log(10.0)
    logs = {n: math.log(max(s, 1e-12)) for n, s in strength.items()}
    mean = sum(logs.values()) / len(logs)
    return {n: 1500.0 + scale * (v - mean) for n, v in logs.items()}


def median(xs: list[float]) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    mid = len(s) // 2
    return s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2


def write_board(
    entries: list[Entry],
    ratings: dict[str, float],
    wins: dict[tuple[str, str], float],
    records: dict[tuple[str, str], list[int]],
    matches: int,
    elapsed: float,
) -> None:
    ranked = [e for e in entries if e.ranked]
    order = sorted(ranked, key=lambda e: -ratings[e.slug])
    total_games = {e.slug: sum(wins.get((e.slug, o.slug), 0.0) + wins.get((o.slug, e.slug), 0.0) for o in entries if o is not e) for e in entries}

    lines = [
        "# sap2-v1 leaderboard",
        "",
        f"Generated by `tools/arena_sap2.py` on {date.today().isoformat()}. Do not edit by hand.",
        "",
        f"{matches} seeds from `{ARENA_SEED_BASE}`, both seatings for every pair. "
        f"{int(sum(total_games.values()) / 2)} matches in {elapsed:.0f}s.",
        "",
        "| # | bot | rating | winrate | median ms | max ms | forfeits | author | notes |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for i, e in enumerate(order, 1):
        won = sum(wins.get((e.slug, o.slug), 0.0) for o in entries if o is not e)
        played = total_games[e.slug]
        lines.append(
            f"| {i} | `{e.slug}` | {ratings[e.slug]:.0f} | {won / played:.1%} | "
            f"{median(e.act_times):.2f} | {max(e.act_times or [0]):.1f} | {e.forfeits} | "
            f"{e.meta.get('author', '?')} | {e.meta.get('notes', '')} |"
        )

    unranked = [e for e in entries if not e.ranked]
    if unranked:
        lines += [
            "",
            "## Reference bots, not ranked",
            "",
            "These break the observation-only rule on purpose, as a ceiling to measure "
            "against. See `bots/README.md` rule 2.",
            "",
            "| bot | winrate | notes |",
            "|---|---|---|",
        ]
        for e in unranked:
            won = sum(wins.get((e.slug, o.slug), 0.0) for o in entries if o is not e)
            played = total_games[e.slug] or 1
            lines.append(f"| `{e.slug}` | {won / played:.1%} | {e.meta.get('notes', '')} |")

    lines += ["", "## Head to head", "", "| pair | record | draws |", "|---|---|---|"]
    for (a, b), (wa, wb, dr) in records.items():
        lines.append(f"| `{a}` vs `{b}` | {wa}-{wb} | {dr} |")

    lines += [
        "",
        "Ratings come from a Bradley-Terry fit on the Elo scale, field mean 1500, with "
        "one drawn game for each pair as a prior. A clean sweep has no finite maximum "
        "likelihood strength, so each rating is a conservative bound on the true "
        "separation, not a point estimate.",
        "",
    ]
    BOARD.write_text("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--matches", type=int, default=60, help="seeds per pair")
    parser.add_argument("--only", type=str, default="", help="comma-separated slugs")
    parser.add_argument("--reference", action="store_true", help="include reference bots")
    parser.add_argument("--no-write", action="store_true", help="print only, leave the board alone")
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="write the board even though a bot failed to load",
    )
    args = parser.parse_args()

    only = {s.strip() for s in args.only.split(",") if s.strip()} or None
    print(f"discovering bots in {BOTS_DIR.relative_to(ROOT)}")
    entries, skipped = discover(only, args.reference)
    if len(entries) < 2:
        sys.exit(f"need at least 2 bots to run a round robin, found {len(entries)}")
    print(f"  {', '.join(e.slug for e in entries)}\n")

    wins: dict[tuple[str, str], float] = {}
    records: dict[tuple[str, str], list[int]] = {}
    t0 = time.perf_counter()

    for a, b in combinations(entries, 2):
        record = [0, 0, 0]
        for i in range(args.matches):
            seed = ARENA_SEED_BASE + i
            for first, second in ((a, b), (b, a)):
                outcome, _ = play(first, second, seed)
                if outcome == Outcome.DRAW:
                    record[2] += 1
                    wins[(a.slug, b.slug)] = wins.get((a.slug, b.slug), 0.0) + 0.5
                    wins[(b.slug, a.slug)] = wins.get((b.slug, a.slug), 0.0) + 0.5
                    continue
                winner = first if outcome == Outcome.PLAYER_0 else second
                loser = second if outcome == Outcome.PLAYER_0 else first
                wins[(winner.slug, loser.slug)] = wins.get((winner.slug, loser.slug), 0.0) + 1.0
                record[0 if winner is a else 1] += 1
        records[(a.slug, b.slug)] = record
        print(f"  {a.slug:>10} vs {b.slug:<10} {record[0]:>4}-{record[1]:<4} ({record[2]} draws)")

    elapsed = time.perf_counter() - t0
    ranked_names = [e.slug for e in entries if e.ranked]
    ratings = bradley_terry(
        {k: v for k, v in wins.items() if k[0] in ranked_names and k[1] in ranked_names},
        ranked_names,
    )

    print("\nrating (Bradley-Terry, Elo scale, field mean 1500)")
    for slug, r in sorted(ratings.items(), key=lambda kv: -kv[1]):
        entry = next(e for e in entries if e.slug == slug)
        flag = f"  {entry.forfeits} FORFEITS" if entry.forfeits else ""
        print(f"  {slug:>10}  {r:7.0f}   median {median(entry.act_times):5.2f} ms{flag}")

    slow = [e for e in entries if median(e.act_times) > TIME_BUDGET_MS]
    for e in slow:
        print(f"\n  WARNING {e.slug} median {median(e.act_times):.1f} ms is over the {TIME_BUDGET_MS:.0f} ms budget")

    if not args.no_write:
        if skipped and not args.allow_partial:
            # The board replaces a committed file, so a partial run must not
            # write it. `ppo_mlx` depends on mlx, which needs an Apple silicon
            # Mac; on any other machine that bot fails to load, and writing
            # here would commit a board with a bot missing and every rating
            # refitted without it. Refuse, and say what to do about it.
            print(f"\nREFUSING to write {BOARD.relative_to(ROOT)}: {', '.join(skipped)} failed to load.")
            print("Install the missing dependencies, or pass --allow-partial to write without them.")
            print(f"done in {elapsed:.0f}s\n")
            sys.exit(1)
        write_board(entries, ratings, wins, records, args.matches, elapsed)
        print(f"\nwrote {BOARD.relative_to(ROOT)}")
    print(f"done in {elapsed:.0f}s\n")


if __name__ == "__main__":
    main()
