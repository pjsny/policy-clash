# sap-v2

Status: **implemented and tested.** The full Super Auto Pets Arena
match — multi-round, life totals, tier progression, growing shop,
freeze — not a single-round slice. This is `sap2` rather than `sap` in
its own naming because it was designed as a second, more complete
iteration on an earlier single-round-only version; that earlier version
is not part of this PR and nothing here depends on it existing in this
repo — `sap2.h` is self-contained (its own species/food tables, its own
RNG, its own battle resolution), not built on top of another file. A few
of this doc's design-rationale notes below still compare against that
earlier version's simpler shape where it's genuinely informative (e.g.
why a step limit is needed here and wasn't there); those comparisons
don't imply the earlier version is present anywhere in this repo.

Implementation: `envs/csrc/sap2.h` / `sap2_binding.c` /
`envs/policyclash_envs/sap2.py`, registered as `sap2-v1`. 18 tests in
`envs/tests/test_sap2.py` (58 total with connect4 and tron-duel's own
suites), plus a 500-match random-legal-play fuzz run at the Python level
(zero crashes, zero illegal forfeits, natural conclusions well inside the
round cap — max turn seen was 16 of the 30-round `MAX_ROUNDS` bound) and
a throughput measurement (~99,000 ticks/sec through the Python adapter —
see "Measured" below).

## Verified against the shipped game, not against a wiki

Every rule below that says "measured" was read out of, or driven inside,
the actual Super Auto Pets build (Steam, `CFBundleShortVersionString`
203, Unity 6000.3.11f1). `policy-clash-re-tools` hosts the game's own IL2CPP
runtime in-process and calls its `SpacewoodCore2` rules directly —
`BoardResolver` for battles, `BoardEvents.*` for the build phase — so
sap2 can be diffed against the real engine instead of against prose. See
`policy-clash-re-tools`' `sap/README.md` for how, and for the two traps that make
naive measurements lie.

Current state of that diff:

- **Battles: equivalent on this roster.** 500 random Tier-1 boards agree
  on the winner; 300 boards with no random ability agree on the exact
  surviving line-up, stat for stat; 60 boards containing Ant or Mosquito
  agree in *distribution* over 200 seeds each (worst per-outcome gap
  0.06, i.e. sampling noise). `policy-clash-re-tools`'s `sap/difftest.py`.
- **Shop phase and placement: scripted checks agree** — exp/level table,
  merge formula, sell values, Pig's doubling, Pigeon's free Bread Crumbs,
  Otter/Beaver/Duck effects, the shop-size schedule, and the buy's
  placement/insert/stack outcomes.
  `policy-clash-re-tools`'s `sap/difftest_shop.py`.
- **Battle lines with holes: verified equivalent.** A buy can leave gaps
  and the real board is never compacted; over 1200 holed Tier-1 boards
  (1181 of them with a gap the battle has to close) the shipped engine's
  start-of-battle `PhaseMove`/`EmptyFront` and sap2's load-time compaction
  agree on winner and on both surviving line-ups.
  `policy-clash-re-tools`'s `sap/difftest.py --holes`.
- **Known remaining gaps**, now roster scope only:
  - Tier-1 Pack1 (Turtle pack) only. The real game unlocks tiers 2–6 on
    turns 3/5/7/9/11 and rolls those species (measured: a turn-5 shop
    offered Badger/Crab/Swan/Hedgehog). sap2 keeps the tier gate but has
    nothing above Tier 1 to put behind it — see the appendix.
  - Three foods (Apple, Honey, Bread Crumbs). The real tier-1 rollable
    food pool at Pack1 turn 1 is exactly Apple and Honey (measured over
    750 rolled slots, uniform), which sap2 matches; later turns roll
    higher-tier food sap2 does not have.
  - The level-up reward has no counterpart: measured, when a team pet's
    level rises the shipped build prepends two `Reward` pets from a higher
    tier to the shop (price 3, over capacity; buying either clears both, as
    does a roll). With a Tier-1-only roster there is no higher tier to
    offer, so this lands with Tier 2.

Eleven real divergences were found and fixed this way; they are called
out where the rule is described below. One apparent twelfth turned out to
be an artifact of how the harness drives the engine - see Pigeon's crumbs
under Match rules.

## A real correction, caught by the user mid-build, worth recording here

An early implementation pass had a pet that faints in battle get its
persistent team slot permanently cleared for the next round — reasoning
that seemed plausible while writing it, but was never actually confirmed
against a source, and was wrong. **Confirmed correction: fainting in
battle is not permanent.** A defeat costs exactly one life — that's the
*only* consequence "The Basics" page states, and it's the only one that's
real. A pet that faints in a losing battle is back, at full health, for
the next round's shop phase, completely unaffected by having fainted.
Only an explicit effect that says so removes a pet from the roster for
good — Sleeping Pill (Tier 2, not in this phase's roster) is the
canonical example, not simply losing a fight. `sap2_battle` in `sap2.h`
never writes back to the persistent team at all, for any reason, matching
this exactly: it's loaded into a throwaway copy and nothing about that
copy — win, lose, fainted or not — is fed back. This is worth stating
explicitly in the spec, not just fixed quietly in code, because it's
exactly the kind of plausible-sounding inference that produces a silent,
hard-to-notice divergence from the real game if it isn't caught.

**Roster scope, decided separately from match mechanics**: this spec
covers the full multi-round *engine* — lives, trophies, tier-gated shop
growth, freeze, the works — but the pet/food roster it ships against
Tier 1 first is still just the 10 pets and 2 foods `sap-v1` already has,
verified. Tiers 2–6 (50 more pets, 15 more foods, already scraped into
`data/turtle_pack/pets.json`) are follow-on work, tier by tier, each
tested before the next — see the appendix. Shipping the match engine and
the full roster in one unverified pass is exactly the failure mode
`sap-v1`'s own build caught repeatedly (three real bugs in ~700 lines for
10 pets); doing it for 61 pets at once with a simultaneously-new match
layer underneath is not a responsible way to ship this.

The rules below were originally written from `superautopets.wiki.gg`'s
"The Basics" and "Shop" pages. They have since been re-derived from the
shipped build itself (see "Verified against the shipped game" above); the
wiki-sourced claims that turned out to be wrong — the shop slot-count
schedule and the level thresholds — are called out where they appear.

## What actually changes from sap-v1

| | sap-v1 | sap-v2 |
|---|---|---|
| Episode = | one shop phase + one battle | a full match: many rounds of shop+battle, until someone wins or is eliminated |
| Team persistence | n/a (one round) | persists round to round; only temporary battle buffs clear |
| Shop | fixed: 3 pet slots, 1 food slot, Tier 1 only | grows with shop tier (tiers unlock on turns 3/5/7/9/11): 3/1 → 4/2 at turn 5 → 5/2 at turn 9 |
| Gold | 10 once | 10 **every** round (does not carry over) |
| Freeze | not modeled (no next turn to persist into) | real mechanic: frozen shop items persist into the next roll, in the leftmost slot(s) |
| Win condition | one battle's Outcome | first to 10 trophies, or opponent's 5 lives hit 0 |
| Roster | Tier 1 (10 pets, 2 foods) | Tier 1 (10 pets, 3 foods); Tiers 2–6 are follow-on phases |

## Match rules (measured from the shipped build)

Source for every number here: `ArenaConstants`, `BoardConstants` and the
build phase driven through the game's own resolver — see
`policy-clash-re-tools`'s `sap/statics.py` and `policy-clash-re-tools`'s `sap/shop.py`.

- **Lives and trophies.** `ArenaConstants.Lives = 5`,
  `ArenaConstants.Victories = 10`, `LossMode = SingleRegain`,
  `RegainTurns = [3]`. Losing a battle costs exactly 1 life at every
  turn — measured: `GetLossPointsBase/GetLossPoints/GetLossPointsMax` all
  return 1 for turns 1–15, so the old "2 lives from turn 3, 3 from turn
  5" scaling is not in this build. Winning gains 1 trophy; a draw changes
  neither. 10 trophies wins the match, 0 lives loses it.
- **Turn-3 life-back.** `RegainTurns = [3]` with `LossMode.SingleRegain`:
  one life back at the start of turn 3 if any were lost, once, capped at
  the starting total. The constants are read from the build; the
  end-to-end regain path is server-side (`ArenaModel`) and was not driven,
  so this is the one match-level rule confirmed only at constant level.
- **Tier schedule.** `BoardConstants.DefaultShopUpgradeTierOnTurn =
  [3, 5, 7, 9, 11]`, and `ArenaUtility.GetTier(turn)` returns
  1,1,2,2,3,3,4,4,5,5,6,6,... for turns 1–12. Once unlocked, lower tiers
  stay in the pool.
- **Shop growth is gated by tier, not by turn — divergence #1, fixed.**
  `DefaultShopUpgradeMinionCapacityOnTier = [3, 5]` and
  `DefaultShopUpgradeSpellCapacityOnTier = [3]`: the pet shop grows at
  tier 3 and tier 5, the food shop at tier 3. Driven turn by turn that is
  **3 pet / 1 food for turns 1–4, 4 pet / 2 food for turns 5–8, 5 pet /
  2 food from turn 9**. sap2 previously used the widely repeated
  3/1 → 4/1 (turn 3) → 5/2 (turn 5) table, which is simply wrong: it
  handed agents a fourth pet slot four turns early.
- **Gold, prices.** 10 gold at the start of every turn (measured turns
  1–12), pet 3 gold (`GetMinionPrice`), food 3 gold (`GetItemPrice`),
  roll 1 gold (`GetRollPrice` — note `GetRefreshGold` is the new-turn
  gold, 10, not a roll cost). Gold does not carry over.
- **Freeze — divergence #8, fixed.** Measured through
  `BoardEvents.FreezeItem`: a frozen shop pet and a frozen food both
  survive a paid roll and the `EndTurn`/`StartTurn` boundary, staying
  frozen, while every unfrozen slot rerolls — and the frozen ones **slide
  to the leftmost slots**, keeping their relative order. A shop
  `[Otter, Cricket, Mosquito]` with the Mosquito frozen rerolls to
  `[Mosquito(frozen), *, *]`; freezing slots 1 and 3 of four leaves them
  at 0 and 1. sap2 used to leave frozen items where they sat, which kept
  the offers right but hid them behind different action indices than the
  real game uses.
- **A roll keeps every frozen food item; the capacity bounds only the
  refill — divergence #9, fixed.** Measured: a turn-1 shop (capacity 1)
  holding a frozen Apple plus two frozen crumbs came back from a roll with
  all three still frozen and in order, and a shop with one frozen crumb
  plus an unfrozen Apple came back as just the crumb. Unfrozen stock past
  the capacity is cleared — those slots are that phase's Pigeon stock, not
  a permanent widening.
- **Pigeon's crumbs are stocked unfrozen**, and the "frozen on a turn-5
  board" reading that briefly looked like a rule was an artifact of the
  oracle, not the game: the flag keys off `BoardModel.TurnOver`, and the
  harness's faked Ready→PreBuild handoff left `TurnOver` set, so every
  board it advanced past turn 1 sat in a build phase no live game is ever
  in. With `TurnOver` cleared the crumbs read unfrozen at every turn and
  tier. A crumb the player freezes by hand behaves like any other frozen
  item. Worth recording because it is the failure mode of measuring
  against a driven engine rather than a played one.
- **Temporary buffs expire at the start of the next turn — divergence
  #11, fixed.** Only Horse's buff is temporary in this roster (its effect
  carries `Duration = Temp(1)`; Ant, Otter, Beaver, Duck and Fish all
  carry `Perm(0)`). Measured: a Horse plus a freshly bought Ant showed the
  Ant at 3/2 on turn 1 and 2/2 from turn 2 on. The buff still counts for
  that round's battle. `SapPet2` now carries permanent and temporary
  components. A stack runs its `max` on the permanent ones and takes the
  **higher of the two temporary** components with no `+1`, so the buff
  survives whichever copy carried it — measured against
  `IntegerStat.Permanent`/`.Temporary` for all four combinations of buffed
  target and buffed incoming copy. A buffed Ant (3/2) stacked with a fresh
  Ant shows 4/3 that turn and 3/3 the next.
