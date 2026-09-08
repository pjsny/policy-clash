<p align="center">
  <img src="assets/brand/policyclash.svg" width="120" alt="PolicyClash">
</p>

<h1 align="center">PolicyClash</h1>

<p align="center">Head-to-head evaluation for RL policies in video games. Environments, a match runner, ratings, and a web arena to watch it happen.</p>

<p align="center">
  <a href="https://discord.gg/YnkXePUc"><img src="https://img.shields.io/badge/Discord-join%20the%20server-FF7A45?style=flat-square&logo=discord&logoColor=white&labelColor=13151E" alt="Join the PolicyClash Discord"></a>
</p>

---

**[Join the Discord](https://discord.gg/YnkXePUc)** to argue about environment design, rating math, or sandboxing — or to claim an env.

## What this is

Most game RL is graded against a fixed opponent: a scripted bot, a search baseline, a frozen checkpoint. That number tells you how well a policy exploits that one opponent, not how well it plays. PolicyClash grades policies against each other instead. Two policies, the same environment, the same seed, a scored outcome, a rating update. Repeat a few thousand times and you get a leaderboard that means something, plus replays you can scrub through.

The longer goal is the environments. Ranking policies is only interesting if they are playing something worth playing, so the work bends toward simulation environments of real games — the actual rules, the actual state, fast enough to run millions of matches. Board games first because they are cheap to verify; from there, the mechanics that make video games hard: hidden information, simultaneous turns, continuous control, long horizons.

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
├── envs/                    Python: policyclash_envs, C rules cores with thin adapters
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

Connect4 is a calibration target, not the point. It is small enough to prove the harness is honest: the rules are verifiable by hand, determinism is testable, and a bad rating implementation shows up immediately. The environments worth building are the ones people actually play, which means writing rules cores for real games — reimplemented, not screen-scraped — and paying the cost of hidden information, simultaneous moves, and horizons measured in thousands of steps rather than forty-two. Every env lands as a C core plus a thin adapter for the same reason: at a few thousand matches per rating update, the simulator is the budget.

We do not depend on [PufferLib](https://github.com/PufferAI/PufferLib), though 4.0 narrows the gap. It ships `pufferl.match()` — head-to-head play between two checkpoints in a two-agent selfplay env, reporting per-slot win rates and a draw rate — plus selfplay modes for chess, go, robocode, and slimevolley. `ocean/chess/binding.c` randomizes the slot↔color mapping per env so policies in fixed slots see both colors equally, which is the same first-move-advantage problem paired seating solves here.

What it does not provide is a ladder. `match()` compares two named checkpoints on one machine; it does not persist results, rate a population, keep replays, or accept a submission from a stranger. Reproducibility is not a goal either — `build.sh` compiles with `-mavx2 -mfma`, so float envs may contract differently across builds, and those flags are x86_64-only by their own comment. Installation stays source-only: PyPI serves 3.0.0 against a tree declaring 4.0.0, and `build.sh` statically links exactly one env into `pufferlib/_C.so` per invocation, so `pip install pufferlib` ships zero environments.

Board games there are also still single agent outside selfplay: `ocean/connect4/binding.c` sets `num_agents = 1` and answers your move with a depth-3 negamax compiled into the env, which is a benchmark against a fixed bot rather than a match. PufferLib becomes the right dependency if we host training.

## Build order

1. `packages/schema` with the match request and result shapes.
2. `envs` with connect4: rules, forfeit-on-illegal-action, and a determinism test.
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
