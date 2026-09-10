# sap-v1

Status: **implemented** — `envs/csrc/sap.h` / `sap_binding.c` /
`envs/policyclash_envs/sap.py`, registered as `sap-v1` and passing 19
env-specific tests (59 total with connect4 and tron-duel's own suites).
This doc was written before that code existed, the way `tron-duel-v1.md`
was written before `tron_duel.h` — and, as expected, writing the C core
against it caught two real gaps in the numbers below, now corrected in
place rather than left to silently disagree with the code (see the two
callouts marked **corrected during implementation**). Full game-rules
reference and the scraped pet/food data this spec's numbers are drawn
from live in a companion project,
[sap-gym-env](https://github.com/colin-cannell/SAP_Clone), rather than in
this repo.

One round: shop phase, then one battle, then done. Tier 1 only — 10 pets,
2 foods, 5 team slots, 10 starting gold. No multi-turn tier progression, no
freeze (there is no next turn for it to persist into). This is the
"build-small-first" MVP slice from `SAP_clone.md` §8, scoped exactly, not
a general N-turn SAP implementation.

## Spec

| field | value |
|---|---|
| `id` | `sap` |
| `version` | `1` |
| `obs_shape` | `(136,)` |
| `num_actions` | `35` |
| `max_episode_steps` | `20` |
| `actors_per_tick` | `2` |
| `recurrent_state_shapes` | `()` |
| `stochastic_dynamics` | `True` |

`stochastic_dynamics` is true — unlike tron-duel, where the seed only picks
the start position and the transition afterward is a pure function of state
and actions, SAP's shop offers are re-rolled from RNG mid-episode (on
reset, and on every `REROLL` action). All of that RNG derives from the
recorded seed. No clock, no global RNG, same rule as both reference envs.

## Why this is `actors_per_tick=2`, not turn-based

The real game's shop phase is not "player A decides, then player B decides"
— both players build against their own hidden shop simultaneously, exactly
like tron-duel's two cycles moving at once, except the two sides never
interact until battle. That maps directly onto `base.py`'s simultaneous
shape: every shop tick, `step(action_0, action_1)` reads one action from
each seat that currently has an observation.

**The one pattern neither reference env exercises: a seat can drop out
before the tick that ends the episode.** Connect4 (`actors_per_tick=1`)
always has exactly one active seat per tick; tron-duel (`actors_per_tick=2`)
always has exactly two, every tick, until the terminal one. SAP has two
active seats per tick *until one seat submits `END_TURN` or exhausts its
action budget* (see below), at which point that seat's observation goes
`None` and only the other seat keeps receiving one — the interface already
states the rule this needs ("a seat the env did not ask to act is not
acting: its argument is ignored, not validated"), it's just unused by
either existing env. `actors_per_tick` stays a fixed `2` on the spec for
the whole episode regardless — it describes the tick shape the replay
format commits to, not how many seats happen to be live on a given tick.

**Battle resolves inside the step() call that ends the shop phase, not a
separate tick.** Once both seats have ended (voluntarily or by budget), the
very `step()` call that receives the second seat's last action applies that
action, then immediately resolves the entire battle deterministically from
the seed and returns the terminal `StepResult` — `observations=(None,
None)`, `done=True`, `outcome` set. No extra "battle tick" exists, and
correspondingly the runner never has to submit a no-op action pair for one.

## Actions

35 actions, fixed contiguous blocks. `t` ranges over the 5 team slots,
`s` over the 3 shop pet slots, `(i, j)` over the 10 unordered pairs of team
slots with `i < j`, in lexicographic order (`(0,1),(0,2),(0,3),(0,4),(1,2),
(1,3),(1,4),(2,3),(2,4),(3,4)`).

| indices | action | legal iff |
|---|---|---|
| 0 | `END_TURN` | always |
| 1–3 | `BUY_PET(s)` | shop slot `s` occupied, gold ≥ 3, ≥1 empty team slot |
| 4–8 | `SELL(t)` | team slot `t` occupied |
| 9–18 | `COMBINE(i, j)` | both occupied, same species, neither already level 3 |
| 19 | `REROLL` | gold ≥ 1 |
| 20–29 | `REPOSITION(i, j)` | `i ≠ j`, at least one of the two occupied |
| 30–34 | `BUY_FOOD(t)` | shop food slot occupied, gold ≥ its cost, team slot `t` occupied |

`BUY_PET` always fills the leftmost empty team slot — the shop-slot index
is the only choice exposed, not a target team slot, which is the MVP
simplification that keeps the action count at 35 instead of 3×5. Anyone who
wants a specific arrangement uses `REPOSITION` afterward; `REPOSITION(i,j)`
swaps the two slots' contents (works whether one side is empty, so it
covers "move into an empty slot" and "swap two pets" with one primitive,
same trick tron-duel doesn't need but connect4-style bitboard state does).
`COMBINE`'s exact XP-threshold-to-level-up arithmetic is left to the C core
— the mask rule above ("neither pet already level 3") is the only part
that's spec-load-bearing; the XP math is an implementation detail, not an
interface one.

Every observation still carries a full 35-wide legal mask, all of it
computed, none of it inferred — same rule as both reference envs.

## Observation

Flat `float32[136]`, C-order, laid out as:

| offset | width | contents |
|---|---|---|
| 0 | 1 | gold |
| 1 | 5 × 19 = 95 | 5 team slots, each: species one-hot(13) + attack(1) + health(1) + level one-hot(3) + honey-perk flag(1) |
| 96 | 3 × 12 = 36 | 3 shop pet slots, each: species one-hot(11) + hp bonus(1) |
| 132 | 4 | shop food slot: food one-hot(4) |

Species one-hot index 0 is "empty"; indices 1–10 are the ten Tier-1 pets in
a fixed order (see appendix). Food one-hot index 0 is "empty"; 1–3 are
Apple, Honey, Bread Crumbs (Bread Crumbs only ever appears via Pigeon's
sell ability — see appendix note). A shop pet slot's species one-hot is
only 11-wide (0–10): a shop offer is never a token, only ever one of the
10 buyable species.

**Corrected during implementation, two gaps the draft version of this
section missed:**

- **Team-slot species one-hot needs 13 categories, not 11.** The draft
  assumed only the 10 shop-buyable species could ever occupy a team slot.
  They aren't the only ones — Cricket's Faint ability and Honey's perk both
  summon a *token* (Cricket Token, Bee) directly onto the team mid-battle,
  and the observation has to be able to name what's actually sitting in a
  slot. Team species one-hot is 0=empty, 1–10=the shop species, 11=Cricket
  Token, 12=Bee.
- **A shop pet slot needs an hp-bonus float, not just its species.** The
  draft's reasoning — "every Tier-1 shop pet spawns at exactly its base
  stats, so the value is redundant with species id" — is false for one
  pet: Duck's Sell ability permanently buffs every pet currently sitting in
  the shop, so a shop pet's health can diverge from its species' base
  value. Hiding that from the observation would make the shop-phase state
  non-Markovian for a policy trying to value a Duck-buffed offer correctly,
  so it's an explicit float per shop slot instead.

Team slot attack/health are not redundant with species either — they
diverge from base stats via combining and food, same reasoning as before,
just now also true of the shop side for the one ability (Duck) that
reaches into it.

There is no opponent-state block. Unlike tron-duel, where the opponent's
position is visible and only unlabeled, SAP's shop phase genuinely hides
the opponent's team and shop — `SAP_clone.md` §7 already calls this out.
"Symmetric observation" here means both seats get an identically-shaped
encoding of their *own* state, not that hidden information is zeroed into
a same-shaped opponent block. Nothing needs to reserve space for it.

No battle-phase observation exists at all: nobody acts during battle, so
there is nothing to hand a policy mid-resolution. Temporary (battle-only)
buffs and mid-battle state accordingly never appear in this vector — the
shop-phase observation only needs to represent shop-phase state.

## Step limit

Unlike tron-duel, where 83 falls out of board geometry (the board runs out
of empty cells on its own), nothing about SAP's shop phase self-terminates:
`SELL`, `COMBINE`, and `REPOSITION` all cost 0 gold, so a degenerate policy
could swap two slots back and forth forever with nothing in the rules to
stop it. There is no natural bound to derive — one has to be imposed.

**`SHOP_ACTION_BUDGET = 20` per seat.** A seat's action count rises by at
most 1 per tick it is still active, starting at tick 1 — so it cannot hit
20 actions before tick 20 itself, meaning both seats are guaranteed
`ended` by tick 20 at the latest, which is exactly the tick that resolves
the battle (see above — there's no separate battle tick, so this is the
same tick, not one after it). Once a seat hits the budget, the env forces
its turn to end immediately (same effect as if it had chosen `END_TURN`:
its observation goes `None` starting next tick). This mirrors tron-duel's
approach of making the limit unreachable by construction rather than
implementing a `STEP_LIMIT` code path — `Termination.STEP_LIMIT` is
asserted unreachable here too, the same way tron-duel asserts it for
board exhaustion instead of coding a check for it. `max_episode_steps =
20`, exactly the budget — **an earlier draft of this doc said 21, adding
one more tick "for" battle resolution on top of the tick that already
resolves it; that double-counts the same tick and was caught writing the
`sap_step` budget check against this section, not by inspection.**

20 is deliberately generous headroom, not a tight bound: even a thorough
turn-1 line (a few rerolls, buy, feed, reposition, combine) lands well
under it. It exists to stop a degenerate free-action loop, not to pressure
real play.

## Outcome and termination

Same three-value `Outcome` and mapping every env uses: `PLAYER_0`,
`PLAYER_1`, `DRAW`, from the battle-resolution algorithm in `SAP_clone.md`
§4 (simultaneous front-pet exchanges, `Termination.NATURAL`). An
out-of-range action index on any shop tick forfeits that seat immediately
— `Termination.ILLEGAL_ACTION` — with the same both-forfeit-same-tick-is-a-
draw rule connect4 and tron-duel both use. This can happen on any shop
tick, not just the last one: an illegal action ends the whole episode right
there, mid-shop-phase, with no battle ever resolving — that's the existing
interface rule, applied to a phase neither reference env has multiple
ticks of before it can fire.

## Replay

Flat `list[int]`, 2 entries per tick (`actors_per_tick = 2`), for every
shop tick that occurred (the tick that triggers battle resolution is the
last entry, and battle itself consumes no replay entries of its own — the
whole battle is reconstructible from the seed plus the final team states,
which the seed plus this replay plus the env version already pin down).

The one thing to get right implementing this: once a seat has ended and
its observation is `None`, the runner still passes *some* value for that
seat's argument on every subsequent tick (ignored per the interface rule),
and that raw ignored value still gets recorded into its replay slot —
same as connect4 records a forfeiting seat's out-of-range action verbatim
rather than dropping it. Don't special-case "seat wasn't asked to act" into
a gap in the replay array; the format is `actors_per_tick` entries every
tick, full stop, exactly as `adding-an-env.md` states it.

## Appendix: Tier-1 roster and the effect primitives it needs

Source: `data/turtle_pack/pets.json` / `foods.json`, filtered to tier 1.
Species one-hot order (indices 1–10): Ant, Beaver, Cricket, Duck, Fish,
Horse, Mosquito, Otter, Pig, Pigeon.

| pet | base A/H | trigger | effect | primitive needed |
|---|---|---|---|---|
| Ant | 2/2 | Faint | random friend +N/+N | `buff(random_friend, atk, hp, permanent)` |
| Beaver | 3/2 | Sell | 2 random friends +N atk | `buff(2×random_friend, atk, 0, permanent)` |
| Cricket | 1/3 | Faint | summon N/N Cricket (token) | `summon(token_species, atk, hp)` |
| Duck | 2/2 | Sell | shop pets +N health | `buff_shop(all_shop_pets, 0, hp)` |
| Fish | 2/3 | Level-up | 2 friends +N/+N (none at L3) | `buff(2×friend, atk, hp, permanent)` |
| Horse | 2/1 | Friend summoned | that friend +N atk, until next turn | `buff(trigger_source, atk, 0, temporary)` |
| Mosquito | 2/2 | Start of battle | N dmg to N random enemies | `damage(N×random_enemy, 1)` — battle-phase only |
| Otter | 1/4 | Buy | N random friends +1 health | `buff(N×random_friend, 0, 1, permanent)` |
| Pig | 4/1 | Sell | gain N gold | `gain_gold(N)` |
| Pigeon | 3/2 | Sell | stock N free Bread Crumbs in shop | `stock_shop_food(Bread Crumbs, free)` |

Foods: Apple (3g, +1/+1 to one pet), Honey (3g, Honey perk → summon 1/1 Bee
on that pet's faint).

Five primitives cover the whole roster: `buff` (friend/self/shop-pets,
atk/hp, temporary/permanent), `summon` (token species at a given
atk/hp/level), `damage` (battle-phase only — Mosquito is the only Tier-1
user), `gain_gold`, and the two shop-mutation ones Duck and Pigeon need
(`buff_shop`, `stock_shop_food`). `N` scales with the pet's level (1/2/3)
per the level table in `pets.json` for everything except Horse, whose
temp-buff amount is stated per-level in the wiki text the same way.

**Two follow-ups this draft left open, both resolved during
implementation** (`sap_sell` and `sap_battle_resolve_faint` in `sap.h`):

- **Pigeon → Bread Crumbs.** Resolved with an explicit default rather than
  a wiki ruling: since MVP's shop has exactly one food slot, `sap_sell`
  just overwrites it with a free Bread Crumbs regardless of Pigeon's level
  (the real "stock up to `level` copies" only matters when more than one
  food slot exists, which this MVP never has). Documented as a resolved
  simplification in `sap.h`'s `SAP_PIGEON` case, not a claim about how a
  multi-slot shop behaves.
- **Honey → Bee.** Implemented as designed: `SAP_BEE` is species id 12,
  entering play only via `sap_battle_insert_front` off a Honey-perked
  pet's faint.

**One more correctness question the appendix didn't anticipate, found
writing `sap_battle_start`:** what happens when a Mosquito volley faints
more than one enemy at once (level 2 or 3 Mosquito, multiple targets), and
one of them is a Cricket or a Honey-perked pet? Summoning a replacement
shifts array indices, which can misdirect a still-pending resolution for a
different target in the same volley if handled naively (insert-then-move-
to-the-next-picked-index). `sap_battle_start` handles this by capturing
every fainted target's (species, level, honey) *before* touching the
array, removing all of them (safe in descending-index order, pure
removal), then applying each one's own summon/buff effect from the
captured data — see the comment block around `f_species`/`f_idx` there.
One deliberate simplification inside that same fix: if a single fainted
pet is *both* a Cricket *and* Honey-perked, only the Cricket's own-ability
summon fires — ability summon wins over a food-perk summon on the same
faint, since only one replacement can occupy the vacated slot. Also
resolved, not previously anticipated: **Fish's `level_1` ability text
never fires.** `LevelUp` only fires on an actual transition to level 2 or
3 via combining; level 1 is the pet's starting state on purchase, never
something combined *into*, so that row of `pets.json`'s ability table is
real wiki text describing an event that cannot occur under normal play —
`sap_combine` only fires the trigger when `level > prev_level && level >=
2`.

## Measured

Apple M3 Max, clang `-O3 -std=c11`. Two lines, both averaged over 200,000
matches with a fresh seed each: the cheapest possible episode (both seats
end turn immediately, 1 tick) for a floor, and a short realistic line
(buy, reroll, end — 3 ticks) for a per-tick number less dominated by
episode setup/teardown.

| | per match | per tick |
|---|---|---|
| C rules alone, 1-tick match | 0.061 us | 0.061 us |
| C rules alone, 3-tick match | 0.211 us | 0.070 us |
| Through the Python adapter, 3-tick match | 16.3 us | 5.4 us |

The adapter costs roughly 77x the rules — close to connect4's 80x, and far
below tron-duel's 480x. That tracks: tron-duel's adapter marshals two
4×13×13 = 676-float observations per tick, this env's marshals two
136-float ones, so there's much less buffer for `numpy.frombuffer` and
`Observation` construction to do per step. The rules themselves are still
essentially free either way; anything that looks like a performance
problem in this env is in the adapter or the policy, never in `sap.h`.

## See also

- [colin-cannell/SAP_Clone](https://github.com/colin-cannell/SAP_Clone) — the
  companion project this env was designed alongside: `SAP_clone.md` (full
  game rules reference, MVP scope in §8, and the open questions this spec
  resolves a few of in §7 and the open-questions section) and
  `data/turtle_pack/` (scraped pet/food data this spec's numbers are drawn
  from).
- [`docs/adding-an-env.md`](../adding-an-env.md) — the interface, the
  layering, and the rules it enforces.
- [`docs/envs/tron-duel-v1.md`](tron-duel-v1.md) — the simultaneous-move
  reference this spec follows the shape of.
- [`envs/csrc/sap.h`](../../envs/csrc/sap.h) — the rules core implementing
  this spec.
- [`envs/csrc/sap_binding.c`](../../envs/csrc/sap_binding.c) — the CPython
  binding. Exports status codes and shape constants (`OBS_FLOATS`,
  `NUM_ACTIONS`, `MAX_TICKS`, ...) so the adapter hardcodes none of the
  numbers above, same convention as `tron_duel_binding.c`.
- [`envs/policyclash_envs/sap.py`](../../envs/policyclash_envs/sap.py) —
  the adapter, class `Sap`. Registered as `sap-v1`.
- [`envs/tests/test_sap.py`](../../envs/tests/test_sap.py) — 19 tests:
  spec/registry shape, buy/sell/combine/reroll/reposition/food mechanics,
  illegal-action and masked-illegal forfeits, the ended-seat-argument-
  ignored rule, the action-budget-forces-end bound, seed determinism, and
  one hand-computable single-winner battle (Otter outlasts Horse) as a
  non-random correctness check on the combat loop.
