# Adding an environment

Rules go in C under `envs/csrc/`. A thin Python module adapts the compiled core to the shared interface. There are two reference implementations, and which one you copy depends on whether your env is turn-based or simultaneous:

- **connect4** — `envs/csrc/connect4.h`, `envs/csrc/connect4_binding.c` (renamed from `binding.c` when the second env landed), `envs/policyclash_envs/connect4.py`. The turn-based reference, and the harness's calibration fixture: small enough to verify by hand, so a bad adapter, a nondeterminism, or a broken rating shows up immediately. It is not a ladder env, for reasons under [the seed](#make-the-seed-load-bearing).
- **tron-duel** — `envs/csrc/tron_duel.h`, `envs/csrc/tron_duel_binding.c`, `envs/policyclash_envs/tron_duel.py`. The simultaneous-move reference and the first ladder env. Spec in [docs/envs/tron-duel-v1.md](envs/tron-duel-v1.md).

Copy one, then register it and write the tests.

## The two layers

**The C core** (`envs/csrc/<env>.h`) holds the rules and nothing else. No Python headers, no allocation, no global state. Connect4 is two 64-bit bitboards, and a step is four shifts. Keeping Python out means the core can be fuzzed as a standalone binary and compiled to wasm for the replay viewer, and neither is possible if `Python.h` is in the include list.

**The binding** (`envs/csrc/<env>_binding.c`) is a CPython extension exposing `reset`, `step`, `observe`, `legal`, and `replay`. Observations come back as `bytes` rather than numpy arrays, which keeps numpy out of the build and makes the array read-only on the Python side, so a policy cannot mutate its own observation.

**The Python layer** (`envs/policyclash_envs/<env>.py`) implements `TwoPlayerEnv` from `base.py`: translate status codes into `Outcome` and `Termination`, wrap the buffers with `numpy.frombuffer`, return `Observation` and `StepResult`. It contains no rules.

- `reset(seed) -> StepResult`. Starts an episode. `done` is false, and the observations say who acts first.
- `step(action_0, action_1) -> StepResult`. One action per seat, positional. A seat the env did not ask to act is not acting: its argument is ignored, not validated.
- `replay() -> list[int]`. Flat, `spec.actors_per_tick` entries per tick. Flat rather than nested so the replay format does not change shape between a turn-based env and a simultaneous one — the viewer unpacks it with the spec it already had to load.

The load-bearing invariant is in `StepResult.observations`. It is a two-tuple indexed **by seat**, and a non-`None` entry means that seat must supply an action to the next `step`. Exactly one entry is set for a turn-based env; both are set for a simultaneous one; when `done` is true both are `None` and `outcome` and `termination` are set. A runner written against that invariant does not branch on which kind of env it is holding — it hands each non-`None` observation to the policy in that seat, passes both actions positionally, and repeats. Set `actors_per_tick = 2` on the spec for a simultaneous env, which is what `spec.simultaneous` reads.

`Observation` has no `player` field. Position carries seat identity now: an observation's seat is its index in the tuple, and a symmetric env's features are already from that seat's own perspective. The field was a second source of a fact the tuple already states, and two sources of one fact can disagree.

Add the extension to `ext_modules` in `envs/setup.py` and one line to `REGISTRY` in `envs/policyclash_envs/__init__.py`. An env that is not registered cannot be scheduled.

## Rules the interface enforces

**Symmetric observations.** `Observation.features` is from the perspective of the seat receiving it, so both seats see an identical encoding of the same position. In a turn-based env that means the encoding flips with the player on move; in a simultaneous env both seats are handed their own view of the same tick, each labelled own/opponent rather than seat 0/seat 1. One network plays both sides either way, which is what makes self-play and rating comparable across seats.

**Legal actions are given, not inferred.** Every observation carries a boolean mask. Entrants apply it before argmax.

**Illegal actions forfeit.** The offending seat loses with `Termination.ILLEGAL_ACTION` and the win goes to the opponent. Both seats forfeiting on the same tick is a draw, still with `ILLEGAL_ACTION`. Silently remapping an illegal action to a legal one would let a policy that never learned the rules climb the ladder, and clamping an out-of-range action would hide a broken ONNX export. Since the mask is handed over for free, playing a full connect4 column is a bug in the submission. An env where every action is always legal — tron-duel, where driving into a wall is legal and fatal — still ships an all-true mask and still forfeits on an index outside `[0, num_actions)`, so policy code never branches on the env.

**Seating is the scheduler's job.** First-move advantage is decisive in most turn-based games, and a seeded starting position favours one seat even in a simultaneous one, so every pairing is played both ways. The env does not know or care which submission is seat 0.

**Keep the state integral.** The rules core holds integers: bitboards, cell bytes, coordinates. No floats, anywhere a rules decision reads them. The same float source compiled with contraction enabled gives different results than without it — PufferLib's `build.sh` compiling with `SIMD_FLAGS=(-mavx2 -mfma)` is the concrete instance — and "same seed, same env version, same policies, same bytes out" is the property the whole leaderboard rests on. Floats belong in the observation buffer handed to the policy, downstream of everything the rules decide, and nowhere else.

