from __future__ import annotations

import numpy as np
import pytest

from policyclash_envs import Outcome, Termination, make
from policyclash_envs.base import Forkable
from policyclash_envs.sap2 import (
    ACT_BUY_FOOD_BASE,
    ACT_BUY_PET_BASE,
    ACT_COMBINE_BASE,
    ACT_FREEZE_FOOD_BASE,
    ACT_FREEZE_PET_BASE,
    ACT_REPOSITION_BASE,
    ACT_REROLL,
    ACT_SELL_BASE,
    FOOD_SLOTS,
    MAX_LEVEL,
    MAX_ROUNDS,
    MAX_SHOP_PETS,
    MAX_STATS,
    MAX_TICKS,
    NUM_ACTIONS,
    NUM_PERKS,
    OBS_FLOATS,
    PERK_HONEY,
    PERK_NONE,
    SHOP_FOOD_SLOT_FLOATS,
    SHOP_PET_SLOT_FLOATS,
    STARTING_GOLD,
    STARTING_LIVES,
    TEAM_SLOT_FLOATS,
    TEAM_SLOTS,
    TROPHIES_TO_WIN,
)

HORSE_SPECIES = 6         # sap2.h's species ids, Tier-1 Pack1 roster
PIGEON_SPECIES = 10
HONEY_FOOD = 2            # SAP2_HONEY
BREAD_CRUMBS_FOOD = 6     # SAP2_BREAD_CRUMBS - Tier 2 foods took 3/4/5
# Tier 3 (sap2.h's enum): pets 21-30, the Ram token 34, foods 9-11.
BADGER_SPECIES = 21
CAMEL_SPECIES = 22
DODO_SPECIES = 23
DOG_SPECIES = 24
DOLPHIN_SPECIES = 25
ELEPHANT_SPECIES = 26
GIRAFFE_SPECIES = 27
OX_SPECIES = 28
RABBIT_SPECIES = 29
SHEEP_SPECIES = 30
RAM_SPECIES = 34
BIRTHDAY_CAKE_FOOD = 9
GARLIC_FOOD = 10
SALAD_BOWL_FOOD = 11
TIER3_PETS = frozenset(range(BADGER_SPECIES, SHEEP_SPECIES + 1))

ENV_ID = "sap2-v1"

# Every offset below comes from the env, not from a copy of the layout:
# blocks have widened twice while matching the shipped game, and a stale
# constant here shows up as a nonsense test failure rather than as a
# layout error.
END_TURN = 0
BUY_PET_BASE = ACT_BUY_PET_BASE
SELL_BASE = ACT_SELL_BASE
COMBINE_BASE = ACT_COMBINE_BASE
REROLL = ACT_REROLL
REPOSITION_BASE = ACT_REPOSITION_BASE
BUY_FOOD_BASE = ACT_BUY_FOOD_BASE
FREEZE_PET_BASE = ACT_FREEZE_PET_BASE
FREEZE_FOOD_BASE = ACT_FREEZE_FOOD_BASE


def slot_of(f: np.ndarray, species: int) -> int:
    """The shop slot currently holding `species`.

    Buying compacts the shop (measured - the real shop is a List<T>), so a
    slot index read before a buy does not survive it. Tests that buy twice
    re-resolve the second slot through this.
    """
    for s in range(MAX_SHOP_PETS):
        if shop_pet_species(f, s) == species:
            return s
    raise AssertionError(f"species {species} is not in the shop")


def buy(shop_slot: int, position: int) -> int:
    """The real game's buy carries the position you dropped the pet on."""
    return BUY_PET_BASE + shop_slot * TEAM_SLOTS + position


def buy_food(food_slot: int, target: int) -> int:
    return BUY_FOOD_BASE + food_slot * TEAM_SLOTS + target


TEAM_BASE = 4  # after gold(1) lives(1) trophies(1) turn(1)
# 13 species one-hot, attack, health, 3 level one-hot, exp, perk one-hot.
TEAM_SLOT_WIDTH = TEAM_SLOT_FLOATS
SHOP_PET_BASE = TEAM_BASE + TEAM_SLOTS * TEAM_SLOT_WIDTH
SHOP_PET_SLOT_WIDTH = SHOP_PET_SLOT_FLOATS
SHOP_FOOD_BASE = SHOP_PET_BASE + MAX_SHOP_PETS * SHOP_PET_SLOT_WIDTH
SHOP_FOOD_SLOT_WIDTH = SHOP_FOOD_SLOT_FLOATS

IGNORED = NUM_ACTIONS + 99


@pytest.fixture
def env():
    return make(ENV_ID)


# Every field offset below is derived from the env's own widths, not
# typed in: the species one-hot has grown twice while matching the
# shipped roster (10 pets -> 20 plus tokens) and the food block gained a
# price, and a hardcoded 11 or 13 here shows up as a nonsense failure
# somewhere unrelated.
NUM_SPECIES = TEAM_SLOT_FLOATS - (2 + MAX_LEVEL + 1 + NUM_PERKS + 2)  # team one-hot
NUM_SHOP_SPECIES_ONEHOT = SHOP_PET_SLOT_FLOATS - 2                # shop one-hot
NUM_FOODS_ONEHOT = SHOP_FOOD_SLOT_FLOATS - 2                      # food one-hot


def team_species(f: np.ndarray, slot: int) -> int:
    base = TEAM_BASE + slot * TEAM_SLOT_WIDTH
    return int(np.argmax(f[base : base + NUM_SPECIES]))


def team_attack(f: np.ndarray, slot: int) -> float:
    return f[TEAM_BASE + slot * TEAM_SLOT_WIDTH + NUM_SPECIES]


def team_health(f: np.ndarray, slot: int) -> float:
    return f[TEAM_BASE + slot * TEAM_SLOT_WIDTH + NUM_SPECIES + 1]


def team_level(f: np.ndarray, slot: int) -> int:
    base = TEAM_BASE + slot * TEAM_SLOT_WIDTH + NUM_SPECIES + 2
    return int(np.argmax(f[base : base + MAX_LEVEL])) + 1


def team_exp(f: np.ndarray, slot: int) -> int:
    return int(f[TEAM_BASE + slot * TEAM_SLOT_WIDTH + NUM_SPECIES + 2 + MAX_LEVEL])


def team_perk(f: np.ndarray, slot: int) -> int:
    base = TEAM_BASE + slot * TEAM_SLOT_WIDTH + NUM_SPECIES + 3 + MAX_LEVEL
    return int(np.argmax(f[base : base + NUM_PERKS]))


def shop_pet_species(f: np.ndarray, slot: int) -> int:
    base = SHOP_PET_BASE + slot * SHOP_PET_SLOT_WIDTH
    return int(np.argmax(f[base : base + NUM_SHOP_SPECIES_ONEHOT]))


def shop_pet_hp_bonus(f: np.ndarray, slot: int) -> float:
    return f[SHOP_PET_BASE + slot * SHOP_PET_SLOT_WIDTH + NUM_SHOP_SPECIES_ONEHOT]


def shop_pet_frozen(f: np.ndarray, slot: int) -> bool:
    base = SHOP_PET_BASE + slot * SHOP_PET_SLOT_WIDTH
    return bool(f[base + NUM_SHOP_SPECIES_ONEHOT + 1])


def shop_food_species(f: np.ndarray, slot: int) -> int:
    base = SHOP_FOOD_BASE + slot * SHOP_FOOD_SLOT_WIDTH
    return int(np.argmax(f[base : base + NUM_FOODS_ONEHOT]))


def shop_food_frozen(f: np.ndarray, slot: int) -> bool:
    base = SHOP_FOOD_BASE + slot * SHOP_FOOD_SLOT_WIDTH
    return bool(f[base + NUM_FOODS_ONEHOT])


