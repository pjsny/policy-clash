"""A fixed rule, no simulation and no lookahead.

The rule, in priority order:

1. Combine a duplicate pair. A level-up is `max(a, b) + 1` on both stats, so it
   beats holding two copies, and it frees a team slot.
2. Buy the shop pet with the best attack plus health, if a team slot is empty.
   Board presence dominates at Tier 1: an empty slot contributes nothing to a
   battle.
3. Buy a pet that duplicates a species already on the team, which sets up rule
   1 on the next tick.
4. End the turn.

The rule never rerolls, sells, buys food, or freezes. Each of those needs a
judgement about a future shop that a fixed rule cannot make well, and at this
roster size spending the gold on a body is the reliable alternative.

Self-contained by the rule in `bots/README.md`, so the action layout and the
observation layout are repeated here rather than imported.
"""

from __future__ import annotations

from itertools import combinations

import numpy as np

END_TURN = 0
BUY_PET_BASE = 1
COMBINE_BASE = 11

TEAM_BASE = 4  # after gold(1) lives(1) trophies(1) turn(1)
TEAM_SLOT_WIDTH = 19
SHOP_PET_BASE = TEAM_BASE + 5 * TEAM_SLOT_WIDTH
SHOP_PET_SLOT_WIDTH = 13

# From sap2.h's SAP2_BASE_ATK / SAP2_BASE_HP, indexed by species.
BASE_ATK = [0, 2, 3, 1, 2, 2, 2, 2, 1, 4, 3, 0, 1]
BASE_HP = [0, 2, 2, 3, 2, 3, 1, 2, 4, 1, 2, 0, 1]

PAIRS = [(i, j) for i, j in combinations(range(5), 2)]


class Bot:
    def __init__(self, seed: int) -> None:
        del seed  # the rule is total over the legal mask

    def act(self, obs) -> int:
        f = obs.features
        legal = obs.legal_actions

        for idx in range(len(PAIRS)):
            if legal[COMBINE_BASE + idx]:
                return COMBINE_BASE + idx

        team = [self._team_species(f, s) for s in range(5)]
        buys = [s for s in range(5) if legal[BUY_PET_BASE + s]]
        if buys:
            if any(sp == 0 for sp in team):
                return BUY_PET_BASE + max(buys, key=lambda s: self._value(f, s))
            dupes = [s for s in buys if self._shop_species(f, s) in team]
            if dupes:
                return BUY_PET_BASE + max(dupes, key=lambda s: self._value(f, s))

        return END_TURN

    @staticmethod
    def _team_species(f: np.ndarray, slot: int) -> int:
        base = TEAM_BASE + slot * TEAM_SLOT_WIDTH
        return int(np.argmax(f[base : base + 13]))

    @staticmethod
    def _shop_species(f: np.ndarray, slot: int) -> int:
        base = SHOP_PET_BASE + slot * SHOP_PET_SLOT_WIDTH
        return int(np.argmax(f[base : base + 11]))

    @classmethod
    def _value(cls, f: np.ndarray, slot: int) -> float:
        species = cls._shop_species(f, slot)
        hp_bonus = float(f[SHOP_PET_BASE + slot * SHOP_PET_SLOT_WIDTH + 11])
        return BASE_ATK[species] + BASE_HP[species] + hp_bonus


def make_bot(seed: int) -> Bot:
    return Bot(seed)
