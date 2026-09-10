#!/usr/bin/env python3
"""Terminal visualizer for sap2-v1 matches, driven by the real C engine.

Runs an actual match through `policyclash_envs.make("sap2-v1")` - the same
compiled `sap2.h` core the tests and fuzz runs exercise, not a
reimplementation - and renders it round by round in the terminal.

What this can and can't show, and why: `sap2_battle` in the C core
resolves a round's fight and returns only the aggregate outcome
(P0_WIN/P1_WIN/DRAW) - it does not record a per-exchange trace, by
design (see docs/envs/sap-v2.md and adding-an-env.md's "keep the adapter
thin" rule). So this tool shows what the real engine actually exposes:
each seat's team/shop/gold/lives/trophies before a round, the shop
actions taken that round (decoded from the replay), and the round's
result - not a fabricated blow-by-blow battle animation. A companion
project has a separate JS reimplementation of the battle algorithm, in a
browser game, that does track a trace for exactly the reason a human
player wants to see it; this tool intentionally doesn't duplicate that
here, so what it shows is never at risk of silently drifting from what
the real engine did.

Usage (run with envs/.venv's python - policyclash_envs is installed
editable there; see tools/README.md for the one extra dependency this
tool needs beyond that):

    envs/.venv/bin/python tools/visualize_sap2.py
    envs/.venv/bin/python tools/visualize_sap2.py --seed 42 --pause 0.6
    envs/.venv/bin/python tools/visualize_sap2.py --style random
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path

import numpy as np

try:
    from policyclash_envs import make
    from policyclash_envs.base import Outcome, Termination
    from policyclash_envs.sap2 import MAX_ROUNDS, STARTING_GOLD, STARTING_LIVES, TROPHIES_TO_WIN
except ImportError:
    sys.exit(
        "Couldn't import policyclash_envs. Run this with the venv it's installed\n"
        "into, e.g.:\n\n"
        "  envs/.venv/bin/python tools/visualize_sap2.py\n"
    )

from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

ENV_ID = "sap2-v1"

# ---- decoding the observation buffer back into something renderable ----
# Layout mirrors sap2.h / envs/tests/test_sap2.py exactly - see
# docs/envs/sap-v2.md "Observation changes" for the field-by-field spec.
TEAM_BASE = 4  # after gold(1) lives(1) trophies(1) turn(1)
TEAM_SLOT_WIDTH = 19
SHOP_PET_BASE = TEAM_BASE + 5 * TEAM_SLOT_WIDTH
SHOP_PET_SLOT_WIDTH = 13
SHOP_FOOD_BASE = SHOP_PET_BASE + 5 * SHOP_PET_SLOT_WIDTH
SHOP_FOOD_SLOT_WIDTH = 5

SPECIES_NAME = {
    0: "-", 1: "Ant", 2: "Beaver", 3: "Cricket", 4: "Duck", 5: "Fish",
    6: "Horse", 7: "Mosquito", 8: "Otter", 9: "Pig", 10: "Pigeon",
    11: "Z.Cricket", 12: "Bee",
}
SPECIES_EMOJI = {
    0: " ", 1: "🐜", 2: "🦫", 3: "🦗", 4: "🦆", 5: "🐟",
    6: "🐴", 7: "🦟", 8: "🦦", 9: "🐖", 10: "🕊", 11: "🦗", 12: "🐝",
}
FOOD_NAME = {0: "-", 1: "Apple", 2: "Honey", 3: "Bread Crumbs"}
FOOD_EMOJI = {0: " ", 1: "🍎", 2: "🍯", 3: "🥖"}

PAIRS = [(i, j) for i in range(5) for j in range(i + 1, 5)]


def shop_size(turn: int) -> tuple[int, int]:
    """Same table as sap2.h's sap2_shop_size - see docs/envs/sap-v2.md for
    why the exact numbers are a documented default, not a pinned source."""
    if turn <= 2:
        return 3, 1
    if turn <= 4:
        return 4, 1
    return 5, 2


def decode_action(a: int) -> str:
    """Inverse of sap2.h's action layout - for printing what a seat did."""
    if a == 0:
        return "END_TURN"
    if 1 <= a < 6:
        return f"buy shop-pet {a - 1}"
    if 6 <= a < 11:
        return f"sell team {a - 6}"
    if 11 <= a < 21:
        i, j = PAIRS[a - 11]
        return f"combine team {i}+{j}"
    if a == 21:
        return "reroll"
    if 22 <= a < 32:
        i, j = PAIRS[a - 22]
        return f"reposition team {i}<->{j}"
    if 32 <= a < 42:
        off = a - 32
        return f"feed food {off // 5} -> team {off % 5}"
    if 42 <= a < 47:
        return f"freeze shop-pet {a - 42}"
    if 47 <= a < 49:
        return f"freeze food {a - 47}"
    return f"illegal({a})"