def shop_food_price(f: np.ndarray, slot: int) -> float:
    base = SHOP_FOOD_BASE + slot * SHOP_FOOD_SLOT_WIDTH
    return f[base + NUM_FOODS_ONEHOT + 1]


def gold(f: np.ndarray) -> float:
    return f[0]


def lives(f: np.ndarray) -> float:
    return f[1]


def trophies(f: np.ndarray) -> float:
    return f[2]


def turn(f: np.ndarray) -> float:
    return f[3]


def end_both(env, result):
    """Play pure end-turns until the whole MATCH ends. For "just get
    through one round" use end_one_round instead - this one does not stop
    at a round boundary, since submitting END_TURN every tick for two
    idle seats has nothing to make it stop there."""
    while not result.done:
        a0 = END_TURN if result.observations[0] is not None else IGNORED
        a1 = END_TURN if result.observations[1] is not None else IGNORED
        result = env.step(a0, a1)
    return result


def end_one_round(env, result):
    """Pure end-turns until either the match ends or the round boundary is
    crossed (env.turn changes) - whichever comes first."""
    prev_turn = env.turn
    while not result.done and env.turn == prev_turn:
        a0 = END_TURN if result.observations[0] is not None else IGNORED
        a1 = END_TURN if result.observations[1] is not None else IGNORED
        result = env.step(a0, a1)
    return result


# --------------------------------------------------------------------------


def test_registered_with_expected_shape():
    spec = make(ENV_ID).spec
    assert spec.qualified_id == ENV_ID
    assert spec.obs_shape == (OBS_FLOATS,)
    assert spec.num_actions == NUM_ACTIONS
    assert spec.actors_per_tick == 2
    assert spec.stochastic_dynamics
    assert MAX_TICKS == MAX_ROUNDS * 20


def test_reset_state(env):
    result = env.reset(seed=0)
    assert not result.done
    assert env.turn == 1
    for obs in result.observations:
        assert obs.features.shape == (OBS_FLOATS,)
        assert gold(obs.features) == STARTING_GOLD
        assert lives(obs.features) == STARTING_LIVES
        assert trophies(obs.features) == 0
        assert turn(obs.features) == 1
        # turn 1: 3 pet slots x 5 team positions (an empty board takes a pet
        # anywhere, as the real game does) + end_turn + reroll + 3 freeze_pet
        # + 1 freeze_food = 21
        assert obs.legal_actions.sum() == 21
        assert not obs.legal_actions[FREEZE_PET_BASE + 3]  # slot 3 doesn't exist yet
        assert not obs.legal_actions[FREEZE_FOOD_BASE + 1]  # slot 1 doesn't exist yet


def test_a_bought_pet_goes_where_it_is_dropped(env):
    """The real game's buy carries a destination: `BoardEvents.PlayMinion`
    takes the point you dropped the pet on, and an empty board accepts one
    anywhere - holes included, since the board is never compacted."""
    result = env.reset(seed=0)
    result = env.step(buy(0, 3), END_TURN)
    f = result.observations[0].features
    assert team_species(f, 3) != 0
    assert all(team_species(f, s) == 0 for s in (0, 1, 2, 4))


def test_dropping_a_pet_on_an_occupied_slot_inserts_and_shifts(env):
    """Measured: dropping a different species onto an occupied position
    inserts it there and slides the neighbours FORWARD - toward the front
    of the line - and only slides them back when the front is full. It
    does not swap and it does not fail.

    The direction was wrong here until a differential that carries a whole
    build phase into a battle caught it (policy-clash-re-tools'
    `sap/difftest_match.py`): insert is the only build-phase rule with a
    direction, and the harness's shop drivers had been comparing sap2
    slot i against the real grid's cell i, which is the mirror of the
    verified battle mapping - the real grid fronts at its HIGHEST cell,
    sap2 at slot 0. With both sides mirrored the old assertion passed."""
    for seed in range(200):
        probe = make(ENV_ID)
        result = probe.reset(seed=seed)
        f = result.observations[0].features
        species = [shop_pet_species(f, s) for s in range(3)]
        if species[0] == species[1]:
            continue  # a same-species drop is a stack, not an insert
        result = probe.step(buy(0, 2), END_TURN)
        first = team_species(result.observations[0].features, 2)
        seat1 = IGNORED if result.observations[1] is None else END_TURN
        # Buying compacts the shop, so the pet that was in slot 1 is now
        # in slot 0 - measured, the real shop is a List<T>.
        assert shop_pet_species(result.observations[0].features, 0) == species[1]
        result = probe.step(buy(0, 2), seat1)  # different species, same position
        f = result.observations[0].features
        assert team_species(f, 1) == first, "the sitting pet slid forward"
        assert team_species(f, 2) == species[1]
        assert team_species(f, 3) == 0, "nothing slid back - the front had room"
        return
    pytest.fail("no seed in 200 gave two different species in the first two shop slots")


def test_buying_a_copy_onto_its_twin_stacks_in_one_action(env):
    """The shop stack is ONE action in the real game (PlayType.Stack), not
    buy-then-merge: exp goes up by one and the stats become the higher of
    each, +1."""
    for seed in range(200):
        probe = make(ENV_ID)
        result = probe.reset(seed=seed)
        f = result.observations[0].features
        species = [shop_pet_species(f, s) for s in range(3)]
        pair = next(
            ((i, j) for i in range(3) for j in range(i + 1, 3) if species[i] == species[j]),
            None,
        )
        if pair is None:
            continue
        i, j = pair
        result = probe.step(buy(i, 0), END_TURN)
        seat1 = IGNORED if result.observations[1] is None else END_TURN
        before = result.observations[0].features
        assert team_level(before, 0) == 1
        # the first buy compacted the shop, so j moved down one slot
        result = probe.step(buy(j - 1 if j > i else j, 0), seat1)  # onto its own twin
        f = result.observations[0].features
        assert team_species(f, 0) == species[i]
        assert all(team_species(f, s) == 0 for s in range(1, 5)), "one pet, not two"
        assert team_attack(f, 0) == team_attack(before, 0) + 1
        assert team_health(f, 0) == team_health(before, 0) + 1
        return
    pytest.fail("no seed in 200 offered a duplicate species in the turn-1 shop")


def test_shop_grows_with_tier_not_turn(env):
    # Measured from the shipped build (policy-clash-re-tools' sap/shop.py): the shop
    # grows on TIER, and tiers unlock on turns 3/5/7/9/11, so the pet slots
    # go 3 (turns 1-4) -> 4 (turns 5-8) -> 5 (turns 9+) and the food slots
    # go 1 -> 2 at turn 5. The old 4-slots-on-turn-3 schedule was folklore.
    result = env.reset(seed=0)
    for expected_turn in (2, 3, 4):
        result = end_one_round(env, result)
        assert not result.done
        assert env.turn == expected_turn
        assert result.observations[0].legal_actions[buy(2, 0)]
        assert not result.observations[0].legal_actions[buy(3, 0)]
        assert not result.observations[0].legal_actions[FREEZE_FOOD_BASE + 1]

    result = end_one_round(env, result)  # -> turn 5, tier 3: 4 pet / 2 food
    assert env.turn == 5
    assert result.observations[0].legal_actions[buy(3, 0)]
    assert not result.observations[0].legal_actions[buy(4, 0)]
    assert result.observations[0].legal_actions[FREEZE_FOOD_BASE + 1]

    for expected_turn in (6, 7, 8, 9):
        result = end_one_round(env, result)
        assert env.turn == expected_turn
    assert env.turn == 9  # tier 5: the shop reaches its full 5 pet slots
    assert result.observations[0].legal_actions[buy(4, 0)]


