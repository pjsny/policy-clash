from __future__ import annotations

import numpy as np
import pytest

from policyclash_envs import make
from policyclash_envs.base import Outcome, Termination
from policyclash_envs.tron_duel import ACTIONS, MAX_TICKS, PLANES, SIZE

ENV_ID = "tron-duel-v1"

LEFT, STRAIGHT, RIGHT = 0, 1, 2

# Facing 0 = N, 1 = E, 2 = S, 3 = W, with y = 0 the top row.
DX = (0, 1, 0, -1)
DY = (-1, 0, 1, 0)

_MASK64 = (1 << 64) - 1


@pytest.fixture
def env():
    return make(ENV_ID)


# --------------------------------------------------------------------------
# An outside source of truth for the board frame.
#
# The env is exactly rotation-equivariant, so an observation reveals the board
# only up to a quarter turn: absolute headings are unobservable from Python by
# design. Board-frame assertions therefore need the start position, and in a
# bit-reproducible env the seeded draw is a frozen contract worth pinning
# anyway. Straight play is then two straight lines, which is the one action
# sequence that can be modelled exactly without a rules engine.
# --------------------------------------------------------------------------


def splitmix64(state: int) -> tuple[int, int]:
    state = (state + 0x9E3779B97F4A7C15) & _MASK64
    z = ((state ^ (state >> 30)) * 0xBF58476D1CE4E5B9) & _MASK64
    z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & _MASK64
    return state, z ^ (z >> 31)


def start_position(seed: int) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    """The (x, y, facing) each seat spawns with, as td_reset draws it."""
    state = seed
    while True:
        coords = []
        for _ in range(4):
            state, draw = splitmix64(state)
            coords.append(draw % (SIZE - 2) + 1)
        x0, y0, x1, y1 = coords
        if abs(x0 - x1) + abs(y0 - y1) >= 4:
            break
    state, draw = splitmix64(state)
    facing_0 = draw % 4
    state, draw = splitmix64(state)
    facing_1 = draw % 4
    return (x0, y0, facing_0), (x1, y1, facing_1)


def straight_duel(seed: int) -> tuple[int, tuple[str | None, str | None]]:
    """Model both seats driving straight: the crash tick, and why each seat
    crashed on it."""
    (x0, y0, facing_0), (x1, y1, facing_1) = start_position(seed)
    heads = [(x0, y0), (x1, y1)]
    trails = [{(x0, y0)}, {(x1, y1)}]
    facing = (facing_0, facing_1)

    for tick in range(1, 2 * MAX_TICKS):
        targets = [
            (heads[s][0] + DX[facing[s]], heads[s][1] + DY[facing[s]]) for s in (0, 1)
        ]
        cause: list[str | None] = [None, None]
        for seat in (0, 1):
            x, y = targets[seat]
            if not (0 <= x < SIZE and 0 <= y < SIZE):
                cause[seat] = "wall"
            elif targets[seat] in trails[1 - seat]:
                cause[seat] = "opponent_trail"
        if cause == [None, None] and targets[0] == targets[1]:
            cause = ["same_cell", "same_cell"]
        # A mutual swap reads as two opponent-trail crashes; it is named apart
        # because it is the case a naive implementation lets pass through.
        if targets[0] == heads[1] and targets[1] == heads[0]:
            cause = ["swap", "swap"]
        if cause != [None, None]:
            return tick, (cause[0], cause[1])
        for seat in (0, 1):
            heads[seat] = targets[seat]
            trails[seat].add(targets[seat])
    raise AssertionError("straight play did not crash")


def find_seed(causes: tuple[str | None, str | None], limit: int = 600) -> int:
    for seed in range(limit):
        if straight_duel(seed)[1] == causes:
            return seed
    raise AssertionError(f"no seed below {limit} produces {causes}")


def closes_a_clean_loop(seed: int) -> bool:
    """Seat 0 can turn right four times, closing a 2x2 loop back onto its own
    spawn, without seat 1's first four straight cells getting in the way."""
    (x0, y0, facing_0), (x1, y1, facing_1) = start_position(seed)
    box = [(x0, y0)]
    x, y = x0, y0
    for turn in (1, 2, 3):
        facing = (facing_0 + turn) % 4
        x, y = x + DX[facing], y + DY[facing]
        box.append((x, y))

    line = [(x1, y1)]
    x, y = x1, y1
    for _ in range(4):
        x, y = x + DX[facing_1], y + DY[facing_1]
        if not (0 <= x < SIZE and 0 <= y < SIZE):
            return False
        line.append((x, y))
    return not set(box) & set(line)