def decode_team(f: np.ndarray) -> list[dict]:
    out = []
    for t in range(5):
        base = TEAM_BASE + t * TEAM_SLOT_WIDTH
        species = int(np.argmax(f[base : base + 13]))
        level = int(np.argmax(f[base + 15 : base + 18])) + 1 if species else 0
        out.append(
            {
                "species": species,
                "atk": int(f[base + 13]),
                "hp": int(f[base + 14]),
                "level": level,
                "honey": bool(f[base + 18]),
            }
        )
    return out


def decode_shop_pets(f: np.ndarray, pet_slots: int) -> list[dict]:
    out = []
    for k in range(5):
        base = SHOP_PET_BASE + k * SHOP_PET_SLOT_WIDTH
        out.append(
            {
                "species": int(np.argmax(f[base : base + 11])),
                "hp_bonus": int(f[base + 11]),
                "frozen": bool(f[base + 12]),
                "active": k < pet_slots,
            }
        )
    return out


def decode_shop_food(f: np.ndarray, food_slots: int) -> list[dict]:
    out = []
    for k in range(2):
        base = SHOP_FOOD_BASE + k * SHOP_FOOD_SLOT_WIDTH
        out.append(
            {
                "species": int(np.argmax(f[base : base + 4])),
                "frozen": bool(f[base + 4]),
                "active": k < food_slots,
            }
        )
    return out


def decode_meta(f: np.ndarray) -> dict:
    return {"gold": int(f[0]), "lives": int(f[1]), "trophies": int(f[2]), "turn": int(f[3])}


# ---- a simple scripted policy driving both seats ----
# Same spirit as the browser game's bot and the fuzz-test harness: not a
# trained model (that's still downstream of the PufferLib build gap - see
# the readiness report), just something that plays plausibly enough for a
# match to be worth watching.


def choose_action(rng: random.Random, legal: np.ndarray, style: str) -> int:
    legal_idx = [i for i, ok in enumerate(legal) if ok]
    if style == "random":
        return rng.choice(legal_idx)
    buys = [a for a in legal_idx if 1 <= a < 6]
    combos = [a for a in legal_idx if 11 <= a < 21]
    if buys and rng.random() < 0.7:
        return rng.choice(buys)
    if combos and rng.random() < 0.5:
        return rng.choice(combos)
    if 21 in legal_idx and rng.random() < 0.3:
        return 21
    return 0


# ---- rendering ----

SEAT_COLOR = ["cyan", "magenta"]


def pet_line(p: dict) -> Text:
    if not p["species"]:
        t = Text("  ·  empty", style="dim")
        return t
    name = SPECIES_NAME[p["species"]]
    t = Text(f"{SPECIES_EMOJI[p['species']]} ")
    t.append(f"{name:<10}", style="bold")
    t.append(f"Lv{p['level']} ", style="dim")
    t.append(f"⚔{p['atk']:<3}", style="red")
    t.append(f"❤{p['hp']:<3}", style="green")
    if p["honey"]:
        t.append(" 🍯")
    return t


def shop_pet_line(p: dict) -> Text:
    if not p["active"]:
        return Text("  ·  (locked)", style="dim")
    if not p["species"]:
        return Text("  ·  empty", style="dim")
    name = SPECIES_NAME[p["species"]]
    t = Text(f"{SPECIES_EMOJI[p['species']]} ")
    t.append(f"{name:<10}", style="bold")
    if p["hp_bonus"]:
        t.append(f"+{p['hp_bonus']}hp ", style="green")
    if p["frozen"]:
        t.append(" ❄", style="blue")
    return t


def shop_food_line(f: dict) -> Text:
    if not f["active"]:
        return Text("  ·  (locked)", style="dim")
    if not f["species"]:
        return Text("  ·  empty", style="dim")
    name = FOOD_NAME[f["species"]]
    t = Text(f"{FOOD_EMOJI[f['species']]} ")
    t.append(name, style="bold")
    if f["frozen"]:
        t.append(" ❄", style="blue")
    return t


def seat_panel(seat: int, features: np.ndarray, pet_slots: int, food_slots: int, actions_log: list[str]) -> Panel:
    meta = decode_meta(features)
    team = decode_team(features)
    shop_pets = decode_shop_pets(features, pet_slots)
    shop_food = decode_shop_food(features, food_slots)

    body = Table.grid(padding=(0, 1))
    body.add_column()
    body.add_row(Text(f"🪙 {meta['gold']}   ❤️ {meta['lives']}   🏆 {meta['trophies']}/{TROPHIES_TO_WIN}", style="bold"))
    body.add_row(Text("Team", style="underline"))
    for p in team:
        body.add_row(pet_line(p))
    body.add_row(Text("Shop", style="underline"))
    for p in shop_pets:
        body.add_row(shop_pet_line(p))
    for fd in shop_food:
        body.add_row(shop_food_line(fd))
    if actions_log:
        body.add_row(Text("This round:", style="underline dim"))
        body.add_row(Text(", ".join(actions_log) or "(none)", style="dim"))

    return Panel(body, title=f"Seat {seat}", border_style=SEAT_COLOR[seat], width=44)


