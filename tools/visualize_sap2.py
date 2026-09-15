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
# Offsets come from the env, not from a copy of the layout: the blocks have
# widened twice while matching the shipped game (see docs/envs/sap-v2.md
# "Observation changes"), and a stale constant here would silently render
# the wrong numbers.
from policyclash_envs.sap2 import (  # noqa: E402 - after the rich imports on purpose
    ACT_BUY_FOOD_BASE,
    ACT_BUY_PET_BASE,
    ACT_COMBINE_BASE,
    ACT_FREEZE_FOOD_BASE,
    ACT_FREEZE_PET_BASE,
    ACT_REPOSITION_BASE,
    ACT_REROLL,
    ACT_SELL_BASE,
    FOOD_SLOTS,
    MAX_SHOP_PETS,
    MAX_LEVEL,
    NUM_ACTIONS,
    NUM_PERKS,
    PERK_HONEY,
    PERK_MEAT_BONE,
    PERK_NONE,
    SHOP_FOOD_SLOT_FLOATS,
    SHOP_PET_SLOT_FLOATS,
    TEAM_SLOT_FLOATS,
    TEAM_SLOTS,
)

TEAM_BASE = 4  # after gold(1) lives(1) trophies(1) turn(1)
# species one-hot, attack, health, level one-hot, exp, perk one-hot - every
# width derived, because the species block has grown twice (10 pets, then
# Tier 2's ten plus a third token) and the food block gained a price.
TEAM_SLOT_WIDTH = TEAM_SLOT_FLOATS
NUM_SPECIES = TEAM_SLOT_FLOATS - (2 + MAX_LEVEL + 1 + NUM_PERKS)
SHOP_PET_BASE = TEAM_BASE + TEAM_SLOTS * TEAM_SLOT_WIDTH
SHOP_PET_SLOT_WIDTH = SHOP_PET_SLOT_FLOATS
NUM_SHOP_SPECIES_ONEHOT = SHOP_PET_SLOT_FLOATS - 2
SHOP_FOOD_BASE = SHOP_PET_BASE + MAX_SHOP_PETS * SHOP_PET_SLOT_WIDTH
SHOP_FOOD_SLOT_WIDTH = SHOP_FOOD_SLOT_FLOATS
NUM_FOODS_ONEHOT = SHOP_FOOD_SLOT_FLOATS - 2

SPECIES_NAME = {
    0: "-", 1: "Ant", 2: "Beaver", 3: "Cricket", 4: "Duck", 5: "Fish",
    6: "Horse", 7: "Mosquito", 8: "Otter", 9: "Pig", 10: "Pigeon",
    11: "Crab", 12: "Flamingo", 13: "Hedgehog", 14: "Kangaroo", 15: "Peacock",
    16: "Rat", 17: "Snail", 18: "Spider", 19: "Swan", 20: "Worm",
    21: "Z.Cricket", 22: "Bee", 23: "Dirty Rat",
}
SPECIES_EMOJI = {
    0: " ", 1: "🐜", 2: "🦫", 3: "🦗", 4: "🦆", 5: "🐟",
    6: "🐴", 7: "🦟", 8: "🦦", 9: "🐖", 10: "🕊",
    11: "🦀", 12: "🦩", 13: "🦔", 14: "🦘", 15: "🦚",
    16: "🐀", 17: "🐌", 18: "🕷", 19: "🦢", 20: "🪱",
    21: "🦗", 22: "🐝", 23: "🐁",
}
FOOD_NAME = {
    0: "-", 1: "Apple", 2: "Honey", 3: "Meat Bone", 4: "Muffin", 5: "Pill",
    6: "Bread Crumbs",
}
FOOD_EMOJI = {0: " ", 1: "🍎", 2: "🍯", 3: "🦴", 4: "🧁", 5: "💊", 6: "🥖"}
PERK_EMOJI = {PERK_NONE: "", PERK_HONEY: "🍯", PERK_MEAT_BONE: "🦴"}

PAIRS = [(i, j) for i in range(5) for j in range(i + 1, 5)]


def shop_size(turn: int) -> tuple[int, int]:
    """Same table as sap2.h's sap2_shop_size - capacity by shop tier, with
    the tier schedule [3, 5, 7, 9, 11] measured out of the shipped build by
    policy-clash-re-tools."""
    if turn <= 4:
        return 3, 1
    if turn <= 8:
        return 4, 2
    return 5, 2