**The seed is recorded even when unused.** Connect4 has no stochastic dynamics, so `reset` deletes the seed explicitly rather than quietly accepting it. If your env is stochastic, set `stochastic_dynamics=True` on the spec and derive all randomness from the seed. No clock, no global RNG, no `os.urandom`.

## Make the seed load-bearing

A ladder env needs distinct seeds to produce distinct episodes. Connect4 does not: it ignores its seed, so every match between two deterministic policies replays the same 42 moves. Playing that game four thousand times and feeding the results to Glicko-2 produces a confident rating built on one sample. It is why connect4 is a fixture and an anchor rather than a ladder.

Do not fix this by making the *dynamics* random if you can avoid it — a stochastic transition adds variance to every rating estimate. Make the *starting position* a function of the seed instead. Tron-duel draws two spawn cells and two facings from the seed, so each seed is a different game with the same deterministic rules.

And make that start asymmetric. A mirrored start is the tempting version and it fails in a way that is easy to miss: two copies of one deterministic policy on a mirrored board play mirror-image moves and meet in the middle, which is a head-on draw on every seed. The seed varies and the episode does not, so you are back where connect4 is with more code. Tron-duel draws the two spawns independently, subject only to a minimum separation.

An asymmetric start favours one seat on any given seed. That is fine and is the scheduler's problem, not the env's: every pairing is played both ways on the same seed, so each submission gets the favoured side exactly once and the advantage cancels in the pair instead of landing in a rating.

## Tests your env needs

Look at `envs/tests/test_connect4.py`. The ones that earn their place:

- Each win geometry, and the boundary case that a naive implementation gets wrong. For bitboards that is a run of four wrapping between columns.
- A draw, if draws are reachable. This exercises the three-outcome path that the rating system needs and a win-only test suite hides.
- Illegal action and out-of-range action, both forfeiting to the right player.
- Observation perspective flips after a move.
- Determinism, in whichever direction your env claims. A seed-ignoring env like connect4 must produce identical episodes from two different seeds. A seeded env must produce identical episodes from the same seed, and must produce a different one from a different seed — the second half is the assertion that catches a seed that was accepted and then dropped.

One warning from writing the reference tests. Every hand-built "full board" ordering I tried filled a column with alternating play, which is a vertical four. The drawn game in the test file was found by search. Do not hand-write terminal positions and assume they are terminal for the reason you think.

## Building and measuring

```
cd envs
uv venv .venv && uv pip install --python .venv/bin/python -e ".[dev]"
.venv/bin/python -m pytest tests -q
```

The editable install compiles the extension in place. Changing a `.h` under `csrc/` means reinstalling, since setuptools tracks the `.c` sources.

Where the time goes in connect4, measured over a full 42-move game:

| | per match | per step |
|---|---|---|
| C rules alone | 0.5 us | 0.01 us |
| Through the Python adapter | 39.8 us | 0.95 us |

The rules cost essentially nothing. Everything else is the adapter allocating an `Observation` and two array views per step. That ratio is the reason the adapter stays thin: any logic added there costs more than the entire rules engine.

Benchmark your env the same way and put the numbers in the PR. An env whose C core is not dramatically cheaper than its adapter has logic in the wrong layer.

## On PufferLib

We do not currently depend on it. 4.0 (branch `4.0`, pushed 2026-09-08) narrows the gap considerably, so the reasons are worth stating accurately before someone proposes it — and worth rechecking, because the version of this section that claimed its envs were all single-agent was wrong.

What it now has. `pufferl.match(env_name, policy_a_path, policy_b_path, num_games=4096)` at `pufferlib/pufferl.py:497` is documented as head-to-head play between two checkpoints in a two-agent selfplay env, reporting `slot_0_score`, `slot_1_score`, and `draw_rate`. Two-agent selfplay exists for `chess` (`CHESS_MODE_SELFPLAY` sets `num_agents = 2`, with the slot-to-colour mapping randomized per env so policies in fixed slots see both colours equally — the same first-move-advantage problem paired seating solves here), `robocode` (`num_agents = 2`, plus frozen historical opponent banks), `go` (a `selfplay` kwarg), and `slimevolley` (`num_agents = 2`, zero-sum +1/-1). `overcooked` also has 2 agents but is cooperative, so it is not a match.

What is still true. `ocean/connect4/binding.c` sets `num_agents = 1` and answers your move with a depth-3 negamax compiled into the env (`ocean/connect4/connect4.h:195`) — a benchmark against a fixed bot rather than a match, and no wrapper turns it into one. Distribution is still source-only: PyPI serves 3.0.0 against a tree declaring 4.0.0, and `build.sh` statically links exactly one env into `pufferlib/_C.so` per invocation, so `pip install pufferlib` ships zero environments. And `build.sh` sets `SIMD_FLAGS=(-mavx2 -mfma)`, with its own comment that this is x86_64-only and must be stripped for ARM and Apple Silicon; a float env compiled under those flags may contract differently across builds, which is the hazard behind the integer-state rule above.

What it does not provide is a ladder. `match()` compares two named checkpoints on one machine. It does not persist results, rate a population, keep replays, or accept a submission from a stranger. That is the whole of what this repo is for, so PufferLib becomes the right dependency when we host training or need a genuinely expensive simulator — not for evaluation.
