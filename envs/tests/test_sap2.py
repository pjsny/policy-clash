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
    MAX_TICKS,
    NUM_ACTIONS,
    NUM_PERKS,
    OBS_FLOATS,
    PERK_GARLIC,
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
OTTER_SPECIES = 8
OTTER_BASE_ATK = 1        # SAP2_BASE_ATK[SAP2_OTTER]
OTTER_BASE_HP = 4         # SAP2_BASE_HP[SAP2_OTTER]
HEDGEHOG_SPECIES = 13     # Tier 2
HONEY_FOOD = 2            # SAP2_HONEY
APPLE_FOOD = 1            # SAP2_APPLE
BREAD_CRUMBS_FOOD = 6     # SAP2_BREAD_CRUMBS - Tier 2 foods took 3/4/5
TIER1_SPECIES = set(range(1, 11))  # SAP2_ANT..SAP2_PIGEON - Dragon's own
                          # trigger (Tier1FriendBought) cares which TIER a
                          # buy is, not which exact species, so its test
                          # searches this whole set rather than one id

# Tier 3 - sap2.h's species enum, SAP2_BADGER..SAP2_SHEEP plus the Ram token.
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
RAM_SPECIES = 64          # Sheep's Faint summon - never in a shop (shifted
                          # 34->44->54->64 as Tier 4, 5 then 6's species
                          # were each inserted before the token block - see
                          # sap2.h's species enum)
SPIDER_SPECIES = 18       # Tier 2 - its Faint summon is the Tier-3 roster's own hole to close
TIER3_SPECIES = {
    BADGER_SPECIES, CAMEL_SPECIES, DODO_SPECIES, DOG_SPECIES, DOLPHIN_SPECIES,
    ELEPHANT_SPECIES, GIRAFFE_SPECIES, OX_SPECIES, RABBIT_SPECIES, SHEEP_SPECIES,
}
SALAD_BOWL_FOOD = 9       # SAP2_SALAD_BOWL
GARLIC_FOOD = 10          # SAP2_GARLIC
PILL_FOOD = 5             # SAP2_PILL - Tier 2

# Tier 4 - sap2.h's species enum, SAP2_SKUNK..SAP2_WHALE plus the Bus token.
SKUNK_SPECIES = 31
BLOWFISH_SPECIES = 32
BISON_SPECIES = 33
DEER_SPECIES = 34
HIPPO_SPECIES = 35
PARROT_SPECIES = 36
PENGUIN_SPECIES = 37
SQUIRREL_SPECIES = 38
TURTLE_SPECIES = 39
WHALE_SPECIES = 40
BUS_SPECIES = 65          # Deer's Faint summon - never in a shop (shifted
                          # 45->55->65 as Tier 5 then Tier 6's species were
                          # each inserted before the token block)
TIER4_SPECIES = {
    SKUNK_SPECIES, BLOWFISH_SPECIES, BISON_SPECIES, DEER_SPECIES, HIPPO_SPECIES,
    PARROT_SPECIES, PENGUIN_SPECIES, SQUIRREL_SPECIES, TURTLE_SPECIES, WHALE_SPECIES,
}
PEAR_FOOD = 11            # SAP2_PEAR
CANNED_FOOD_FOOD = 12     # SAP2_CANNED_FOOD
BREAD_FOOD = 13           # SAP2_BREAD
PERK_MELON = 4            # SAP2_PERK_MELON - Tier 3, reused by Turtle
PERK_BREAD_ID = 5         # SAP2_PERK_BREAD
PERK_CHILI = 6            # SAP2_PERK_CHILI - Tier 4, Deer's Bus carries it
PERK_PEANUT = 7           # SAP2_PERK_PEANUT - Tier 5, Scorpion
ANT_SPECIES = 1           # Tier 1 - BEFORE_DEATH buffs a random friend; used
                          # to prove Parrot actually copies a DIFFERENT
                          # species' ability, not just its own

# Tier 5 - sap2.h's species enum, SAP2_SCORPION..SAP2_TURKEY plus the Chick token.
SCORPION_SPECIES = 41
CROCODILE_SPECIES = 42
RHINO_SPECIES = 43
MONKEY_SPECIES = 44
ARMADILLO_SPECIES = 45
COW_SPECIES = 46
SEAL_SPECIES = 47
ROOSTER_SPECIES = 48
SHARK_SPECIES = 49
TURKEY_SPECIES = 50
CHICK_SPECIES = 66        # Rooster's Faint summon - never in a shop (shifted
                          # 56->66 once Tier 6's ten species were inserted
                          # before the token block)
TIER5_SPECIES = {
    SCORPION_SPECIES, CROCODILE_SPECIES, RHINO_SPECIES, MONKEY_SPECIES,
    ARMADILLO_SPECIES, COW_SPECIES, SEAL_SPECIES, ROOSTER_SPECIES, SHARK_SPECIES,
    TURKEY_SPECIES,
}

# Tier 6 - sap2.h's species enum, SAP2_LEOPARD..SAP2_FLY plus the Zombie Fly token.
LEOPARD_SPECIES = 51
BOAR_SPECIES = 52
TIGER_SPECIES = 53
WOLVERINE_SPECIES = 54
GORILLA_SPECIES = 55
DRAGON_SPECIES = 56
MAMMOTH_SPECIES = 57
CAT_SPECIES = 58
SNAKE_SPECIES = 59
FLY_SPECIES = 60
ZOMBIE_FLY_SPECIES = 67   # Fly's Faint-watcher summon - never in a shop
TIER6_SPECIES = {
    LEOPARD_SPECIES, BOAR_SPECIES, TIGER_SPECIES, WOLVERINE_SPECIES,
    GORILLA_SPECIES, DRAGON_SPECIES, MAMMOTH_SPECIES, CAT_SPECIES, SNAKE_SPECIES,
    FLY_SPECIES,
}
PIZZA_FOOD = 20           # SAP2_PIZZA
MUSHROOM_FOOD = 21        # SAP2_MUSHROOM
MELON_FOOD = 22           # SAP2_MELON - the food; the perk it grants is
                          # PERK_MELON above (Tier 3's, reused)
STEAK_FOOD = 23           # SAP2_STEAK
PERK_COCONUT = 8          # SAP2_PERK_COCONUT - Tier 6, Gorilla
PERK_MUSHROOM_ID = 9      # SAP2_PERK_MUSHROOM - Tier 6, the Mushroom food
PERK_STEAK_ID = 10        # SAP2_PERK_STEAK - Tier 6, the Steak food
SUSHI_FOOD = 14           # SAP2_SUSHI
CHOCOLATE_FOOD = 15       # SAP2_CHOCOLATE
CHILI_FOOD = 16           # SAP2_CHILI (the food - the perk shipped a tier
                          # early, with Deer's Bus)
MILK_FOOD = 17            # SAP2_MILK - never rolled, only from Cow

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
NUM_SPECIES = TEAM_SLOT_FLOATS - (2 + MAX_LEVEL + 1 + NUM_PERKS)  # team one-hot
# shop one-hot: Tier 4 added atk_bonus alongside hp_bonus (Canned Food), so
# a shop-pet slot now carries 3 trailing scalars (hp_bonus, atk_bonus,
# frozen), not 2 - see sap2.h's SAP2_SHOP_PET_SLOT_FLOATS.
NUM_SHOP_SPECIES_ONEHOT = SHOP_PET_SLOT_FLOATS - 3
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


def shop_pet_atk_bonus(f: np.ndarray, slot: int) -> float:
    return f[SHOP_PET_BASE + slot * SHOP_PET_SLOT_WIDTH + NUM_SHOP_SPECIES_ONEHOT + 1]