def run(seed: int, style: str, pause: float, max_rounds: int | None) -> None:
    console = Console()
    env = make(ENV_ID)
    rng = random.Random(seed)
    result = env.reset(seed=seed)

    console.print(
        Panel(
            f"[bold]sap2-v1[/bold] match, seed=[bold]{seed}[/bold], policy=[bold]{style}[/bold]\n"
            f"Real C engine via policyclash_envs — not the browser game's JS reimplementation.",
            border_style="yellow",
        )
    )

    seat_actions: list[list[str]] = [[], []]
    round_start_features = [result.observations[0].features.copy(), result.observations[1].features.copy()]
    rounds_shown = 0

    # Plain sequential prints, not a rich.Live region: each round is new
    # content appended below the last, not one area refreshed in place, so
    # Live's continuous-redraw model is the wrong tool here.
    while not result.done:
        turn = env.turn
        ps, fs = shop_size(turn)
        actions = [0, 0]
        for seat in range(2):
            obs = result.observations[seat]
            if obs is None:
                continue
            a = choose_action(rng, obs.legal_actions, style)
            actions[seat] = a
            seat_actions[seat].append(decode_action(a))

        prev_meta = [decode_meta(round_start_features[s]) for s in range(2)]
        result = env.step(actions[0], actions[1])

        round_ended = result.done or env.turn != turn
        if round_ended:
            # Render this round's pre-battle state (captured at round
            # start) plus the actions each seat took, then the outcome.
            panels = [seat_panel(s, round_start_features[s], ps, fs, seat_actions[s]) for s in range(2)]
            console.print(Columns(panels, equal=True))

            if result.done:
                outcome_line = _final_summary(result)
            else:
                # Read what actually happened off the observed deltas, not
                # an inference from who won - the turn-3 life-back rule can
                # fire in this same transition and immediately cancel a
                # life just lost, which would make an inferred "loses a
                # life" message contradict the very next panel's display.
                new_meta = [decode_meta(result.observations[s].features) for s in range(2)]
                d_trophy = [new_meta[s]["trophies"] - prev_meta[s]["trophies"] for s in range(2)]
                d_lives = [new_meta[s]["lives"] - prev_meta[s]["lives"] for s in range(2)]
                if d_trophy[0] > 0 or d_trophy[1] > 0:
                    winner, loser = (0, 1) if d_trophy[0] > 0 else (1, 0)
                    outcome_line = f"[bold {SEAT_COLOR[winner]}]Seat {winner} wins round {env.turn - 1}[/]"
                    if d_lives[loser] < 0:
                        outcome_line += f" — Seat {loser} loses a life"
                    elif d_lives[loser] == 0:
                        outcome_line += f" — Seat {loser} loses a life, but the turn-3 catch-up rule gives it right back"
                else:
                    outcome_line = f"Round {env.turn - 1} was a draw — no lives or trophies change"
                    # A draw costs nobody a life, but either seat can still
                    # gain one here if they'd already lost lives earlier
                    # and this transition crosses into turn 3.
                    for s in range(2):
                        if d_lives[s] > 0:
                            outcome_line += f"\n  [dim]Seat {s} gets a life back — turn-3 catch-up rule[/dim]"
            console.print(outcome_line)
            console.print()
            rounds_shown += 1
            seat_actions = [[], []]
            time.sleep(pause)

            if max_rounds is not None and rounds_shown >= max_rounds:
                if not result.done:
                    console.print(f"[dim]--max-rounds {max_rounds} reached; stopping early (match not over).[/dim]")
                break

            if not result.done:
                round_start_features = [
                    result.observations[0].features.copy(),
                    result.observations[1].features.copy(),
                ]

    if result.done and (max_rounds is None or rounds_shown < max_rounds):
        console.print(Panel(_final_summary(result), border_style="green", title="Match over"))
    console.print(f"[dim]replay length: {len(env.replay())} ints ({len(env.replay()) // 2} ticks)[/dim]")


def _final_summary(result) -> str:
    outcome = result.outcome
    term = result.termination
    label = {
        Outcome.PLAYER_0: f"[bold {SEAT_COLOR[0]}]Seat 0 wins the match![/]",
        Outcome.PLAYER_1: f"[bold {SEAT_COLOR[1]}]Seat 1 wins the match![/]",
        Outcome.DRAW: "[bold]Match ends in a draw[/]",
    }[outcome]
    reason = {
        Termination.NATURAL: "10 trophies or opponent eliminated",
        Termination.ILLEGAL_ACTION: "illegal action forfeit",
        Termination.STEP_LIMIT: f"round limit reached ({MAX_ROUNDS} rounds)",
    }[term]
    return f"{label} ({reason})"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seed", type=int, default=None, help="match seed (random if omitted)")
    parser.add_argument("--style", choices=["greedy", "random"], default="greedy", help="scripted policy for both seats")
    parser.add_argument("--pause", type=float, default=0.8, help="seconds to pause after each round")
    parser.add_argument("--max-rounds", type=int, default=None, help="stop after this many rounds even if the match continues")
    args = parser.parse_args()

    seed = args.seed if args.seed is not None else random.randrange(2**31)
    run(seed, args.style, args.pause, args.max_rounds)


if __name__ == "__main__":
    main()
