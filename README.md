<p align="center">
  <img src="assets/brand/policyclash.svg" width="120" alt="PolicyClash">
</p>

<h1 align="center">PolicyClash</h1>

<p align="center">Head-to-head evaluation for RL policies. Environments, a match runner, ratings, and a web arena to watch it happen.</p>

---

Early. The layout below is settled, the code is not written yet.

## What this is

PolicyClash runs two policies against the same environment, scores the result, and updates a rating. Repeat a few thousand times and you get a leaderboard that means something, plus replays you can scrub through.

Three moving parts:

1. **Environments.** Gymnasium-compatible, versioned, deterministic given a seed.
2. **Runner.** Loads two policies, plays a match, emits a result and a replay.
3. **Platform.** Web app that submits matches, stores results, computes ratings, and renders replays and leaderboards.

## Repository layout

```
policy-clash/
├── apps/
│   └── web/                 Next.js app: leaderboards, replays, submissions
├── packages/
│   ├── schema/              Match/replay/policy JSON contracts (zod), the TS↔Python boundary
│   ├── rating/              Glicko-2 implementation, pure functions, no I/O
│   └── ui/                  Shared React components and brand tokens
├── envs/                    Python: policyclash_envs, thin wrappers over PufferLib Ocean
├── runner/                  Python: match runner, policy loading, sandboxing
├── docs/                    Design notes, env specs, rating math
├── assets/brand/            Logo SVG and PNG exports
└── infra/                   Deploy config, migrations, queue workers
```

Two runtimes, kept apart on purpose. TypeScript owns everything user-facing and everything stateful. Python owns environments and match execution, because that is where the ecosystem lives. They talk over JSON, never over shared memory or a shared ORM.

### The contract between them

`packages/schema` is the single source of truth for match requests, match results, and replay format. The runner mirrors those shapes as pydantic models and a CI check fails if the two drift. Changing a field means changing it in `schema` first.

A match request names two policy references, an environment id, a version, and a seed. A match result carries the outcome, per-step rewards, termination reason, and a replay blob. Nothing in the result depends on which machine ran it. Same seed, same environment version, same policies, same bytes out. That property is what makes the leaderboard defensible, so treat any nondeterminism as a bug rather than noise.

### Why rating is its own package

Glicko-2 is small, fiddly, and easy to get subtly wrong. Isolating it means it can be tested against known vectors without spinning up a database, and it can be recomputed over the full match history when the formula changes. Rating math never goes in an API route.

## Environments

Rules are C, under `envs/csrc/`. A thin Python layer in `envs/policyclash_envs` adapts each compiled core to one interface: `reset(seed)`, `step(action)`, `replay()`. Connect4 is the reference implementation. See [docs/adding-an-env.md](docs/adding-an-env.md) to add your own.

The C core carries no Python headers, so it can be fuzzed standalone and compiled to wasm for the replay viewer. A full 42-move connect4 game costs 0.5 microseconds in the rules and 39.8 microseconds through the Python adapter, which is why the adapter stays thin.

We do not depend on [PufferLib](https://github.com/PufferAI/PufferLib), despite it being the obvious candidate. Its Ocean envs are single agent: `ocean/connect4/binding.c` sets `num_agents = 1` and `c_step` answers your move with a depth-3 negamax compiled into the env, which is a benchmark against a fixed bot rather than a match. Its PyPI release is also 3.0.0 against a source tree declaring 4.0.0, and `build.sh` links exactly one env into `pufferlib/_C.so` per build with no extension modules in `pyproject.toml`, so `pip install pufferlib` ships zero environments. It becomes the right dependency if we host training or need an expensive simulator.

## Build order

1. `packages/schema` with the match request and result shapes.
2. `envs` with connect4. Done: rules, forfeit-on-illegal-action, and a determinism test.
3. `runner` that plays a match between two random policies and writes a result.
4. `apps/web` reading results from disk before any database exists.
5. `packages/rating`, once there are real match results to rate.

Ratings and the web app come last because both need real data to be worth anything.

## Conventions

- Environments are versioned and never mutated. A rules change is `cartpole-duel-v2`, not an edit to `v1`. Results reference the version they ran under.
- Submissions are exported ONNX graphs until tier 2 ships. Architecture is unconstrained, operators are allowlisted. Arbitrary code runs only under gVisor with no network egress. See [docs/sandbox.md](docs/sandbox.md).
- Seeds are recorded on every match. A result without a seed is not a result.

## Brand

Base `#13151E`, orange `#FF7A45`, teal `#35D6C4`. The mark is a P cleaved on the diagonal, the orange half against the teal half, inside a ring of two arcs that reads as a rating dial. Source of truth is `assets/brand/policyclash.svg`. PNGs are exported from it, never edited as raster.

## License

[MIT](LICENSE).
