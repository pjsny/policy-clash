"""One-ply search scored by rollouts on `env.clone()`. A reference ceiling.

This bot breaks rule 2 in `bots/README.md` on purpose, so it never ranks. A
clone carries both seats' teams and the random number generator words that
decide the coming shop rolls and battles, and an observation shows none of
that. The bot therefore measures how much a search with full information can
take, which is a ceiling for the ranked field rather than a competitor in it.

It declares `act_privileged(env, seat, obs)`, which the arena calls only for a
reference bot.

For every legal action: fork the match, apply the action, play both seats to
the end of a bounded number of rounds, and score the result from this seat's
view. Ties break toward the lower action index, which keeps the bot
deterministic.

One property worth knowing. `clone()` copies the random number generator words
rather than re-seeding them, so every rollout of a single candidate resolves
the CURRENT round's battle identically - the first round is exact lookahead,
not a sample. Variance appears only past that round, where the random
continuation actions consume the streams differently. So `rollouts` above 1
buys nothing at horizon 1, and the horizon here is 2.

Self-contained by the rule in `bots/README.md`.
"""

from __future__ import annotations

import math
import random

import numpy as np

from policyclash_envs.base import Outcome

END_TURN = 0
IGNORED = 0

TROPHIES_INDEX = 2
LIVES_INDEX = 1

ROLLOUTS = 4
HORIZON = 2


class Bot:
    def __init__(self, seed: int) -> None:
        self.rng = random.Random(seed)

    def act(self, obs) -> int:
        raise RuntimeError("mc_search is a reference bot; the arena calls act_privileged")

    def act_privileged(self, env, seat: int, obs) -> int:
        legal = np.flatnonzero(obs.legal_actions).tolist()
        if len(legal) == 1:
            return int(legal[0])

        best_action = int(legal[0])
        best_score = -math.inf
        for action in legal:
            total = sum(self._rollout(env, seat, int(action)) for _ in range(ROLLOUTS))
            if total > best_score:
                best_score = total
                best_action = int(action)
        return best_action

    def _rollout(self, env, seat: int, action: int) -> float:
        sim = env.clone()
        start_turn = sim.turn
        actions = [IGNORED, IGNORED]
        actions[seat] = action
        actions[1 - seat] = END_TURN
        result = sim.step(*actions)

        # Stop at the horizon, but never while this seat has no observation: a
        # seat that already ended its shop turn has no features to read, so the
        # rollout continues until the round resolves and the next one deals it
        # back in. The per-round action budget bounds that wait.
        while not result.done and (
            sim.turn < start_turn + HORIZON or result.observations[seat] is None
        ):
            step = [IGNORED, IGNORED]
            for s in (0, 1):
                if result.observations[s] is not None:
                    choices = np.flatnonzero(result.observations[s].legal_actions).tolist()
                    step[s] = int(self.rng.choice(choices))
            result = sim.step(*step)

        if result.done:
            if result.outcome == Outcome.DRAW:
                return 0.0
            won = result.outcome == (Outcome.PLAYER_0 if seat == 0 else Outcome.PLAYER_1)
            return 100.0 if won else -100.0

        f = result.observations[seat].features
        return float(f[TROPHIES_INDEX]) - (5.0 - float(f[LIVES_INDEX]))


def make_bot(seed: int) -> Bot:
    return Bot(seed)
