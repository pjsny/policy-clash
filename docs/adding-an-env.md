# Adding an environment

Rules go in C under `envs/csrc/`. A thin Python module adapts the compiled core to the shared interface. Connect4 is the reference implementation: copy `envs/csrc/connect4.h`, `envs/csrc/binding.c`, and `envs/policyclash_envs/connect4.py`, then register it and write the tests.

## The two layers

**The C core** (`envs/csrc/<env>.h`) holds the rules and nothing else. No Python headers, no allocation, no global state. Connect4 is two 64-bit bitboards, and a step is four shifts. Keeping Python out means the core can be fuzzed as a standalone binary and compiled to wasm for the replay viewer, and neither is possible if `Python.h` is in the include list.

**The binding** (`envs/csrc/binding.c`) is a CPython extension exposing `reset`, `step`, `observe`, `legal`, and `replay`. Observations come back as `bytes` rather than numpy arrays, which keeps numpy out of the build and makes the array read-only on the Python side, so a policy cannot mutate its own observation.

**The Python layer** (`envs/policyclash_envs/<env>.py`) implements `TwoPlayerEnv` from `base.py`: translate status codes into `Outcome` and `Termination`, wrap the buffers with `numpy.frombuffer`, return `Observation` and `StepResult`. It contains no rules.

- `reset(seed) -> Observation`. Player 0 moves first, always.
- `step(action) -> StepResult`. Applies the current player's action and passes the turn.
- `replay() -> list[int]`. Actions in order, enough to reconstruct the episode given the seed.

Add the extension to `ext_modules` in `envs/setup.py` and one line to `REGISTRY` in `envs/policyclash_envs/__init__.py`. An env that is not registered cannot be scheduled.

## Rules the interface enforces

**Symmetric observations.** `Observation.features` is from the perspective of the player on move, so both seats see an identical encoding. One network plays both sides, which is what makes self-play and rating comparable across seats.

**Legal actions are given, not inferred.** Every observation carries a boolean mask. Entrants apply it before argmax.

**Illegal actions forfeit.** Connect4 returns `Termination.ILLEGAL_ACTION` and awards the win to the opponent. Silently remapping an illegal action to a legal one would let a policy that never learned the rules climb the ladder. Since the mask is handed over for free, playing a full column is a bug in the submission.

**Seating is the scheduler's job.** First-move advantage is decisive in most of these games, so every pairing is played both ways. The env does not know or care which submission is player 0.

**The seed is recorded even when unused.** Connect4 has no stochastic dynamics, so `reset` deletes the seed explicitly rather than quietly accepting it. If your env is stochastic, set `stochastic_dynamics=True` on the spec and derive all randomness from the seed. No clock, no global RNG, no `os.urandom`.

## Tests your env needs

Look at `envs/tests/test_connect4.py`. The ones that earn their place:

- Each win geometry, and the boundary case that a naive implementation gets wrong. For bitboards that is a run of four wrapping between columns.
- A draw, if draws are reachable. This exercises the three-outcome path that the rating system needs and a win-only test suite hides.
- Illegal action and out-of-range action, both forfeiting to the right player.
- Observation perspective flips after a move.
- Two different seeds produce identical episodes, for a deterministic env.

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

We do not currently depend on it, for reasons that are worth knowing before proposing it.

Its Ocean envs are single agent. `ocean/connect4/binding.c` sets `num_agents = 1`, and `c_step` plays your move and then immediately plays the opponent's with `compute_env_move`, a depth-3 negamax compiled into the env. That is a benchmark against a fixed bot, not a head-to-head match, and no wrapper turns it into one.

Its distribution is also awkward. PyPI's latest is 3.0.0 while the source tree declares 4.0.0, so the published package and the documented library are a major version apart. `build.sh` statically links exactly one env into `pufferlib/_C.so` per build, and `pyproject.toml` declares no extension modules, so `pip install pufferlib` gives you a trainer and zero environments.

It becomes the right dependency when we host training or need a genuinely expensive simulator. For turn-based evaluation it is cost without benefit.
