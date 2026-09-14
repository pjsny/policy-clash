# tools

## `visualize_sap2.py`

A terminal visualizer for `sap2-v1` matches, driven by the real C engine
(`policyclash_envs.make("sap2-v1")`) — not a reimplementation.

```
uv pip install --python envs/.venv/bin/python rich   # one-time, not an envs/ dependency - see below
envs/.venv/bin/python tools/visualize_sap2.py
envs/.venv/bin/python tools/visualize_sap2.py --seed 42 --pause 0.6
envs/.venv/bin/python tools/visualize_sap2.py --style random --max-rounds 5
```

Run with `envs/.venv`'s Python — `policyclash_envs` is installed editable
there. `rich` isn't declared in `envs/pyproject.toml`: it's this one
terminal tool's dependency, not the rules/adapter package's, and adding it
there would be exactly the kind of adapter bloat `adding-an-env.md` argues
against — install it into that same venv once, as above.

**What it can and can't show, and why.** `sap2_battle` in the C core
resolves a round's fight and returns only the aggregate outcome
(`P0_WIN`/`P1_WIN`/`DRAW`) — it doesn't record a per-exchange trace, by
design (`adding-an-env.md`'s "keep the adapter thin" rule). So this tool
shows exactly what the real engine exposes: each seat's team/shop/gold/
lives/trophies before a round, the shop actions taken that round (decoded
from the actions the env actually received), and the round's result — not
a fabricated blow-by-blow battle animation. A companion project has a
separate JS reimplementation of the battle algorithm, in a browser game,
that does track a trace for exactly the reason a human player wants to
see it; this tool deliberately doesn't duplicate that here, so nothing it
shows can silently drift from what the real engine did.

Caught one real thing worth knowing about while building this: the
turn-3 life-back rule can fire in the same transition that costs a seat
its first life, immediately restoring it — so "Seat X loses a life" from
naively inferring off the trophy count can flatly contradict the very
next panel's displayed life total. The tool reads the actual before/after
lives delta rather than inferring, and calls out the catch-up rule
explicitly when it's what happened.

## `arena_sap2.py`

The `sap2-v1` arena. Discovers every `bots/sap2/*/bot.py`, plays a round
robin, fits a rating, and rewrites `bots/sap2/LEADERBOARD.md`. See
`bots/README.md` for the submission interface and the rules a bot plays
under.

```
envs/.venv/bin/python tools/arena_sap2.py
envs/.venv/bin/python tools/arena_sap2.py --matches 120
envs/.venv/bin/python tools/arena_sap2.py --only greedy,ppo_mlx
envs/.venv/bin/python tools/arena_sap2.py --reference --no-write
```

A ranked bot receives an `Observation` and nothing else. That is enforced by
construction, not by review: `act()` takes one argument, so a bot has nothing
else to reach for. A bot marked `"class": "reference"` may declare
`act_privileged(env, seat, obs)` and reach the env, and never ranks —
`mc_search` is one, because a clone exposes the opponent's team and the RNG
words behind the coming shop rolls.

Ratings come from a Bradley-Terry fit rather than sequential Elo updates. A
round robin has no meaningful match order, so an Elo update would report the
order and the K factor as much as the strength. The fit adds one drawn game
per pair as a prior: a bot that wins every game has no finite
maximum-likelihood strength, and a clean sweep is normal here, so without it a
rating reports only how long the iteration ran.

The arena also reports per-action median and maximum milliseconds and counts
forfeits. A forfeit means the bot returned an out-of-range action, which
`sap2-v1` treats as an instant loss — a broken bot, not a weak one.

## `train_ppo_sap2.py`

A small PPO in MLX that trains a `sap2-v1` policy and writes weights into
`bots/sap2/ppo_mlx/weights.safetensors`.

```
uv pip install --python envs/.venv/bin/python mlx       # one-time
envs/.venv/bin/python tools/train_ppo_sap2.py --iters 40 --episodes 64 \
    --save bots/sap2/ppo_mlx/weights.safetensors
```

2x128 tanh, a policy head and a value head, masked logits. Four things the
task forces, each of which sinks a run if skipped:

- **Action masking is mandatory.** An out-of-range action forfeits, and most
  of the 49 actions are illegal at any tick. An unmasked policy forfeits its
  way through early training.
- **Reward is terminal-only and ~146 ticks away.** The per-round potential
  `trophies - (5 - lives)` supplies the intermediate signal — the same
  quantity `mc_search` scores, so the two chase a comparable objective.
- **Train against a pool, never `greedy` alone.** `greedy` is deterministic,
  so a policy trained against it can win by memorizing its fixed replies
  instead of playing the game. The opponent seat draws from the current
  policy, `greedy`, and `random` — all loaded from `bots/`, so a bot cannot
  behave one way in training and another way on the board.
- **Evaluate on held-out seeds.** Training draws seeds below 500000;
  evaluation uses two disjoint ranges from 900000 and 1400000. One range can
  flatter a policy that happened to suit its shop rolls.

Measured: 40 iterations x 64 episodes, 242k transitions, **65 seconds** on an
M4 Pro GPU. The result on both held-out ranges was 92.5% and 90.8% against
`greedy`, and 74.2% and 70.0% against `mc_search`. The arena reproduces those
numbers exactly from its own independent match loop, which is the cross-check
that makes them worth quoting.