- **A battle is capped at 71 exchanges — divergence #12, fixed.**
  Measured: two 0-attack pets trade for exactly 71 front-vs-front
  exchanges (142 `Attack` events, independent of team size and health) and
  the resolver then reports a draw with both lines standing. This roster
  cannot reach the cap (every species has base attack ≥ 1 and nothing
  reduces attack), but without it a 0-attack stalemate would spin forever
  instead of ending the way the real game ends it.
- **Exp, levels and the merge formula — divergence #2, fixed.**
  `BoardConstants.LevelRequirements = [0, 2, 5]`, `MaxLevel = 3`. A pet
  bought fresh is exp 0, level 1; each copy stacked on adds exactly +1
  exp, and the stats become **the higher of each stat, then +1**.
  Measured: an Ant walks 2/2 exp0 L1 → 3/3 exp1 L1 → 4/4 exp2 L2 → 5/5 →
  6/6 → 7/7 exp5 L3, and merging a 4/4 copy into a 5/2 pet gives 6/5
  (not 6/3, not 5/5), while merging an exp-4 copy into an exp-0 pet gives
  exp 5 (the two exps sum, plus one). At exp 5 the pet is maxed and a
  further copy does not stack at all. sap2 previously treated the copy
  count as the level, so level 2 arrived on the second copy and level 3 on
  the third — roughly three times too cheap.