def rotate(plane: np.ndarray, facing: int) -> np.ndarray:
    """A board plane as the seat with that heading sees it.

    A counter-clockwise quarter turn takes an eastward heading to an upward
    one, so facing E needs one, S two, W three. Written with rot90 rather than
    index algebra so it states the rotation independently instead of
    transcribing the one in tron_duel.h.
    """
    return np.rot90(plane, facing)


def plane_of(cells) -> np.ndarray:
    plane = np.zeros((SIZE, SIZE), dtype=np.float32)
    for x, y in cells:
        plane[y, x] = 1.0
    return plane


def head_cell(observation, plane: int = 2) -> tuple[int, int]:
    """Where a head plane marks its single cell, as (row, column)."""
    rows = np.argwhere(observation.features[plane] == 1.0)
    assert len(rows) == 1
    return int(rows[0][0]), int(rows[0][1])


def play_out(env, seed: int, action_0: int = STRAIGHT, action_1: int = STRAIGHT):
    result = env.reset(seed=seed)
    ticks = 0
    while not result.done:
        result = env.step(action_0, action_1)
        ticks += 1
    return result, ticks


def test_spec_describes_a_simultaneous_env(env):
    assert env.spec.simultaneous
    assert env.spec.actors_per_tick == 2
    assert env.spec.obs_shape == (PLANES, SIZE, SIZE)
    assert env.spec.max_episode_steps == MAX_TICKS
    assert not env.spec.stochastic_dynamics


def test_registry_resolves_the_qualified_id():
    assert make(ENV_ID).spec.qualified_id == ENV_ID


def test_driving_into_a_wall_loses(env):
    """Every action is legal, so a wall is a losing move and not a forfeit."""
    seed = find_seed(("wall", None))
    result, ticks = play_out(env, seed)

    assert ticks == straight_duel(seed)[0]
    assert result.outcome is Outcome.PLAYER_1
    assert result.termination is Termination.NATURAL


def test_wall_crash_is_charged_to_the_seat_that_crashed(env):
    seed = find_seed((None, "wall"))
    result, _ = play_out(env, seed)

    assert result.outcome is Outcome.PLAYER_0
    assert result.termination is Termination.NATURAL


def test_driving_into_your_own_trail_loses(env):
    """Four right turns close a 2x2 loop back onto the seat's own spawn cell,
    and the seed is chosen so seat 1 drives straight past without touching
    it: the only thing seat 0 can hit is itself."""
    seed = next(seed for seed in range(600) if closes_a_clean_loop(seed))

    result = env.reset(seed=seed)
    for _ in range(3):
        result = env.step(RIGHT, STRAIGHT)
        assert not result.done
    result = env.step(RIGHT, STRAIGHT)

    assert result.outcome is Outcome.PLAYER_1
    assert result.termination is Termination.NATURAL
    assert len(env.replay()) == 2 * 4


def test_driving_into_the_opponents_trail_loses(env):
    seed = find_seed(("opponent_trail", None))
    result, ticks = play_out(env, seed)

    assert ticks == straight_duel(seed)[0]
    assert result.outcome is Outcome.PLAYER_1
    assert result.termination is Termination.NATURAL


def test_both_seats_entering_one_cell_is_a_draw(env):
    seed = find_seed(("same_cell", "same_cell"))
    result, ticks = play_out(env, seed)

    assert ticks == straight_duel(seed)[0]
    assert result.outcome is Outcome.DRAW
    assert result.termination is Termination.NATURAL


def test_head_on_swap_is_terminal(env):
    """Each seat moving into the cell the other is vacating kills both.

    The failure this guards against is a silent pass-through, where two cycles
    trade places because each target looked empty once the other had moved.
    """
    seed = find_seed(("swap", "swap"))
    crash_tick = straight_duel(seed)[0]

    result = env.reset(seed=seed)
    for _ in range(crash_tick - 1):
        result = env.step(STRAIGHT, STRAIGHT)
        assert not result.done

    result = env.step(STRAIGHT, STRAIGHT)
    assert result.done
    assert result.outcome is Outcome.DRAW
    assert result.termination is Termination.NATURAL