def test_gold_resets_every_round_does_not_carry(env):
    result = env.reset(seed=0)
    result = env.step(REROLL, END_TURN)  # seat0 spends 1g -> 9g
    assert gold(result.observations[0].features) == STARTING_GOLD - 1
    result = end_one_round(env, result)  # round resolves, next round starts
    assert gold(result.observations[0].features) == STARTING_GOLD  # not 9, not accumulated


def test_levelling_follows_the_shipped_exp_table(env):
    """Measured from the shipped build (policy-clash-re-tools' sap/difftest_shop.py):
    a copy is worth +1 exp and the higher of each stat +1, and the level
    thresholds are exp 0/2/5 - so an Ant walks 2/2 L1, 3/3 L1, 4/4 L2 and
    only reaches L3 on the sixth copy. sap2 used to level up on the second
    copy, which made levels roughly three times too cheap."""
    result = env.reset(seed=0)
    # Find a seed whose turn-1 shop offers the same species twice, so one
    # round is enough to observe a stack.
    for seed in range(200):
        probe = make(ENV_ID)
        result = probe.reset(seed=seed)
        f = result.observations[0].features
        species = [shop_pet_species(f, s) for s in range(3)]
        pair = next(
            ((i, j) for i in range(3) for j in range(i + 1, 3) if species[i] == species[j]),
            None,
        )
        if pair is None:
            continue
        i, j = pair
        result = probe.step(buy(i, 0), END_TURN)
        f = result.observations[0].features
        result = probe.step(
            buy(slot_of(f, species[j]), 1),
            IGNORED if result.observations[1] is None else END_TURN,
        )
        assert result.observations[0].legal_actions[COMBINE_BASE + 0]  # slots 0,1 stack
        result = probe.step(COMBINE_BASE + 0, IGNORED if result.observations[1] is None else END_TURN)
        f = result.observations[0].features
        assert team_level(f, 0) == 1, "one stack is exp 1, still level 1"
        assert team_exp(f, 0) == 1, "the exp counter is observable, not just the level"
        return
    pytest.fail("no seed in 200 offered a duplicate species in the turn-1 shop")


def test_horses_buff_counts_in_this_rounds_battle_and_expires_next_turn(env):
    """Measured from the shipped build via policy-clash-re-tools: Horse's
    ability effect carries Duration = Temp(1) - the only one in this
    roster, Ant/Otter/Beaver/Duck/Fish are all Perm(0) - and the deadline
    Temp(1) names is the start of the NEXT TURN, not the end of battle.
    A Horse plus a freshly bought Ant showed Ant 3/2 on turn 1, including
    that turn's battle, and 2/2 from turn 2 on.

    Both halves are checked. The battle half compares two plays that
    differ in nothing but the buff: buying the Horse first buffs the pet
    dropped beside it, buying it second does not, and both plays end the
    shop phase with the same two bodies in the same two positions. The
    buffed pet is picked to be neither Otter nor Fish - the only pets
    whose on-play/level-up draw from the seat RNG - so the two plays also
    consume the RNG identically. A buff that did not reach the battle
    would have to give both plays the same round result.
    """
    for seed in range(200):
        f = make(ENV_ID).reset(seed=seed).observations[0].features
        shop = [shop_pet_species(f, s) for s in range(3)]
        horse = next((s for s in range(3) if shop[s] == HORSE_SPECIES), None)
        # Not Otter (8) and not Fish (5): those two draw from the seat RNG
        # when they are played, which would make the two plays below
        # differ in more than the buff.
        other = next((s for s in range(3) if shop[s] not in (HORSE_SPECIES, 5, 8)), None)
        if horse is None or other is None:
            continue

        plays = {}
        for name, first, second in (
            ("buffed", (horse, 1), (other, 0)),  # Horse first: the next pet is summoned beside it
            ("plain", (other, 0), (horse, 1)),   # Horse last: nobody is summoned after it
        ):
            probe = make(ENV_ID)
            result = probe.reset(seed=seed)
            # Seat 1 buys the same two pets in both plays, so seat 0's
            # ordering is the only thing that differs.
            result = probe.step(buy(*first), buy(0, 0))
            f0 = result.observations[0].features
            # The first buy compacted both shops, so the second slot is
            # re-resolved by species rather than reused.
            seat1 = IGNORED if result.observations[1] is None else buy(0, 1)
            result = probe.step(buy(slot_of(f0, shop[second[0]]), second[1]), seat1)
            plays[name] = (result.observations[0].features, end_one_round(probe, result))

        buffed_obs, buffed_result = plays["buffed"]
        plain_obs, plain_result = plays["plain"]
        assert team_species(buffed_obs, 0) == team_species(plain_obs, 0) == shop[other]
        assert team_species(buffed_obs, 1) == team_species(plain_obs, 1) == HORSE_SPECIES
        assert team_attack(buffed_obs, 0) == team_attack(plain_obs, 0) + 1  # Horse is level 1
        assert team_health(buffed_obs, 0) == team_health(plain_obs, 0)  # attack only

        after = buffed_result.observations[0].features
        assert team_species(after, 0) == shop[other], "the pet is still there"
        assert team_attack(after, 0) == team_attack(plain_obs, 0), "the buff expired"

        plain_after = plain_result.observations[0].features
        if (trophies(after), lives(after)) == (trophies(plain_after), lives(plain_after)):
            continue  # this seed's battle was not decided by one point of attack
        return
    pytest.fail("no seed in 200 gave a Horse plus a battle the buff decided")


def test_a_stack_keeps_the_honey_perk_from_the_absorbed_copy(env):
    """Honey changes no stat - it leaves a perk on the pet, which summons
    a 1/1 Bee when that pet faints - and the perk survives a merge from
    either copy: feed Honey to one of two twins, drag it onto the other,
    and the survivor is the one carrying the Bee. The observation shows
    the perk as a one-hot, so this reads it back from what the agent
    actually sees."""
    for seed in range(400):
        probe = make(ENV_ID)
        result = probe.reset(seed=seed)
        f = result.observations[0].features
        if shop_food_species(f, 0) != HONEY_FOOD:
            continue
        species = [shop_pet_species(f, s) for s in range(3)]
        pair = next(
            ((i, j) for i in range(3) for j in range(i + 1, 3) if species[i] == species[j]),
            None,
        )
        if pair is None:
            continue
        i, j = pair
        result = probe.step(buy(i, 0), END_TURN)  # 3g
        seat1 = IGNORED if result.observations[1] is None else END_TURN
        f = result.observations[0].features  # the buy compacted the shop
        result = probe.step(buy(slot_of(f, species[j]), 1), seat1)  # 6g
        seat1 = IGNORED if result.observations[1] is None else END_TURN
        result = probe.step(buy_food(0, 1), seat1)  # 9g, Honey onto the second copy
        f = result.observations[0].features
        assert team_perk(f, 0) == PERK_NONE
        assert team_perk(f, 1) == PERK_HONEY
        assert team_attack(f, 1) == team_attack(f, 0)  # Honey is not an Apple
        assert team_health(f, 1) == team_health(f, 0)

        result = probe.step(COMBINE_BASE + 0, seat1)  # pair (0,1): 1 is absorbed into 0
        f = result.observations[0].features
        assert team_species(f, 0) == species[i]
        assert team_species(f, 1) == 0, "one body, not two"
        assert team_exp(f, 0) == 1
        assert team_perk(f, 0) == PERK_HONEY, "the perk came with the absorbed copy"
        return
    pytest.fail("no seed in 400 offered a duplicate species and Honey in the same turn-1 shop")