def shop_pet_frozen(f: np.ndarray, slot: int) -> bool:
    base = SHOP_PET_BASE + slot * SHOP_PET_SLOT_WIDTH
    return bool(f[base + NUM_SHOP_SPECIES_ONEHOT + 2])


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
    inserts it there and slides the neighbours - pets at 2,3 taking a drop
    on 2 end up at 3,4. It does not swap and it does not fail."""
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
        assert team_species(f, 3) == first, "the sitting pet slid back"
        assert team_species(f, 2) == species[1]
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
# Tier 3 (Badger, Camel, Dodo, Dog, Dolphin, Elephant, Giraffe, Ox, Rabbit,
# Sheep + Salad Bowl, Garlic). Every seed-search test below follows the
# existing pattern above (a bounded search over seeds/rerolls, `pytest.fail`
# if the budget runs out) - Tier-3 species only turn up in a shop from turn
# 5 on and only alongside Tier 1/2, so getting a SPECIFIC one requires
# spending some of a turn's reroll budget hunting for it, not just picking
# the first seed that offers it turn 1 the way most tests above do.
#
# Scope note: Ox, Dog, Dolphin, Elephant and Camel's abilities only fire in
# BATTLE (SUMMON/HURT/START_BATTLE/AFTER_ATTACK), and constructing a
# specific, deterministic battle line-up through the public action API
# alone (buy/sell/position, no direct state injection) is materially more
# expensive than the build-phase cases below - not attempted here. Their
# wiring is instead covered by: (a) the 3000-seed random-legal-action smoke
# run this phase was validated with (every Tier-3 species observed reaching
# a team, including Ram, with zero crashes across 30-round matches), and
# (b) direct code review against data/turtle_pack's scrape. Rabbit's
# max_per_turn=3 cap shares its enforcement code path 1:1 with Ox's (see
# Sap2Ability.max_per_turn), so test_rabbit_gains_health_when_food_is_eaten
# below exercises that shared path even though it only drives one proc.


def advance_to_turn(env, result, target_turn):
    """Pure end-turns until `env.turn == target_turn` or the match ends."""
    while not result.done and env.turn < target_turn:
        result = end_one_round(env, result)
    return result


def _seat1(result, action=END_TURN):
    return IGNORED if result.observations[1] is None else action


PET_PRICE = 3  # flat, sap2_buy_pet - see sap2.h


def buy_species_at_turn(probe, result, turn, species, dest, max_rerolls=10):
    """Advance to `turn`'s shop for seat 0, rerolling (within that turn's
    own gold) until `species` shows up in the pet shop AND is still
    affordable (a reroll spends gold too, so the search can find the right
    species with too little left to actually buy it), then buy it onto
    `dest`. Returns (ok, result); ok is False if the budget ran out or the
    turn was never reached (species doesn't roll, or the match ended)."""
    result = advance_to_turn(probe, result, turn)
    if result.done:
        return False, result
    for _ in range(max_rerolls + 1):
        f = result.observations[0].features
        slot = next(
            (s for s in range(MAX_SHOP_PETS) if shop_pet_species(f, s) == species), None
        )
        if slot is not None and gold(f) >= PET_PRICE:
            result = probe.step(buy(slot, dest), _seat1(result))
            return True, result
        if gold(f) < 1:
            return False, result
        result = probe.step(REROLL, _seat1(result))
    return False, result


def buy_any_at_turn(probe, result, turn, dest):
    """Advance to `turn` and buy whatever is in shop slot 0, no search -
    for filler team members whose species doesn't matter (only that they
    are SOME distinct occupied pet). Needed once a shop's pool gets wide
    (Tier 5's is 50 species uniform - see SAP2_SPECIES_TIER's comment):
    buying a SPECIFIC species repeatedly via buy_species_at_turn's reroll
    search becomes prohibitively rare there, but the shop always has
    SOMETHING rolled, so skipping the search entirely is both cheaper and
    correct when identity truly does not matter."""
    result = advance_to_turn(probe, result, turn)
    if result.done:
        return False, result
    f = result.observations[0].features
    if gold(f) < PET_PRICE or shop_pet_species(f, 0) == 0:
        return False, result
    result = probe.step(buy(0, dest), _seat1(result))
    return True, result


def buy_from_set_at_turn(probe, result, turn, species_set, dest, max_rerolls=10):
    """Same idea as buy_species_at_turn, but succeeds on ANY species in
    `species_set` rather than one exact id - for a scenario that only
    needs "some pet from this family" (Dragon's test needs a Tier-1 buy,
    not one specific Tier-1 species). Tier 6's shop pool is 60 species
    uniform, wider than Tier 5's - see buy_any_at_turn's own comment on
    why a single exact species becomes a bad search target there; a
    10-species family is a much likelier hit per roll."""
    result = advance_to_turn(probe, result, turn)
    if result.done:
        return False, result
    for _ in range(max_rerolls + 1):
        f = result.observations[0].features
        slot = next(
            (s for s in range(MAX_SHOP_PETS) if shop_pet_species(f, s) in species_set), None
        )
        if slot is not None and gold(f) >= PET_PRICE:
            result = probe.step(buy(slot, dest), _seat1(result))
            return True, result
        if gold(f) < 1:
            return False, result
        result = probe.step(REROLL, _seat1(result))
    return False, result


def feed_species_at_turn(probe, result, turn, food_species, dest, max_rerolls=10):
    """Same idea as buy_species_at_turn, for the food shop - reroll until
    `food_species` appears and is still affordable, then feed it to team
    slot `dest`."""
    result = advance_to_turn(probe, result, turn)
    if result.done:
        return False, result
    for _ in range(max_rerolls + 1):
        f = result.observations[0].features
        slot = next(
            (s for s in range(2) if shop_food_species(f, s) == food_species), None
        )
        if slot is not None and gold(f) >= shop_food_price(f, slot):
            result = probe.step(buy_food(slot, dest), _seat1(result))
            return True, result
        if gold(f) < 1:
            return False, result
        result = probe.step(REROLL, _seat1(result))
    return False, result


def test_roster_reaches_tier_3_at_turn_5(env):
    """SAP2_ROSTER_TIER is 3 now: once the shop reaches tier 3 (turn 5),
    Tier-3 species can appear in the roll pool alongside Tier 1/2 - not
    guaranteed on any one roll, but findable within a normal turn's reroll
    budget. Regression for the roster actually being wired into the pool,
    not just the tier-gate math around it (which test_shop_grows_with_tier
    already covers on its own)."""
    for seed in range(30):
        probe = make(ENV_ID)
        result = probe.reset(seed=seed)
        result = advance_to_turn(probe, result, 5)
        if result.done:
            continue
        found = False
        for _ in range(11):
            f = result.observations[0].features
            if any(shop_pet_species(f, s) in TIER3_SPECIES for s in range(MAX_SHOP_PETS)):
                found = True
                break
            if gold(f) < 1:
                break
            result = probe.step(REROLL, _seat1(result))
        if found:
            return
    pytest.fail("no Tier-3 species turned up in 30 seeds x 10 rerolls at turn 5")


def test_spider_faint_summons_a_real_tier3_pet(env):
    """The documented hole this phase closes: before Tier 3 existed,
    SAP2_ABILITY[SPIDER] was `{0}, {0}` - a Spider that fainted summoned
    nothing, because there was no Tier-3 pet to summon. Now it summons a
    random one at 2/2, level 1 (per data/turtle_pack's scrape - Spider is
    Tier 2, so it rolls from turn 3, well before Tier 3 pets themselves
    are common)."""
    for seed in range(40):
        probe = make(ENV_ID)
        result = probe.reset(seed=seed)
        ok, result = buy_species_at_turn(probe, result, 3, SPIDER_SPECIES, 0)
        if not ok:
            continue
        result = end_one_round(probe, result)  # -> turn 4, Spider persists
        ok, result = feed_species_at_turn(probe, result, 4, PILL_FOOD, 0)
        if not ok:
            continue
        f = result.observations[0].features
        assert team_species(f, 0) in TIER3_SPECIES
        assert team_attack(f, 0) == 2
        assert team_health(f, 0) == 2
        assert team_level(f, 0) == 1
        return
    pytest.fail("couldn't get both a Spider and a Pill within 40 seeds' reroll budgets")


def test_sheep_faint_summons_two_rams(env):
    """SAP2_SEL_SUMMON_SLOT used to fill only the trigger's own vacated
    slot, looping `count` times over the SAME slot (harmless while every
    user was count=1). Sheep is this roster's first count=2 summon: the
    fix places the first Ram in the vacated slot and the second in the
    next empty one."""
    for seed in range(60):
        probe = make(ENV_ID)
        result = probe.reset(seed=seed)
        ok, result = buy_species_at_turn(probe, result, 5, SHEEP_SPECIES, 0)
        if not ok:
            continue
        result = end_one_round(probe, result)  # -> turn 6, Sheep persists
        ok, result = feed_species_at_turn(probe, result, 6, PILL_FOOD, 0)
        if not ok:
            continue
        f = result.observations[0].features
        assert team_species(f, 0) == RAM_SPECIES
        assert team_species(f, 1) == RAM_SPECIES
        assert team_attack(f, 0) == 2 and team_health(f, 0) == 2  # level 1: 2x1
        assert team_attack(f, 1) == 2 and team_health(f, 1) == 2
        assert all(team_species(f, t) == 0 for t in range(2, 5)), "exactly two Rams, not more"
        return
    pytest.fail("couldn't get both a Sheep (turn 5+) and a Pill within 60 seeds' budgets")


def test_badger_faint_damages_adjacent_pets_and_garlic_reduces_it(env):
    """Two Tier-3 mechanics in one scenario, since both need the same
    build-phase multi-pet setup: team [Otter, Badger, Otter(Garlic)].
    Feeding Badger a Pill fires its BEFORE_DEATH damage at both neighbours
    - SAP2_SEL_ADJACENT_ANY_TEAM's own-team-only build-phase case, since
    there is no opponent board yet. Badger is base 6/3; at level 1 that is
    floor(6 x 50% x 1) = 3 damage each, per Sap2Ability.percent's
    convention (same `percent x level` formula Crab already uses). The
    Garlic-fed Otter takes less: max(3 - 2, 2) = 2, the floor from
    sap2_perk_reduce_damage's comment - not zero, because Garlic can never
    reduce a hit below 2."""
    for seed in range(80):
        probe = make(ENV_ID)
        result = probe.reset(seed=seed)
        ok, result = buy_species_at_turn(probe, result, 1, OTTER_SPECIES, 0)
        if not ok:
            continue
        ok, result = buy_species_at_turn(probe, result, 2, OTTER_SPECIES, 2)
        if not ok:
            continue
        ok, result = buy_species_at_turn(probe, result, 5, BADGER_SPECIES, 1)
        if not ok:
            continue
        result = end_one_round(probe, result)  # -> turn 6, team persists
        # Both feeds happen in this SAME turn 6, deliberately: seat 1 never
        # buys anything in this test (it only mirrors END_TURN), so its
        # lives run out and the match ends around the turn 6/7 boundary -
        # well inside a normal player's pace, but this scenario needs two
        # separate food purchases to still be mid-turn-6 when it reads the
        # result, not spread across a round boundary it might not survive.
        ok, result = feed_species_at_turn(probe, result, 6, GARLIC_FOOD, 2, max_rerolls=6)
        if not ok:
            continue
        f = result.observations[0].features
        assert team_perk(f, 2) == PERK_GARLIC
        before_ahead, before_behind = team_health(f, 0), team_health(f, 2)
        ok, result = feed_species_at_turn(probe, result, 6, PILL_FOOD, 1)  # kills Badger
        if not ok:
            continue
        f = result.observations[0].features
        assert team_species(f, 1) == 0, "Badger's own slot is empty"
        assert team_health(f, 0) == before_ahead - 3, "no Garlic: full 3 damage"
        assert team_health(f, 2) == before_behind - 2, "Garlic: floored at 2, not 3"
        return
    pytest.fail("couldn't assemble Otter+Badger+Otter(Garlic) within 80 seeds' budgets")


def test_giraffe_buffs_friends_ahead_at_the_start_of_every_turn(env):
    """Giraffe reuses SAP2_SEL_FRIENDS_AHEAD - Snail's own selector - but
    with count=SAP2_BY_LEVEL (1 friend at level 1) instead of Snail's fixed
    3, and no condition gating it: it fires every turn, unconditionally.
    Team [Otter, Otter, Giraffe]: only the Otter directly ahead of Giraffe
    (slot 1) should be buffed, not the one two slots ahead (slot 0)."""
    for seed in range(60):
        probe = make(ENV_ID)
        result = probe.reset(seed=seed)
        ok, result = buy_species_at_turn(probe, result, 1, OTTER_SPECIES, 0)
        if not ok:
            continue
        ok, result = buy_species_at_turn(probe, result, 2, OTTER_SPECIES, 1)
        if not ok:
            continue
        ok, result = buy_species_at_turn(probe, result, 5, GIRAFFE_SPECIES, 2)
        if not ok:
            continue
        before = result.observations[0].features
        before0 = (team_attack(before, 0), team_health(before, 0))
        before1 = (team_attack(before, 1), team_health(before, 1))
        result = end_one_round(probe, result)  # -> next turn: Giraffe's START_TURN fires
        if result.done or result.observations[0] is None:
            continue
        f = result.observations[0].features
        assert (team_attack(f, 1), team_health(f, 1)) == (before1[0] + 1, before1[1] + 1), \
            "the Otter directly ahead of Giraffe (slot 1) should gain +1/+1"
        assert (team_attack(f, 0), team_health(f, 0)) == before0, \
            "the Otter two slots ahead (slot 0) is out of Giraffe's level-1 range"
        return
    pytest.fail("couldn't assemble Otter+Otter+Giraffe within 60 seeds' budgets")


def test_rabbit_gains_health_when_a_teammate_eats_food(env):
    """Rabbit's SAP2_TRIG_EAT_FOOD fires on every occupied slot, not just
    the fed one ("including Rabbit itself" per the scrape) - fed via
    sap2_buy_food's own new watcher loop. This also exercises the
    max_per_turn plumbing Ox shares (see this file's Tier-3 section
    docstring): the check/increment on SapPet2.turn_uses runs on every
    feed even though a single feed can never hit Rabbit's cap of 3.

    Fed to a DIFFERENT pet (an Otter, not Rabbit itself) deliberately: the
    food's own direct effect (Apple's +1/+1, Muffin's +3/+3, ...) would
    otherwise land on Rabbit too and confound the +1-per-level this test is
    isolating - Rabbit's OWN health is only ever touched by its ability
    here, never by what the food does on its own."""
    for seed in range(60):
        probe = make(ENV_ID)
        result = probe.reset(seed=seed)
        ok, result = buy_species_at_turn(probe, result, 5, RABBIT_SPECIES, 0)
        if not ok:
            continue
        ok, result = buy_species_at_turn(probe, result, 6, OTTER_SPECIES, 1)
        if not ok:
            continue
        result = end_one_round(probe, result)  # -> fresh 10g turn
        f = result.observations[0].features
        before_hp = team_health(f, 0)
        # Any rollable food but Pill works - Pill would destroy the Otter
        # rather than feed it, which is a different (also correct, see the
        # food-shop switch's comment) scenario this test isn't after.
        food_slot = next(
            (s for s in range(2) if shop_food_species(f, s) not in (0, PILL_FOOD)), None
        )
        if food_slot is None or gold(f) < shop_food_price(f, food_slot):
            continue
        result = probe.step(buy_food(food_slot, 1), _seat1(result))  # fed to the Otter
        f = result.observations[0].features
        assert team_health(f, 0) == before_hp + 1, "level 1: +1 health per proc, on Rabbit alone"
        return
    pytest.fail("couldn't get a Rabbit+Otter and a rollable food within 60 seeds' budgets")


def test_salad_bowl_buffs_two_random_pets(env):
    """Salad Bowl (+1/+1 to two random pets) is this roster's first food
    whose effect lands somewhere other than the clicked `target` slot -
    sap2_buy_food's own switch case. With three pets on the team, at
    least two must show the +1/+1 (the third might be the one skipped, or
    Salad Bowl's own random pick might include the nominal target too)."""
    for seed in range(60):
        probe = make(ENV_ID)
        result = probe.reset(seed=seed)
        ok, result = buy_species_at_turn(probe, result, 1, OTTER_SPECIES, 0)
        if not ok:
            continue
        ok, result = buy_species_at_turn(probe, result, 2, OTTER_SPECIES, 1)
        if not ok:
            continue
        ok, result = buy_species_at_turn(probe, result, 3, OTTER_SPECIES, 2)
        if not ok:
            continue
        # Salad Bowl is Tier 3, so it needs the shop's OWN tier to reach 3
        # too (turn 5+) - not just any later turn, which is what tripped
        # this test up before this comment: turn 4's food pool is still
        # Tier <=2 and can never roll it.
        result = advance_to_turn(probe, result, 5)
        if result.done:
            continue
        f = result.observations[0].features
        before = [team_attack(f, t) for t in range(3)]
        ok, result = feed_species_at_turn(probe, result, 5, SALAD_BOWL_FOOD, 0)
        if not ok:
            continue
        f = result.observations[0].features
        after = [team_attack(f, t) for t in range(3)]
        buffed = sum(1 for t in range(3) if after[t] == before[t] + 1)
        untouched = sum(1 for t in range(3) if after[t] == before[t])
        assert buffed == 2 and untouched == 1, f"expected exactly 2 of 3 buffed, got {after} vs {before}"
        return
    pytest.fail("couldn't assemble three Otters for a Salad Bowl within 60 seeds' budgets")


# --------------------------------------------------------------------------
# Tier 4 (Skunk, Blowfish, Bison, Deer, Hippo, Parrot, Penguin, Squirrel,
# Turtle, Whale + Pear, Canned Food, Bread). Same search-bounded pattern as
# Tier 3's section above.
#
# All of these delay every purchase until turn 7 (or later), deliberately:
# Tier 4 species/foods only roll from turn 7 on (the shop reaches tier 4
# there - see SAP2_ROSTER_TIER's comment, which this pass also caught
# stating turn 9 instead of the actual turn 7), and with seat 1 never
# buying anything in these tests, an empty seat 1 starts losing a life
# every round from whichever round seat 0 first fields a live pet. Buying
# nothing before turn 7 keeps every round up to then a 0-vs-0 draw (costs
# neither seat a life - sap2_battle_ex returns a draw outright when both
# counts start at 0), so the match is still guaranteed alive when turn 7's
# shop opens; the six seeds' worth of Tier-3 tests above only affect
# THEIR OWN probes, never these.
#
# Scope note, same shape as Tier 3's own: Skunk, Blowfish, Hippo, Whale and
# Chili's splash only fire in BATTLE (Start of Battle/Hurt/Knock Out), and
# this file has no way to force a specific battle line-up through the
# public action API alone. Covered instead by the 3000-seed random-legal-
# play smoke run (zero crashes; every Tier-4 species and the Bus token
# observed reaching a team) and direct code review. Bison's
# has-a-level-3-friend condition is skipped here too - reaching level 3
# costs 6 copies of one species, which this file's existing tests already
# show takes real engineering to set up cheaply (see
# test_levelling_follows_the_shipped_exp_table's own seed-search), and its
# condition check is a direct structural copy of
# SAP2_COND_HAS_OTHER_MINION's already-tested shape (same loop, different
# field compared) - low marginal risk for the cost of a dedicated test.
#
# Parrot is the other one skipped, for a sharper reason than "battle only":
# its copy is set during the SHOP phase (End Turn) but only ever matters
# during the BATTLE that immediately follows - it is reset back to 0
# before the next shop phase opens (see SapPet2.copy_species), so there is
# no shop-phase observation point where a copy is both active and
# inspectable, and copy_species itself is pure internal state with no
# direct field in the observation buffer. Proving it fired would need an
# outcome-based differential test in the shape of
# test_horses_buff_counts_in_this_rounds_battle_and_expires_next_turn
# above, except harder: that test compares two plays that both WIN;
# proving Parrot's copy requires MY OWN pet to survive as the copy's
# target of a BEFORE_DEATH-shaped effect while a DIFFERENT pet faints
# beside it, which this file has no lever to force against an
# always-empty seat 1. Covered by code review only: `effective_species`
# is one substitution point shared identically by sap2_fire and
# sap2_battle_fire, and every other Tier 1-4 ability already exercised
# above keeps passing through that same substitution when copy_species is
# 0 (its default), which is the strongest signal this file's own test
# suite can offer that the substitution itself did not break anything it
# touches.


def test_canned_food_buffs_current_and_future_shop_pets(env):
    """SapShopPet2 gained an atk_bonus field for this - Duck's hp_bonus was
    the only shop-pet stat modifier that existed before. Checks both
    halves the scrape's wording calls out: pets ALREADY in the shop when
    Canned Food is bought, and pets a FUTURE reroll puts there."""
    for seed in range(40):
        probe = make(ENV_ID)
        result = probe.reset(seed=seed)
        result = advance_to_turn(probe, result, 7)
        if result.done:
            continue
        ok, result = buy_species_at_turn(probe, result, 7, OTTER_SPECIES, 0)
        if not ok:
            continue
        f = result.observations[0].features
        before_atk = [shop_pet_atk_bonus(f, s) for s in range(MAX_SHOP_PETS)]
        before_hp = [shop_pet_hp_bonus(f, s) for s in range(MAX_SHOP_PETS)]
        ok, result = feed_species_at_turn(probe, result, 7, CANNED_FOOD_FOOD, 0)
        if not ok:
            continue
        f = result.observations[0].features
        occupied = [s for s in range(MAX_SHOP_PETS) if shop_pet_species(f, s) != 0]
        assert occupied, "the shop should still have pets after buying Canned Food"
        for s in occupied:
            assert shop_pet_atk_bonus(f, s) == before_atk[s] + 1, "current shop pets: +1 attack"
            assert shop_pet_hp_bonus(f, s) == before_hp[s] + 1, "current shop pets: +1 health"
        if gold(f) < 1:
            continue
        result = probe.step(REROLL, _seat1(result))
        f = result.observations[0].features
        occupied2 = [s for s in range(MAX_SHOP_PETS) if shop_pet_species(f, s) != 0]
        assert occupied2, "a reroll should still produce pets"
        for s in occupied2:
            assert shop_pet_atk_bonus(f, s) == 1, "future (rerolled) pets carry the running bonus too"
            assert shop_pet_hp_bonus(f, s) == 1
        return
    pytest.fail("couldn't get an Otter and Canned Food within 40 seeds' budgets")


def test_pear_gives_plus_two_plus_two(env):
    """Mechanically identical to Apple's own case, just a bigger flat
    amount - SAP2_APPLE_BUFF carries Pear's entry."""
    for seed in range(40):
        probe = make(ENV_ID)
        result = probe.reset(seed=seed)
        result = advance_to_turn(probe, result, 7)
        if result.done:
            continue
        ok, result = buy_species_at_turn(probe, result, 7, OTTER_SPECIES, 0)
        if not ok:
            continue
        f = result.observations[0].features
        before_atk, before_hp = team_attack(f, 0), team_health(f, 0)
        ok, result = feed_species_at_turn(probe, result, 7, PEAR_FOOD, 0)
        if not ok:
            continue
        f = result.observations[0].features
        assert team_attack(f, 0) == before_atk + 2
        assert team_health(f, 0) == before_hp + 2
        return
    pytest.fail("couldn't get an Otter and a Pear within 40 seeds' budgets")


def test_bread_grants_its_perk(env):
    """Bread leaves a perk (End Turn: +7 health, temporary) rather than
    changing a stat directly - same shape as Honey/Meat Bone/Garlic before
    it, just the first one whose own effect is itself a declarative
    ability (SAP2_PERK_ABILITY's new Bread row) instead of hardcoded. The
    End-Turn buff itself resolves inside battle (see this section's own
    scope note on why a mid-battle read isn't available through the public
    API), so this checks the wiring this file CAN observe directly: the
    perk lands."""
    for seed in range(40):
        probe = make(ENV_ID)
        result = probe.reset(seed=seed)
        result = advance_to_turn(probe, result, 7)
        if result.done:
            continue
        ok, result = buy_species_at_turn(probe, result, 7, OTTER_SPECIES, 0)
        if not ok:
            continue
        ok, result = feed_species_at_turn(probe, result, 7, BREAD_FOOD, 0)
        if not ok:
            continue
        f = result.observations[0].features
        assert team_perk(f, 0) == PERK_BREAD_ID
        return
    pytest.fail("couldn't get an Otter and Bread within 40 seeds' budgets")


def test_deer_faint_summons_a_bus_with_chili(env):
    """Deer's Faint summon (SAP2_SEL_SUMMON_SLOT, count=1, param=SAP2_BUS)
    is otherwise Cricket's own shape - stats scaled 5x/3x level - but is
    also this roster's first summon to carry grant_perk: the Bus comes
    out holding Chili, a Tier-5 food's perk pulled forward the same way
    Ox pulled Melon forward in Tier 3."""
    for seed in range(40):
        probe = make(ENV_ID)
        result = probe.reset(seed=seed)
        ok, result = buy_species_at_turn(probe, result, 7, DEER_SPECIES, 0)
        if not ok:
            continue
        result = end_one_round(probe, result)  # -> turn 8, Deer persists
        ok, result = feed_species_at_turn(probe, result, 8, PILL_FOOD, 0)
        if not ok:
            continue
        f = result.observations[0].features
        assert team_species(f, 0) == BUS_SPECIES
        assert team_attack(f, 0) == 5 and team_health(f, 0) == 3  # level 1: 5x1, 3x1
        assert team_perk(f, 0) == PERK_CHILI
        return
    pytest.fail("couldn't get a Deer (turn 7+) and a Pill within 40 seeds' budgets")


def test_turtle_faint_grants_melon_to_friends_behind(env):
    """SAP2_SEL_FRIENDS_BEHIND's grant_perk branch, shared with the
    FRIENDS_AHEAD/BEHIND buff path Snail/Flamingo/Camel/Dodo/Elephant
    already exercise - Turtle carries attack=health=0, so only the perk
    should land, on the ONE nearest friend behind (level 1)."""
    for seed in range(60):
        probe = make(ENV_ID)
        result = probe.reset(seed=seed)
        ok, result = buy_species_at_turn(probe, result, 7, TURTLE_SPECIES, 0)
        if not ok:
            continue
        ok, result = buy_species_at_turn(probe, result, 7, OTTER_SPECIES, 1)
        if not ok:
            continue
        result = end_one_round(probe, result)  # -> turn 8, team persists
        f = result.observations[0].features
        before_atk, before_hp = team_attack(f, 1), team_health(f, 1)
        ok, result = feed_species_at_turn(probe, result, 8, PILL_FOOD, 0)  # kills Turtle
        if not ok:
            continue
        f = result.observations[0].features
        assert team_species(f, 0) == 0, "Turtle's own slot is empty"
        assert team_species(f, 1) == OTTER_SPECIES, "a build-phase faint leaves a hole, not a shift"
        assert team_perk(f, 1) == PERK_MELON, "the Otter behind it gets Melon"
        assert team_attack(f, 1) == before_atk, "Turtle's own row carries no stat change"
        assert team_health(f, 1) == before_hp
        return
    pytest.fail("couldn't assemble Turtle+Otter within 60 seeds' budgets")


def test_squirrel_discounts_shop_food_at_start_of_turn(env):
    """SAP2_EFF_DISCOUNT_SHOP_FOOD - a one-time edit to whatever the roll
    just put in the food shop, floored at 1 gold (Pill, already 1, is
    untouched; every other Tier 1-4 food is a flat 3, so a level-1
    Squirrel's -1 should read as exactly 2)."""
    for seed in range(40):
        probe = make(ENV_ID)
        result = probe.reset(seed=seed)
        ok, result = buy_species_at_turn(probe, result, 7, SQUIRREL_SPECIES, 0)
        if not ok:
            continue
        result = end_one_round(probe, result)  # -> turn 8: Squirrel's Start of Turn fires
        if result.done or result.observations[0] is None:
            continue
        f = result.observations[0].features
        occupied = [s for s in range(2) if shop_food_species(f, s) != 0]
        if not occupied:
            continue  # this turn's roll happened to offer no food; try another seed
        for s in occupied:
            sp = shop_food_species(f, s)
            expected = 1 if sp == PILL_FOOD else 2
            assert shop_food_price(f, s) == expected, f"slot {s} (food {sp}): expected {expected}g"
        return
    pytest.fail("couldn't get a Squirrel with a rolled food within 40 seeds' budgets")


def test_penguin_is_a_noop_with_no_level2plus_friend(env):
    """SAP2_SEL_RANDOM_LEVEL2PLUS_FRIEND - SAP2_SEL_RANDOM_FRIEND's own
    pick, filtered to level>=2 - with a level-1-only team (a freshly bought
    Penguin plus a freshly bought Otter, neither leveled), the filtered
    candidate pool is empty and the ability should touch nobody, not crash
    or fall back to buffing an ineligible pet.

    Doesn't test the positive "does buff a level-2+ friend" half: reaching
    level 2 needs 3 copies of one species (9g - see
    test_levelling_follows_the_shipped_exp_table), and finding 3 copies of
    a SPECIFIC species in the SAME turn Penguin needs to already be
    present is a much steeper seed-search than anything else in this
    section - Tier 4's shop draws from all 40 Tier 1-4 species UNIFORMLY
    (measured, see SAP2_SPECIES_TIER's comment - not weighted toward
    cheaper tiers), so a specific species is only ~1-in-40 per rolled
    slot, not the ~1-in-10 a Tier 1-only shop offers every other test in
    this file relies on. The selector's own code is a direct filtered
    variant of SAP2_SEL_RANDOM_FRIEND, already exercised by Otter/Fish/Ant
    above - low marginal risk left uncovered by skipping the positive
    case."""
    for seed in range(40):
        probe = make(ENV_ID)
        result = probe.reset(seed=seed)
        ok, result = buy_species_at_turn(probe, result, 7, PENGUIN_SPECIES, 0)
        if not ok:
            continue
        ok, result = buy_species_at_turn(probe, result, 7, OTTER_SPECIES, 1)
        if not ok:
            continue
        f = result.observations[0].features
        before0 = (team_attack(f, 0), team_health(f, 0))
        before1 = (team_attack(f, 1), team_health(f, 1))
        result = end_one_round(probe, result)  # -> turn 8: Penguin's Start of Turn fires
        if result.done or result.observations[0] is None:
            continue
        f = result.observations[0].features
        assert (team_attack(f, 0), team_health(f, 0)) == before0
        assert (team_attack(f, 1), team_health(f, 1)) == before1
        return
    pytest.fail("couldn't get a Penguin and an Otter within 40 seeds' budgets")


# --------------------------------------------------------------------------
# Tier 5 (Scorpion, Crocodile, Rhino, Monkey, Armadillo, Cow, Seal, Rooster,
# Shark, Turkey + Sushi, Chocolate, Chili, Milk/Better Milk/Best Milk). Same
# search-bounded pattern as Tier 3/4's sections above, and the same "delay
# every purchase until the shop reaches this tier" reasoning - Tier 5 opens
# at turn 9 this time (SAP2_TIER_ON_TURN[3]), confirmed alive with zero
# purchases beforehand across 30/30 seeds before writing anything below.
#
# Scope note, same shape as before: Crocodile, Rhino and Armadillo's
# abilities only fire in BATTLE (Start of Battle / Knock Out), and Rooster's
# percent-of-self-attack summon is exactly the Whale/Badger-style state this
# file has never had a lever to construct deterministically either. Covered
# by the 3000-seed random-legal-play smoke run (zero crashes; every Tier-5
# species and the Chick token observed reaching a team) and code review.
# Peanut's instant-kill and Chili's splash are ALSO battle-only by
# construction (they hook the exchange loop directly) and share that same
# scope note - Scorpion's grant of Peanut is tested below, just not its
# combat effect.


def test_scorpion_gains_peanut_perk_when_bought(env):
    """SAP2_TRIG_SELF_SUMMONED fires directly on the arriving pet, not via
    a watcher fan-out - unlike every earlier "reacts to an arrival" trigger
    in this roster (SAP2_TRIG_SUMMON), which structurally excludes the
    arriving pet itself. Buying Scorpion is the cheapest possible exercise
    of it: one buy, no setup."""
    for seed in range(40):
        probe = make(ENV_ID)
        result = probe.reset(seed=seed)
        ok, result = buy_species_at_turn(probe, result, 9, SCORPION_SPECIES, 0)
        if not ok:
            continue
        f = result.observations[0].features
        assert team_perk(f, 0) == PERK_PEANUT
        return
    pytest.fail("couldn't get a Scorpion within 40 seeds' budgets")


def test_cow_replaces_shop_food_with_milk(env):
    """SAP2_EFF_REPLACE_SHOP_FOOD - clears every food slot and stocks
    exactly 2 free (price 0) Milk. Also exercises Milk's own asymmetric
    +1atk/+2hp feed effect (SAP2_MILK_ATK/HP), which cannot reuse
    SAP2_APPLE_BUFF's single symmetric table."""
    for seed in range(40):
        probe = make(ENV_ID)
        result = probe.reset(seed=seed)
        ok, result = buy_species_at_turn(probe, result, 9, OTTER_SPECIES, 1)
        if not ok:
            continue
        ok, result = buy_species_at_turn(probe, result, 9, COW_SPECIES, 0)
        if not ok:
            continue
        f = result.observations[0].features
        occupied = [s for s in range(2) if shop_food_species(f, s) != 0]
        assert len(occupied) == 2, "Cow stocks exactly two"
        for s in occupied:
            assert shop_food_species(f, s) == MILK_FOOD
            assert shop_food_price(f, s) == 0
        before_atk, before_hp = team_attack(f, 1), team_health(f, 1)
        result = probe.step(buy_food(occupied[0], 1), _seat1(result))
        f = result.observations[0].features
        assert team_attack(f, 1) == before_atk + 1
        assert team_health(f, 1) == before_hp + 2
        return
    pytest.fail("couldn't get an Otter and a Cow within 40 seeds' budgets")


def test_seal_buffs_three_friends_attack_on_eat_food(env):
    """SAP2_TRIG_EAT_FOOD - Rabbit's own trigger (Tier 3), reused - with
    SAP2_SEL_RANDOM_FRIEND, count=3, attack only (no health, unlike
    Rabbit). Seal plus four filler pets (species doesn't matter - see
    buy_any_at_turn, needed at Tier 5's 50-species uniform pool) guarantees
    the 3 random picks land entirely among the fillers, never needing to
    exclude Seal itself by chance. Spread over two turns - Seal + 4 fillers
    is 15g, over one turn's 10g budget on its own, before any food."""
    for seed in range(40):
        probe = make(ENV_ID)
        result = probe.reset(seed=seed)
        ok, result = buy_species_at_turn(probe, result, 9, SEAL_SPECIES, 0)
        if not ok:
            continue
        ok, result = buy_any_at_turn(probe, result, 9, 1)
        if not ok:
            continue
        ok, result = buy_any_at_turn(probe, result, 9, 2)
        if not ok:
            continue
        result = end_one_round(probe, result)  # -> turn 10, fresh 10g
        if result.done or result.observations[0] is None:
            continue
        ok, result = buy_any_at_turn(probe, result, 10, 3)
        if not ok:
            continue
        ok, result = buy_any_at_turn(probe, result, 10, 4)
        if not ok:
            continue
        f = result.observations[0].features
        before = [(team_attack(f, t), team_health(f, t)) for t in range(1, 5)]
        food_slot = next(
            (s for s in range(2) if shop_food_species(f, s) not in (0, PILL_FOOD)), None
        )
        if food_slot is None or gold(f) < shop_food_price(f, food_slot):
            continue
        result = probe.step(buy_food(food_slot, 0), _seat1(result))  # fed to Seal itself
        f = result.observations[0].features
        after = [(team_attack(f, t), team_health(f, t)) for t in range(1, 5)]
        buffed = sum(1 for i in range(4) if after[i][0] == before[i][0] + 1)
        health_changed = sum(1 for i in range(4) if after[i][1] != before[i][1])
        assert buffed == 3, f"expected exactly 3 of 4 fillers +1 attack, got {before} -> {after}"
        assert health_changed == 0, "Seal's buff is attack only"
        return
    pytest.fail("couldn't assemble Seal+4 fillers within 40 seeds' budgets")


def test_chocolate_gives_xp_and_stats_with_no_duplicate(env):
    """Direct XP with no merge needed - the stack-merge formula
    (sap2_stack_onto) run against a single pet: +1/+1 permanent AND +1
    experience, inferred from the scrape's own "each Chocolate/experience
    will also add +1 Attack and +1 Health"."""
    for seed in range(40):
        probe = make(ENV_ID)
        result = probe.reset(seed=seed)
        ok, result = buy_species_at_turn(probe, result, 9, OTTER_SPECIES, 0)
        if not ok:
            continue
        f = result.observations[0].features
        before_atk, before_hp, before_xp = team_attack(f, 0), team_health(f, 0), team_exp(f, 0)
        ok, result = feed_species_at_turn(probe, result, 9, CHOCOLATE_FOOD, 0)
        if not ok:
            continue
        f = result.observations[0].features
        assert team_attack(f, 0) == before_atk + 1
        assert team_health(f, 0) == before_hp + 1
        assert team_exp(f, 0) == before_xp + 1
        assert team_level(f, 0) == 1, "one point of exp is not enough for level 2 (needs 2)"
        return
    pytest.fail("couldn't get an Otter and Chocolate within 40 seeds' budgets")


def test_sushi_buffs_three_pets(env):
    """Salad Bowl's own shape (Tier 3), 3 random pets instead of 2. With
    exactly 3 pets on the team, the pick of 3 covers all of them - no
    "wasted" buff, and no randomness left for a seed search to fight.
    Filler species don't matter (see buy_any_at_turn, needed at Tier 5's
    50-species uniform pool)."""
    for seed in range(40):
        probe = make(ENV_ID)
        result = probe.reset(seed=seed)
        ok, result = buy_any_at_turn(probe, result, 9, 0)
        if not ok:
            continue
        ok, result = buy_any_at_turn(probe, result, 9, 1)
        if not ok:
            continue
        ok, result = buy_any_at_turn(probe, result, 9, 2)
        if not ok:
            continue
        # 3 pets (9g) plus Sushi (3g) is 12g - over one turn's 10g budget,
        # so the food waits for turn 10's fresh gold.
        result = end_one_round(probe, result)
        if result.done or result.observations[0] is None:
            continue
        f = result.observations[0].features
        before = [(team_attack(f, t), team_health(f, t)) for t in range(3)]
        ok, result = feed_species_at_turn(probe, result, 10, SUSHI_FOOD, 0)
        if not ok:
            continue
        f = result.observations[0].features
        after = [(team_attack(f, t), team_health(f, t)) for t in range(3)]
        assert after == [(a + 1, h + 1) for a, h in before], f"{before} -> {after}"
        return
    pytest.fail("couldn't assemble three Otters for a Sushi within 40 seeds' budgets")


def test_chili_food_grants_its_perk(env):
    """The food form of Tier 4's Chili perk (Deer's Bus already carries it
    directly) - this is the first way a player can grant it themselves."""
    for seed in range(40):
        probe = make(ENV_ID)
        result = probe.reset(seed=seed)
        ok, result = buy_species_at_turn(probe, result, 9, OTTER_SPECIES, 0)
        if not ok:
            continue
        ok, result = feed_species_at_turn(probe, result, 9, CHILI_FOOD, 0)
        if not ok:
            continue
        f = result.observations[0].features
        assert team_perk(f, 0) == PERK_CHILI
        return
    pytest.fail("couldn't get an Otter and Chili within 40 seeds' budgets")


def test_monkey_buffs_the_frontmost_friend_at_end_of_turn(env):
    """SAP2_SEL_FRONTMOST_FRIEND - always team slot 0, unlike
    SAP2_SEL_FRIENDS_AHEAD's walk relative to the firer's own position.
    Monkey bought behind an Otter at slot 0 still buffs slot 0, not
    itself."""
    for seed in range(60):
        probe = make(ENV_ID)
        result = probe.reset(seed=seed)
        ok, result = buy_species_at_turn(probe, result, 9, OTTER_SPECIES, 0)
        if not ok:
            continue
        ok, result = buy_species_at_turn(probe, result, 9, MONKEY_SPECIES, 1)
        if not ok:
            continue
        f = result.observations[0].features
        before0 = (team_attack(f, 0), team_health(f, 0))
        before1 = (team_attack(f, 1), team_health(f, 1))
        result = end_one_round(probe, result)  # -> next turn: Monkey's End Turn already fired
        if result.done or result.observations[0] is None:
            continue
        f = result.observations[0].features
        assert (team_attack(f, 0), team_health(f, 0)) == (before0[0] + 2, before0[1] + 2), \
            "the frontmost Otter (slot 0) should gain +2/+2"
        assert (team_attack(f, 1), team_health(f, 1)) == before1, "Monkey does not buff itself"
        return
    pytest.fail("couldn't assemble Otter+Monkey within 60 seeds' budgets")


def test_turkey_buffs_a_newly_bought_friend(env):
    """SAP2_TRIG_SUMMON (Horse's own trigger) + SAP2_SEL_TRIGGER_TARGET
    (also Horse's) - Turkey is this roster's second user of that exact
    combination, just PERMANENT rather than temporary (no "until next
    turn" in the scrape, unlike Horse's measured Tier-1 row). Buying a
    second pet after Turkey is already the cheapest possible exercise -
    the fires-on-every-buy plumbing (sap2_fire_friend_summoned) is already
    exercised by the Horse tests above; this just checks Turkey's own
    amounts land on it."""
    for seed in range(40):
        probe = make(ENV_ID)
        result = probe.reset(seed=seed)
        ok, result = buy_species_at_turn(probe, result, 9, TURKEY_SPECIES, 0)
        if not ok:
            continue
        ok, result = buy_species_at_turn(probe, result, 9, OTTER_SPECIES, 1)
        if not ok:
            continue
        f = result.observations[0].features
        assert team_attack(f, 1) == OTTER_BASE_ATK + 3
        assert team_health(f, 1) == OTTER_BASE_HP + 1
        return
    pytest.fail("couldn't get a Turkey and an Otter within 40 seeds' budgets")


def test_shark_gains_stats_when_a_friend_faints(env):
    """SAP2_TRIG_FRIEND_FAINTED - ANY friend fainting, anywhere on the
    team, fired as a full watcher fan-out (sap2_fire_watchers) - broader
    than Ox's single-neighbor SAP2_TRIG_FRIEND_AHEAD_FAINTED. Pill kills
    the second pet (species doesn't matter - see buy_any_at_turn, needed
    at Tier 5's 50-species uniform pool); Shark, elsewhere on the team,
    should react."""
    for seed in range(40):
        probe = make(ENV_ID)
        result = probe.reset(seed=seed)
        ok, result = buy_species_at_turn(probe, result, 9, SHARK_SPECIES, 0)
        if not ok:
            continue
        ok, result = buy_any_at_turn(probe, result, 9, 1)
        if not ok:
            continue
        f = result.observations[0].features
        before_atk, before_hp = team_attack(f, 0), team_health(f, 0)
        ok, result = feed_species_at_turn(probe, result, 9, PILL_FOOD, 1)
        if not ok:
            continue
        f = result.observations[0].features
        assert team_species(f, 1) == 0, "the fainted pet's own slot is empty"
        assert team_attack(f, 0) == before_atk + 2
        assert team_health(f, 0) == before_hp + 2
        return
    pytest.fail("couldn't get a Shark and an Otter within 40 seeds' budgets")


# --------------------------------------------------------------------------
# Tier 6 - the roster's last tier (Leopard, Boar, Tiger, Wolverine, Gorilla,
# Dragon, Mammoth, Cat, Snake, Fly + Pizza, Mushroom, Melon, Steak). Same
# search-bounded pattern as every tier above, and the same "delay every
# purchase until the shop reaches this tier" reasoning - Tier 6 opens at
# turn 11 (SAP2_ROSTER_TIER's own comment). A scenario that needs more gold
# than one turn's 10 affords a search+multi-buy for splits its buys across
# a couple of turns instead (each extra turn is one more won round against
# seat 1's empty board - fine in the small numbers these tests use, nowhere
# near TROPHIES_TO_WIN).
#
# Scope note, same shape as every tier above: Leopard (Start of Battle),
# Boar (Before Attack), Snake (a friend ahead attacking) and Wolverine
# (a running Hurt count) only ever fire in BATTLE - this file has no lever
# to construct a specific battle line-up deterministically through the
# public action API alone (see the Tier 3 section's own note on this).
# Covered instead by the 3000-seed random-legal-play smoke run (zero
# crashes; every Tier-6 species and the Zombie Fly token observed reaching
# a team) and code review. Tiger's repeat mechanic is BOTH battle-only and
# a two-pet interaction (needs a specific adjacency, not just a specific
# species) - the same scope gap, one layer deeper; also smoke-tested and
# code-reviewed only, not exercised by a deterministic test here.


def test_roster_reaches_tier_6_at_turn_11(env):
    """SAP2_ROSTER_TIER is 6 now: once the shop reaches tier 6 (turn 11),
    Tier-6 species can appear in the roll pool. Regression for the roster
    actually being wired into the pool, same as test_roster_reaches_tier_3
    covers for Tier 3."""
    for seed in range(40):
        probe = make(ENV_ID)
        result = probe.reset(seed=seed)
        result = advance_to_turn(probe, result, 11)
        if result.done:
            continue
        found = False
        for _ in range(11):
            f = result.observations[0].features
            if any(shop_pet_species(f, s) in TIER6_SPECIES for s in range(MAX_SHOP_PETS)):
                found = True
                break
            if gold(f) < 1:
                break
            result = probe.step(REROLL, _seat1(result))
        if found:
            return
    pytest.fail("no Tier-6 species turned up in 40 seeds x 10 rerolls at turn 11")


def test_dragon_buffs_friends_but_not_itself_on_tier1_buy(env):
    """SAP2_TRIG_TIER1_FRIEND_BOUGHT - Dragon's own trigger, checked
    against SAP2_SPECIES_TIER at the one call site that already knows what
    was bought (sap2_buy_pet), not a whole new per-species trigger. Reuses
    SAP2_SEL_ALL_MINIONS with effect=BUFF (Hedgehog's own selector, Tier
    2) rather than a new one - which excludes the FIRING pet (`self_slot`)
    from its own targets, so Dragon buffs every friend except itself, and
    that includes the newly bought Tier-1 pet itself, not just pets
    already on the team."""
    for seed in range(80):
        probe = make(ENV_ID)
        result = probe.reset(seed=seed)
        ok, result = buy_species_at_turn(probe, result, 11, DRAGON_SPECIES, 0)
        if not ok:
            continue
        f = result.observations[0].features
        dragon_before = (team_attack(f, 0), team_health(f, 0))
        ok, result = buy_from_set_at_turn(probe, result, 12, TIER1_SPECIES, 1)
        if not ok:
            continue
        f = result.observations[0].features
        assert (team_attack(f, 0), team_health(f, 0)) == dragon_before, "Dragon excludes itself"
        friend_before = (team_attack(f, 1), team_health(f, 1))  # already +1/+1 from its OWN buy
        ok, result = buy_from_set_at_turn(probe, result, 13, TIER1_SPECIES, 2)
        if not ok:
            continue
        f = result.observations[0].features
        assert (team_attack(f, 0), team_health(f, 0)) == dragon_before, "still excludes itself"
        assert team_attack(f, 1) == friend_before[0] + 1
        assert team_health(f, 1) == friend_before[1] + 1
        return
    pytest.fail("couldn't get a Dragon and two Tier-1 buys within 80 seeds' budgets")


def test_mammoth_faint_buffs_all_friends(env):
    """SAP2_TRIG_DEATH + the new SAP2_SEL_ALL_FRIENDS selector (shop half):
    every occupied slot on the seat, buffed by BY_LEVEL_X2 - the shop-phase
    twin of Sheep/Deer/Turtle's own Pill-kill tests above, now exercising
    the selector Mammoth needed that none of Tier 1-5's Faint abilities
    did (they all targeted a fixed count or a fixed direction, never
    "everyone")."""
    for seed in range(60):
        probe = make(ENV_ID)
        result = probe.reset(seed=seed)
        ok, result = buy_species_at_turn(probe, result, 11, MAMMOTH_SPECIES, 0)
        if not ok:
            continue
        ok, result = buy_any_at_turn(probe, result, 12, 1)
        if not ok:
            continue
        ok, result = buy_any_at_turn(probe, result, 13, 2)
        if not ok:
            continue
        f = result.observations[0].features
        before1 = (team_attack(f, 1), team_health(f, 1))
        before2 = (team_attack(f, 2), team_health(f, 2))
        ok, result = feed_species_at_turn(probe, result, 13, PILL_FOOD, 0)
        if not ok:
            continue
        f = result.observations[0].features
        assert team_species(f, 0) == 0, "Mammoth's own slot is empty"
        assert (team_attack(f, 1), team_health(f, 1)) == (before1[0] + 2, before1[1] + 2)
        assert (team_attack(f, 2), team_health(f, 2)) == (before2[0] + 2, before2[1] + 2)
        return
    pytest.fail("couldn't assemble a Mammoth and two friends within 60 seeds' budgets")


def test_fly_faint_watcher_summons_a_zombie_fly(env):
    """SAP2_TRIG_FRIEND_FAINTED + SAP2_SEL_SUMMON_SLOT - Fly is this
    roster's first FRIEND_FAINTED user that summons into the FAINTED
    pet's own vacated slot (ctx->trigger_slot), not its own or a fixed
    direction; Shark (Tier 5) reacts to the same trigger but only ever
    buffs itself (SAP2_SEL_SELF), so this is the first test exercising
    SUMMON_SLOT driven by someone ELSE's death."""
    for seed in range(60):
        probe = make(ENV_ID)
        result = probe.reset(seed=seed)
        ok, result = buy_species_at_turn(probe, result, 11, FLY_SPECIES, 0)
        if not ok:
            continue
        ok, result = buy_any_at_turn(probe, result, 12, 1)
        if not ok:
            continue
        ok, result = feed_species_at_turn(probe, result, 12, PILL_FOOD, 1)
        if not ok:
            continue
        f = result.observations[0].features
        assert team_species(f, 0) == FLY_SPECIES, "Fly itself is untouched"
        assert team_species(f, 1) == ZOMBIE_FLY_SPECIES
        assert team_attack(f, 1) == 4 and team_health(f, 1) == 4  # level 1: 4x1
        return
    pytest.fail("couldn't get a Fly, a friend and a Pill within 60 seeds' budgets")


def test_cat_doubles_a_food_purchase_stat_bonus(env):
    """Cat's passive multiplier - not a table-driven ability at all (see
    the trigger enum's closing comment), read directly off the team by
    sap2_buy_food's own `cat_mult` computation before every food's normal
    effect runs. A single level-1 Cat makes cat_mult = 1 + 1 = 2, so an
    Apple's usual +1/+1 lands as +2/+2."""
    for seed in range(60):
        probe = make(ENV_ID)
        result = probe.reset(seed=seed)
        ok, result = buy_species_at_turn(probe, result, 11, CAT_SPECIES, 0)
        if not ok:
            continue
        ok, result = buy_any_at_turn(probe, result, 12, 1)
        if not ok:
            continue
        f = result.observations[0].features
        before = (team_attack(f, 1), team_health(f, 1))
        ok, result = feed_species_at_turn(probe, result, 12, APPLE_FOOD, 1)
        if not ok:
            continue
        f = result.observations[0].features
        assert team_attack(f, 1) == before[0] + 2, "Apple's +1 doubled by Cat's x2"
        assert team_health(f, 1) == before[1] + 2
        return
    pytest.fail("couldn't get a Cat, a friend and an Apple within 60 seeds' budgets")


def test_pizza_buffs_two_of_three_pets_by_two(env):
    """Pizza is Salad Bowl's own shape (test_salad_bowl_buffs_two_random_pets
    above) with a bigger per-recipient amount - +2/+2, not +1/+1 - rather
    than a wider count; same shared switch case as Salad Bowl and Sushi
    (sap2_buy_food's SAP2_SALAD_BOWL/SAP2_SUSHI/SAP2_PIZZA case)."""
    for seed in range(60):
        probe = make(ENV_ID)
        result = probe.reset(seed=seed)
        ok, result = buy_any_at_turn(probe, result, 11, 0)
        if not ok:
            continue
        ok, result = buy_any_at_turn(probe, result, 11, 1)
        if not ok:
            continue
        ok, result = buy_any_at_turn(probe, result, 12, 2)
        if not ok:
            continue
        f = result.observations[0].features
        before = [team_attack(f, t) for t in range(3)]
        ok, result = feed_species_at_turn(probe, result, 12, PIZZA_FOOD, 0)
        if not ok:
            continue
        f = result.observations[0].features
        after = [team_attack(f, t) for t in range(3)]
        buffed = sum(1 for t in range(3) if after[t] == before[t] + 2)
        untouched = sum(1 for t in range(3) if after[t] == before[t])
        assert buffed == 2 and untouched == 1, f"expected exactly 2 of 3 buffed, got {after} vs {before}"
        return
    pytest.fail("couldn't assemble three pets for a Pizza within 60 seeds' budgets")


def test_tier6_perk_foods_grant_their_perks(env):
    """Melon, Mushroom and Steak carry no stat change of their own - each
    just leaves a perk on the fed pet, same shape as Bread/Chili's own
    tests above. Melon reuses Tier 3's Ox perk (PERK_MELON, not a new
    id); Mushroom and Steak are new perks this tier."""
    for food, expected_perk in (
        (MELON_FOOD, PERK_MELON),
        (MUSHROOM_FOOD, PERK_MUSHROOM_ID),
        (STEAK_FOOD, PERK_STEAK_ID),
    ):
        for seed in range(40):
            probe = make(ENV_ID)
            result = probe.reset(seed=seed)
            ok, result = buy_any_at_turn(probe, result, 11, 0)
            if not ok:
                continue
            ok, result = feed_species_at_turn(probe, result, 12, food, 0)
            if not ok:
                continue
            f = result.observations[0].features
            assert team_perk(f, 0) == expected_perk
            break
        else:
            pytest.fail(f"couldn't feed food {food} within 40 seeds' budgets")
