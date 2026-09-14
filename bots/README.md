# bots

Submissions for the `policy-clash` arenas, and the rules they play under.

One directory per bot: `bots/<env>/<slug>/`, holding `bot.py` and `meta.json`.
`tools/arena_sap2.py` discovers every bot under `bots/sap2/`, plays a round
robin, and rewrites `bots/sap2/LEADERBOARD.md`.

```
envs/.venv/bin/python tools/arena_sap2.py                  # rank and rewrite the board
envs/.venv/bin/python tools/arena_sap2.py --only greedy,ppo_mlx
envs/.venv/bin/python tools/arena_sap2.py --reference      # include privileged bots, unranked
```

## A record is frozen

A bot directory is a record, not a library. Once it lands and appears on the
board, its `bot.py` does not change — a later idea is a new directory, so the
board stays a history rather than a single moving number.

That is why every `bot.py` is self-contained and repeats the observation
decoding it needs instead of importing a shared helper. A shared helper would
let a refactor silently change what an old record scores. Duplication is the
cheaper mistake.

## The interface

`bot.py` exposes one factory:

```python
def make_bot(seed: int) -> Bot: ...
```

The returned object needs one method:

```python
def act(self, obs) -> int: ...
```

`obs` is an `Observation` from `envs/policyclash_envs/base.py`, holding
`features` (a read-only float32 array) and `legal_actions` (a bool array).
Return an action index.

The seed is the bot's only randomness source. Two bots built from the same
seed must play the same match against the same opponent.

## Rules

1. **Observation only.** A bot receives `obs` and nothing else. No env handle,
   no seat index, no match seed, no opponent state.
2. **No `clone()`.** The `Forkable` feature exposes both seats' teams and the
   random number generator words behind the coming shop rolls and battles. An
   observation shows none of that. A bot that forks the env is not playing the
   game the interface describes. Bots that do are marked `"class":
   "reference"` and never rank.
3. **Mask your actions.** An out-of-range action forfeits the match
   (`Termination.ILLEGAL_ACTION`). Read `obs.legal_actions`. The arena reports
   a forfeit as a loss and counts it.
4. **Stay inside the time budget.** 20 milliseconds per action, measured as a
   median over the run. The arena reports median and maximum for every bot.
5. **Declare dependencies** in `meta.json`. The arena skips a bot whose
   imports fail and says so rather than dropping it quietly.
6. **No training at evaluation time.** A bot loads weights; it does not fit
   them. Put training in `tools/`, and commit the weights next to `bot.py`.

## Evaluation protocol

Fixed, so two runs of the board agree:

- Seeds `900000` through `900000 + matches - 1`, disjoint from the range
  `tools/train_ppo_sap2.py` trains on.
- Every unordered pair plays both seatings for each seed. Seat 0 is not
  neutral, so a one-sided sample rates the seat and not the bot.
- Ratings come from a Bradley-Terry fit on the Elo scale, field mean 1500,
  with one drawn game for each pair as a prior. A bot that wins every game has
  no finite maximum likelihood strength, and a clean sweep is a normal result
  here, so each rating is a conservative bound on the true separation.

## `meta.json`

```json
{
  "name": "greedy",
  "author": "pjsny",
  "added": "2026-09-14",
  "class": "ranked",
  "deps": [],
  "notes": "One sentence on the idea."
}
```

`class` is `ranked` or `reference`. Use `reference` for a bot that breaks rule
2 on purpose, as a ceiling to measure against.
