"""A fixed rule, no simulation and no lookahead.

The rule, in priority order:

1. Buy a shop copy of a species already on the team, dropped straight onto
   that pet: one action in the real game, and a level-up is
   `max(a, b) + 1` on both stats, so it beats holding two bodies.
2. Combine a duplicate pair already sitting on the team - the same rule,
   for copies bought before this one.
3. Buy the shop pet with the best attack plus health into an empty
   position. Board presence dominates at Tier 1: an empty slot contributes
   nothing to a battle.
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
BUY_PET_BASE = 1    # +0..24: shop_slot*5 + team position
COMBINE_BASE = 31   # +0..9: team slot pair

TEAM_BASE = 4  # after gold(1) lives(1) trophies(1) turn(1)
# 24 species one-hot, attack, health, 3 level one-hot, exp, 3 perk one-hot.
NUM_SPECIES = 24
TEAM_SLOT_WIDTH = 33
SHOP_PET_BASE = TEAM_BASE + 5 * TEAM_SLOT_WIDTH
# 21 shop-species one-hot (20 rollable + empty), hp bonus, frozen.
NUM_SHOP_SPECIES = 21
SHOP_PET_SLOT_WIDTH = 23

# From sap2.h's SAP2_BASE_ATK / SAP2_BASE_HP, indexed by species:
# empty, the ten Tier-1 pets, the ten Tier-2 pets, then the three tokens.
BASE_ATK = [0, 2, 3, 1, 2, 2, 2, 2, 1, 4, 3, 4, 3, 4, 2, 2, 3, 2, 2, 1, 1, 0, 1, 1]
BASE_HP = [0, 2, 2, 3, 2, 3, 1, 2, 4, 1, 2, 1, 2, 2, 2, 5, 6, 3, 2, 2, 4, 0, 1, 1]

PAIRS = [(i, j) for i, j in combinations(range(5), 2)]


class Bot:
    def __init__(self, seed: int) -> None:
        del seed  # the rule is total over the legal mask

    def act(self, obs) -> int:
        f = obs.features
        legal = obs.legal_actions
        team = [self._team_species(f, s) for s in range(5)]

        # A shop copy dropped on its twin stacks in one action.
        stacks = [
            (shop, slot)
            for shop in range(5)
            for slot in range(5)
            if team[slot] and self._shop_species(f, shop) == team[slot]
            and legal[BUY_PET_BASE + shop * 5 + slot]
        ]
        if stacks:
            shop, slot = max(stacks, key=lambda pair: self._value(f, pair[0]))
            return BUY_PET_BASE + shop * 5 + slot

        for idx in range(len(PAIRS)):
            if legal[COMBINE_BASE + idx]:
                return COMBINE_BASE + idx

        empties = [s for s in range(5) if team[s] == 0]
        if empties:
            dest = empties[0]
            buys = [s for s in range(5) if legal[BUY_PET_BASE + s * 5 + dest]]
            if buys:
                return BUY_PET_BASE + max(buys, key=lambda s: self._value(f, s)) * 5 + dest

        return END_TURN

    @staticmethod
    def _team_species(f: np.ndarray, slot: int) -> int:
        base = TEAM_BASE + slot * TEAM_SLOT_WIDTH
        return int(np.argmax(f[base : base + NUM_SPECIES]))

    @staticmethod
    def _shop_species(f: np.ndarray, slot: int) -> int:
        base = SHOP_PET_BASE + slot * SHOP_PET_SLOT_WIDTH
        return int(np.argmax(f[base : base + NUM_SHOP_SPECIES]))

    @classmethod
    def _value(cls, f: np.ndarray, slot: int) -> float:
        species = cls._shop_species(f, slot)
        hp_bonus = float(f[SHOP_PET_BASE + slot * SHOP_PET_SLOT_WIDTH + NUM_SHOP_SPECIES])
        return BASE_ATK[species] + BASE_HP[species] + hp_bonus


def make_bot(seed: int) -> Bot:
    return Bot(seed)
