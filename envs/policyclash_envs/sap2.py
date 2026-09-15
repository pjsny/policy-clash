"""SAP2 (Super Auto Pets), the full Arena match - Tier 1 roster.

The actual multi-round Arena match: lives, trophies, a tier-gated shop
that grows with the turn number, freeze, and the turn-3 life-back rule
real Arena mode uses - not a single shop-phase-then-one-battle slice. See
docs/envs/sap-v2.md for the design. The shop-phase numbers (level
requirements, sell value, shop capacity per tier, Pigeon's free Bread
Crumbs) were measured out of the shipped build by policy-clash-re-tools, not
taken from a wiki.

Roster is still Tier 1 only (10 pets, 3 foods) - the *match engine* here
is the real game's full structure; the pet roster is a separate, later
expansion tracked in sap-v2.md's appendix.

Rules live in C, under envs/csrc/sap2.h - self-contained, no dependency
on any other env's files - with a thin CPython binding in
envs/csrc/sap2_binding.c, following the same layering every env in this
repo uses (see docs/adding-an-env.md). This module is the thin Python
layer over that binding and contains no rules of its own.
"""

from __future__ import annotations

import numpy as np

from . import _sap2
from .base import EnvSpec, Observation, Outcome, StepResult, Termination

OBS_FLOATS = _sap2.OBS_FLOATS
NUM_ACTIONS = _sap2.NUM_ACTIONS
MAX_TICKS = _sap2.MAX_TICKS
TEAM_SLOTS = _sap2.TEAM_SLOTS
MAX_SHOP_PETS = _sap2.MAX_SHOP_PETS
ROSTER_TIER = _sap2.ROSTER_TIER  # how far the implemented roster reaches
MAX_SHOP_FOOD = _sap2.MAX_SHOP_FOOD  # the largest food shop a ROLL fills
FOOD_SLOTS = _sap2.FOOD_SLOTS  # array width: Pigeon prepends up to 3 free crumbs
MAX_LEVEL = _sap2.MAX_LEVEL
MAX_EXP = _sap2.MAX_EXP  # a pet stops stacking here (LevelRequirements[-1])
MAX_STATS = _sap2.MAX_STATS  # BoardConstants.MaxStats - attack and health cap
NUM_PERKS = _sap2.NUM_PERKS  # width of a team slot's perk one-hot
PERK_NONE = _sap2.PERK_NONE
PERK_HONEY = _sap2.PERK_HONEY
PERK_MEAT_BONE = _sap2.PERK_MEAT_BONE  # Tier 2's Meat Bone

# Layout, for consumers that decode features or build actions. Derived from
# the C core rather than copied, so a widened block cannot leave a stale
# offset behind in a test, a bot or the visualizer.
TEAM_SLOT_FLOATS = _sap2.TEAM_SLOT_FLOATS
SHOP_PET_SLOT_FLOATS = _sap2.SHOP_PET_SLOT_FLOATS
SHOP_FOOD_SLOT_FLOATS = _sap2.SHOP_FOOD_SLOT_FLOATS
ACT_BUY_PET_BASE = _sap2.ACT_BUY_PET_BASE
ACT_SELL_BASE = _sap2.ACT_SELL_BASE
ACT_COMBINE_BASE = _sap2.ACT_COMBINE_BASE
ACT_REROLL = _sap2.ACT_REROLL
ACT_REPOSITION_BASE = _sap2.ACT_REPOSITION_BASE
ACT_BUY_FOOD_BASE = _sap2.ACT_BUY_FOOD_BASE
ACT_FREEZE_PET_BASE = _sap2.ACT_FREEZE_PET_BASE
ACT_FREEZE_FOOD_BASE = _sap2.ACT_FREEZE_FOOD_BASE
STARTING_GOLD = _sap2.STARTING_GOLD
STARTING_LIVES = _sap2.STARTING_LIVES
TROPHIES_TO_WIN = _sap2.TROPHIES_TO_WIN
MAX_ROUNDS = _sap2.MAX_ROUNDS

SPEC = EnvSpec(
    id="sap2",
    version=1,
    obs_shape=(OBS_FLOATS,),
    num_actions=NUM_ACTIONS,
    max_episode_steps=MAX_TICKS,
    actors_per_tick=2,
    stochastic_dynamics=True,
)