def test_a_stack_keeps_a_temporary_buff_from_either_copy(env):
    """Measured against `IntegerStat.Permanent`/`.Temporary` in the shipped
    build: a merge stacks the permanent components (higher of each, +1) and
    takes the HIGHER of the two temporary components with no +1 - so the
    buff survives whichever copy carried it. sap2 used to keep only the
    survivor's, dropping Horse's buff when the absorbed copy was the buffed
    one. Here the absorbed copy is the buffed one: the Horse is bought
    last, so only the twin bought after it is buffed."""
    for seed in range(400):
        probe = make(ENV_ID)
        result = probe.reset(seed=seed)
        f = result.observations[0].features
        species = [shop_pet_species(f, s) for s in range(3)]
        horse = next((s for s in range(3) if species[s] == HORSE_SPECIES), None)
        pair = next(
            (
                (i, j)
                for i in range(3)
                for j in range(i + 1, 3)
                if species[i] == species[j] and species[i] != HORSE_SPECIES
            ),
            None,
        )
        if horse is None or pair is None:
            continue
        i, j = pair
        result = probe.step(buy(i, 0), END_TURN)  # the unbuffed twin
        seat1 = IGNORED if result.observations[1] is None else END_TURN
        f = result.observations[0].features  # each buy compacts the shop
        result = probe.step(buy(slot_of(f, HORSE_SPECIES), 4), seat1)
        seat1 = IGNORED if result.observations[1] is None else END_TURN
        f = result.observations[0].features
        result = probe.step(buy(slot_of(f, species[j]), 1), seat1)  # with the Horse present
        f = result.observations[0].features
        buffed = team_attack(f, 1)
        plain = team_attack(f, 0)
        assert buffed == plain + 1, "Horse buffed the pet bought after it"

        result = probe.step(COMBINE_BASE + 0, seat1)  # absorbs slot 1 into slot 0
        f = result.observations[0].features
        # permanent max(2,2)+1 = 3, plus the absorbed copy's temporary +1.
        assert team_attack(f, 0) == plain + 2
        # And it is still temporary: it goes away when the next turn starts.
        result = end_one_round(probe, result)
        if result.observations[0] is not None:
            assert team_attack(result.observations[0].features, 0) == plain + 1
        return
    pytest.fail("no seed in 400 offered a Horse and a duplicate pair in the turn-1 shop")


def test_pigeon_stocks_free_bread_crumbs_without_evicting_food(env):
    """Measured: selling a Pigeon prepends `level` free Bread Crumbs to the
    food shop and leaves the rolled food where it is (pushed right), which
    is why the food array is wider than the rolled capacity - a roll only
    ever fills 1 or 2 slots."""
    for seed in range(200):
        probe = make(ENV_ID)
        result = probe.reset(seed=seed)
        f = result.observations[0].features
        pigeon_slot = next(
            (s for s in range(3) if shop_pet_species(f, s) == PIGEON_SPECIES), None
        )
        if pigeon_slot is None:
            continue
        food_before = shop_food_species(f, 0)
        result = probe.step(buy(pigeon_slot, 0), END_TURN)
        seat1 = IGNORED if result.observations[1] is None else END_TURN
        result = probe.step(SELL_BASE + 0, seat1)
        f = result.observations[0].features
        assert shop_food_species(f, 0) == BREAD_CRUMBS_FOOD
        assert shop_food_species(f, 1) == food_before  # the rolled food survived
        assert result.observations[0].legal_actions[FREEZE_FOOD_BASE + 1]
        return
    pytest.fail("no seed in 200 offered a Pigeon in the turn-1 shop")


def test_pigeon_crumbs_are_unfrozen_and_a_roll_clears_them(env):
    """Measured: the crumbs a Pigeon stocks come in UNFROZEN, so the next
    roll clears them along with any other unfrozen stock past the rolled
    capacity. A reading that said otherwise on a turn>=2 board turned out
    to be the oracle sitting with BoardModel.TurnOver still set - see
    docs/envs/sap-v2.md."""
    for seed in range(200):
        probe = make(ENV_ID)
        result = probe.reset(seed=seed)
        f = result.observations[0].features
        pigeon = next((s for s in range(3) if shop_pet_species(f, s) == PIGEON_SPECIES), None)
        if pigeon is None:
            continue
        result = probe.step(buy(pigeon, 0), END_TURN)
        seat1 = IGNORED if result.observations[1] is None else END_TURN
        result = probe.step(SELL_BASE + 0, seat1)
        f = result.observations[0].features
        assert shop_food_species(f, 0) == BREAD_CRUMBS_FOOD
        assert not shop_food_frozen(f, 0), "a stocked crumb is not frozen"
        seat1 = IGNORED if result.observations[1] is None else END_TURN
        result = probe.step(REROLL, seat1)
        f = result.observations[0].features
        # Unfrozen, so the roll replaced it and cleared the stock past the
        # turn-1 capacity of one.
        assert shop_food_species(f, 0) != BREAD_CRUMBS_FOOD
        assert shop_food_species(f, 1) == 0
        return
    pytest.fail("no seed in 200 offered a Pigeon in the turn-1 shop")


def test_the_food_shop_is_wide_enough_for_its_worst_case(env):
    """The array is sized for the worst case the real game allows, because
    measured against the shipped build nothing is ever evicted and every
    slot stays buyable: the largest rolled capacity, plus a team of
    level-3 Pigeons' crumbs (frozen, so they survive the next roll), plus
    a team of Worms' Apples prepended the turn after."""
    from policyclash_envs.sap2 import MAX_LEVEL as _lvl

    assert FOOD_SLOTS == 2 + TEAM_SLOTS * _lvl + TEAM_SLOTS
    # And the action space reaches all of them.
    assert ACT_FREEZE_PET_BASE == ACT_BUY_FOOD_BASE + FOOD_SLOTS * TEAM_SLOTS
    assert NUM_ACTIONS == ACT_FREEZE_FOOD_BASE + FOOD_SLOTS


def test_a_frozen_shop_pet_slides_to_the_leftmost_slot(env):
    """Measured: a roll refills around frozen items and they slide left -
    freezing slot 1 of three and rerolling leaves the frozen pet at slot 0.
    The offers would be the same either way, but the slot decides which
    action index buys it, so the ordering is behaviour."""
    result = env.reset(seed=0)
    f = result.observations[0].features
    frozen_species = shop_pet_species(f, 1)
    result = env.step(FREEZE_PET_BASE + 1, END_TURN)
    assert shop_pet_frozen(result.observations[0].features, 1)
    seat1 = IGNORED if result.observations[1] is None else END_TURN
    result = env.step(REROLL, seat1)
    f = result.observations[0].features
    assert shop_pet_species(f, 0) == frozen_species
    assert shop_pet_frozen(f, 0)
    assert not shop_pet_frozen(f, 1)


def test_a_lost_battle_costs_a_life_not_the_pet(env):
    """The corrected behavior: fainting in battle is not permanent. Search
    a small seed range for a decisive first round (loser found by their
    lives dropping), then confirm the loser's team is completely
    unchanged going into round 2 - it lost life, not pets."""
    for seed in range(100):
        probe = make(ENV_ID)
        result = probe.reset(seed=seed)
        result = probe.step(buy(0, 0), buy(0, 0))
        before = [
            [team_species(result.observations[s].features, t) for t in range(5)] for s in range(2)
        ]
        result = probe.step(END_TURN, END_TURN)
        if result.done:
            continue
        after_lives = [lives(result.observations[s].features) for s in range(2)]
        if after_lives == [STARTING_LIVES, STARTING_LIVES]:
            continue  # draw, try another seed
        loser = 0 if after_lives[0] < STARTING_LIVES else 1
        after = [team_species(result.observations[loser].features, t) for t in range(5)]
        assert after_lives[loser] == STARTING_LIVES - 1
        assert after == before[loser], "loser's team must be unchanged - fainting isn't permanent"
        return
    pytest.fail("no decisive first round found in 100 seeds")


