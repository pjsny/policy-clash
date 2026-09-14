"""A small PPO for `sap2-v1`, in MLX, with held-out evaluation.

Answers one question: can a learned policy beat the fixed `greedy` rule in
`bots/sap2/greedy/`? The bar comes from the arena's own board,
`bots/sap2/LEADERBOARD.md`.

Design choices that the question forces:

- **Action masking is mandatory, not an optimization.** An out-of-range action
  forfeits the match outright (`Termination.ILLEGAL_ACTION`), and most of the
  49 actions are illegal at any given tick. The policy masks its logits with
  `Observation.legal_actions`, so it cannot forfeit and cannot waste capacity
  on unreachable actions.
- **Reward is terminal-only and about 146 ticks away**, which is a hard credit
  assignment problem for a short run. A per-round potential supplies the
  intermediate signal: `trophies - (5 - lives)`, the same quantity
  `bots/sap2/mc_search/bot.py` scores, so the learned policy and the search
  reference chase a comparable objective.
- **Train against a pool, never against `greedy` alone.** `greedy` is
  deterministic, so a policy trained against it can win by memorizing its
  fixed replies rather than by playing the game. The opponent seat draws from
  the current policy, `greedy`, and `random`.
- **Evaluate on held-out seeds**, disjoint from the training range, in both
  seatings. `tools/arena_sap2.py` is the authority on ratings; the winrates
  printed here exist so a run reports whether it went anywhere, and they must
  reproduce the board's.

A trained policy becomes a submission by writing its weights into
`bots/sap2/ppo_mlx/weights.safetensors`, which that bot loads. Pass `--save`.

The policy never touches `env.clone()`. A clone exposes the opponent's team
and the random number generator words, which no observation shows.

Usage:

    envs/.venv/bin/python tools/train_ppo_sap2.py
    envs/.venv/bin/python tools/train_ppo_sap2.py --iters 40 --episodes 64
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    import mlx.core as mx
    import mlx.nn as nn
    import mlx.optimizers as optim
except ImportError:
    sys.exit("mlx is missing. Install it with:\n\n  uv pip install --python envs/.venv/bin/python mlx\n")

try:
    from policyclash_envs import make
    from policyclash_envs.base import Outcome
except ImportError:
    sys.exit("Run this with envs/.venv/bin/python - policyclash_envs lives there.")

from arena_sap2 import ENV_ID, load_bot

# The opponent pool comes from the committed bots, not from a private copy.
# One source means a bot cannot behave one way here and another way on the
# board.
make_greedy = load_bot("greedy")
make_random = load_bot("random")

OBS = 174
ACTIONS = 49
IGNORED = 0

# Seed ranges. Disjoint by construction: a policy that memorized a training
# seed's shop rolls gains nothing at evaluation time.
TRAIN_SEED_HI = 500_000
EVAL_SEED_BASE = 900_000


# Observation indices, from sap2.h's SAP2_OBS_FLOATS: gold, lives, trophies,
# turn, then the per-slot blocks.
LIVES_INDEX = 1
TROPHIES_INDEX = 2


def potential(features: np.ndarray) -> float:
    """Shaping potential, from this seat's view. Identical to the quantity
    `bots/sap2/mc_search/bot.py` scores, so the learned policy and the search
    reference chase the same intermediate objective."""
    return float(features[TROPHIES_INDEX]) - (5.0 - float(features[LIVES_INDEX]))


class ActorCritic(nn.Module):
    """Two hidden layers, then a policy head and a value head.

    Small on purpose. The observation is 174 floats of mostly one-hot species
    blocks, the action space is 49, and the run has to stay cheap; a wider
    network would spend the budget on parameters rather than on episodes.
    """

    def __init__(self, hidden: int = 128) -> None:
        super().__init__()
        self.l1 = nn.Linear(OBS, hidden)
        self.l2 = nn.Linear(hidden, hidden)
        self.pi = nn.Linear(hidden, ACTIONS)
        self.v = nn.Linear(hidden, 1)

    def __call__(self, x: mx.array) -> tuple[mx.array, mx.array]:
        h = mx.tanh(self.l2(mx.tanh(self.l1(x))))
        return self.pi(h), self.v(h).squeeze(-1)


def masked_logits(logits: mx.array, mask: mx.array) -> mx.array:
    """Illegal actions get a large negative logit rather than -inf: -inf
    produces NaN gradients when a whole row is masked, and a row that is
    entirely illegal cannot occur here but must not be able to poison a
    batch if the rules core ever changes."""
    return mx.where(mask, logits, mx.array(-1e9, dtype=logits.dtype))


def log_probs(logits: mx.array, mask: mx.array, actions: mx.array) -> tuple[mx.array, mx.array]:
    lg = masked_logits(logits, mask)
    logp_all = lg - mx.logsumexp(lg, axis=-1, keepdims=True)
    chosen = mx.take_along_axis(logp_all, actions[:, None], axis=-1).squeeze(-1)
    probs = mx.exp(logp_all) * mask
    entropy = -mx.sum(probs * mx.where(mask, logp_all, mx.zeros_like(logp_all)), axis=-1)
    return chosen, entropy


class PolicyAgent:
    """Wraps the network in the submission interface from `bots/README.md`, so
    the in-flight policy plays by the same rules as a committed bot: one
    `act(obs)` call, observation only, nothing else reachable."""

    def __init__(self, model: ActorCritic, greedy: bool = True):
        self.model = model
        self.greedy = greedy

    def act(self, obs) -> int:
        x = mx.array(np.asarray(obs.features, dtype=np.float32)[None, :])
        mask = mx.array(np.asarray(obs.legal_actions)[None, :])
        logits, _ = self.model(x)
        lg = masked_logits(logits, mask)
        if self.greedy:
            return int(mx.argmax(lg, axis=-1).item())
        p = np.asarray(mx.softmax(lg, axis=-1), dtype=np.float64)[0]
        p = np.maximum(p, 0.0)
        return int(np.random.choice(ACTIONS, p=p / p.sum()))


def rollout_episode(model: ActorCritic, seed: int, opponent, learner_seat: int) -> dict:
    """One match. Records transitions for the learner's seat only.

    The opponent seat is played by `opponent`, which may be the current policy,
    `greedy`, or `random`. Recording one seat keeps the advantage estimates on
    a single consistent trajectory; the opponent's own view is a different
    Markov process whenever the opponent is not the current policy.
    """
    env = make(ENV_ID)
    result = env.reset(seed=seed)

    obs_buf, mask_buf, act_buf, rew_buf = [], [], [], []
    last_phi = None

    while not result.done:
        actions = [IGNORED, IGNORED]
        own = result.observations[learner_seat]

        if own is not None:
            x = mx.array(own.features[None, :].astype(np.float32))
            mask = mx.array(own.legal_actions[None, :])
            logits, _ = model(x)
            lg = masked_logits(logits, mask)
            p = np.asarray(mx.softmax(lg, axis=-1), dtype=np.float64)[0]
            p = np.maximum(p, 0.0)
            p /= p.sum()
            action = int(np.random.choice(ACTIONS, p=p))

            phi = potential(own.features)
            if last_phi is not None:
                rew_buf.append(phi - last_phi)
            last_phi = phi

            obs_buf.append(own.features.astype(np.float32))
            mask_buf.append(own.legal_actions.copy())
            act_buf.append(action)
            actions[learner_seat] = action

        other = result.observations[1 - learner_seat]
        if other is not None:
            actions[1 - learner_seat] = int(opponent.act(other))

        result = env.step(*actions)

    # The last recorded action has no follow-up observation, so the match
    # result is its reward. Outcome dominates the shaping term deliberately.
    terminal = 0.0
    if result.outcome != Outcome.DRAW:
        won = result.outcome == (Outcome.PLAYER_0 if learner_seat == 0 else Outcome.PLAYER_1)
        terminal = 5.0 if won else -5.0
    while len(rew_buf) < len(act_buf):
        rew_buf.append(0.0)
    if rew_buf:
        rew_buf[-1] += terminal

    return {
        "obs": np.array(obs_buf, dtype=np.float32),
        "mask": np.array(mask_buf, dtype=bool),
        "act": np.array(act_buf, dtype=np.int32),
        "rew": np.array(rew_buf, dtype=np.float32),
        "won": terminal > 0,
    }


def gae(rewards: np.ndarray, values: np.ndarray, gamma: float, lam: float) -> tuple[np.ndarray, np.ndarray]:
    n = len(rewards)
    adv = np.zeros(n, dtype=np.float32)
    running = 0.0
    for t in range(n - 1, -1, -1):
        next_v = values[t + 1] if t + 1 < n else 0.0
        delta = rewards[t] + gamma * next_v - values[t]
        running = delta + gamma * lam * running
        adv[t] = running
    return adv, adv + values


def match(first, second, seed: int) -> Outcome:
    """One match between 2 objects that implement `act(obs)`. Seat 0 is
    `first`. Deliberately the same shape the arena uses, so a winrate measured
    here and a winrate measured on the board mean the same thing."""
    env = make(ENV_ID)
    bots = (first, second)
    result = env.reset(seed=seed)
    while not result.done:
        actions = [IGNORED, IGNORED]
        for s in (0, 1):
            if result.observations[s] is not None:
                actions[s] = int(bots[s].act(result.observations[s]))
        result = env.step(*actions)
    return result.outcome


def evaluate(model: ActorCritic, opponents: dict, matches: int, base: int = EVAL_SEED_BASE) -> dict:
    """Held-out evaluation, both seatings, deterministic policy.

    The arena is the authority on ratings. This exists so a training run
    reports whether it went anywhere without a second process, and its
    winrates should reproduce the board's.
    """
    out = {}
    for name, factory in opponents.items():
        wins = 0.0
        total = 0
        for i in range(matches):
            seed = base + i
            for learner_seat in (0, 1):
                agent = PolicyAgent(model, greedy=True)
                foe = factory(seed * 7919 + 3)
                pair = (agent, foe) if learner_seat == 0 else (foe, agent)
                outcome = match(pair[0], pair[1], seed)
                if outcome == Outcome.DRAW:
                    wins += 0.5
                else:
                    winner_seat = 0 if outcome == Outcome.PLAYER_0 else 1
                    wins += 1.0 if winner_seat == learner_seat else 0.0
                total += 1
        out[name] = wins / total
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--iters", type=int, default=30)
    parser.add_argument("--episodes", type=int, default=48, help="episodes per iteration")
    parser.add_argument("--epochs", type=int, default=4, help="PPO epochs per iteration")
    parser.add_argument("--batch", type=int, default=512)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--clip", type=float, default=0.2)
    parser.add_argument("--gamma", type=float, default=0.995)
    parser.add_argument("--lam", type=float, default=0.95)
    parser.add_argument("--entropy", type=float, default=0.01)
    parser.add_argument("--eval-matches", type=int, default=60)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--save", type=str, default="", help="write weights to this .safetensors path")
    args = parser.parse_args()

    random.seed(args.seed)
    np.random.seed(args.seed)
    mx.random.seed(args.seed)

    model = ActorCritic()
    mx.eval(model.parameters())
    opt = optim.Adam(learning_rate=args.lr)

    def loss_fn(m, obs, mask, act, old_logp, adv, ret):
        logits, values = m(obs)
        logp, entropy = log_probs(logits, mask, act)
        ratio = mx.exp(logp - old_logp)
        pg = -mx.minimum(ratio * adv, mx.clip(ratio, 1 - args.clip, 1 + args.clip) * adv)
        vloss = mx.square(values - ret)
        return mx.mean(pg) + 0.5 * mx.mean(vloss) - args.entropy * mx.mean(entropy)

    grad_fn = nn.value_and_grad(model, loss_fn)

    pool_rng = random.Random(args.seed)
    t0 = time.perf_counter()
    env_ticks = 0

    print(f"training: {args.iters} iters x {args.episodes} episodes, device {mx.default_device()}")
    for it in range(1, args.iters + 1):
        batches = []
        wins_vs_pool = 0.0
        for ep in range(args.episodes):
            seed = pool_rng.randrange(TRAIN_SEED_HI)
            # Opponent pool: the current policy most of the time, with the two
            # committed scripted bots mixed in so early training sees
            # competent play and late training does not drift into a
            # self-play-only niche. Never `greedy` alone - it is
            # deterministic, so a policy trained against it can win by
            # memorizing its fixed replies instead of by playing the game.
            draw = pool_rng.random()
            if draw < 0.5:
                opponent = PolicyAgent(model, greedy=False)
            elif draw < 0.8:
                opponent = make_greedy(seed)
            else:
                opponent = make_random(seed)
            learner_seat = ep % 2
            traj = rollout_episode(model, seed, opponent, learner_seat)
            if len(traj["act"]) == 0:
                continue
            wins_vs_pool += 1.0 if traj["won"] else 0.0
            batches.append(traj)
            env_ticks += len(traj["act"])

        obs = mx.array(np.concatenate([b["obs"] for b in batches]))
        mask = mx.array(np.concatenate([b["mask"] for b in batches]))
        act = mx.array(np.concatenate([b["act"] for b in batches]).astype(np.int32))

        logits, values = model(obs)
        old_logp, _ = log_probs(logits, mask, act)
        mx.eval(old_logp, values)
        vals = np.asarray(values)

        advs, rets = [], []
        off = 0
        for b in batches:
            n = len(b["act"])
            a, r = gae(b["rew"], vals[off : off + n], args.gamma, args.lam)
            advs.append(a)
            rets.append(r)
            off += n
        adv = np.concatenate(advs)
        ret = np.concatenate(rets)
        adv = (adv - adv.mean()) / (adv.std() + 1e-8)
        adv_mx, ret_mx = mx.array(adv), mx.array(ret)

        n = len(act)
        for _ in range(args.epochs):
            order = np.random.permutation(n)
            for s in range(0, n, args.batch):
                idx = mx.array(order[s : s + args.batch].astype(np.int32))
                loss, grads = grad_fn(
                    model,
                    obs[idx], mask[idx], act[idx],
                    old_logp[idx], adv_mx[idx], ret_mx[idx],
                )
                opt.update(model, grads)
                mx.eval(model.parameters(), opt.state)

        if it % 5 == 0 or it == 1:
            print(
                f"  iter {it:>3}  transitions {n:>6}  pool winrate {wins_vs_pool / max(len(batches), 1):.1%}"
                f"  loss {float(loss.item()):+.3f}  {time.perf_counter() - t0:.0f}s"
            )

    train_time = time.perf_counter() - t0
    print(f"\ntrained in {train_time:.0f}s, {env_ticks} learner transitions\n")

    # `mc_search` is left out on purpose: it needs `env.clone()`, which this
    # match loop does not hand out. The arena rates it as a reference bot.
    opponents = {"random": make_random, "greedy": make_greedy}

    # Two disjoint held-out ranges, not one. A single range can flatter a
    # policy that happened to suit its shop rolls; agreement across two
    # ranges is what rules that out.
    for base in (EVAL_SEED_BASE, EVAL_SEED_BASE + 500_000):
        print(f"held-out seeds {base}..{base + args.eval_matches - 1}, both seatings")
        res = evaluate(model, opponents, args.eval_matches, base)
        for name, wr in res.items():
            verdict = "beats" if wr > 0.5 else "loses to"
            print(f"  ppo vs {name:<7} {wr:6.1%}   ({verdict})")
        print()

    if args.save:
        model.save_weights(args.save)
        print(f"weights written to {args.save}\n")


if __name__ == "__main__":
    main()
