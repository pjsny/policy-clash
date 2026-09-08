# tron-duel-v1

Two light cycles on a 13x13 grid. Both seats move every tick, at the same time, and every cell either seat has occupied stays blocked for the rest of the episode. The board fills, the space runs out, someone drives into something. Last one alive wins.

This is the first ladder env: the first one where a rating computed over a few thousand matches carries information. Connect4 remains the harness fixture and the anchor ladder, but two deterministic policies play the same 42 moves there on every seed. Tron-duel is seeded, simultaneous, and asymmetric, so distinct seeds are distinct games.

## Spec

| field | value |
|---|---|
| `id` | `tron-duel` |
| `version` | `1` |
| `obs_shape` | `(4, 13, 13)` |
| `num_actions` | `3` |
| `max_episode_steps` | `83` |
| `actors_per_tick` | `2` |
| `recurrent_state_shapes` | `()` |
| `stochastic_dynamics` | `False` |

`actors_per_tick == SEATS`, so `spec.simultaneous` is true: every `StepResult` hands out an observation to both seats, and `step(action_0, action_1)` reads both arguments.

`stochastic_dynamics` is false. The transition is a pure function of the grid, the two heads, and the two actions. The seed picks the starting position and nothing after it.

## Rules

**Grid.** 13x13, 169 cells, all playable. There is no wall ring inside the board; the boundary is the edge of the board itself, and a step whose target coordinate falls outside it is a crash.

**Trails.** A head leaves its cell permanently blocked when it moves on. Trails never clear, never expire, and are not distinguishable from each other by age. Both seats' trails and both heads occupy the same 169 cells.

**Actions are relative.** Three of them, applied to the seat's current facing:

| action | meaning |
|---|---|
| 0 | turn left, then advance one cell |
| 1 | continue straight one cell |
| 2 | turn right, then advance one cell |

There is no "stand still" and no reverse — a reverse would always target the cell the head just came from, which is that seat's own trail, so it would be a crash dressed up as a move.

Every action is always available. `legal_actions` is all true on every observation, always, and it ships anyway so that policy code does not branch on which env it is playing. Driving into a wall is a legal action with a fatal result, which is the point: the mask does not do the players' thinking for them here, the way it does in connect4.

**Crash.** A seat crashes when its target cell is out of bounds, or already occupied by any trail or either head. Both conditions are checked against the state at the start of the tick, before either seat is moved, so the order the two seats are resolved in cannot change the result.

**Resolution.** Both target cells are computed from the pre-tick state, then compared:

| situation | result |
|---|---|
| neither seat crashes, targets differ | episode continues, both heads advance |
| one seat crashes | the other seat wins, `NATURAL` |
| both seats crash on the same tick | `DRAW`, `NATURAL` |
| both seats target the same empty cell | `DRAW`, `NATURAL` (head-on) |

Two heads facing each other one cell apart is not a special case: each one targets the other's occupied head cell, both crash, draw. Because a vacated head cell becomes trail, no cell is ever freed, so there is no swap-through to adjudicate.

**Spawns.** Derived from the seed. Both heads are placed on interior cells — never on the boundary ring, so neither seat starts with a forced turn — subject to a Manhattan distance of at least 4 between them, and each gets a facing drawn uniformly from the four directions. The two positions are drawn independently and are deliberately not mirror images of each other; see the rationale below.

**Forfeits.** An action outside `[0, 3)` forfeits: the opponent wins with `Termination.ILLEGAL_ACTION`. Both seats out of range on the same tick is a draw with `ILLEGAL_ACTION`. Since the mask is all true, an out-of-range action is a broken export, not a misread of the rules.

## Observation

Four planes of 13x13 `float32`, C-order, in this order:

| plane | contents |
|---|---|
| 0 | own trail |
| 1 | opponent trail |
| 2 | own head |
| 3 | opponent head |

Cells are 1.0 or 0.0. The head planes have exactly one live cell each while both seats are alive.

Every plane is rotated so that the observing seat faces up. A seat facing east sees the board turned a quarter turn; the seat itself never sees any facing but north. This is what makes the encoding symmetric in the sense `base.py` requires: both seats receive an identical-looking observation of the same position, so one network plays both sides, and the "own"/"opponent" split means neither seat has to be told which one it is. `Observation` carries no `player` field; the seat's identity is its index in `StepResult.observations`.

The buffer comes out of C as `bytes` and is wrapped with `np.frombuffer`, so the array a policy receives is read-only and numpy is not in the build.

## Step limit

`max_episode_steps = 83 = (169 - 2) / 2`, rounded down.

Natural termination inside that bound is guaranteed, not hoped for. Reset consumes 2 of the 169 cells for the two heads. Every tick that does not end the episode consumes one previously-empty cell per seat, two per tick, and trails never clear. After 83 ticks at most 167 cells are gone, and the 168th and 169th consumptions cannot both happen, so at the latest the 84th tick has no empty target for at least one seat and ends the episode.

So `Termination.STEP_LIMIT` is unreachable here and is deliberately not implemented. `max_episode_steps` is still on the spec, because a submission needs the horizon to size a rollout buffer and the runner needs a number to bound a match, but no code path produces `STEP_LIMIT`. An env where the limit is reachable must implement it; this one asserts the arithmetic instead.

## Replay

Flat `list[int]`, 2 entries per tick, `[tick0_seat0, tick0_seat1, tick1_seat0, ...]` — `spec.actors_per_tick` entries per tick, as `replay()` promises for every env. Length is `2 * ticks`. The seed plus the version plus this list reconstructs the episode exactly, including a forfeit tick, whose out-of-range action is recorded as given rather than clamped.

