/* Connect4 rules. Pure C, no Python, no allocation.
 *
 * Board state is two bitboards in the standard column-major layout with a
 * sentinel row. Column c occupies bits c*7 .. c*7+5, and bit c*7+6 is a
 * sentinel that always stays empty so win detection cannot wrap from the top
 * of one column to the bottom of the next.
 *
 * Kept free of Python so it can be compiled standalone for fuzzing and, later,
 * to wasm for the replay viewer.
 */

#ifndef POLICYCLASH_CONNECT4_H
#define POLICYCLASH_CONNECT4_H

#include <stdint.h>
#include <string.h>

#define C4_COLS 7
#define C4_ROWS 6
#define C4_CELLS (C4_COLS * C4_ROWS)
#define C4_H (C4_ROWS + 1) /* bits per column, sentinel included */

/* Step status. Outcome and termination are folded into one code so the step
 * function has no out-parameters and the binding stays a single integer. */
enum {
    C4_ONGOING = 0,
    C4_P0_WIN = 1,
    C4_P1_WIN = 2,
    C4_DRAW = 3,
    C4_P0_WIN_ILLEGAL = 4, /* player 1 played an illegal action */
    C4_P1_WIN_ILLEGAL = 5  /* player 0 played an illegal action */
};

typedef struct {
    uint64_t pieces[2];
    int to_move;
    int done;
    int num_moves;
    uint8_t moves[C4_CELLS];
} Connect4;

static inline uint64_t c4_bottom(int col) {
    return (uint64_t)1 << (col * C4_H);
}

static inline int c4_column_full(uint64_t mask, int col) {
    return (mask & ((uint64_t)1 << (col * C4_H + C4_ROWS - 1))) != 0;
}

static inline int c4_won(uint64_t pieces) {
    /* Vertical, horizontal, and both diagonals. */
    static const int shifts[4] = {1, C4_H, C4_H - 1, C4_H + 1};
    for (int i = 0; i < 4; i++) {
        uint64_t pairs = pieces & (pieces >> shifts[i]);
        if (pairs & (pairs >> (2 * shifts[i]))) {
            return 1;
        }
    }
    return 0;
}

static inline void c4_reset(Connect4 *env) {
    env->pieces[0] = 0;
    env->pieces[1] = 0;
    env->to_move = 0;
    env->done = 0;
    env->num_moves = 0;
}

static inline int c4_step(Connect4 *env, int action) {
    const int player = env->to_move;
    const uint64_t mask = env->pieces[0] | env->pieces[1];

    if (action < 0 || action >= C4_COLS || c4_column_full(mask, action)) {
        env->done = 1;
        return player == 0 ? C4_P1_WIN_ILLEGAL : C4_P0_WIN_ILLEGAL;
    }

    env->moves[env->num_moves++] = (uint8_t)action;
    env->pieces[player] |= (mask + c4_bottom(action)) & ~mask;

    if (c4_won(env->pieces[player])) {
        env->done = 1;
        return player == 0 ? C4_P0_WIN : C4_P1_WIN;
    }

    if (env->num_moves == C4_CELLS) {
        env->done = 1;
        return C4_DRAW;
    }

    env->to_move ^= 1;
    return C4_ONGOING;
}

/* Observation from the perspective of the player on move: own pieces are +1,
 * the opponent's are -1. Index is col * C4_ROWS + row, row 0 at the bottom. */
static inline void c4_observe(const Connect4 *env, float *out) {
    const uint64_t mine = env->pieces[env->to_move];
    const uint64_t theirs = env->pieces[env->to_move ^ 1];

    memset(out, 0, C4_CELLS * sizeof(float));
    for (int col = 0; col < C4_COLS; col++) {
        for (int row = 0; row < C4_ROWS; row++) {
            const uint64_t bit = (uint64_t)1 << (col * C4_H + row);
            if (mine & bit) {
                out[col * C4_ROWS + row] = 1.0f;
            } else if (theirs & bit) {
                out[col * C4_ROWS + row] = -1.0f;
            }
        }
    }
}

static inline void c4_legal(const Connect4 *env, uint8_t *out) {
    const uint64_t mask = env->pieces[0] | env->pieces[1];
    for (int col = 0; col < C4_COLS; col++) {
        out[col] = (uint8_t)(!c4_column_full(mask, col));
    }
}

#endif /* POLICYCLASH_CONNECT4_H */