- **Sell value.** `MinionExtensions.GetGoldValue` = level (1/2/3),
  independent of stats, confirmed by the gold delta of a real sell. Pig
  doubles it (observed +2/+4/+6 at L1/L2/L3).
- **Per-pet shop abilities, as measured.** Otter on buy: +1 health to
  `level` random friends. Beaver on sell: +`level` attack to exactly two
  random friends. Duck on sell: +`level` health to every shop pet. Pig on
  sell: doubles the sale. Fish on level-up: exactly two random friends,
  +(new level − 1) to each — measured +1/+1 at level 2 and +2/+2 at level
  3, *not* level-many friends at +level. Pigeon on sell: `level` free
  Bread Crumbs prepended to the food shop, existing food pushed right and
  kept.
- **Foods.** Apple +1/+1, Bread Crumbs +1 attack, Honey grants the Honey
  perk only (no stats); the Honey perk's ability is "Summon one 1/1 Bee"
  on death. The rollable food pool at Pack1 tier 1 is exactly Apple and
  Honey, uniform (measured over 750 rolled food slots).
- **Shop roll pool.** Uniform over the 10 Pack1 Tier-1 species —
  Ant, Beaver, Cricket, Duck, Fish, Horse, Mosquito, Otter, Pig, Pigeon —
  measured over 2250 rolled pet slots (209–244 each, expected 225).
  Their base stats, read from `MinionConstants`: 2/2, 3/2, 1/3, 2/2, 2/3,
  2/1, 2/2, 1/4, 4/1, 3/2 — exactly sap2's tables.
