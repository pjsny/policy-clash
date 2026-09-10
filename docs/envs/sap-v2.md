# sap-v2

Status: **implemented and tested.** `sap-v1` is one round: shop phase, one
battle, done. This is the actual full game — the multi-round Arena match,
life totals, tier progression, growing shop, freeze — built as a genuinely
new version per the project's own convention ("environments are versioned
and never mutated... a rules change is `cartpole-duel-v2`, not an edit to
`v1`"), not an edit to `sap-v1`. `sap-v1` stays exactly as it is, still
registered, still passing its own 19 tests (72 total across every env now).

Implementation: `envs/csrc/sap2.h` / `sap2_binding.c` /
`envs/policyclash_envs/sap2.py`, registered as `sap2-v1`. 13 tests in
`envs/tests/test_sap2.py`, plus a 500-match random-legal-play fuzz run at
the Python level (zero crashes, zero illegal forfeits, natural
conclusions well inside the round cap — max turn seen was 16 of the
30-round `MAX_ROUNDS` bound) and a throughput measurement (~99,000
ticks/sec through the Python adapter — see "Measured" below).

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

Source for every real-game fact below: `superautopets.wiki.gg`'s "The
Basics" and "Shop" pages, fetched directly this session — not carried over
from memory. One number below (the exact shop pet/food slot count at each
turn) could not be pinned to a specific wiki paragraph in this session's
search and is flagged as such rather than presented as verified.

## What actually changes from sap-v1

| | sap-v1 | sap-v2 |
|---|---|---|
| Episode = | one shop phase + one battle | a full match: many rounds of shop+battle, until someone wins or is eliminated |
| Team persistence | n/a (one round) | persists round to round; only temporary battle buffs clear |
| Shop | fixed: 3 pet slots, 1 food slot, Tier 1 only | grows with turn number; tier gate expands turn 1/3/5/7/9/11 |
| Gold | 10 once | 10 **every** round (does not carry over) |
| Freeze | not modeled (no next turn to persist into) | real mechanic: frozen shop items persist into the next roll, in the leftmost slot(s) |
| Win condition | one battle's Outcome | first to 10 trophies, or opponent's 5 lives hit 0 |
| Roster | Tier 1 (10 pets, 2 foods) | Tier 1 first; Tiers 2–6 are follow-on phases |

## Match rules (wiki-confirmed)

- **Lives and trophies.** Both seats start at 5 lives, 0 trophies (Normal
  Arena mode's numbers — the mode this spec targets). Losing a battle
  costs the loser exactly 1 life, flat — not a formula based on surviving
  pets, tiers, or levels. Winning gains the winner exactly 1 trophy. A
  draw changes neither. Reaching 10 trophies wins the match outright;
  reaching 0 lives loses it outright. If both would resolve on the same
  round (winner's 10th trophy and loser's last life, same battle), it's
  simply a win for whoever has 10 trophies — no ambiguity, since only one
  side can lose a life per round and it's always the side that didn't
  just gain a trophy.
- **Turn-3 life-back.** "Due to the limited options and high randomization
  in turns 1 and 2, players will gain one life at the start of turn 3 if
  they have lost any so far." A one-time correction, not a repeating
  rule — check once, at the start of turn 3 specifically.
- **Tier schedule**, confirmed exactly matching `SAP_clone.md`'s existing
  claim: tier unlocks turn 1 (T1), 3 (T2), 5 (T3), 7 (T4), 9 (T5), 11+
  (T6, stays there). Once unlocked, all lower tiers remain in the pool.
- **Shop growth.** Turn number also grows the shop's own slot count, not
  just which tiers can appear in it — **the exact slot-count-by-turn table
  could not be pinned to a specific wiki paragraph this session**; the
  widely-documented numbers (3 pet slots/1 food through turn 2, 4 pet/1
  food turns 3–4, 5 pet/2 food turn 5 on) are a reasonable default but
  need confirming against the wiki (or a fresh game capture) before being
  treated as load-bearing the way the tier schedule above is.
- **Freeze.** A shop pet or food can be frozen; frozen items persist into
  the *next* roll (whether that's a paid re-roll this same turn or the
  free roll at the start of next turn) and occupy the shop's leftmost
  slot(s), reducing how many fresh offers that roll produces by however
  many are frozen. Unfreezing or buying a frozen item releases its slot.
- **Leveling up grants early tier access.** Merging a pet from level 1 to
  level 2 (not level 2 to level 3) offers a choice between two pets from
  the *next* tier up — a real sub-decision this spec's action space has
  to account for, not something `sap-v1` needed since it never levels
  anything past what a single round allows in practice.
- **Combine formula unchanged from `sap-v1`.** The Basics page's loose
  phrasing ("a level-up results in +1 attack and +1 health") reads as
  describing the common case — two freshly-bought, stat-identical
  copies — where `max(a,b)+1` and flat `+1` produce the same number by
  construction (`max(x,x)+1 = x+1`). `sap-v1`'s already-implemented,
  already-tested `max(a,b)+1` rule (from `SAP_clone.md` §3's more precise
  original phrasing) is kept, not replaced, since it's the one that's
  actually been verified and it subsumes the common case correctly.
- **Opponent matching, simplified for a 2-seat env.** Real Arena mode
  matches you against a stranger's team from an async pool. This env only
  ever has two seats, so there is no pool — each round, seat 0's
  current team battles seat 1's current team directly. This is a
  simplification of *how an opponent is found*, not of the battle or
  match rules themselves, and it's arguably a better fit for
  `policy-clash`'s actual purpose (head-to-head, not vs.-a-stranger) than
  the real game's own matchmaking would be.

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

`sap-v1`'s 35 actions extend to **49**, sized to the largest shop the
default slot-growth table reaches (5 pet slots, 2 food slots):

| indices | action |
|---|---|
| 0 | `END_TURN` |
| 1–5 | `BUY_PET(shop slot)` |
| 6–10 | `SELL(team slot)` |
| 11–20 | `COMBINE(team pair)` |
| 21 | `REROLL` |
| 22–31 | `REPOSITION(team pair)` |
| 32–41 | `BUY_FOOD(food_slot·5 + team_target)` |
| 42–46 | `FREEZE_PET(shop slot)`, toggles |
| 47–48 | `FREEZE_FOOD(food slot)`, toggles |

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
existing per-slot encoding by 1 float each). No opponent lives/trophies —
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
(174-float observation and 49-action mask vs. 136/35).

## Appendix: roster rollout plan

1. **Tier 1 — done.** Match engine + existing 10 pets/2 foods, fully
   tested (13 tests, `envs/tests/test_sap2.py`) — the actual deliverable
   of this pass.
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

Each phase: port abilities from `data/turtle_pack/pets.json`, extend the
trigger taxonomy only as far as that tier's roster actually needs (same
rule `sap-v1` followed — it implemented only `FAINT`/`SELL`/`BUY`/
`LEVELUP`/`FRIEND_SUMMONED`/`START_OF_BATTLE`, the subset Tier 1 uses, not
the full taxonomy speculatively), write tests before calling it done, and
benchmark. No tier's implementation blocks reporting the previous one as
finished.

## See also

- [`sap-v1.md`](sap-v1.md) — the one-round env this extends. Unmodified.
- [colin-cannell/SAP_Clone](https://github.com/colin-cannell/SAP_Clone) — the
  companion project this env was designed alongside: `SAP_clone.md` §2
  (turn structure) and the now-resolved multi-round-meta open question,
  and `data/turtle_pack/pets.json` — the full 61-pet, 17-food dataset
  every later tier phase in the appendix above ports from.
