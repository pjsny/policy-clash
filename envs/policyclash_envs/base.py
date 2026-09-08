"""Interface every PolicyClash environment implements.

Two-player, zero-sum. The env owns the rules and decides who acts. It never
owns the policies, and it never calls them.

Turn-based and simultaneous envs share one shape. A step takes an action for
each seat, and the env reads only the seats it asked to act. Which seats those
are is announced by the previous `StepResult`: a seat with an observation must
act, a seat with `None` must not. Turn-based games hand out one observation per
tick, simultaneous games hand out two, and a runner written against the
invariant does not care which kind it is holding.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable

import numpy as np

SEATS = 2


class Outcome(str, Enum):
    PLAYER_0 = "player_0"
    PLAYER_1 = "player_1"
    DRAW = "draw"


class Termination(str, Enum):
    """Why the episode ended. Recorded in the match result."""

    NATURAL = "natural"
    ILLEGAL_ACTION = "illegal_action"
    STEP_LIMIT = "step_limit"


@dataclass(frozen=True)
class EnvSpec:
    """Everything a submission needs to export a compatible ONNX graph."""

    id: str
    version: int
    obs_shape: tuple[int, ...]
    num_actions: int
    max_episode_steps: int
    actors_per_tick: int = 1
    recurrent_state_shapes: tuple[tuple[int, ...], ...] = ()
    stochastic_dynamics: bool = False

    @property
    def qualified_id(self) -> str:
        return f"{self.id}-v{self.version}"

    @property
    def simultaneous(self) -> bool:
        return self.actors_per_tick == SEATS


@dataclass(frozen=True)
class Observation:
    """What a seat that must act this tick sees.

    `features` is always from that seat's own perspective, so a symmetric env
    presents an identical encoding to both seats. One network plays both sides.

    `legal_actions` is a boolean mask. Entrants are expected to apply it before
    argmax. Ignoring it forfeits the match, so it is part of the observation
    rather than something a policy has to infer. An env where every action is
    always available still ships the mask, all true, so that policy code does
    not branch on the env.
    """

    features: np.ndarray
    legal_actions: np.ndarray


@dataclass(frozen=True)
class StepResult:
    """Outcome of a tick, and who acts next.

    `observations` is indexed by seat. A non-`None` entry means that seat must
    supply an action to the next `step`. Exactly one entry is set for a
    turn-based env and both are set for a simultaneous one. When `done` is
    true, both are `None` and `outcome` and `termination` are set.
    """

    observations: tuple[Observation | None, Observation | None]
    done: bool
    outcome: Outcome | None = None
    termination: Termination | None = None


@runtime_checkable
class TwoPlayerEnv(Protocol):
    spec: EnvSpec

    def reset(self, seed: int) -> StepResult:
        """Start an episode. In a turn-based env, seat 0 acts first.

        Which submission occupies seat 0 is the scheduler's decision, not the
        env's. Seating is swapped across paired matches: first-move advantage
        is real in turn-based games, and a seeded starting position favours one
        seat even in simultaneous ones.

        All randomness derives from `seed`. No clock, no global RNG.
        """

    def step(self, action_0: int, action_1: int) -> StepResult:
        """Apply one tick.

        Both actions are passed positionally by seat. A seat that was not
        handed an observation is not acting this tick, and its argument is
        ignored rather than validated, so a runner may pass anything for it.

        Actions arrive as plain ints and are never trusted. An out-of-range
        action forfeits, and if both seats forfeit on the same tick the result
        is a draw.
        """

    def replay(self) -> list[int]:
        """Actions in order, flat, `spec.actors_per_tick` entries per tick.

        Flat rather than nested so the replay format does not change shape
        between turn-based and simultaneous envs: the viewer unpacks it using
        the spec it already had to load. Enough to reconstruct the episode
        given the seed and the env version.
        """
