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


@pytest.fixture
def env():
    return make(ENV_ID)


def play(env, moves):
    env.reset(seed=0)
    result = None
    for move in moves:
        result = env.step(move)
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
    assert result.outcome is Outcome.DRAW
    assert result.termination is Termination.NATURAL
    assert len(env.replay()) == COLS * ROWS


def test_illegal_action_forfeits(env):
    play(env, FILLS_COLUMN_1)
    result = env.step(1)  # column 1 is full
    assert result.termination is Termination.ILLEGAL_ACTION
    assert result.outcome is Outcome.PLAYER_1  # 30 moves played, so player 0 moved


def test_out_of_range_action_forfeits(env):
    env.reset(seed=0)
    result = env.step(COLS)
    assert result.outcome is Outcome.PLAYER_1
    assert result.termination is Termination.ILLEGAL_ACTION


def test_observation_is_from_the_movers_perspective(env):
    obs = env.reset(seed=0)
    assert obs.player == 0
    assert not obs.features.any()

    result = env.step(3)
    # Player 0's piece reads as -1 to player 1, who is now on move.
    assert result.observation.player == 1
    assert result.observation.features[3 * ROWS] == -1.0


def test_legal_mask_closes_a_full_column(env):
    result = play(env, FILLS_COLUMN_1)
    legal = result.observation.legal_actions
    assert not legal[1]
    assert legal.sum() == COLS - 1


def test_replay_reproduces_the_episode(env):
    moves = [3, 3, 4, 4, 5, 5, 6]
    first = play(env, moves)
    recorded = env.replay()

    second = play(make(ENV_ID), recorded)

    assert recorded == moves
    assert second.outcome is first.outcome


def test_seed_does_not_change_the_episode():
    """Dynamics are deterministic, so two seeds must agree bit for bit.

    The runner records a seed on every match. This env ignores it, and that
    has to stay true or replays stop reproducing.
    """
    a, b = make(ENV_ID), make(ENV_ID)
    a.reset(seed=1)
    b.reset(seed=999_999)

    for move in [3, 3, 2, 4, 1, 0, 5]:
        ra, rb = a.step(move), b.step(move)
        assert ra.done == rb.done
        assert ra.outcome is rb.outcome
        if ra.observation and rb.observation:
            assert np.array_equal(ra.observation.features, rb.observation.features)

    assert a.replay() == b.replay()


def test_step_after_done_raises(env):
    play(env, [0, 1, 0, 1, 0, 1, 0])
    with pytest.raises(RuntimeError):
        env.step(2)


def test_unknown_env_id_names_what_is_registered():
    with pytest.raises(KeyError, match=ENV_ID):
        make("connect4-v99")