def test_out_of_range_action_forfeits_to_the_other_seat(env):
    env.reset(seed=0)
    result = env.step(ACTIONS, STRAIGHT)
    assert result.outcome is Outcome.PLAYER_1
    assert result.termination is Termination.ILLEGAL_ACTION

    env.reset(seed=0)
    result = env.step(STRAIGHT, -1)
    assert result.outcome is Outcome.PLAYER_0
    assert result.termination is Termination.ILLEGAL_ACTION


def test_both_seats_out_of_range_is_a_draw(env):
    env.reset(seed=0)
    result = env.step(-5, ACTIONS + 7)

    assert result.outcome is Outcome.DRAW
    assert result.termination is Termination.ILLEGAL_ACTION


def test_action_beyond_int_range_forfeits_rather_than_raising(env):
    """An action too large for a C int is still just a bad action, so it is
    clamped to a forfeiting sentinel instead of becoming an exception."""
    env.reset(seed=0)
    result = env.step(1 << 40, STRAIGHT)

    assert result.outcome is Outcome.PLAYER_1
    assert result.termination is Termination.ILLEGAL_ACTION


def test_forfeit_is_recorded_raw_in_the_replay(env):
    env.reset(seed=0)
    env.step(9, STRAIGHT)

    assert env.replay() == [9, STRAIGHT]


def test_both_seats_act_every_ongoing_tick_and_neither_once_done(env):
    seed = find_seed(("opponent_trail", None))
    result = env.reset(seed=seed)
    assert not result.done
    assert all(observation is not None for observation in result.observations)

    while not result.done:
        result = env.step(STRAIGHT, STRAIGHT)
        if result.done:
            assert result.observations == (None, None)
        else:
            assert all(observation is not None for observation in result.observations)


def test_legal_mask_is_all_true(env):
    result = env.reset(seed=0)
    for observation in result.observations:
        assert observation.legal_actions.tolist() == [True] * ACTIONS


def test_head_planes_mark_exactly_one_cell_each(env):
    for seed in range(20):
        result = env.reset(seed=seed)
        for observation in result.observations:
            assert observation.features[2].sum() == 1.0
            assert observation.features[3].sum() == 1.0


def test_seats_see_the_same_board_from_rotated_frames(env):
    """Seat 0's own-trail plane is seat 1's opponent-trail plane, turned by
    the difference between the two headings."""
    for seed in range(30):
        (_, _, facing_0), (_, _, facing_1) = start_position(seed)

        result = env.reset(seed=seed)
        # Straight play leaves both headings alone, so the rotation between
        # the two frames stays the one the spawn drew.
        for _ in range(2):
            stepped = env.step(STRAIGHT, STRAIGHT)
            if stepped.done:
                break
            result = stepped

        own_0 = result.observations[0].features[0]
        opponent_1 = result.observations[1].features[1]
        assert own_0.sum() >= 1.0
        np.testing.assert_array_equal(
            rotate(own_0, (facing_1 - facing_0) % 4), opponent_1
        )


def test_egocentric_frame_matches_a_hand_built_board(env):
    """Whole observations rebuilt from the board frame, for all four headings.

    After k straight ticks the board is two straight lines, which this test
    lays out itself and rotates with rot90, so the comparison checks the
    rotation table in tron_duel.h against an independently derived rotation.
    """
    covered = set()
    for seed in range(120):
        (x0, y0, facing_0), (x1, y1, facing_1) = start_position(seed)
        ticks = min(3, straight_duel(seed)[0] - 1)
        if ticks < 1:
            continue

        result = env.reset(seed=seed)
        for _ in range(ticks):
            result = env.step(STRAIGHT, STRAIGHT)
        assert not result.done

        facings = (facing_0, facing_1)
        trails = [
            [(x0 + DX[facing_0] * k, y0 + DY[facing_0] * k) for k in range(ticks + 1)],
            [(x1 + DX[facing_1] * k, y1 + DY[facing_1] * k) for k in range(ticks + 1)],
        ]
        heads = [trails[0][-1], trails[1][-1]]

        for seat in (0, 1):
            other = 1 - seat
            expected = np.stack(
                [
                    rotate(plane_of(trails[seat]), facings[seat]),
                    rotate(plane_of(trails[other]), facings[seat]),
                    rotate(plane_of([heads[seat]]), facings[seat]),
                    rotate(plane_of([heads[other]]), facings[seat]),
                ]
            )
            np.testing.assert_array_equal(result.observations[seat].features, expected)
            covered.add(facings[seat])

    assert covered == {0, 1, 2, 3}


