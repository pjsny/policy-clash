from __future__ import annotations

import numpy as np
import pytest

from policyclash_envs import Outcome, Termination, make
from policyclash_envs.sap import MAX_TICKS, NUM_ACTIONS, OBS_FLOATS, STARTING_GOLD

ENV_ID = "sap-v1"

END_TURN = 0
BUY_PET_BASE = 1
SELL_BASE = 4
COMBINE_BASE = 9
REROLL = 19
REPOSITION_BASE = 20
BUY_FOOD_BASE = 30

# Species one-hot order in the observation (index 0 is "empty"); matches
# docs/envs/sap-v1.md's appendix and SAP_BASE_ATK/SAP_BASE_HP in sap.h.
ANT, BEAVER, CRICKET, DUCK, FISH, HORSE, MOSQUITO, OTTER, PIG, PIGEON = range(1, 11)
BASE_ATK = {ANT: 2, BEAVER: 3, CRICKET: 1, DUCK: 2, FISH: 2, HORSE: 2, MOSQUITO: 2, OTTER: 1, PIG: 4, PIGEON: 3}
BASE_HP = {ANT: 2, BEAVER: 2, CRICKET: 3, DUCK: 2, FISH: 3, HORSE: 1, MOSQUITO: 2, OTTER: 4, PIG: 1, PIGEON: 2}

# Observation offsets, mirroring sap.h's SAP_TEAM_SLOT_FLOATS etc.
TEAM_SLOT_WIDTH = 19  # 13 species one-hot + attack + health + 3 level one-hot + honey
SHOP_PET_SLOT_WIDTH = 12  # 11 species one-hot + hp bonus
TEAM_BASE = 1  # after gold
SHOP_PET_BASE = TEAM_BASE + 5 * TEAM_SLOT_WIDTH


@pytest.fixture
def env():
    return make(ENV_ID)


# A seat that has ended is not asked to act; the interface's own rule is that
# its argument is ignored rather than validated. This deliberately
# out-of-range sentinel keeps that promise under test wherever it's passed
# for an already-ended seat.
IGNORED = NUM_ACTIONS + 99


def team_species(features: np.ndarray, slot: int) -> int:
    base = TEAM_BASE + slot * TEAM_SLOT_WIDTH
    return int(np.argmax(features[base : base + 13]))


def team_stats(features: np.ndarray, slot: int) -> tuple[int, int, int]:
    base = TEAM_BASE + slot * TEAM_SLOT_WIDTH
    attack = int(features[base + 13])
    health = int(features[base + 14])
    level_onehot = features[base + 15 : base + 18]
    level = int(np.argmax(level_onehot)) + 1 if level_onehot.any() else 0
    return attack, health, level


def shop_species(features: np.ndarray, slot: int) -> int:
    base = SHOP_PET_BASE + slot * SHOP_PET_SLOT_WIDTH
    return int(np.argmax(features[base : base + 11]))


def find_shop_slot(features: np.ndarray, species: int) -> int | None:
    for slot in range(3):
        if shop_species(features, slot) == species:
            return slot
    return None


def find_seed_with_shop(seat0_species: int, seat1_species: int, max_seed: int = 2000) -> int:
    """A seed whose *initial* shop roll offers `seat0_species` to seat 0 and
    `seat1_species` to seat 1, found by search rather than by modelling the
    RNG in Python. Reasonable here (unlike tron-duel's closed-form spawn
    model): the thing under test is the ability/battle graph, not the RNG,
    so a black-box search for a convenient starting shop is the cheaper and
    equally rigorous source of truth.
    """
    probe = make(ENV_ID)
    for seed in range(max_seed):
        result = probe.reset(seed=seed)
        f0, f1 = result.observations[0].features, result.observations[1].features
        if find_shop_slot(f0, seat0_species) is not None and find_shop_slot(f1, seat1_species) is not None:
            return seed
    raise AssertionError(f"no seed under {max_seed} offers ({seat0_species}, {seat1_species})")


def find_seed_with_shop_duplicate(seat: int = 0, max_seed: int = 2000) -> int:
    """A seed whose initial shop roll offers the same species in two of
    `seat`'s three slots, for testing combine without burning gold on
    rerolls hoping for a duplicate."""
    probe = make(ENV_ID)
    for seed in range(max_seed):
        result = probe.reset(seed=seed)
        species = [shop_species(result.observations[seat].features, s) for s in range(3)]
        if len(set(species)) < 3:
            return seed
    raise AssertionError(f"no seed under {max_seed} gives seat {seat} a duplicate shop offer")


def end_both(env, result):
    """Step both seats to END_TURN repeatedly until the episode ends,
    tolerating a seat that already ended (its argument is ignored)."""
    while not result.done:
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
    assert spec.simultaneous
    assert spec.stochastic_dynamics


