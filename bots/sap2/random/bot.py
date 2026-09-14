"""Uniform over the legal mask. The rating floor.

Self-contained by the rule in `bots/README.md`: a record never imports a
shared helper, so a later refactor cannot change what it scores.
"""

from __future__ import annotations

import random

import numpy as np


class Bot:
    def __init__(self, seed: int) -> None:
        self.rng = random.Random(seed)

    def act(self, obs) -> int:
        legal = np.flatnonzero(obs.legal_actions).tolist()
        return int(self.rng.choice(legal))


def make_bot(seed: int) -> Bot:
    return Bot(seed)