- **Start-of-battle abilities are queued — divergence #3, fixed.** All
  start-of-battle triggers are collected up front and every one of them
  fires, even if its owner has already been killed by an earlier one.
  Measured: Mosquito 5/1 vs Mosquito 1/1 is a draw for every seed, because
  the 1/1 dies to the 5/1's shot and its own queued shot still lands.
  sap2 previously dropped the dead pet's trigger, handing the higher-attack
  Mosquito a free win.
- **Opponent matching, simplified for a 2-seat env.** Real Arena mode
  matches you against a stranger's team from an async pool. This env only
  ever has two seats, so there is no pool — each round, seat 0's
  current team battles seat 1's current team directly. This is a
  simplification of *how an opponent is found*, not of the battle or
  match rules themselves.
- **Level-up tier choice, still not modeled.** Reaching level 2 offers a
  choice of two pets from the next tier up. With a Tier-1-only roster
  there is nothing to choose from, so the action space has no entry for
  it; it lands with the tier rollout in the appendix.

## Episode shape

Same `TwoPlayerEnv` interface as `sap-v1` — this does **not** need a new
interface, resolving the open question `SAP_clone.md` flagged. A "round"
is simply another block of simultaneous shop ticks (exactly like
`sap-v1`'s single round), except:

1. Team state, lives, and trophies carry forward into the next round's
   shop phase instead of the episode ending.
2. Gold resets to 10, a fresh shop rolls (tier-gated by the new turn
   number, sized by the shop-growth table), and any frozen items from the
   previous round's shop persist into it.
3. Once both seats end their shop turn (voluntarily or by budget, same
   rule as `sap-v1`), battle resolves — but instead of setting `done=True`,
   it updates lives/trophies and either starts the next round's shop phase
   (both conditions unmet) or sets `done=True` with the match's `Outcome`
   (someone hit 10 trophies or 0 lives).

`stochastic_dynamics=True` still applies — same reason as `sap-v1`, now
compounded over many rounds' worth of shop rolls instead of one.

## Action space changes

`sap-v1`'s 35 actions extend to **159**, and the bases are derived from the
block widths in `sap2.h` rather than written out, so widening a block
cannot leave a stale offset behind. Two blocks are wider than the shop
they serve, both for measured reasons: `BUY_PET` carries the team position
you dropped the pet on (5 shop slots × 5 positions), and the food block is
`SAP2_FOOD_SLOTS = 17` wide rather than 2, because a Pigeon sale prepends
`level` free Bread Crumbs in front of the rolled food and nothing is
evicted — five level-1 Pigeons sold in one phase left **seven** food items
in the real build, the item in the last slot was still buyable, and a
whole team of level-3 Pigeons is the worst case (2 + 5 × 3).

| indices | action |
|---|---|
| 0 | `END_TURN` |
| 1–25 | `BUY_PET(shop_slot·5 + team position)` |
| 26–30 | `SELL(team slot)` |
| 31–40 | `COMBINE(team pair)` |
| 41 | `REROLL` |
| 42–51 | `REPOSITION(team pair)` |
| 52–136 | `BUY_FOOD(food_slot·5 + team_target)`, 17 food slots |
| 137–141 | `FREEZE_PET(shop slot)`, toggles |
| 142–158 | `FREEZE_FOOD(food slot)`, toggles |

The env re-exports every base and slot width (`ACT_*`, `TEAM_SLOT_FLOATS`,
…) so tests, the visualizer and layout-aware bots derive offsets instead of
copying them.

**Why the buy carries a destination — divergence #6, fixed.** In the real
game a buy *is* a drop on a point: `BoardEvents.PlayMinion` takes the
position, and the position picks one of three outcomes, all measured:

- **empty position** → the pet goes there. Holes are legal; the board is
  never compacted (an Ant dropped on position 3 with 0–2 empty stays at 3).
- **occupied by the same species, exp < 5** → a **stack**, one action.
  Stats become the higher of each +1, exp goes up by one, and the bought
  pet's own on-play ability fires at its *post*-stack level: a second
  Otter on a level-1 Otter gave one friend +1 health, the copy that took
  it to level 2 gave two friends +1 health. A stack is not a summon, so
  Horse stays out of it (measured: stacking onto an Ant 3/2 with a Horse
  on the team gave 4/3, not 5/3).
- **anything else** → an **insert**, sliding the smallest block that has
  room. With a free slot behind the drop point the block from there slides
  back (pets at 1,2,3 + a drop on 2 → 1, new, 3, 4); with no room behind,
  the block in front slides forward (pets at 2,3,4 + a drop on 3 → 1, 2,
  new, 4). A full team refuses the insert — the real build answers
  `FailureReason.NoSpace` — so the mask drops those indices.

sap2 used to auto-place at the leftmost empty slot and make the agent
spell a stack out as buy-then-`COMBINE`, which cost two ticks of the
per-round budget and fired Otter at the wrong level. `COMBINE` remains,
because dragging one team pet onto another is its own real action
(`BoardEvents.StackMinion`), and `REPOSITION` stays a pairwise swap —
verified equivalent to the real `OrderMinion`, which swaps when the target
is occupied and simply moves when it is empty.

A bought pet also arrives with the shop slot's health bonus (Duck's sell
buff) — **divergence #7, fixed**; sap2 used to show the bonus in the
observation and then discard it at the till.