def test_reset_both_seats_get_full_gold_and_five_legal_actions(env):
    result = env.reset(seed=0)
    assert not result.done
    for obs in result.observations:
        assert obs is not None
        assert obs.features.shape == (OBS_FLOATS,)
        assert obs.features[0] == STARTING_GOLD
        # END_TURN + 3x BUY_PET (shop full, gold >= 3, team has room) +
        # REROLL (gold >= 1); nothing else is legal against an empty team.
        assert obs.legal_actions.sum() == 5
        assert obs.legal_actions[END_TURN]
        assert obs.legal_actions[REROLL]
        assert not obs.legal_actions[SELL_BASE]


def test_both_end_turn_immediately_is_a_draw(env):
    env.reset(seed=0)
    result = env.step(END_TURN, END_TURN)
    assert result.done
    assert result.outcome is Outcome.DRAW
    assert result.termination is Termination.NATURAL
    assert result.observations == (None, None)


def test_buy_places_pet_at_base_stats_and_consumes_gold(env):
    result = env.reset(seed=0)
    species = shop_species(result.observations[0].features, 0)
    result = env.step(BUY_PET_BASE + 0, END_TURN)
    f0 = result.observations[0].features
    assert f0[0] == STARTING_GOLD - 3
    assert team_species(f0, 0) == species
    assert team_stats(f0, 0) == (BASE_ATK[species], BASE_HP[species], 1)
    # Bought pet fills the leftmost slot; the rest stay empty.
    for slot in range(1, 5):
        assert team_species(f0, slot) == 0


def test_sell_refunds_one_gold_at_level_one(env):
    result = env.reset(seed=0)
    result = env.step(BUY_PET_BASE + 0, END_TURN)
    gold_after_buy = result.observations[0].features[0]
    result = env.step(SELL_BASE + 0, IGNORED if result.observations[1] is None else END_TURN)
    f0 = result.observations[0].features
    assert f0[0] == gold_after_buy + 1
    assert team_species(f0, 0) == 0


def test_combine_takes_max_plus_one_not_a_sum_and_levels_up(env):
    seed = find_seed_with_shop_duplicate(seat=0)
    env = make(ENV_ID)
    result = env.reset(seed=seed)
    species = [shop_species(result.observations[0].features, s) for s in range(3)]
    dup = next(sp for sp in species if species.count(sp) >= 2)
    slots = [s for s in range(3) if species[s] == dup]

    result = env.step(BUY_PET_BASE + slots[0], END_TURN)
    seat1_action = IGNORED if result.observations[1] is None else END_TURN
    result = env.step(BUY_PET_BASE + slots[1], seat1_action)

    seat1_action = IGNORED if result.observations[1] is None else END_TURN
    result = env.step(COMBINE_BASE + 0, seat1_action)  # pair (0, 1)
    f0 = result.observations[0].features
    base_atk, base_hp = BASE_ATK[dup], BASE_HP[dup]
    assert team_stats(f0, 0) == (max(base_atk, base_atk) + 1, max(base_hp, base_hp) + 1, 2)
    assert team_species(f0, 1) == 0  # slot 1 emptied into slot 0


def test_reroll_costs_one_gold_and_reshapes_shop(env):
    result = env.reset(seed=0)
    before = [shop_species(result.observations[0].features, s) for s in range(3)]
    result = env.step(REROLL, END_TURN)
    f0 = result.observations[0].features
    assert f0[0] == STARTING_GOLD - 1
    after = [shop_species(f0, s) for s in range(3)]
    assert before != after


def test_reposition_swaps_team_slots(env):
    result = env.reset(seed=0)
    sp0 = shop_species(result.observations[0].features, 0)
    result = env.step(BUY_PET_BASE + 0, END_TURN)
    seat1_action = IGNORED if result.observations[1] is None else END_TURN
    result = env.step(REPOSITION_BASE + 0, seat1_action)  # swap slots (0, 1)
    f0 = result.observations[0].features
    assert team_species(f0, 0) == 0
    assert team_species(f0, 1) == sp0


def test_apple_buffs_the_fed_pet(env):
    result = env.reset(seed=0)
    # Buy whatever seat 0's shop offers, then feed it whatever food is on
    # sale - Apple gives +1/+1, Honey sets the perk flag with no stat change.
    species = shop_species(result.observations[0].features, 0)
    result = env.step(BUY_PET_BASE + 0, END_TURN)
    seat1_action = IGNORED if result.observations[1] is None else END_TURN
    before = team_stats(result.observations[0].features, 0)
    result = env.step(BUY_FOOD_BASE + 0, seat1_action)
    f0 = result.observations[0].features
    after = team_stats(f0, 0)
    honey_flag = f0[TEAM_BASE + 18]
    # Either it was Apple (+1/+1, no perk) or Honey (no stat change, perk set).
    assert (after == (before[0] + 1, before[1] + 1, before[2]) and honey_flag == 0) or (
        after == before and honey_flag == 1
    )


