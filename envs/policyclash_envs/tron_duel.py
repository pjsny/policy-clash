"""Tron Duel. The first ladder environment.

Connect4 is the reference env: small, solved, and useful only for proving the
interface works. Tron Duel is what submissions are actually ranked on. It is
simultaneous-move, so there is no move order to exploit and no way to read the
opponent's action before choosing your own; it is fully deterministic given the
start position, so a match is reproducible from a seed and a pair of policies;
and it has no known solution, so the ladder measures play rather than lookup.

Rules live in C, under `envs/csrc/`. This module is the thin Python layer that
adapts the compiled core to the `TwoPlayerEnv` interface: it translates status
codes into outcomes and wraps the returned buffers as numpy arrays.

Keeping the rules in C and the adaptation in Python is the pattern every env
follows. The C core has no Python in it, so it can be fuzzed standalone and
compiled to wasm for the replay viewer.
"""

from __future__ import annotations

import numpy as np

from . import _tron_duel
from .base import EnvSpec, Observation, Outcome, StepResult, Termination

SIZE = _tron_duel.SIZE
PLANES = _tron_duel.PLANES
ACTIONS = _tron_duel.ACTIONS
MAX_TICKS = _tron_duel.MAX_TICKS

SPEC = EnvSpec(
    id="tron-duel",
    version=1,
    obs_shape=(PLANES, SIZE, SIZE),
    num_actions=ACTIONS,
    max_episode_steps=MAX_TICKS,
    actors_per_tick=2,
    # The transition is a pure function of grid, heads, and actions: no dice,
    # no hidden rolls. It is the START POSITION that is seeded, which is the
    # difference from connect4, where the seed changes nothing at all. Distinct
    # seeds give distinct episodes here without making the dynamics random.
    stochastic_dynamics=False,
)

# Status code from the C core to (outcome, termination).
_TERMINAL: dict[int, tuple[Outcome, Termination]] = {
    _tron_duel.P0_WIN: (Outcome.PLAYER_0, Termination.NATURAL),
    _tron_duel.P1_WIN: (Outcome.PLAYER_1, Termination.NATURAL),
    _tron_duel.DRAW: (Outcome.DRAW, Termination.NATURAL),
    _tron_duel.P0_WIN_ILLEGAL: (Outcome.PLAYER_0, Termination.ILLEGAL_ACTION),
    _tron_duel.P1_WIN_ILLEGAL: (Outcome.PLAYER_1, Termination.ILLEGAL_ACTION),
    _tron_duel.DRAW_ILLEGAL: (Outcome.DRAW, Termination.ILLEGAL_ACTION),
}


class TronDuel:
    """Two-player light-cycles on a 13x13 grid.

    Both seats act on every tick. Actions are relative to the seat's own
    heading - turn left, straight, turn right - and there is no reversal, so
    no action is ever illegal and the legal mask is all true. Driving into a
    wall, a trail, or the other cycle is fatal, but it is a losing move rather
    than a rules violation: the env does not rescue a policy from its own
    steering. Only an out-of-range action forfeits.

    `Termination.STEP_LIMIT` never appears. Both seats consume a previously
    empty cell every tick and trails never clear, so the board runs out and a
    crash is forced well inside `max_episode_steps`.
    """

    spec = SPEC

    def __init__(self) -> None:
        self._core = _tron_duel.TronDuel()

    def reset(self, seed: int) -> StepResult:
        # The seed picks the start position: two interior spawn cells and two
        # headings. Everything after that is deterministic.
        self._core.reset(seed)
        return StepResult(observations=self._observations(), done=False)

    def step(self, action_0: int, action_1: int) -> StepResult:
        status = self._core.step(action_0, action_1)
        if status == _tron_duel.ONGOING:
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

    def _observations(self) -> tuple[Observation, Observation]:
        # Both seats always act, so both always get an observation.
        return (self._observe(0), self._observe(1))

    def _observe(self, seat: int) -> Observation:
        # frombuffer is a read-only view over the bytes the core returned, so
        # this costs no copy and the policy cannot mutate its own observation.
        # reshape keeps the view: planes stay separable without a copy.
        features = np.frombuffer(self._core.observe(seat), dtype=np.float32)
        return Observation(
            features=features.reshape(SPEC.obs_shape),
            legal_actions=np.frombuffer(self._core.legal(seat), dtype=bool),
        )
