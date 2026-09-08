"""Connect4. The reference environment.

Rules live in C, under `envs/csrc/`. This module is the thin Python layer that
adapts the compiled core to the `TwoPlayerEnv` interface: it translates status
codes into outcomes and wraps the returned buffers as numpy arrays.

Keeping the rules in C and the adaptation in Python is the pattern every env
follows. The C core has no Python in it, so it can be fuzzed standalone and
compiled to wasm for the replay viewer.
"""

from __future__ import annotations

import numpy as np

from . import _connect4
from .base import EnvSpec, Observation, Outcome, StepResult, Termination

COLS = _connect4.COLS
ROWS = _connect4.ROWS

# `actors_per_tick` defaults to 1: connect4 is the turn-based case of the
# shared protocol, so it hands out one observation per tick and the runner's
# loop is the same one a simultaneous env drives.
SPEC = EnvSpec(
    id="connect4",
    version=1,
    obs_shape=(COLS * ROWS,),
    num_actions=COLS,
    max_episode_steps=COLS * ROWS,
    stochastic_dynamics=False,
)

# Status code from the C core to (outcome, termination).
_TERMINAL: dict[int, tuple[Outcome, Termination]] = {
    _connect4.P0_WIN: (Outcome.PLAYER_0, Termination.NATURAL),
    _connect4.P1_WIN: (Outcome.PLAYER_1, Termination.NATURAL),
    _connect4.DRAW: (Outcome.DRAW, Termination.NATURAL),
    _connect4.P0_WIN_ILLEGAL: (Outcome.PLAYER_0, Termination.ILLEGAL_ACTION),
    _connect4.P1_WIN_ILLEGAL: (Outcome.PLAYER_1, Termination.ILLEGAL_ACTION),
}


class Connect4:
    """Two-player Connect4.

    Illegal actions forfeit. The legal mask is handed to the policy in every
    observation, so playing a full column is a bug in the submission rather
    than bad luck, and silently remapping it would let a policy that never
    learned the rules climb the ladder.
    """

    spec = SPEC

    def __init__(self) -> None:
        self._core = _connect4.Connect4()

    def reset(self, seed: int) -> StepResult:
        # Connect4 has no stochastic dynamics, so the seed changes nothing. It
        # is still part of the signature: the runner records a seed for every
        # match, and an env that ignores it must ignore it visibly.
        del seed
        self._core.reset()
        return StepResult(observations=self._observations(), done=False)

    def step(self, action_0: int, action_1: int) -> StepResult:
        # Only the seat on move is read; the other seat's argument is ignored
        # by contract rather than validated. That is what lets one runner loop
        # drive turn-based and simultaneous envs without branching on which.
        action = action_0 if self._core.to_move == 0 else action_1

        status = self._core.step(action)
        if status == _connect4.ONGOING:
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
        # Seat identity is carried by position in the tuple, not by a field on
        # the observation: the seat not on move gets `None` and must not act.
        obs = self._observe()
        return (obs, None) if self._core.to_move == 0 else (None, obs)

    def _observe(self) -> Observation:
        # frombuffer is a read-only view over the bytes the core returned, so
        # this costs no copy and the policy cannot mutate its own observation.
        return Observation(
            features=np.frombuffer(self._core.observe(), dtype=np.float32),
            legal_actions=np.frombuffer(self._core.legal(), dtype=bool),
        )