def test_going_straight_moves_the_head_one_row_up(env):
    """In its own frame a seat always moves up the board, whatever it faces.

    This is the property that fixes the rotation's direction: a frame rotated
    the wrong way would send an eastbound seat's head downwards.
    """
    for seed in range(40):
        result = env.reset(seed=seed)
        before = result.observations
        stepped = env.step(STRAIGHT, STRAIGHT)
        if stepped.done:
            continue

        for seat in (0, 1):
            row, column = head_cell(before[seat])
            assert head_cell(stepped.observations[seat]) == (row - 1, column)

            grown = before[seat].features[0].copy()
            grown[row - 1, column] = 1.0
            np.testing.assert_array_equal(
                stepped.observations[seat].features[0], grown
            )


def test_a_turn_rotates_the_frame_by_one_quarter(env):
    """Undoing the turn must give back the previous frame plus one cell.

    A right turn adds a heading, so rotating the new frame three more quarters
    lands back on the old one; the new head sits one column right of the old
    head there, because right in the old frame is right on the screen.
    """
    for turn, undo, column_step in ((RIGHT, 3, 1), (LEFT, 1, -1)):
        for seed in range(40):
            result = env.reset(seed=seed)
            for _ in range(3):
                before = result.observations[0]
                result = env.step(turn, STRAIGHT)
                if result.done:
                    break

                row, column = head_cell(before)
                grown = before.features[0].copy()
                grown[row, column + column_step] = 1.0
                np.testing.assert_array_equal(
                    rotate(result.observations[0].features[0], undo), grown
                )


def test_same_seed_replays_identically(env):
    first, _ = play_out(env, 7)
    replay = env.replay()

    other = make(ENV_ID)
    second, _ = play_out(other, 7)

    assert other.replay() == replay
    assert second.outcome is first.outcome
    assert second.termination is first.termination


def test_seeds_give_different_start_positions(env):
    starts = {
        env.reset(seed=seed).observations[0].features.tobytes() for seed in range(20)
    }
    assert len(starts) > 1


def test_replay_holds_two_entries_per_tick(env):
    seed = find_seed(("wall", None))
    _, ticks = play_out(env, seed)
    replay = env.replay()

    assert len(replay) == 2 * ticks
    assert replay[::2] == [STRAIGHT] * ticks
    assert replay[1::2] == [STRAIGHT] * ticks


def test_fixed_policies_always_terminate_naturally(env):
    """The board fills, so a crash is forced and the tick bound is never
    reached: there is no step-limit path to exercise. Turning policies are the
    stress case, since they survive far longer than driving at a wall."""
    pattern_0 = [STRAIGHT, STRAIGHT, RIGHT, STRAIGHT, LEFT, STRAIGHT]
    pattern_1 = [STRAIGHT, LEFT, STRAIGHT, STRAIGHT, RIGHT]

    for seed in range(300):
        result = env.reset(seed=seed)
        ticks = 0
        while not result.done:
            result = env.step(
                pattern_0[ticks % len(pattern_0)], pattern_1[ticks % len(pattern_1)]
            )
            ticks += 1

        assert result.termination is Termination.NATURAL
        assert 0 < ticks <= env.spec.max_episode_steps
        assert len(env.replay()) == 2 * ticks


def test_step_after_done_raises(env):
    play_out(env, find_seed(("wall", None)))
    with pytest.raises(RuntimeError):
        env.step(STRAIGHT, STRAIGHT)


def test_unknown_env_id_names_what_is_registered():
    with pytest.raises(KeyError, match=ENV_ID):
        make("tron-duel-v99")
