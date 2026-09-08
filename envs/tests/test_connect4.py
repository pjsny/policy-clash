from __future__ import annotations

import numpy as np
import pytest

from policyclash_envs import Outcome, Termination, make
from policyclash_envs.connect4 import COLS, ROWS

ENV_ID = "connect4-v1"

# A real 42-move game that fills the board with no line of four. Found by
# search, not by hand: every obvious hand-built ordering fills a column with
# alternating play, which is a vertical four.
DRAWN_GAME = [
    4, 6, 1, 3, 6, 1, 1, 2, 5, 6, 1, 0, 2, 2, 0,
    4, 6, 3, 4, 3, 0, 5, 0, 0, 5, 2, 2, 4, 1, 1,
    4, 4, 3, 6, 2, 0, 6, 3, 5, 3, 5, 5,
]

# Column 1 is the first to fill, on move index 29.
FILLS_COLUMN_1 = DRAWN_GAME[:30]

# Fed to the seat that is not on move. The contract says a non-acting seat's
# action is ignored rather than validated, so passing something that would
# forfeit if it were read keeps that promise under test everywhere.
IGNORED = COLS + 99


@pytest.fixture
def env():
    return make(ENV_ID)


def seat_to_move(result):
    seats = [seat for seat, obs in enumerate(result.observations) if obs is not None]
    assert len(seats) == 1, "connect4 is turn-based: exactly one seat acts per tick"
    return seats[0]


def mover_obs(result):
    return result.observations[seat_to_move(result)]


def advance(env, result, move):
    """Step the seat `result` put on move, garbage for the other seat."""
    actions = [IGNORED, IGNORED]
    actions[seat_to_move(result)] = move
    return env.step(*actions)


def play(env, moves):
    result = env.reset(seed=0)
    for move in moves:
        result = advance(env, result, move)
    return result


def test_vertical_four_wins(env):
    result = play(env, [0, 1, 0, 1, 0, 1, 0])
    assert result.outcome is Outcome.PLAYER_0
    assert result.termination is Termination.NATURAL


def test_horizontal_four_wins(env):
    result = play(env, [0, 0, 1, 1, 2, 2, 3])
    assert result.outcome is Outcome.PLAYER_0


def test_diagonal_four_wins(env):
    result = play(env, [0, 1, 1, 2, 2, 3, 2, 3, 3, 0, 3])
    assert result.outcome is Outcome.PLAYER_0


def test_win_does_not_wrap_between_columns(env):
    """A run of four crossing a column boundary is not a win.

    The sentinel row exists to stop this, and it is the first thing a naive
    bitboard gets wrong. The drawn game fills every column, so if wins wrapped
    it would terminate early instead of reaching 42 moves.
    """
    result = play(env, DRAWN_GAME)
    assert result.outcome is Outcome.DRAW


def test_full_board_is_a_draw(env):
    result = play(env, DRAWN_GAME)
    assert result.done
    assert result.observations == (None, None)
    assert result.outcome is Outcome.DRAW
    assert result.termination is Termination.NATURAL
    assert len(env.replay()) == COLS * ROWS


def test_exactly_one_seat_acts_and_the_seats_alternate(env):
    """The invariant the runner leans on, on the turn-based side.

    A runner reads `observations` to learn who owes an action and never tracks
    turn order itself, which is what lets the same loop drive a simultaneous
    env where both entries are set.
    """
    result = env.reset(seed=0)
    acting = []
    for move in [0, 1, 2, 3, 4]:
        assert sum(obs is not None for obs in result.observations) == 1
        acting.append(seat_to_move(result))
        result = advance(env, result, move)

    assert acting == [0, 1, 0, 1, 0]


def test_illegal_action_forfeits(env):
    result = play(env, FILLS_COLUMN_1)
    result = advance(env, result, 1)  # column 1 is full
    assert result.termination is Termination.ILLEGAL_ACTION
    assert result.outcome is Outcome.PLAYER_1  # 30 moves played, so player 0 moved


def test_out_of_range_action_forfeits(env):
    start = env.reset(seed=0)
    assert seat_to_move(start) == 0

    result = env.step(COLS, IGNORED)
    assert result.outcome is Outcome.PLAYER_1
    assert result.termination is Termination.ILLEGAL_ACTION


def test_non_movers_action_is_ignored_not_validated(env):
    """Seat 1 is handed a forfeiting action while seat 0 is on move."""
    env.reset(seed=0)
    result = env.step(3, COLS + 5)
    assert not result.done
    assert seat_to_move(result) == 1


def test_observation_is_from_the_movers_perspective(env):
    start = env.reset(seed=0)
    assert start.observations[0] is not None  # seat 0 opens
    assert not start.observations[0].features.any()

    result = advance(env, start, 3)
    # Player 0's piece reads as -1 to player 1, who is now on move.
    assert result.observations[0] is None
    assert result.observations[1].features[3 * ROWS] == -1.0


def test_legal_mask_closes_a_full_column(env):
    result = play(env, FILLS_COLUMN_1)
    legal = mover_obs(result).legal_actions
    assert not legal[1]
    assert legal.sum() == COLS - 1


def test_replay_reproduces_the_episode(env):
    moves = [3, 3, 4, 4, 5, 5, 6]
    first = play(env, moves)
    recorded = env.replay()

    second = play(make(ENV_ID), recorded)

    # One entry per tick, which is the flat contract at actors_per_tick == 1.
    assert recorded == moves
    assert second.outcome is first.outcome


def test_seed_does_not_change_the_episode():
    """Dynamics are deterministic, so two seeds must agree bit for bit.

    The runner records a seed on every match. This env ignores it, and that
    has to stay true or replays stop reproducing.
    """
    a, b = make(ENV_ID), make(ENV_ID)
    ra, rb = a.reset(seed=1), b.reset(seed=999_999)

    for move in [3, 3, 2, 4, 1, 0, 5]:
        ra, rb = advance(a, ra, move), advance(b, rb, move)
        assert ra.done == rb.done
        assert ra.outcome is rb.outcome
        for oa, ob in zip(ra.observations, rb.observations):
            assert (oa is None) == (ob is None)
            if oa is not None:
                assert np.array_equal(oa.features, ob.features)

    assert a.replay() == b.replay()


def test_step_after_done_raises(env):
    play(env, [0, 1, 0, 1, 0, 1, 0])
    with pytest.raises(RuntimeError):
        env.step(2, 2)


def test_unknown_env_id_names_what_is_registered():
    with pytest.raises(KeyError, match=ENV_ID):
        make("connect4-v99")