def test_freeze_persists_across_reroll(env):
    result = env.reset(seed=0)
    sp0 = shop_pet_species(result.observations[0].features, 0)
    result = env.step(FREEZE_PET_BASE + 0, END_TURN)
    assert shop_pet_frozen(result.observations[0].features, 0)
    seat1_action = IGNORED if result.observations[1] is None else END_TURN
    result = env.step(REROLL, seat1_action)
    f0 = result.observations[0].features
    assert shop_pet_species(f0, 0) == sp0  # frozen slot untouched by the reroll
    assert shop_pet_frozen(f0, 0)  # stays frozen until explicitly toggled or bought


def test_freeze_persists_into_next_round(env):
    result = env.reset(seed=0)
    sp0 = shop_pet_species(result.observations[0].features, 0)
    result = env.step(FREEZE_PET_BASE + 0, END_TURN)
    result = end_one_round(env, result)
    f0 = result.observations[0].features
    assert shop_pet_species(f0, 0) == sp0
    assert shop_pet_frozen(f0, 0)


def test_win_on_ten_trophies():
    # Cheapest deterministic route to a decisive match: buy one pet on
    # turn 1 for seat 0 only, then pure end-turns forever. Seat 1 stays
    # empty the whole match, so seat 0's single Tier-1 pet wins every
    # round on its own - no need to keep buying - racking up 10 trophies
    # (and never losing a life) well inside MAX_ROUNDS.
    env = make(ENV_ID)
    result = env.reset(seed=0)
    result = env.step(buy(0, 0), END_TURN)
    result = end_both(env, result)
    assert result.outcome is Outcome.PLAYER_0
    assert result.termination is Termination.NATURAL


def test_illegal_action_forfeits(env):
    env.reset(seed=0)
    result = env.step(NUM_ACTIONS, END_TURN)
    assert result.done
    assert result.outcome is Outcome.PLAYER_1
    assert result.termination is Termination.ILLEGAL_ACTION


def test_budget_forces_end_after_twenty_actions_per_round(env):
    # Both seats take the same 20 actions (buy, then 19 repositions) and
    # never voluntarily END_TURN, so both hit the budget on the same,
    # 20th tick - round 1 resolves right there (mirrored actions -> a
    # draw), landing on round 2's fresh turn rather than leaving seat 0
    # mid-round-1 with seat 1 already idle, which is what let round 1
    # resolve earlier than a naive "20 actions should end this seat" check
    # expects - budgets reset every round, so hitting one is a round
    # event, not necessarily an end-of-episode one.
    result = env.reset(seed=0)
    result = env.step(buy(0, 0), buy(0, 0))
    for _ in range(19):
        result = env.step(REPOSITION_BASE + 0, REPOSITION_BASE + 0)
        if result.done:
            break
    assert result.done or env.turn == 2


def test_step_limit_is_reachable_and_uses_documented_tiebreak(env):
    # Both seats do nothing, every round, forever -> MAX_ROUNDS reached
    # with 0-0 trophies and 5-5 lives -> DRAW_STEP_LIMIT.
    result = env.reset(seed=0)
    result = end_both(env, result)
    assert env.turn == MAX_ROUNDS
    assert result.outcome is Outcome.DRAW
    assert result.termination is Termination.STEP_LIMIT


def test_deterministic_given_same_seed():
    def play(seed):
        e = make(ENV_ID)
        result = e.reset(seed=seed)
        result = e.step(buy(0, 0), buy(0, 0))
        result = end_both(e, result)
        result = end_both(e, result)
        return e.replay(), (result.outcome, result.done)

    a = play(seed=42)
    b = play(seed=42)
    assert a == b


def test_replay_is_flat_two_per_tick(env):
    env.reset(seed=0)
    r = env.step(END_TURN, REROLL)
    replay = env.replay()
    assert replay == [END_TURN, REROLL]
    assert len(replay) == 2


def test_env_advertises_the_forkable_capability(env):
    # How a runner decides whether a search-based submission can be served
    # at all. sap2 opts in; Forkable is not part of TwoPlayerEnv, so this is
    # a real capability check and not a tautology about the base interface.
    assert isinstance(env, Forkable)


def test_clone_does_not_affect_the_original(env):
    result = env.reset(seed=7)
    result = end_one_round(env, result)
    turn_at_fork = env.turn

    fork = env.clone()
    end_both(fork, fork.step(END_TURN, END_TURN))

    # The fork played the match out to its end. The original is still sitting
    # exactly where it was forked, which is the whole point of the capability.
    assert env.turn == turn_at_fork
    assert not result.done


def test_clone_continues_the_rng_stream_rather_than_restarting_it(env):
    # A clone that re-seeded, or that shared shop/battle RNG words with its
    # source, would make a search's rollouts disagree with what the real match
    # goes on to do - the failure that makes forking worthless. Same state and
    # same actions must therefore produce the same match.
    result = env.reset(seed=11)
    result = end_one_round(env, result)

    fork = env.clone()
    fork_result = end_both(fork, fork.step(END_TURN, END_TURN))
    real_result = end_both(env, env.step(END_TURN, END_TURN))

    assert fork_result.outcome == real_result.outcome
    assert fork_result.termination == real_result.termination
    assert fork.replay() == env.replay()
    assert fork.turn == env.turn


# --------------------------------------------------------------------------
# Battle rules, resolved from explicit line-ups.
#
# `resolve_battle` exists because the match API cannot address a battle
# rule: reaching a named board through reset/buy/end_turn means searching
# seeds for a shop that offers the right pets at the right stats, which for
# a five-pet fixture is not reachable at all. Every expected value below is
# the SHIPPED GAME's answer, read out of its own BoardResolver by hosting
# its IL2CPP runtime (policy-clash-re-tools: sap/difftest.py resolves the
# board in both engines, sap/diag.py dumps the engine's BattleState.EventLog
# for it, sap/order_probe.py isolates the rule).

CRICKET_SPECIES = 3        # sap2.h's species ids - see HORSE_SPECIES above
DUCK_SPECIES = 4
FISH_SPECIES = 5
OTTER_SPECIES = 8
PIG_SPECIES = 9
CRAB_SPECIES = 11
FLAMINGO_SPECIES = 12
HEDGEHOG_SPECIES = 13
RAT_SPECIES = 16
SPIDER_SPECIES = 18
CRICKET_TOKEN_SPECIES = 31   # the tokens moved up when Tier 3 landed
DIRTY_RAT_SPECIES = 33

# Enough seeds that a rule which only holds for one RNG word cannot pass.
# Every fixture here is built with DISTINCT attacks among its simultaneous
# faints, which is what makes it seed-independent: equal attack is a coin
# flip in the shipped build as much as here (measured - one such board
# split 0.518/0.482 over 600 seeds), so a fixture that leant on one would
# not be testable at all.
BATTLE_SEEDS = range(1, 25)


def species_of(line: list[tuple]) -> list[int]:
    return [row[0] for row in line]


def resolve(team0: list[tuple], team1: list[tuple], seed: int) -> tuple:
    from policyclash_envs.sap2 import debug_resolve_battle

    return debug_resolve_battle(team0, team1, seed)


