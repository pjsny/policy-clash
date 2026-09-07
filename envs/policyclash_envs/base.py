"""Interface every PolicyClash environment implements.

Turn-based, two-player, zero-sum. The env owns the rules and whose turn it is.
It never owns the policies, and it never calls them.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable

import numpy as np


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
    recurrent_state_shapes: tuple[tuple[int, ...], ...] = ()
    stochastic_dynamics: bool = False

    @property
    def qualified_id(self) -> str:
        return f"{self.id}-v{self.version}"


@dataclass(frozen=True)
class Observation:
    """What the policy about to move sees.

    `features` is always from the perspective of `player`, so a symmetric env
    presents an identical view to both seats. One network plays both sides.

    `legal_actions` is a boolean mask. Entrants are expected to apply it before
    argmax. Ignoring it forfeits the match, so it is part of the observation
    rather than something a policy has to infer.
    """

    player: int
    features: np.ndarray
    legal_actions: np.ndarray


@dataclass(frozen=True)
class StepResult:
    observation: Observation | None
    done: bool
    outcome: Outcome | None = None
    termination: Termination | None = None


@runtime_checkable
class TwoPlayerEnv(Protocol):
    spec: EnvSpec

    def reset(self, seed: int) -> Observation:
        """Start an episode. Player 0 always moves first.

        Which submission occupies seat 0 is the scheduler's decision, not the
        env's. Seating is swapped across paired matches because first-move
        advantage is real in most of these games.
        """

    def step(self, action: int) -> StepResult:
        """Apply the current player's action and hand the turn over."""

    def replay(self) -> list[int]:
        """Actions in order. Enough to reconstruct the episode given the seed."""