## Design rationale

**Asymmetric spawns, not mirrored.** A mirrored start is the obvious choice and it is the wrong one. Two copies of the same deterministic policy on a mirrored board play mirror-image moves forever and meet in the middle: a head-on draw, on every seed. The seed would then be recorded and rated over while carrying no information at all, which is exactly the failure connect4 has and the reason connect4 cannot be a ladder. Independent spawns with a minimum separation break the symmetry, so a seed selects a genuinely different game and a rating over many seeds measures play rather than reproducing one game a few thousand times.

**Paired seating cancels the positional advantage.** An asymmetric start favours one seat, sometimes decisively — more open space, better distance to the boundary. That is fine, because the scheduler plays every pairing twice on the same seed with the seats swapped, so each submission gets the favoured side exactly once. The advantage cancels in the pair instead of being absorbed into a rating. This is the same reason connect4 pairs matches to cancel first-move advantage; the env does not know or care which submission is seat 0.

**Integer state only.** The rules core holds a byte per cell, integer head coordinates, and a facing in `0..3`. Nothing in it is a float. Floats are how bit-reproducibility dies: the same source compiled with contraction enabled produces different results than without it, and PufferLib's `build.sh` shipping `SIMD_FLAGS=(-mavx2 -mfma)` is the concrete version of that hazard. "Same seed, same env version, same policies, same bytes out" is the property the leaderboard rests on, so the only floats in this env are in the observation buffer handed to the policy, downstream of every decision the rules make.

**Egocentric rotation.** Three reasons, in order of weight. It quarters the symmetry the network has to learn: a tactical pattern appears in one orientation instead of four, so training does not spend capacity rediscovering the same trap rotated. It composes with the relative action space — action 1 is always "toward the top of the observation", so the mapping from a plane to a move is fixed and does not have to be conditioned on a facing input. And rotation alone is enough: quarter turns map a square grid onto itself, so the observation stays 13x13 with no padding and no extra plane marking which cells are off-board. Translating the head to the centre as well would have forced a 25x25 frame and an out-of-bounds plane, for no additional invariance the rotation does not already give.

**No pickups.** Speed boosts, jumps, and bonus cells were all considered and none of them are here. Their purpose would have been to make the seed matter, and the asymmetric spawn plus permanent trails already does that. Each one would add a randomness source to reproduce, a plane to the observation, and a rules branch to fuzz, in exchange for no additional rating signal. The rules core stays a grid and two heads.

## Measured

Apple M3 Max, clang `-O3 -std=c11`, both seats driving straight until someone crashes. Straight-line play from interior spawns ends fast, so the per-match rows describe a 4.8-tick average rather than a typical match; the per-tick column is the one to compare.

| | per match | per tick |
|---|---|---|
| C rules alone | 0.034 us | 0.007 us |
| Through the Python adapter | 16.7 us | 3.48 us |

The adapter costs roughly 480x the rules. Connect4's ratio is 80x, and the difference is entirely observation volume: this env builds two `Observation` objects per tick, each wrapping 4x169 `float32`, against connect4's one wrapping 42. The rules themselves are 7 nanoseconds. Anything that looks like a performance problem in this env is in the adapter or the policy, never in `tron_duel.h`.

The benchmark also compiles `tron_duel.h` into a standalone binary with no Python in the include path, which is the property that keeps the core fuzzable and wasm-compilable.

### Does the seed buy anything

The reason this env exists rather than a patched connect4, measured. One fixed deterministic policy — a random projection of the observation, masked argmax, the shape of a real ONNX submission — played against itself over seeds 0 to 199:

| env | distinct episodes | outcomes |
|---|---|---|
| `connect4-v1` | 1 / 200 | 200 seat 0 |
| `tron-duel-v1` | 198 / 200 | 95 seat 0, 85 seat 1, 20 draws |

Connect4 ignores its seed, so two hundred matches are one match recorded two hundred times. Glicko-2 fed that history would shrink its rating deviation as though it had two hundred observations, and report high confidence off a single bit. Tron-duel's seeded start gives 198 distinct episodes, a near-even seat split, and a 10% draw rate that Glicko-2 handles as a half-score.

Note the measurement trap: an observation-blind policy, such as uniform random action selection, scores only 2 distinct episodes here. It replays one action stream every game and only the crash tick moves. Episode diversity is a property of the env and the policy together, so measure it with a policy that reads its observation.

## Rejected: absolute planes plus a facing one-hot

The alternative observation frame was absolute planes — the board as the replay viewer draws it, in board coordinates, with the observing seat's facing supplied separately as a 4-way one-hot. It is genuinely nicer to debug: a plane dumped next to a replay frame lines up cell for cell, with no mental rotation.

It was rejected because it pushes the four rotations onto the network. Every wall-hugging pattern, every trap, every cut-off has to be learned once per facing, and the facing input has to be threaded into whatever layer decides the move. Rotating in C costs one pass over 4x169 cells per observation, which is far below what the Python adapter already spends allocating the `Observation`. Paying that on the env side once is strictly cheaper than paying it in every submission's parameter budget forever.

## See also

- [docs/adding-an-env.md](../adding-an-env.md) — the interface, the layering, and the rules it enforces.
- `envs/csrc/tron_duel.h` — the rules core. Simultaneous-move reference.
- `envs/csrc/tron_duel_binding.c` — the CPython binding. Exports `SIZE`, `CELLS`, `PLANES`, `ACTIONS`, and `MAX_TICKS` as module constants, so the adapter hardcodes none of the numbers in the table above.
- `envs/policyclash_envs/tron_duel.py` — the adapter, class `TronDuel`. Registered as `tron-duel-v1`.