def test_the_debug_battle_entry_point_refuses_bad_input():
    """It is a public C entry point reachable from Python, so a bad
    argument has to raise rather than index past an array or wrap an
    int8_t into a stat the engine can never produce."""
    good = [(PIG_SPECIES, 1, 1, 1)]
    for bad in (
        [(0, 1, 1, 1)],                                # SAP2_SPECIES_EMPTY
        [(-1, 1, 1, 1)],
        [(999, 1, 1, 1)],                              # past the species table
        [(PIG_SPECIES, 0, 1, 1)],                      # level below 1
        [(PIG_SPECIES, MAX_LEVEL + 1, 1, 1)],
        [(PIG_SPECIES, 1, -1, 1)],                     # negative attack
        [(PIG_SPECIES, 1, MAX_STATS + 1, 1)],          # past the stat cap
        [(PIG_SPECIES, 1, 1, 0)],                      # a pet cannot start dead
        [(PIG_SPECIES, 1, 1, MAX_STATS + 1)],
        [(PIG_SPECIES, 1, 1, 1, NUM_PERKS)],           # past the perk table
        [(PIG_SPECIES, 1, 1, 1, -1)],
        [good[0]] * (TEAM_SLOTS + 1),                  # more pets than slots
    ):
        with pytest.raises(ValueError):
            resolve(bad, good, 1)
        with pytest.raises(ValueError):
            resolve(good, bad, 1)

    # Malformed SHAPES, not just out-of-range values. These used to come
    # back as SystemError - "internal error" - because the rows were parsed
    # with PyArg_ParseTuple, which refuses anything that is not a tuple.
    for bad, expected in (
        (None, TypeError),                             # not a sequence at all
        (42, TypeError),
        ([PIG_SPECIES], TypeError),                    # a row that is not a sequence
        ([(PIG_SPECIES, 1)], ValueError),              # too few fields
        ([()], ValueError),
        ([(PIG_SPECIES, 1, 1, 1, 0, 0)], ValueError),  # too many fields
        ([("Pig", 1, 1, 1)], TypeError),               # a field that is not an int
        ([(PIG_SPECIES, None, 1, 1)], TypeError),
        ([(2**200, 1, 1, 1)], OverflowError),          # wider than a C long
    ):
        with pytest.raises(expected):
            resolve(bad, good, 1)
        with pytest.raises(expected):
            resolve(good, bad, 1)

    # A list row is as good as a tuple, a short team is how a hole is
    # expressed, and an empty side is legal.
    assert resolve([[PIG_SPECIES, 1, 1, 1]], good, 1)[0] == -1
    assert resolve([], good, 1)[0] == 1


def test_a_summon_lands_in_the_cell_the_body_vacated():
    """Not at the front of the line - the cell the dying pet just left.

    Tier 1 could not tell the two apart: nothing there kills a pet that is
    not already the front, so the vacated cell always WAS the front.
    Hedgehog's splash is the first thing in this roster that separates
    them, and it used to put a Cricket's token in front of a living friend
    that should have stayed ahead of it.

    Measured: a mid-line Cricket killed outright on the shipped build's
    ten-cell battle grid leaves {5: Pig#1, 6: CricketToken#4, 7: Pig#3} -
    the token in cell 6, exactly where the Cricket stood, with the
    survivor in front and the survivor behind both untouched.
    """
    # p1's front Pig survives the splash, the mid-line Cricket does not,
    # and the Pig behind it survives too: the token has a living friend on
    # BOTH sides, which is the only arrangement that can see the difference.
    hedgehog = [(HEDGEHOG_SPECIES, 1, 1, 1)]
    line = [
        (PIG_SPECIES, 1, 1, 9),
        (CRICKET_SPECIES, 1, 1, 2),
        (PIG_SPECIES, 1, 1, 9),
    ]
    for seed in BATTLE_SEEDS:
        _, _, survivors = resolve(hedgehog, line, seed)
        assert species_of(survivors) == [
            PIG_SPECIES,
            CRICKET_TOKEN_SPECIES,
            PIG_SPECIES,
        ], f"seed {seed}: {survivors}"


def test_a_summon_pushes_whatever_filled_the_cell_it_aims_at():
    """The target is a CELL, not a rank among the survivors.

    Rat's Dirty Rats each take the opponent's FRONT cell and push the line
    back; a Cricket's token then claims its own cell and pushes again. So
    with three Dirty Rats landing on a side whose Cricket also died, one
    Dirty Rat ends up IN FRONT of the token and two behind it - which no
    "insert at the front" and no arithmetic on ranks reproduces.

    Measured on this exact board: the shipped build ends with
    {1: RatToken, 2: RatToken, 3: CricketToken, 4: RatToken}, i.e. front to
    back RatToken, CricketToken, RatToken, RatToken.
    """
    mine = [
        (FISH_SPECIES, 1, 3, 5),
        (HEDGEHOG_SPECIES, 3, 6, 4),
        (CRICKET_SPECIES, 1, 2, 4),
    ]
    theirs = [
        (FISH_SPECIES, 1, 4, 6),
        (FISH_SPECIES, 1, 2, 6),
        (RAT_SPECIES, 2, 5, 8),
        (RAT_SPECIES, 1, 3, 6),
    ]
    for seed in BATTLE_SEEDS:
        winner, survivors, theirs_left = resolve(mine, theirs, seed)
        assert winner == 0, f"seed {seed}"
        assert theirs_left == []
        assert species_of(survivors) == [
            DIRTY_RAT_SPECIES,
            CRICKET_TOKEN_SPECIES,
            DIRTY_RAT_SPECIES,
            DIRTY_RAT_SPECIES,
        ], f"seed {seed}: {survivors}"


def test_a_new_faint_competes_on_attack_with_the_faints_already_pending():
    """The pending-faint set is a PRIORITY QUEUE on attack - not a fixed
    batch, and not a stack.

    Both boards below trade their fronts lethally, and the 5-attack
    Hedgehog resolves first either way. Its splash drops p1's Flamingo
    while p1's other Hedgehog is still waiting its turn. Whether the
    Flamingo's +1/+1 reaches the Otter before that second splash is
    decided purely by attack:

      Flamingo 1 attack, pending Hedgehog 3 - the Hedgehog goes first and
      the Otter takes 2 then 2 from 4 health and dies (measured: wiped in
      1.000 of 120 seeds in the shipped build);
      Flamingo 3 attack, pending Hedgehog 1 - the newcomer jumps the
      queue, the Otter is buffed first and survives at 2/1 (measured:
      1.000 of 120 seeds).

    A fixed batch order gets the second wrong; a stack gets the first
    wrong.
    """
    striker = [(HEDGEHOG_SPECIES, 1, 5, 1)]
    for flamingo_attack, hedgehog_attack, expected in (
        (1, 3, []),
        (3, 1, [(OTTER_SPECIES, 2, 1, 1)]),
    ):
        line = [
            (HEDGEHOG_SPECIES, 1, hedgehog_attack, 1),
            (FLAMINGO_SPECIES, 1, flamingo_attack, 1),
            (OTTER_SPECIES, 1, 1, 4),
        ]
        for seed in BATTLE_SEEDS:
            _, _, survivors = resolve(striker, line, seed)
            assert survivors == expected, (
                f"Flamingo {flamingo_attack} attack vs pending Hedgehog "
                f"{hedgehog_attack}, seed {seed}: {survivors}"
            )


