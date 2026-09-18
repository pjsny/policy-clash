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
`envs/policyclash_envs/sap2.py`, registered as `sap2-v1`. Roster is Tier 1
(10 pets) plus Tiers 2 and 3 (20 more, unlocked turn 3+ per the tier
schedule below) and their foods — see "Tier 2 roster" and "Tier 3
roster" below for what shipped, what
was measured, and the two abilities still deferred. 21 tests in
`envs/tests/test_sap2.py` (70 total with connect4 and tron-duel's own
suites), plus a 2000-match random-legal-play fuzz run at the Python level
(zero crashes, zero illegal forfeits, natural conclusions well inside the
round cap — max turn seen was 16 of the 30-round `MAX_ROUNDS` bound) and
a throughput measurement (~99,000 ticks/sec through the Python adapter —
see "Measured" below; not remeasured post-Tier-2, since nothing about the
per-tick cost changed, only table sizes).

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
  - Tiers 1–3 (Pack1). The real game unlocks tiers 2–6 on turns
    3/5/7/9/11 and rolls those species (measured: a turn-5 shop offered
    Badger/Crab/Swan/Hedgehog — all three tiers, and all three are now
    in scope). Tiers 4–6 still have nothing to put behind the gate — see
    the appendix.
  - Two Tier-2 abilities are explicit no-ops, not silently wrong:
    Hedgehog's Faint damage (needs a general "resolve every pet at ≤0
    health, anywhere on either board, recursively" pass that the battle
    core doesn't have yet — every call site currently assumes index 0)
    and Spider's Faint summon (needs a Tier-3 roster to summon from).
    Both pets are fully buyable/sellable/combinable; see
    `sap2_battle_resolve_faint`'s own comments.
  - Nine foods now: Apple, Honey, Bread Crumbs (Tier 1 - the tier-1
    natural pool is still exactly Apple and Honey, measured over 750
    rolled slots uniform, Bread Crumbs is Pigeon-only), plus Meat Bone,
    Muffin, Sleeping Pill (Tier 2's natural pool from turn 3 on) and
    Apple-Discount/Better Apple/Best Apple (Worm-only stock, never a
    roll — see "Worm" below). Tiers 3–6's foods are still missing.
  - The level-up reward has no counterpart: measured, when a team pet's
    level rises the shipped build prepends two `Reward` pets from a
    higher tier to the shop (price 3, over capacity; buying either clears
    both, as does a roll). This needs a pet's level-up to be able to
    reach into Tier 3, so it stays open even with Tier 2 shipped — it
    lands with Tier 3.

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
| Roster | Tier 1 (10 pets, 2 foods) | Tiers 1–3 (30 pets, 8 rollable foods + 2 Worm-only Apples + Pigeon's crumbs), all rollable on the tier schedule. Tiers 4–6 are follow-on phases |

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

## Tier 2: the roster, the pools, and what is still capped

Every number in this section was read out of the shipped build through
`policy-clash-re-tools`: `sap/ability_check.py` fires one named ability or
food and reports the full observable delta, `sap/pool_probe.py` enumerates
the roll pools out of the build's own filter closures, `sap/perk_probe.py`
reads the perk model, and `sap/food_probe.py` re-measures the foods.

- **The roll pool is the union of every species with `tier <= shop tier`,
  uniform, with replacement.** Not per-tier weighted, not current-tier
  only. Measured twice over: the build's own `RandomizeShop` filter
  closure enumerated directly (cross-checked against
  `BuildExtensions.GetAvailableMinionsByTier`), and 120k sampled slots
  (χ²=23.2, df=29, p=0.77 against uniform at tier 3). Foods the same way:
  tier 1 is {Apple, Honey}, tier 2 adds {Meat Bone, Muffin, Pill}, tier 3
  adds {Cake, Garlic, Salad Bowl}.
- **Prices are not uniform.** Every Pack1 food is 3 gold *except Pill,
  which is 1*, so a single food price would be wrong the moment Tier 2
  lands. A Worm-stocked Apple costs 2 — an absolute price, not a discount
  off 3 — and Pigeon's crumbs are free. Price is therefore a property of
  the **shop slot**, not of the food id, in both the state and the
  observation.
- **The refill is sorted by tier, descending — and by nothing else.**
  Measured by calling the build's own comparator
  (`BoardExtensions.<>c.<RandomizeShop>b__119_4` for pets, `b__119_7` for
  foods) over a full pair matrix: attack, health, price, enum value and
  pool position all compare equal within a tier. Ties keep draw order (a
  stable tier-descending sort of the draw sequence predicted 11998/11998
  real shops). Frozen items are **not** re-sorted: they stay packed left
  in their existing relative order, and the refill is ordered only within
  itself, so a shop with anything frozen is not globally tier-sorted.
- **Buying out of the middle compacts the shop — a live Tier-1 divergence,
  fixed.** The real shop is a `List<T>`: buying index 1 of
  `[Giraffe, Giraffe, Rat, Worm]` leaves `[Giraffe, Rat, Worm]`, length 3.
  sap2 blanked the slot in place, which left a hole the real game never
  has and put every later slot behind the wrong action index. This one had
  been wrong since the first version and survived 18 scripted shop checks
  and a 24,000-action fuzzer, because the harness compared shop *contents*
  and not shop *slots*; the harness now compares slot identity and has
  scripted checks for compaction, for the tier-descending refill, and for
  frozen items not being re-sorted.
- **Perks carry no durability in Pack1.** All nine Pack1 perk templates
  have `Durability = null`, so a perk here is an id and nothing else, and
  a charge counter would have been fiction. (Melon's one-shot shield is a
  `Shield` perk the combat pipeline removes on first absorb, and Melon is
  Tier **6**, not Tier 3 as the rollout plan used to say. The perks that
  do carry a durability — Lemon, Strawberry, Potato, White Okra — are all
  Pack2/3/4.) The slot is strictly single-valued: a second food replaces
  the first unconditionally, raising perk-lost then perk-gained.
- **Meat Bone is a damage-time bonus, not a stat.** Flat +3 on every
  attack (Hurt amounts 1→4, 2→5, 10→13), invisible in the displayed
  attack, and it does **not** boost ability damage — a Mosquito with Meat
  Bone still deals 1, a Hedgehog still deals 2.
- **Muffin is entirely temporary**: +3/+3 in the temporary components,
  permanent halves untouched, surviving the EndTurn and cleared by the
  next StartTurn — the same deadline Horse's buff already uses here.
- **Pill destroys the pet it is fed to**, for 1 gold, and the faint
  triggers fire: an Ant given a Pill leaves a surviving friend permanently
  +1/+1 before the body goes.
- **Worm's Apples.** A Worm stocks Apple / Apple2 / Apple3 by level
  (+1/+1, +2/+2, +3/+3 permanent), prepended at slot 0 at 2 gold, after
  the turn's roll and ignoring the food capacity entirely. Apple2/Apple3
  are unrollable (`Rollable = false`, empty pack list) and reachable only
  this way. The stock does not survive a roll.

**What is still capped, and why.** `SAP2_ROSTER_TIER = 3` — this
paragraph described the Tier-2 state and is kept for the reasoning, which
still applies one tier up. Tier 2 shipped with exactly one hole, Spider's
faint, because holding the whole tier back was measured to be worse: with
the roster capped at Tier 1 every turn-3-and-later shop drew from 10
species where the real game draws from 20, so the whole shop distribution
was wrong by construction rather than one species' faint effect. Tier 3
closed that hole and left nothing deferred inside a shipped tier; see
"Tier 3 roster" below for what is behind the cap now.

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

## Tier 2 roster

This section and the one above were written from two independent
measurement passes over the same shipped build, merged: the pass above
covers the pools, prices, perk model, compaction and ordering, this one
covers the roster itself. Where they overlapped they agreed, with the
exceptions called out below.

Ground truth for every number came out of the build via
`policy-clash-re-tools` — `roster.py`'s minion/spell dump for
stats/prices, `ability_check.py` for every ability's per-level template
and observed delta, `order_probe.py` for the orderings — not from
`data/turtle_pack`'s wiki scrape and not from memory of the game's 2021
balance. That mattered here in a way it had not for Tier 1: this build's
Tier-2 foods are **Meat Bone, Muffin, Sleeping Pill**, not "Cupcake", and
Worm's ability stocks an upgraded **Apple** rather than a "friend eats an
apple" trigger. A wiki-first pass would have shipped both wrong.

**Roster**: Crab 4/1, Flamingo 3/2, Hedgehog 4/2, Kangaroo 2/2, Peacock
2/5, Rat 3/6, Snail 2/3, Spider 2/2, Swan 1/2, Worm 1/4 — all buyable,
sellable, combinable, freezable, and rollable from turn 3 alongside
Tier 1. Abilities, with the per-level amounts read off the cast template
rather than the UI text:

| Pet | Trigger | Effect (L1/L2/L3) |
|---|---|---|
| Crab | StartBattle | health += ceil(25/50/75% of the healthiest friend's TOTAL health), added not set, self excluded |
| Flamingo | BeforeDeath | the two nearest friends behind +1/+1, +2/+2, +3/+3 (count fixed at two) |
| Hedgehog | BeforeDeath | 2/4/6 damage to every other pet on BOTH sides, gated on at least one other pet existing |
| Kangaroo | the friend ahead attacked | itself +1/+1, +2/+2, +3/+3 |
| Peacock | Hurt (and survived) | itself +3/+6/+9 attack |
| Rat | Death | 1/2/3 Dirty Rats, each 1/1 level 1, up front on the OPPONENT's side, trigger-disabled |
| Snail | EndTurn, only after a LOSS | the three nearest friends ahead +1/+2/+3 attack (count fixed at three) |
| Spider | Death | a random tier-3 pet at 2/2, 4/4, 6/6 — **deferred, see below** |
| Swan | StartTurn | +1/+2/+3 gold, on top of the turn's allowance |
| Worm | StartTurn | stocks Apple / Apple2 / Apple3 at 2 gold, prepended after the roll |

**Deferred, not silently wrong — and now landed**: Spider's summon needed
a Tier-3 roster to draw from. It was the one Tier-2 rule this env did not
implement, and Tier 3 closed it (see "Tier 3 roster"). Holding the whole tier back instead would be worse:
capped at Tier 1, every turn-3-and-later shop is wrong by construction.

Two claims from the first pass that the second corrected:

- **Worm's stock is an ordinary Apple at a slot price of 2**, not a
  separate discounted-Apple species. The build's `Catalogue.Price = 2` is
  an absolute price on the stocked item, so price is a property of the
  shop SLOT (a rolled Apple beside it still costs 3). Only the *upgraded*
  Apples are distinct ids, because they are distinct items: Apple2 and
  Apple3 give +2/+2 and +3/+3 and are unrollable.
- **Hedgehog's splash needed the general fix, not a sweep.** Its damage
  really can faint pets anywhere on either board, and the first
  implementation of that was a post-hoc sweep for anyone left at ≤0
  health. What the differential harness then showed is that the actual
  defect was narrower and worse: faints were being resolved by array
  INDEX after an ability had already shifted the line, so a Rat's
  opponent-side summon could make a removal delete the wrong body and
  leave a corpse fighting on at negative health. Bodies now carry a
  stable id and every resolution re-finds itself. That fixed 80 of the 86
  divergent Tier-2 boards; cross-pet faint order is attack-descending
  with a coin flip on ties, which is measured, rather than board order,
  which is not.

Verified: 67 env tests, 24/24 scripted shop checks, 200 fuzz episodes at
turn 1 and 120 at turn 3 with no divergence, 300/300 Tier-1 exact
surviving line-ups, and Tier-2 exact survivors down from 86/200
mismatching to 6/300 — the tail is under investigation and is recorded
here rather than rounded off.

## Tier 3 roster

Same method as Tier 2, one level stricter: every row below was generated
from `sap/spec.py`'s dump of the shipped build's own ability templates
and then FIRED once with `sap/ability_check.py --pet X --levels`, and the
rules a template cannot carry were each driven separately in
`sap/tier3_drive.py` (named per row). Nothing here came from a scrape.
The gate is `sap/audit_roster.py --tier 3`, which diffs the header
against the build mechanically: zero WRONG and zero MISSING rows for
tiers 1-3.

**Roster**: Badger 6/3, Camel 3/3, Dodo 4/2, Dog 3/2, Dolphin 4/3,
Elephant 3/7, Giraffe 1/2, Ox 1/3, Rabbit 1/2, Sheep 2/2, rollable from
turn 3 alongside Tiers 1-2, plus **Birthday Cake, Garlic and Salad
Bowl** at 3 gold each. The food pool matters as much as the pets: a
tier-3 food roll draws 1/8, and a roster that omitted Birthday Cake
would make every turn-3-and-later food roll wrong by construction.

| Pet | Trigger | Effect (L1/L2/L3) |
|---|---|---|
| Badger | BeforeDeath | floor(own attack x 50/100/150%) damage to the nearest living body EACH way - and "each way" crosses the battle line |
| Camel | Hurt | the nearest friend behind +1/+2, +2/+4, +3/+6 - fires even when the hurt was lethal |
| Dodo | StartBattle | floor(own attack x 50/100/150%) ATTACK to the nearest friend ahead |
| Dog | a friend was summoned | itself +2/+1, +4/+2, +6/+3, TEMPORARY |
| Dolphin | StartBattle | 4 damage to the fewest-health living enemy, 1/2/3 times, re-picked per shot |
| Elephant | after it attacks | 1 damage to the nearest friend behind, 1/2/3 times |
| Giraffe | StartTurn | the nearest 1/2/3 friends ahead +1/+1 - the COUNT scales, not the amount |
| Ox | the friend directly ahead fainted | itself the Melon perk and +1 attack, 1/2/3 times a turn |
| Rabbit | a friendly pet ate | the EATER +1/+2/+3 health, three times a turn |
| Sheep | Death | two Rams at 2/2, 4/4, 6/6, at its own level, into the cell it vacated |
| Spider (Tier 2) | Death | one random rollable tier-3 pet at 2/2, 4/4, 6/6 - **the hole Tier 2 shipped with, now closed** |

| Food | Effect |
|---|---|
| Birthday Cake | a perk worth +1 gold of sell value at EVERY end of turn, cumulative |
| Garlic | a permanent perk: every incoming hit takes 2 less, floored at 2, never more than was coming |
| Salad Bowl | +1/+1 to TWO RANDOM friends - played on the BOARD, not on a pet |

**What the templates could not say, and what driving them showed.**

- **Badger's "adjacent" is not a team-local rule.** Its targets node
  carries no Team filter at all, and on the merged ten-cell battle grid
  the cell in front of your own front IS the enemy's front. Driven four
  ways: mid-line it hits two friends, at the front it hits the friend
  behind AND the enemy front, alone it hits only the enemy front. A
  fifth board, which only a Tier-3 differential run produced, sharpened
  it further: with the enemy front mid-faint beside it the splash
  reaches the body BEHIND that one, so the finder steps over a dying
  body exactly like every other finder here.
- **The percentage is floored, and it is the firer's own attack.** The
  multiplier lives in the template as a `System.Decimal` inside a
  `Calculator`, which the dump cannot read. Fired across odd attacks at
  all three levels, Badger and Dodo agree on one expression: 7 attack
  deals 3 at level 1 and 10 at level 3.
- **A lethal hit does not cancel the hurt trigger.** This file used to
  say "survival is the whole gate", which fit Peacock and nothing else.
  A Camel taken to exactly 0 still buffs the friend behind it; a Peacock
  taken to 0 gains nothing. The difference is that a mid-faint body is
  not a legal TARGET and Peacock targets itself - one rule, not two.
- **Rabbit's target is the EATER.** `TargetsTriggerTarget` names whoever
  the food was played on, which is the Rabbit only when the food was
  aimed at the Rabbit. And its cap of three is per TURN: the fourth and
  fifth food play of a turn carry no bonus and the count resets at the
  boundary.
- **A granted PERK counts as a food played on a friendly.** Ox gaining
  Melon wakes a Rabbit on the same team, which then adds its health to
  the Ox. A plain buff does not - a Camel's and an Otter's woke nothing.
- **Salad Bowl takes no aim.** A `PlaySpell` that names a target is
  dropped by the resolver outright: no gold spent, the food not even
  consumed. An Apple is the mirror image. sap2 therefore offers a
  board-wide food on target 0 only, which stands for "played on the
  board" rather than on the pet in slot 0.
- **Melon blocks 20 once; Garlic takes 2 off forever.** 1, 5 and 20
  damage all land as 0 through a Melon and the perk is gone afterwards
  whatever the amount was. Garlic's floor is 2, not 1: 3 damage lands as
  2, and 2 damage lands as 2.
- **Two summons onto one cell push, and which way is measured.** Sheep's
  Rams both aim at the cell it vacated; the run behind them slides one
  further back when there is room, and when there is not, the run in
  FRONT slides one further forward instead. Six shop layouts pin it, and
  the battle line now uses the same rule - the previous "no room behind"
  fallback was marked unmeasured in the code and was wrong.

**Three rules landed that Tier 3 did not introduce but exposed.** Each
was reachable before and simply never driven, and each is now measured:
damage eats the TEMPORARY health before the permanent half (a Muffin'd
pet at perm 1 / temp 3 takes a 2-damage splash as perm 1 / temp 1); a
Pilled pet is mid-faint for the whole of its own faint, so its own
splash cannot pick it as a target; and Dolphin's lowest-health finder
breaks a TIE at random rather than by position (28/32 over 60 seeds).

**What is still capped.** `SAP2_ROSTER_TIER = 3`. Behind it is only
tiers 4-6, which are not written: a turn-7 shop draws from 30 species
where the real game draws from 40. Nothing inside a shipped tier is
deferred any more - Tier 2's one hole, Spider's summon, closed here.
Two Tier-3 pets reach forward out of the roster and are complete anyway:
Ox grants the Melon perk, whose food form is Tier 6, and Sheep's Ram
token belongs to no tier at all.

**Verified**: 84 env tests; `audit_roster.py --tier 3` with zero WRONG
and zero MISSING rows for tiers 1-3; 26/26 scripted shop checks; 200
fuzz episodes at turn 1 and 120 at turn 5 with no divergence;
`difftest_match.py` with no divergence; and 300/300 exact surviving
line-ups at Tier 1, Tier 2 and Tier 3, 300/300 deterministic boards and
200/200 holed boards at Tier 3 - `difftest.py` grew a `--tier3` flag and
its species map grew the ten new pets for exactly this.

## Pack scope: Turtle only, and the ladder is not

Measured via `policy-clash-re-tools`' `sap/pack_probe.py`, driving the
build's own `PackConstants`, `PackExtensions` and `GenerateBoard`.

**A pack is a table swap, not a rules change.** No `*Constants` class in
`SpacewoodCore2` keys anything on `Pack` - the only nine methods that take
one either build the tables or are `PackConstants`' own accessors - and ten
playable packs generated through the build's own `GenerateBoard` produce
boards identical in every scalar field: 5 lives, 10 trophies, 10 gold a
turn, the `[3,5,7,9,11]` tier schedule, 5/2 shop capacities, roll price 1.
The only column that moves is the roll pool. So `sap2-v1` being Pack1-only
is not hiding a constant, and a second pack would be new table rows and
nothing else. (One pack-scoped flag does exist - `PackTemplate.CarryGold`,
which would change gold carry-over - and it is set on exactly one pack,
Pack7, which is unreleased.)

**Pack1 is not a disjoint slice of the roster.** Four of its 60 species
(Duck, Beaver, Dragon, Boar) and seven of its 18 foods (Apple, Pill,
Canned Food, Pear, Chocolate, Steak, Melon) belong to other packs as well,
and a shared item is the *same row* in each - tier, price and base stats
are scalar fields on the template. The tables here are therefore correct
as a membership query. The summoned tokens belong to no pack at all (148
minion rows and 56 spell rows carry an empty pack set), so Cricket's
token, the Bee and the Dirty Rat are shared by every pack.

**The real ladder is cross-pack, and this env cannot express that.**
`PackExtensions.GetPossibleOpponents(Pack1)` is a client-side table and it
returns six packs - Pack1 through Pack5 and Danger - so a Turtle team
really does meet teams built from other pools. The predicate keeps a pack
that is released, playable, not custom-only and not "special"; the four
deck packs (Custom, Challenge, Plus, Wacky) each return only themselves,
i.e. forced mirror. The client is built for cross-pack pairings all the way
down: `BoardModel` carries both `Pack` and `OpponentPack`, `BattleModel`
holds two whole boards each with its own pack, and `UserVersusOpponent`,
`VersusPlayerModel` and `PlaybackResultPlayer` all carry one.

`sap2-v1` is a symmetric two-seat match in which both seats roll the same
pool, so a cross-pack pairing is not representable here. That is the same
deliberate scope difference as matchmaking itself (the real thing queues
you against asynchronous ghost teams through a server this build does not
contain), and it is recorded rather than modelled. **Unverified and not
answerable from the shipped client:** which endpoint consumes
`GetPossibleOpponents`, and how the ghost-board pool is sampled -
`QueueArenaRequest` carries no pack at all (the pack is account state, set
by `ChangePackRequest`), so the sampling lives entirely server-side.

## Appendix: roster rollout plan

1. **Tier 1 — done.** Match engine + existing 10 pets/3 foods, verified
   against the shipped build (18 tests, `envs/tests/test_sap2.py`, plus
   policy-clash-re-tools' differential suites).
2. **Tier 2 — done**, see "Tier 2 roster" above. Snail, Crab, Swan, Rat,
   Hedgehog, Peacock, Flamingo, Worm, Kangaroo, Spider, plus Meat Bone/
   Muffin/Sleeping Pill and Worm's Apple-Discount/Apple2/Apple3. Spider's
   own battle-phase ability is an explicit deferred no-op,
   not shipped wrong. Introduced `Attack`, `Hurt`, `StartTurn` and
   `EndTurn`-conditional, none of which `sap-v1`'s taxonomy had.
3. **Tier 3 — done**, see "Tier 3 roster" above. Badger, Camel, Dodo,
   Dog, Dolphin, Elephant, Giraffe, Ox, Rabbit, Sheep + Birthday Cake,
   Garlic and Salad Bowl, and Spider's summon with them. **This build's
   Turtle Pack Tier 3 DOES include Birthday Cake** - contradicting this
   doc's own earlier note (now wrong, left crossed out rather than
   silently deleted) that it was scraped as absent; that scrape was
   stale or wiki-sourced rather than measured, and the food pool is
   1/8 at tier 3, so omitting it would have made every tier-3 food roll
   wrong. ~~Cake is confirmed not currently in Turtle Pack per
   `data/turtle_pack`'s own scrape notes — Salad Bowl and Garlic only.~~
   Introduced `AfterAttack` (Elephant), `FriendAheadFainted` (Ox) and
   `EatFood` (Rabbit) as triggers, cross-team adjacency
   (`ADJACENT_ANY_TEAM`, Badger) and an ordered enemy finder
   (`LOWEST_HEALTH_ENEMY`, Dolphin) as selectors, and three perks
   beyond Honey/Meat Bone: Garlic, Melon (which Ox grants a tier early)
   and Birthday Cake. The earlier guess in this appendix that Badger
   would need a new "damage arbitrary positions" primitive was wrong in
   an interesting way - the faint cascade `main` already carries did the
   whole job, and what Badger actually needed was for "adjacent" to be
   read off the merged grid rather than off one team's line.
   `EatFood` is named for the build's `FoodEatenByFriendly`; Seal's
   tier-5 `FoodEatenByThis` is a DIFFERENT enum on the same trigger
   class and needs its own id when that tier lands.
4. **Tier 4** (Skunk, Hippo, Bison, Blowfish, Turtle, Squirrel, Penguin,
   Deer, Whale, Parrot + Pear, Canned Food, Bread): introduces `KnockOut`
   (Hippo) and permanent shop-wide buffs (Canned Food).
5. **Tier 5** (Scorpion, Crocodile, Rhino, Monkey, Armadillo, Cow, Seal,
   Rooster, Shark, Turkey + Sushi, Chocolate, Chili): introduces
   `FriendFainted` (Shark) and Chocolate's direct-XP-no-merge leveling.
6. **Tier 6** (Leopard, Boar, Tiger, Wolverine, Gorilla, Dragon, Mammoth,
   Cat, Snake, Fly + Pizza, Mushroom, Melon, Steak): introduces
   `BeforeAttack` (Boar; `AfterAttack` already landed with Tier 3's
   Elephant) and `Fly`'s bounded-trigger-count ability.

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