Freeze doesn't consume gold, but still counts as one action toward the
per-round budget, same uniform rule every action type already follows.

**Not implemented this phase, and correctly so**: the tier-up pet choice
(leveling a pet 1→2 offers a pick between two next-tier pets) never fires
against a Tier-1-only roster — there is no next tier to offer from. It
stays an open action-space item for whichever roster phase first adds
Tier 2, not something this phase's action space needs to reserve space
for speculatively.

## Observation changes

Adds, per seat, to `sap-v1`'s existing layout: own **lives** (1 float),
own **trophies** (1 float), current **turn number** (1 float, informs
which tiers/shop size are active — a policy needs this to know what it
can legally reach for), and a **frozen flag** per shop slot (widening the
existing per-slot encoding by 1 float each). A team slot also carries its
**exp** counter and a **perk one-hot**: the real game draws exp pips on the
card, so a level-2 pet at exp 2 and one at exp 4 are visibly different to a
player and used to be the same observation here, and the perk is a one-hot
so a second perk widens a block instead of adding a field. Attack and
health are the TOTALS the card shows — permanent plus any live temporary
buff. 259 floats in total. No opponent lives/trophies —
same reasoning as `sap-v1`'s "no opponent-state block": the real game
doesn't show you the opponent's economy during the shop phase either, only
final battle outcomes are visible.

