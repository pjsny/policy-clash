"""SAP2 (Super Auto Pets), the full Arena match - Tier 1 roster.

Extends sap-v1's single round into an actual match: lives, trophies, a
shop that grows and gates tiers by turn number, freeze, and the turn-3
life-back rule real Arena mode uses. See docs/envs/sap-v2.md for the
design and the wiki sources every rule is drawn from, and
docs/envs/sap-v1.md for the single-round env this one extends without
modifying (sap-v1 stays registered, unchanged, still passing its own
tests).

Roster is still Tier 1 only (10 pets, 2 foods) - the *match engine* here
is the real game's full structure; the pet roster is a separate, later
expansion tracked in sap-v2.md's appendix.

Rules live in C, under envs/csrc/sap2.h, itself built on
envs/csrc/sap2_binding.c following the exact pattern sap.py/sap_binding.c
already established. This module is the thin Python layer over it and
contains no rules of its own.
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
MAX_SHOP_FOOD = _sap2.MAX_SHOP_FOOD
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