def test_illegal_action_forfeits_to_the_other_seat(env):
    env.reset(seed=0)
    result = env.step(NUM_ACTIONS, END_TURN)
    assert result.done
    assert result.outcome is Outcome.PLAYER_1
    assert result.termination is Termination.ILLEGAL_ACTION


def test_both_illegal_same_tick_is_a_draw(env):
    env.reset(seed=0)
    result = env.step(NUM_ACTIONS, -1)
    assert result.done
    assert result.outcome is Outcome.DRAW
    assert result.termination is Termination.ILLEGAL_ACTION


def test_masked_illegal_action_forfeits(env):
    # Selling an empty team slot is masked out at reset.
    env.reset(seed=0)
    result = env.step(SELL_BASE + 0, END_TURN)
    assert result.done
    assert result.outcome is Outcome.PLAYER_1
    assert result.termination is Termination.ILLEGAL_ACTION


def test_ended_seats_argument_is_ignored_not_validated(env):
    # Seat 0 ends now; seat 1 keeps going. An out-of-range action fed to
    # seat 0 on a later tick, while it is no longer being asked to act,
    # must not forfeit - the interface's own rule for a non-acting seat.
    env.reset(seed=0)
    result = env.step(END_TURN, REROLL)
    assert result.observations[0] is None
    assert result.observations[1] is not None
    result = env.step(IGNORED, END_TURN)
    assert result.done
    assert result.termination is not Termination.ILLEGAL_ACTION


def test_budget_forces_end_after_twenty_actions(env):
    result = env.reset(seed=0)
    result = env.step(BUY_PET_BASE + 0, END_TURN)  # seat0: 1 action so far
    seat1_done = result.observations[1] is None
    for _ in range(19):  # 19 more free actions -> 20 total
        a1 = IGNORED if seat1_done else END_TURN
        result = env.step(REPOSITION_BASE + 0, a1)
        if result.done:
            break
    assert result.done
    assert len(env.replay()) // 2 == 20
    assert len(env.replay()) // 2 <= MAX_TICKS


def test_step_limit_is_unreachable(env):
    # The action budget forces both seats to `ended` by MAX_TICKS at the
    # latest, so nothing in this env should ever produce STEP_LIMIT. Drive
    # a full-budget episode and confirm the termination is never STEP_LIMIT.
    result = env.reset(seed=0)
    result = env.step(BUY_PET_BASE + 0, BUY_PET_BASE + 0)
    while not result.done:
        a0 = REPOSITION_BASE + 0 if result.observations[0] is not None else IGNORED
        a1 = REPOSITION_BASE + 0 if result.observations[1] is not None else IGNORED
        result = env.step(a0, a1)
    assert result.termination is not Termination.STEP_LIMIT


def test_deterministic_given_same_seed(env):
    def play(seed):
        e = make(ENV_ID)
        result = e.reset(seed=seed)
        result = e.step(BUY_PET_BASE + 0, BUY_PET_BASE + 0)
        result = end_both(e, result)
        return e.replay(), result.outcome

    a = play(seed=123)
    b = play(seed=123)
    assert a == b


def test_different_seed_gives_a_different_shop_roll(env):
    r1 = make(ENV_ID).reset(seed=1)
    r2 = make(ENV_ID).reset(seed=2)
    species_1 = [shop_species(r1.observations[0].features, s) for s in range(3)]
    species_2 = [shop_species(r2.observations[0].features, s) for s in range(3)]
    assert species_1 != species_2


def test_otter_outlasts_horse_one_on_one(env):
    """A hand-computable battle with no randomness in its outcome: Otter
    (1/4) vs Horse (2/1). Horse's attack exactly kills nothing of Otter's
    (4 - 2 = 2 > 0) while Otter's attack exactly kills Horse (1 - 1 = 0), so
    Horse's side is empty after the first exchange and Otter's side still has
    a live pet - a clean single-winner case, not a double-KO, which is the
    trap most hand-built small-team fights fall into (see connect4's own
    test file for the same lesson about hand-built terminal positions)."""
    seed = find_seed_with_shop(OTTER, HORSE)
    result = env.reset(seed=seed)
    slot0 = find_shop_slot(result.observations[0].features, OTTER)
    slot1 = find_shop_slot(result.observations[1].features, HORSE)
    result = env.step(BUY_PET_BASE + slot0, BUY_PET_BASE + slot1)
    result = end_both(env, result)
    assert result.outcome is Outcome.PLAYER_0
    assert result.termination is Termination.NATURAL


def test_replay_is_flat_two_per_tick_and_reflects_ignored_ticks(env):
    env.reset(seed=0)
    r = env.step(END_TURN, REROLL)
    r = env.step(IGNORED, END_TURN)
    replay = env.replay()
    assert replay == [END_TURN, REROLL, IGNORED, END_TURN]
    assert len(replay) == 2 * 2