# Status code from the C core to (outcome, termination). Unlike sap-v1,
# Termination.STEP_LIMIT is a real, reachable path here: SAP2_MAX_ROUNDS
# with neither side at 10 trophies or 0 lives. See sap2.h's
# sap2_resolve_round for the tie-break policy that produces these.
_TERMINAL: dict[int, tuple[Outcome, Termination]] = {
    _sap2.P0_WIN: (Outcome.PLAYER_0, Termination.NATURAL),
    _sap2.P1_WIN: (Outcome.PLAYER_1, Termination.NATURAL),
    _sap2.DRAW: (Outcome.DRAW, Termination.NATURAL),
    _sap2.P0_WIN_ILLEGAL: (Outcome.PLAYER_0, Termination.ILLEGAL_ACTION),
    _sap2.P1_WIN_ILLEGAL: (Outcome.PLAYER_1, Termination.ILLEGAL_ACTION),
    _sap2.DRAW_ILLEGAL: (Outcome.DRAW, Termination.ILLEGAL_ACTION),
    _sap2.P0_WIN_STEP_LIMIT: (Outcome.PLAYER_0, Termination.STEP_LIMIT),
    _sap2.P1_WIN_STEP_LIMIT: (Outcome.PLAYER_1, Termination.STEP_LIMIT),
    _sap2.DRAW_STEP_LIMIT: (Outcome.DRAW, Termination.STEP_LIMIT),
}


class Sap2:
    """Two-player Super Auto Pets, full Arena match, Tier 1 roster.

    Each round is shaped exactly like sap-v1's single round - both seats
    act simultaneously during the shop phase, a seat that ends stops
    receiving observations, and the tick that both seats end resolves that
    round's battle. Unlike sap-v1, that tick does not end the episode: it
    updates lives/trophies and either starts the next round's shop phase
    (team persists; gold, turn budget, and the shop reroll - respecting any
    frozen slots - all reset) or ends the match if someone has reached 10
    trophies or been reduced to 0 lives.

    A pet that faints in battle is not permanently lost - only the life
    total changes. It returns for the next round at its persistent stats,
    exactly as if the battle had never touched it, because it wasn't:
    battle resolution never writes back to the persistent team. Only
    selling (or, in a later roster phase, an explicit effect like Sleeping
    Pill) removes a pet from the roster for good.
    """

    spec = SPEC

    def __init__(self) -> None:
        self._core = _sap2.Sap2()

    def reset(self, seed: int) -> StepResult:
        self._core.reset(seed)
        return StepResult(observations=self._observations(), done=False)

    def step(self, action_0: int, action_1: int) -> StepResult:
        status = self._core.step(action_0, action_1)
        if status == _sap2.ONGOING:
            return StepResult(observations=self._observations(), done=False)

        outcome, termination = _TERMINAL[status]
        return StepResult(
            observations=(None, None),
            done=True,
            outcome=outcome,
            termination=termination,
        )

    def replay(self) -> list[int]:
        return self._core.replay()

    def clone(self) -> Sap2:
        """An independent copy of the match, satisfying `base.Forkable`.

        Present so a search-based submission can explore without replaying
        from the seed at every node - the alternative costs O(depth) per
        expansion, which is most of a search's budget in a match that runs to
        MAX_ROUNDS * SHOP_ACTION_BUDGET ticks.

        This module holds no state of its own beyond `_core`, so forking the
        core is the entire copy; `object.__new__` skips `__init__` only to
        avoid allocating a core that would be thrown away. Note the clone
        exposes both seats' state and the RNG streams - see `base.Forkable`'s
        warning about handing one to a competitor rather than to tooling.
        """
        copy = object.__new__(type(self))
        copy._core = self._core.clone()
        return copy

    @property
    def turn(self) -> int:
        """Current turn number (1-indexed). Not part of the TwoPlayerEnv
        interface - a convenience for tests and any tooling that wants to
        report match progress without decoding it back out of an
        observation."""
        return self._core.turn

    def _observations(self) -> tuple[Observation | None, Observation | None]:
        return (
            None if self._core.ended(0) else self._observe(0),
            None if self._core.ended(1) else self._observe(1),
        )

    def _observe(self, seat: int) -> Observation:
        features = np.frombuffer(self._core.observe(seat), dtype=np.float32)
        return Observation(
            features=features,
            legal_actions=np.frombuffer(self._core.legal(seat), dtype=bool),
        )