def test_a_mid_faint_pet_cannot_be_targeted_or_healed_back():
    """A body at <=0 health is still on the line - bodies do not leave
    until the cascade closes - but no target finder can see it.

    Measured two ways in the shipped build's own event log:

    - it cannot be healed back. p0 [Flamingo 1/3, Crab L3 1/1] against p1
      Hedgehog L2 3/1 wipes in all 120 seeds: the 3-attack Hedgehog's
      splash takes the Crab to exactly 0 first, and the Flamingo's +1/+1
      then finds nothing to buff - no FlamingoAbility cast appears in the
      log at all. Letting the buff land on a body already at 0 left the
      Crab alive at 2/1.
    - and a positional finder steps OVER it. With a mid-faint Pig and then
      a living Duck behind it, the log holds exactly one HealthGained and
      it names the DUCK.
    """
    # The Crab's own start-of-battle takes it to 1/4; the splash is 4.
    flamingo_and_crab = [(FLAMINGO_SPECIES, 1, 1, 3), (CRAB_SPECIES, 3, 1, 1)]
    hedgehog = [(HEDGEHOG_SPECIES, 2, 3, 1)]
    for seed in BATTLE_SEEDS:
        assert resolve(flamingo_and_crab, hedgehog, seed) == (-1, [], []), f"seed {seed}"

    # Stepping over: the Hedgehog front dies in the exchange and its splash
    # kills the Flamingo and the Pig directly behind it, leaving the Duck.
    # The Duck is the only living friend behind the Flamingo, so it takes
    # the buff even though the Pig is nearer.
    line = [
        (HEDGEHOG_SPECIES, 1, 1, 1),
        (FLAMINGO_SPECIES, 1, 2, 2),
        (PIG_SPECIES, 1, 1, 2),
        (DUCK_SPECIES, 1, 1, 30),
    ]
    wall = [(PIG_SPECIES, 1, 1, 40)]
    for seed in BATTLE_SEEDS:
        _, survivors, _ = resolve(line, wall, seed)
        duck = [row for row in survivors if row[0] == DUCK_SPECIES]
        assert duck, f"seed {seed}: the Duck should outlive the splash: {survivors}"
        # base 1 attack, +1 from the Flamingo's faint.
        assert duck[0][1] == 2, f"seed {seed}: Duck came out {duck[0]}"


# ---------------------------------------------------------------- Tier 3
#
# One test per rule the Tier-3 roster landed. Every number below was read
# off the shipped build - `sap/ability_check.py --pet X --levels` for the
# per-level amounts, `sap/tier3_drive.py` for the rules the template dump
# cannot carry - and the drive that settles each one is named in the
# docstring and again in sap2.h's row.
#
# The fixtures share one shape: a 0-ATTACK wall on the far side, so the
# only damage on the near side is the ability under test, plus - where
# the rule needs a faint - a 1-health killer in front of it. Health is
# capped at MAX_STATS, so nothing here can out-stat that cap.

WALL = (PIG_SPECIES, 1, 0, 50)        # hits nothing, outlives everything


def killer(attack: int) -> tuple:
    """A 1-health body that kills once and then dies to any attack."""
    return (PIG_SPECIES, 1, attack, 1)


def test_badger_splashes_half_its_attack_per_level_across_the_battle_line():
    """Badger's faint deals floor(attack x 50% x level) to the nearest
    living body EACH WAY, and "each way" crosses the fighting front.

    Measured (sap/tier3_drive.py `badger_percent`, `badger_cross_team`):
    7 attack deals 3 at level 1 and 10 at level 3 - floored, not rounded -
    and a Badger alone at the front splashed the ENEMY front, which no
    same-team reading of "adjacent" produces.
    """
    for level in (1, 2, 3):
        splash = 7 * 50 * level // 100
        for seed in BATTLE_SEEDS:
            _, mine, theirs = resolve(
                [(BADGER_SPECIES, level, 7, 1)], [(PIG_SPECIES, 1, 1, 50)], seed
            )
            assert mine == [], f"L{level} seed {seed}: the Badger trades lethally"
            # 50, minus the 7 the Badger hit for, minus the splash its
            # faint put across the line into the same body.
            assert theirs == [(PIG_SPECIES, 1, 50 - 7 - splash, 1)], (
                f"L{level} seed {seed}: {theirs}"
            )


def test_camel_buffs_the_friend_behind_even_when_the_hurt_was_lethal():
    """Camel gives the nearest friend behind +1 attack and +2 health per
    level when hurt, and the hurt trigger is NOT gated on surviving.

    Measured (sap/tier3_drive.py `camel_no_friend`): a Camel taken to
    exactly 0 still handed its buff over, where a Peacock taken to 0
    gained nothing - the difference is that a mid-faint body is not a
    legal TARGET and Peacock targets itself.
    """
    for level in (1, 2, 3):
        line = [(CAMEL_SPECIES, level, 1, 4), (PIGEON_SPECIES, 1, 0, 20)]
        for seed in BATTLE_SEEDS:
            _, mine, _ = resolve(line, [killer(9), WALL], seed)
            assert mine == [(PIGEON_SPECIES, level, 20 + 2 * level, 1)], (
                f"L{level} seed {seed}: {mine}"
            )


def test_dodo_hands_half_its_attack_to_the_friend_ahead_at_start_of_battle():
    """Dodo gives floor(own attack x 50% x level) ATTACK - and no health -
    to the nearest friend ahead, once, before the first exchange.

    Measured (sap/tier3_drive.py `dodo_percent`): 1 attack at level 1
    buffs nothing at all, 9 at level 3 buffs +13; the same floored
    multiplier Badger uses.
    """
    for level in (1, 2, 3):
        gain = 7 * 50 * level // 100
        line = [(PIGEON_SPECIES, 1, 0, 20), (DODO_SPECIES, level, 7, 20)]
        for seed in BATTLE_SEEDS:
            _, mine, _ = resolve(line, [WALL], seed)
            front = [row for row in mine if row[0] == PIGEON_SPECIES]
            assert front == [(PIGEON_SPECIES, gain, 20, 1)], (
                f"L{level} seed {seed}: {mine}"
            )


def test_dolphin_shoots_the_lowest_health_enemy_once_per_level():
    """Dolphin deals a flat 4 to the fewest-health living enemy, level-many
    times, re-picking between shots.

    Measured (sap/tier3_drive.py `dolphin`): a level-3 Dolphin facing
    enemies of 30, 6 and 20 health spent two shots on the 6-health one and
    the third on the 20-health one, so the pick is re-made per shot and a
    body already at <=0 is no longer a candidate.
    """
    for level in (1, 2, 3):
        for seed in BATTLE_SEEDS:
            _, _, theirs = resolve(
                [(DOLPHIN_SPECIES, level, 0, 20)],
                [(PIG_SPECIES, 1, 0, 30), (PIG_SPECIES, 1, 0, 40)],
                seed,
            )
            # every shot lands on the 30-health one; the 40 is untouched
            assert theirs == [
                (PIG_SPECIES, 0, 30 - 4 * level, 1),
                (PIG_SPECIES, 0, 40, 1),
            ], f"L{level} seed {seed}: {theirs}"


def test_elephant_hits_the_friend_behind_once_per_level_after_it_attacks():
    """Elephant deals 1 to the nearest friend behind after every attack it
    makes, level-many times.

    Measured (sap/tier3_drive.py `elephant_no_target`): a 1/2 Cricket
    behind a level-3 Elephant took 1 and 1 and the third shot landed on
    nothing, because the Cricket was mid-faint by then; and the volley
    fires even in the exchange the Elephant dies in.
    """
    for level in (1, 2, 3):
        # 50 attack wipes the wall in one exchange, so exactly one volley
        line = [(ELEPHANT_SPECIES, level, 50, 20), (PIGEON_SPECIES, 1, 0, 40)]
        for seed in BATTLE_SEEDS:
            _, mine, _ = resolve(line, [WALL], seed)
            friend = [row for row in mine if row[0] == PIGEON_SPECIES]
            assert friend == [(PIGEON_SPECIES, 0, 40 - level, 1)], (
                f"L{level} seed {seed}: {mine}"
            )


def test_dog_gains_a_temporary_buff_whenever_a_friend_is_summoned():
    """Dog gains +2 attack and +1 health per level every time a friend is
    summoned - a Cricket's faint token here.

    Measured: the buff carries Duration = Temp, so it lands in the
    temporary halves and is gone by the next turn exactly like Horse's; a
    Dirty Rat arriving on this side does NOT wake it, because that summon
    carries the build's TriggerDisabled (sap/tier3_drive.py
    `dog_any_summon`).
    """
    for level in (1, 2, 3):
        line = [(CRICKET_SPECIES, 1, 0, 1), (DOG_SPECIES, level, 0, 20)]
        for seed in BATTLE_SEEDS:
            _, mine, _ = resolve(line, [killer(5), WALL], seed)
            dog = [row for row in mine if row[0] == DOG_SPECIES]
            assert dog == [(DOG_SPECIES, 2 * level, 20 + level, level)], (
                f"L{level} seed {seed}: {mine}"
            )