def decode_action(a: int) -> str:
    """Inverse of sap2.h's action layout - for printing what a seat did."""
    if a == ACT_BUY_PET_BASE - 1:
        return "END_TURN"
    if ACT_BUY_PET_BASE <= a < ACT_SELL_BASE:
        off = a - ACT_BUY_PET_BASE
        return f"buy shop-pet {off // TEAM_SLOTS} -> team {off % TEAM_SLOTS}"
    if ACT_SELL_BASE <= a < ACT_COMBINE_BASE:
        return f"sell team {a - ACT_SELL_BASE}"
    if ACT_COMBINE_BASE <= a < ACT_REROLL:
        i, j = PAIRS[a - ACT_COMBINE_BASE]
        return f"combine team {i}+{j}"
    if a == ACT_REROLL:
        return "reroll"
    if ACT_REPOSITION_BASE <= a < ACT_BUY_FOOD_BASE:
        i, j = PAIRS[a - ACT_REPOSITION_BASE]
        return f"reposition team {i}<->{j}"
    if ACT_BUY_FOOD_BASE <= a < ACT_FREEZE_PET_BASE:
        off = a - ACT_BUY_FOOD_BASE
        return f"feed food {off // TEAM_SLOTS} -> team {off % TEAM_SLOTS}"
    if ACT_FREEZE_PET_BASE <= a < ACT_FREEZE_FOOD_BASE:
        return f"freeze shop-pet {a - ACT_FREEZE_PET_BASE}"
    if ACT_FREEZE_FOOD_BASE <= a < NUM_ACTIONS:
        return f"freeze food {a - ACT_FREEZE_FOOD_BASE}"
    return f"illegal({a})"


def decode_team(f: np.ndarray) -> list[dict]:
    out = []
    for t in range(5):
        base = TEAM_BASE + t * TEAM_SLOT_WIDTH
        species = int(np.argmax(f[base : base + NUM_SPECIES]))
        lvl_base = base + NUM_SPECIES + 2
        level = int(np.argmax(f[lvl_base : lvl_base + MAX_LEVEL])) + 1 if species else 0
        out.append(
            {
                "species": species,
                # atk/hp are the totals sap2.h's accessors report, so a
                # Horse buff that expires next turn shows here while it
                # is live - same number the game's card shows.
                "atk": int(f[base + NUM_SPECIES]),
                "hp": int(f[base + NUM_SPECIES + 1]),
                "level": level,
                "exp": int(f[lvl_base + MAX_LEVEL]),
                "perk": (
                    int(np.argmax(f[lvl_base + MAX_LEVEL + 1 : lvl_base + MAX_LEVEL + 1 + NUM_PERKS]))
                    if species
                    else PERK_NONE
                ),
            }
        )
    return out


def decode_shop_pets(f: np.ndarray, pet_slots: int) -> list[dict]:
    out = []
    for k in range(5):
        base = SHOP_PET_BASE + k * SHOP_PET_SLOT_WIDTH
        out.append(
            {
                "species": int(np.argmax(f[base : base + NUM_SHOP_SPECIES_ONEHOT])),
                "hp_bonus": int(f[base + NUM_SHOP_SPECIES_ONEHOT]),
                "frozen": bool(f[base + NUM_SHOP_SPECIES_ONEHOT + 1]),
                "active": k < pet_slots,
            }
        )
    return out


def decode_shop_food(f: np.ndarray, food_slots: int) -> list[dict]:
    """Every food slot, not just the rolled ones: Pigeon's sell prepends
    free Bread Crumbs past the rolled capacity, so a slot outside it can
    still hold real, buyable stock (see sap2.h's SAP2_FOOD_SLOTS). Only
    the occupied ones are rendered."""
    out = []
    for k in range(FOOD_SLOTS):
        base = SHOP_FOOD_BASE + k * SHOP_FOOD_SLOT_WIDTH
        species = int(np.argmax(f[base : base + NUM_FOODS_ONEHOT]))
        out.append(
            {
                "species": species,
                "frozen": bool(f[base + NUM_FOODS_ONEHOT]),
                # The price is per slot: a Worm stocks a 2-gold Apple and
                # Pigeon's crumbs are free, so the species does not say
                # what a slot costs.
                "price": int(f[base + NUM_FOODS_ONEHOT + 1]),
                "active": k < food_slots or species != 0,
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
    t.append(f"xp{p['exp']} ", style="dim")  # the card's exp pips
    if p["perk"] == PERK_HONEY:
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
    t.append(f" {f['price']}g", style="yellow")
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