## Step limit

Resolved: `sap-v1`'s `SHOP_ACTION_BUDGET=20` bound still holds *within*
each round (same unreachable-by-construction proof, applied per round).
Across rounds there is no such guarantee from the rules alone, so an
explicit cap was added: **`MAX_ROUNDS=30`**, giving `max_episode_steps =
30 × 20 = 600`. Unlike every other env in this project, `STEP_LIMIT` is a
genuinely reachable path here, not an assertion — verified: a 500-match
random-legal-play run never came close (max turn seen was 16), so 30 is
comfortably generous rather than tight, but a match that drags on
(trading wins symmetrically, or two policies stuck in a stalemate of
draws) can legitimately hit it.

**Tie-break policy for a `STEP_LIMIT` termination** (a decision no other
env in this project needed, since none reach this path): whoever has more
trophies wins; if tied, whoever has more lives wins; if still tied, draw.
Implemented in `sap2_resolve_round`.

## Measured

Python-level, Apple M-series, random-legal-play (500 full matches, seeds
0–499): zero crashes, zero illegal forfeits, all 500 concluded naturally
(`Termination.NATURAL`), 256/244 `PLAYER_0`/`PLAYER_1` split with no exact
draws (expected — a full 10-trophy-or-0-life match essentially never lands
both conditions on the same tick under random play), average 145.7 ticks
per match, max turn reached 16 of the 30-round cap. Throughput: ~99,000
ticks/sec through the Python adapter (10.1 µs/tick) — roughly half
`sap-v1`'s ~185,000/sec, consistent with `sap2`'s larger per-tick surface
(a 259-float observation and 159-action mask vs. 136/35). The throughput
figure predates the rules corrections; the layout has grown to 259 floats
and 159 actions since, so treat it as a loose upper bound.

## Appendix: roster rollout plan