def test_ox_takes_a_melon_shield_when_the_friend_ahead_faints():
    """Ox gains the Melon perk and a flat +1 attack when the friend in the
    cell DIRECTLY ahead faints.

    Measured (sap/tier3_drive.py `ox_friend_ahead`, `ox_limit`,
    `melon_perk`): only distance 1 counts - with two friends ahead dying
    in one blast a level-3 Ox still fired once - the cap is level-many
    activations a turn, and the Melon blocks 20 damage once.
    """
    for level in (1, 2, 3):
        line = [(PIGEON_SPECIES, 1, 0, 1), (OX_SPECIES, level, 1, 20)]
        for seed in BATTLE_SEEDS:
            _, mine, _ = resolve(line, [killer(5), WALL], seed)
            # +1 attack, and the shield ate the killer's 5 damage whole
            assert mine == [(OX_SPECIES, 2, 20, level)], f"L{level} seed {seed}: {mine}"

    # Two ahead is not distance 1: the Ox reacts to the body next to it
    # and to nothing further away, so with a living friend in between it
    # gains nothing when the front dies.
    # The middle body kills the killer in the exchange after the front
    # dies, so nothing ever faints in the cell next to the Ox.
    far = [
        (PIGEON_SPECIES, 1, 0, 1),
        (PIGEON_SPECIES, 1, 1, 40),
        (OX_SPECIES, 1, 1, 20),
    ]
    for seed in BATTLE_SEEDS:
        _, mine, _ = resolve(far, [killer(5), WALL], seed)
        ox = [row for row in mine if row[0] == OX_SPECIES]
        assert ox == [(OX_SPECIES, 1, 20, 1)], f"seed {seed}: {mine}"


def test_sheep_leaves_two_rams_in_the_cell_it_vacated():
    """Sheep's faint summons TWO Rams at 2/2 per level, at its own level,
    both aimed at the cell the body left, the second pushing the first.

    Measured (sap/tier3_drive.py `sheep_cells`): mid-line the two Rams end
    in the Sheep's own cell and the one behind it, with the friend that
    was behind pushed one further back; on a full line only one lands.
    """
    for level in (1, 2, 3):
        for seed in BATTLE_SEEDS:
            _, mine, _ = resolve(
                [(SHEEP_SPECIES, level, 1, 1)], [killer(5), WALL], seed
            )
            rams = [row for row in mine if row[0] == RAM_SPECIES]
            assert len(rams) == 2, f"L{level} seed {seed}: {mine}"
            for ram in rams:
                assert ram[1] == 2 * level and ram[3] == level, (
                    f"L{level} seed {seed}: {ram}"
                )


def test_spider_summons_a_random_tier_3_pet_at_two_per_level():
    """With a Tier-3 roster present, Spider's faint finally summons
    something: one rollable tier-3 pet at 2/2, 4/4 or 6/6 by level, at the
    Spider's own level, in the cell the body vacated.

    This is the hole Tier 2 shipped with on purpose - see sap2.h's
    SAP2_ROSTER_TIER. Measured (sap/tier3_drive.py `spider_summon`): 200
    drives per level landed exactly the ten tier-3 rollables, 19-21
    apiece, at those stats and that level.
    """
    seen = set()
    for level in (1, 2, 3):
        for seed in range(1, 200):
            _, mine, _ = resolve(
                [(SPIDER_SPECIES, level, 1, 1)], [killer(5), WALL], seed
            )
            assert len(mine) == 1, f"L{level} seed {seed}: {mine}"
            species, attack, _, body_level = mine[0]
            assert species in TIER3_PETS, f"L{level} seed {seed}: {mine[0]}"
            assert attack == 2 * level and body_level == level, (
                f"L{level} seed {seed}: {mine[0]}"
            )
            if level == 1:
                seen.add(species)
    assert seen == set(TIER3_PETS), f"the draw should reach every tier-3 pet: {seen}"


def test_garlic_takes_two_off_every_hit_with_a_floor_of_two():
    """Garlic is permanent and takes 2 off every incoming hit, but never
    below 2 and never above what was coming.

    Measured (sap/tier3_drive.py `garlic_perk`): 1 -> 1, 2 -> 2, 3 -> 2,
    4 -> 2, 5 -> 3, 10 -> 8, 25 -> 23, four hits in a row each reduced
    with the perk still on, and ability damage reduced like an attack.
    """
    from policyclash_envs.sap2 import PERK_GARLIC

    for swing, taken in ((1, 1), (2, 2), (3, 2), (4, 2), (5, 3), (10, 8)):
        line = [(PIGEON_SPECIES, 1, 1, 40, PERK_GARLIC)]
        for seed in BATTLE_SEEDS:
            _, mine, _ = resolve(line, [killer(swing)], seed)
            assert mine == [(PIGEON_SPECIES, 1, 40 - taken, 1)], (
                f"{swing} damage, seed {seed}: {mine}"
            )


def test_melon_blocks_twenty_damage_once():
    """Melon is a one-shot shield worth 20 - the perk Ox grants.

    Measured (sap/tier3_drive.py `melon_perk`): 1, 5 and 20 damage all
    land as 0, 21 lands as 1, 25 as 5, and the perk is gone afterwards
    whatever the amount was, so the next hit is unreduced.
    """
    from policyclash_envs.sap2 import PERK_MELON

    for swing, taken in ((5, 0), (20, 0), (21, 1), (25, 5)):
        line = [(PIGEON_SPECIES, 1, 1, 40, PERK_MELON)]
        for seed in BATTLE_SEEDS:
            _, mine, _ = resolve(line, [killer(swing)], seed)
            assert mine == [(PIGEON_SPECIES, 1, 40 - taken, 1)], (
                f"{swing} damage, seed {seed}: {mine}"
            )


def test_tier_three_widened_the_roster_the_perks_and_the_team_slot():
    """The three rules with no battle lever at all, pinned where they are
    observable: the roster cap, the perk block and the team slot's width.

    Rabbit's three-plays-a-turn cap, Birthday Cake's +1 sell value per
    turn and Salad Bowl's two random friends are shop-phase rules; each
    is driven against the shipped build in sap/tier3_drive.py
    (`rabbit_limit`, `birthday_cake_perk`, `salad_bowl`) and diffed
    action-for-action by sap/fuzz_shop.py, which is where a divergence
    would show. What the env owes them is state to live in, and that is
    what this checks: two more per-pet numbers in the observation (the
    sell bonus a cake has added and the activations spent this turn) and
    three more perk ids.
    """
    from policyclash_envs.sap2 import (
        PERK_BIRTHDAY_CAKE,
        PERK_GARLIC,
        PERK_MELON,
        ROSTER_TIER,
    )

    assert ROSTER_TIER == 3
    assert len({PERK_NONE, PERK_HONEY, PERK_GARLIC, PERK_MELON, PERK_BIRTHDAY_CAKE}) == 5
    assert NUM_PERKS == 6
    # 34 species ids (30 rollable + 4 tokens), and the slot carries the
    # one-hot, attack, health, the level one-hot, exp, the perk one-hot,
    # the sell bonus and the uses counter.
    assert NUM_SPECIES == 35
    assert TEAM_SLOT_FLOATS == NUM_SPECIES + 2 + MAX_LEVEL + 1 + NUM_PERKS + 2
