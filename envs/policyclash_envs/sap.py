"""SAP (Super Auto Pets), Tier-1-only single-round MVP.

One round: both seats build a 5-slot team against their own hidden Tier-1
shop, then one battle resolves and the episode ends. No freeze, no
multi-turn tier progression, no Tier 2+ - see docs/envs/sap-v1.md for the
full design this scopes down from, and SAP_clone.md (in the sap-gym-env
project this was designed alongside) for the underlying game rules.

Rules live in C, under `envs/csrc/sap.h`. This module is the thin Python
layer that adapts the compiled core to the `TwoPlayerEnv` interface: it
translates status codes into outcomes and wraps the returned buffers as
numpy arrays. It contains no rules of its own.

Both seats act every shop tick until one ends its turn - voluntarily via
END_TURN, or forced once it hits its own action budget - at which point
that seat's observation goes `None` and only the other seat keeps
receiving one, same "a seat the env did not ask to act is not acting"
rule the interface already states, just not exercised by connect4 (always
exactly one active seat) or tron-duel (always exactly two) before this env.
The very step() call that leaves both seats ended resolves the entire
battle in the same call and returns the terminal StepResult - there is no
separate battle tick.
"""

from __future__ import annotations

import numpy as np

from . import _sap
from .base import EnvSpec, Observation, Outcome, StepResult, Termination

OBS_FLOATS = _sap.OBS_FLOATS
NUM_ACTIONS = _sap.NUM_ACTIONS
MAX_TICKS = _sap.MAX_TICKS
TEAM_SLOTS = _sap.TEAM_SLOTS
SHOP_PET_SLOTS = _sap.SHOP_PET_SLOTS
STARTING_GOLD = _sap.STARTING_GOLD

SPEC = EnvSpec(
    id="sap",
    version=1,
    obs_shape=(OBS_FLOATS,),
    num_actions=NUM_ACTIONS,
    max_episode_steps=MAX_TICKS,
    actors_per_tick=2,
    # Shop offers (the initial roll and every REROLL) are drawn from RNG
    # derived entirely from the reset seed - unlike tron-duel, where the seed
    # only picks the start position and nothing after it, here the shop
    # transitions themselves are stochastic, so this has to be True.
    stochastic_dynamics=True,
)

# Status code from the C core to (outcome, termination).
_TERMINAL: dict[int, tuple[Outcome, Termination]] = {
    _sap.P0_WIN: (Outcome.PLAYER_0, Termination.NATURAL),
    _sap.P1_WIN: (Outcome.PLAYER_1, Termination.NATURAL),
    _sap.DRAW: (Outcome.DRAW, Termination.NATURAL),
    _sap.P0_WIN_ILLEGAL: (Outcome.PLAYER_0, Termination.ILLEGAL_ACTION),
    _sap.P1_WIN_ILLEGAL: (Outcome.PLAYER_1, Termination.ILLEGAL_ACTION),
    _sap.DRAW_ILLEGAL: (Outcome.DRAW, Termination.ILLEGAL_ACTION),
}


class Sap:
    """Two-player Super Auto Pets, Tier 1 only, one round.

    Both seats act every tick during the shop phase - simultaneous, not
    turn-based, because the real shop phase is: neither seat sees the
    other's team or shop while building. A seat that ends (voluntarily or by
    running out of its action budget) stops receiving observations for the
    rest of the episode; the other seat keeps going alone until it too ends,
    at which point the same step() call resolves the battle and the episode
    is done. `Termination.STEP_LIMIT` never appears, for the same reason it
    doesn't in tron-duel: the action budget forces both seats to `ended` by
    `MAX_TICKS` at the latest, so the bound is enforced by construction
    rather than checked for.
    """

    spec = SPEC

    def __init__(self) -> None:
        self._core = _sap.Sap()

    def reset(self, seed: int) -> StepResult:
        self._core.reset(seed)
        return StepResult(observations=self._observations(), done=False)

    def step(self, action_0: int, action_1: int) -> StepResult:
        status = self._core.step(action_0, action_1)
        if status == _sap.ONGOING:
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

    def _observations(self) -> tuple[Observation | None, Observation | None]:
        # A seat that has ended - voluntarily via END_TURN, or forced once it
        # hit its action budget - stops receiving observations for the rest
        # of the episode. `ended` is the same role connect4's `to_move`
        # getter plays for its turn-based case: state the core already
        # tracks, read directly rather than inferred from something else.
        return (
            None if self._core.ended(0) else self._observe(0),
            None if self._core.ended(1) else self._observe(1),
        )

    def _observe(self, seat: int) -> Observation:
        # frombuffer is a read-only view over the bytes the core returned, so
        # this costs no copy and the policy cannot mutate its own observation.
        features = np.frombuffer(self._core.observe(seat), dtype=np.float32)
        return Observation(
            features=features,
            legal_actions=np.frombuffer(self._core.legal(seat), dtype=bool),
        )