1. **Tier 1 — done.** Match engine + existing 10 pets/3 foods, verified
   against the shipped build (18 tests, `envs/tests/test_sap2.py`, plus
   policy-clash-re-tools' differential suites).
2. **Tier 2** (Snail, Crab, Swan, Rat, Hedgehog, Peacock, Flamingo, Worm,
   Kangaroo, Spider + Cupcake, Meat Bone, Sleeping Pill): next phase.
   Introduces the `Hurt` trigger for the first time (Peacock).
3. **Tier 3** (Dodo, Badger, Dolphin, Giraffe, Elephant, Camel, Rabbit,
   Ox, Dog, Sheep + Cake\*, Salad Bowl, Garlic): introduces
   `FriendAheadFaints`/`FriendAheadAttacks`-style positional triggers
   (Camel, Giraffe, Ox) not in `sap-v1`'s taxonomy at all yet. \*Cake is
   confirmed **not** currently in Turtle Pack per `data/turtle_pack`'s own
   scrape notes — Salad Bowl and Garlic only.
4. **Tier 4** (Skunk, Hippo, Bison, Blowfish, Turtle, Squirrel, Penguin,
   Deer, Whale, Parrot + Pear, Canned Food, Bread): introduces `KnockOut`
   (Hippo) and permanent shop-wide buffs (Canned Food).
5. **Tier 5** (Scorpion, Crocodile, Rhino, Monkey, Armadillo, Cow, Seal,
   Rooster, Shark, Turkey + Sushi, Chocolate, Chili): introduces
   `FriendFainted` (Shark) and Chocolate's direct-XP-no-merge leveling.
6. **Tier 6** (Leopard, Boar, Tiger, Wolverine, Gorilla, Dragon, Mammoth,
   Cat, Snake, Fly + Pizza, Mushroom, Melon, Steak): introduces
   `BeforeAttack`/`AfterAttack` (Boar, Elephant already tier 3 — Boar is
   the tier-6 case) and `Fly`'s bounded-trigger-count ability.

Each phase: generate the tier's rows from `sap/spec.py`'s dump of the
shipped build's own ability templates (not from a wiki or a scrape),
extend the trigger/selector/effect taxonomy only as far as that tier's
roster actually needs, drive each new ability in both engines with
`policy-clash-re-tools`' `sap/ability_check.py`, and re-run the battle and
shop differential suites before calling it done. No tier's implementation
blocks reporting the previous one as finished.

## Abilities are data, not code

The shipped build does not write an ability as code either: each one is an
`Ability` object carrying a Trigger, an Aim (target selector) and a list of
AbilityPairs (condition + effect), looked up per level through
`AbilityUtility.GetTemplate`. `sap2.h` mirrors that shape - a
`Sap2Ability` table row per species (`SAP2_ABILITY`) and per perk
(`SAP2_PERK_ABILITY`), read by two interpreters:

- `sap2_fire` / `sap2_fire_watchers` resolve a row against a `SapSeat2` -
  the shop phase's fixed slots and holes.
- `sap2_battle_fire` / `sap2_battle_resolve_faint` / `sap2_battle_start`
  resolve the same row against a `SapBattle2` - a packed line that mutates
  as bodies leave.

The two containers are genuinely different, so selectors and effects are
implemented twice; the data describing each ability lives in one place.
All ten Tier-1 pets plus the Honey perk are rows. `sap/spec.py --inventory`
says what the rest of Pack1 needs on top: 17 trigger families, 18 effect
kinds, 9 target selectors, and no conditions at all.

Two families exist in the enum with no Tier-1 listener and therefore no
firing point yet: `SAP2_TRIG_HURT`, `SAP2_TRIG_ATTACK` and
`SAP2_TRIG_KILL`. Their *order* relative to the exchange and to each other
is not measurable on this roster - nothing listens - so the hooks are
deliberately absent rather than guessed. Tier 2's Peacock (`Hurt`) is the
first pet that can measure them.

## See also

- [colin-cannell/SAP_Clone](https://github.com/colin-cannell/SAP_Clone) — the
  companion project this env was designed alongside: `SAP_clone.md` §2
  (turn structure) and the now-resolved multi-round-meta open question.
  Its `data/turtle_pack/pets.json` is a community scrape; later tiers port
  from `policy-clash-re-tools`' `sap/spec.py` instead, which reads the
  shipped build's own templates (60 pets, 18 foods, 186 templates).
