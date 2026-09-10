"""Environment registry.

Adding an env means adding one line here. The runner resolves a qualified id
from the match request against this table and nothing else, so an env that is
not registered cannot be scheduled.
"""

from __future__ import annotations

from typing import Callable

from .base import EnvSpec, Observation, Outcome, StepResult, Termination, TwoPlayerEnv
from .connect4 import Connect4
from .sap import Sap
from .sap2 import Sap2
from .tron_duel import TronDuel

REGISTRY: dict[str, Callable[[], TwoPlayerEnv]] = {
    Connect4.spec.qualified_id: Connect4,
    TronDuel.spec.qualified_id: TronDuel,
    Sap.spec.qualified_id: Sap,
    Sap2.spec.qualified_id: Sap2,
}


def make(qualified_id: str) -> TwoPlayerEnv:
    try:
        factory = REGISTRY[qualified_id]
    except KeyError:
        known = ", ".join(sorted(REGISTRY)) or "none"
        raise KeyError(f"unknown env {qualified_id!r}; registered: {known}") from None
    return factory()


def spec(qualified_id: str) -> EnvSpec:
    return make(qualified_id).spec


__all__ = [
    "REGISTRY",
    "Connect4",
    "EnvSpec",
    "Observation",
    "Outcome",
    "Sap",
    "Sap2",
    "StepResult",
    "Termination",
    "TronDuel",
    "TwoPlayerEnv",
    "make",
    "spec",
]
