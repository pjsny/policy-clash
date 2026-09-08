/* Tron Duel rules. Pure C, no Python, no allocation, no global state.
 *
 * Light-cycles on a square grid. Both seats move every tick, simultaneously,
 * and each leaves a permanent trail behind it. Driving into a wall, into a
 * trail, or into the other cycle is fatal. The survivor wins.
 *
 * Every value in here is an integer. Floats appear only in the observation
 * buffer, which nothing in the rules reads back. A single fused multiply-add
 * in a rules path would make the outcome depend on the compiler and the host,
 * and "same seed, same env version, same policies, same bytes out" is the
 * property the whole leaderboard rests on.
 *
 * Kept free of Python so it can be compiled standalone for fuzzing and, later,
 * to wasm for the replay viewer.
 */

#ifndef POLICYCLASH_TRON_DUEL_H
#define POLICYCLASH_TRON_DUEL_H

#include <stdint.h>
#include <string.h>

/* The egocentric observation is a rotation of the board onto itself, which
 * only closes on a square grid: a rectangle rotated a quarter turn does not
 * fit back in its own bounds and would need a padding plane. */
#define TD_SIZE 13
#define TD_CELLS (TD_SIZE * TD_SIZE)
#define TD_PLANES 4
#define TD_ACTIONS 3

/* Spawns are drawn from the interior with a minimum separation of 4, which
 * only exists on a board this size or larger. Guarded because the draw is a
 * rejection loop: on a smaller board it would never terminate. */
_Static_assert(TD_SIZE >= 5, "spawn interior and minimum spawn separation need a 5x5 board");

/* Both seats consume one previously-empty cell on every ongoing tick and
 * trails never clear, so after t ongoing ticks 2 + 2t of the TD_CELLS cells
 * are occupied and t cannot exceed this bound. A crash is therefore forced,
 * and Termination.STEP_LIMIT is unreachable in this env: there is no
 * step-limit rules path here and no dead code pretending there might be.
 *
 * Precondition: the caller must not step once num_ticks == TD_MAX_TICKS. That
 * state means the cell-consumption argument above is broken, i.e. a bug in
 * this file, so it is checked by the caller rather than papered over here. */
#define TD_MAX_TICKS ((TD_CELLS - 2) / 2)

/* Step status. Outcome and termination are folded into one code so the step
 * function has no out-parameters and the binding stays a single integer. */
enum {
    TD_ONGOING = 0,
    TD_P0_WIN = 1,
    TD_P1_WIN = 2,
    TD_DRAW = 3,
    TD_P0_WIN_ILLEGAL = 4, /* seat 1 submitted an out-of-range action */
    TD_P1_WIN_ILLEGAL = 5, /* seat 0 did */
    TD_DRAW_ILLEGAL = 6    /* both did */
};

/* grid holds occupancy: 0 empty, 1 seat 0's trail, 2 seat 1's trail. Head
 * cells are part of the trail, so occupancy alone answers "can a cycle enter
 * this cell". Index is y * TD_SIZE + x with y = 0 the top row.
 *
 * facing is 0 = N (-y), 1 = E (+x), 2 = S (+y), 3 = W (-x). */
typedef struct {
    uint8_t grid[TD_CELLS];
    int head_x[2];
    int head_y[2];
    int facing[2];
    int done;
    int num_ticks;
    int32_t moves[2 * TD_MAX_TICKS];
} TronDuel;

static const int TD_DX[4] = {0, 1, 0, -1};
static const int TD_DY[4] = {-1, 0, 1, 0};

static inline uint64_t td_splitmix64(uint64_t *state) {
    uint64_t z = (*state += 0x9E3779B97F4A7C15ull);
    z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ull;
    z = (z ^ (z >> 27)) * 0x94D049BB133111EBull;
    return z ^ (z >> 31);
}

/* A coordinate strictly inside the border, so a spawn is never already boxed
 * in against a wall. */
static inline int td_interior(uint64_t *rng) {
    return (int)(td_splitmix64(rng) % (uint64_t)(TD_SIZE - 2)) + 1;
}

static inline int td_manhattan(int ax, int ay, int bx, int by) {
    const int dx = ax > bx ? ax - bx : bx - ax;
    const int dy = ay > by ? ay - by : by - ay;
    return dx + dy;
}

/* Seeded start position.
 *
 * The two spawns are drawn independently rather than mirrored. A mirrored
 * start is the tempting choice because it is exactly fair, but two copies of
 * one deterministic policy then play mirror-image moves and meet head-on in
 * the middle on every single seed: the seed carries no information and every
 * match is the same draw. Asymmetric spawns are what make distinct seeds
 * distinct episodes. The per-seed positional advantage that buys is cancelled
 * at the scheduler level, which swaps seats across a paired match. */
static inline void td_reset(TronDuel *env, uint64_t seed) {
    uint64_t rng = seed;

    memset(env->grid, 0, sizeof(env->grid));
    env->done = 0;
    env->num_ticks = 0;

    /* Rejection sampling. A separation of 4 subsumes the requirement that the
     * two cells differ, and keeps the opening from being decided on tick one
     * by a spawn that is already adjacent to the opponent. */
    int x0, y0, x1, y1;
    do {
        x0 = td_interior(&rng);
        y0 = td_interior(&rng);
        x1 = td_interior(&rng);
        y1 = td_interior(&rng);
    } while (td_manhattan(x0, y0, x1, y1) < 4);

    env->head_x[0] = x0;
    env->head_y[0] = y0;
    env->head_x[1] = x1;
    env->head_y[1] = y1;
    env->facing[0] = (int)(td_splitmix64(&rng) % 4);
    env->facing[1] = (int)(td_splitmix64(&rng) % 4);

    env->grid[y0 * TD_SIZE + x0] = 1;
    env->grid[y1 * TD_SIZE + x1] = 2;
}

/* One simultaneous tick. Actions are relative to the seat's own facing:
 * 0 turns left, 1 goes straight, 2 turns right. There is deliberately no
 * reversal action, so every in-range action is legal and driving into a wall
 * is a skill failure rather than a rules violation. */
static inline int td_step(TronDuel *env, int action_0, int action_1) {
    const int actions[2] = {action_0, action_1};

    /* Recorded raw and un-clamped, before the range check, so replaying the
     * move list reproduces a forfeit as faithfully as it reproduces a crash. */
    env->moves[2 * env->num_ticks] = action_0;
    env->moves[2 * env->num_ticks + 1] = action_1;
    env->num_ticks++;

    const int bad_0 = action_0 < 0 || action_0 >= TD_ACTIONS;
    const int bad_1 = action_1 < 0 || action_1 >= TD_ACTIONS;
    if (bad_0 || bad_1) {
        env->done = 1;
        if (bad_0 && bad_1) {
            return TD_DRAW_ILLEGAL;
        }
        return bad_0 ? TD_P1_WIN_ILLEGAL : TD_P0_WIN_ILLEGAL;
    }

    int facing[2];
    int next_x[2];
    int next_y[2];
    int crashed[2];
    for (int seat = 0; seat < 2; seat++) {
        /* left is +3, straight +0, right +1, so the action folds straight
         * into the turn as (action + 3) % 4. */
        facing[seat] = (env->facing[seat] + actions[seat] + 3) % 4;
        const int nx = env->head_x[seat] + TD_DX[facing[seat]];
        const int ny = env->head_y[seat] + TD_DY[facing[seat]];
        const int inside = nx >= 0 && nx < TD_SIZE && ny >= 0 && ny < TD_SIZE;

        /* A seat's current head cell is already marked occupied, so a head-on
         * swap - each cycle driving into the cell the other is vacating - is
         * caught by this occupancy test with no special case for it. */
        crashed[seat] = !inside || env->grid[ny * TD_SIZE + nx] != 0;
        next_x[seat] = nx;
        next_y[seat] = ny;
    }

    /* The one collision occupancy cannot see: both seats claiming the same
     * still-empty cell, where neither is blocked by anything already there. */
    if (!crashed[0] && !crashed[1] && next_x[0] == next_x[1] && next_y[0] == next_y[1]) {
        crashed[0] = 1;
        crashed[1] = 1;
    }

    if (crashed[0] || crashed[1]) {
        env->done = 1;
        if (crashed[0] && crashed[1]) {
            return TD_DRAW;
        }
        return crashed[0] ? TD_P1_WIN : TD_P0_WIN;
    }

    for (int seat = 0; seat < 2; seat++) {
        env->grid[next_y[seat] * TD_SIZE + next_x[seat]] = (uint8_t)(seat + 1);
        env->head_x[seat] = next_x[seat];
        env->head_y[seat] = next_y[seat];
        env->facing[seat] = facing[seat];
    }
    return TD_ONGOING;
}

/* Observation for one seat: TD_PLANES * TD_CELLS floats, plane-major then row
 * major, so out[p * TD_CELLS + y * TD_SIZE + x]. Planes are 0 own trail,
 * 1 opponent trail, 2 own head, 3 opponent head. The head cell is occupied
 * and so also appears in its trail plane; planes 0 and 1 together are exactly
 * the set of cells no cycle can enter, and 2 and 3 only say where each cycle
 * currently is.
 *
 * Egocentric: the board is rotated so the observing seat always faces up.
 * That quarters the symmetry the network has to learn and composes with the
 * relative action space, where "left" means the same thing in every frame.
 * A quarter turn maps the square grid onto itself, so the real border stays
 * the border and no out-of-bounds plane is needed. */
static inline void td_observe(const TronDuel *env, int seat, float *out) {
    const int f = env->facing[seat];
    const uint8_t mine = (uint8_t)(seat + 1);
    const int own_x = env->head_x[seat];
    const int own_y = env->head_y[seat];
    const int opp_x = env->head_x[seat ^ 1];
    const int opp_y = env->head_y[seat ^ 1];

    memset(out, 0, TD_PLANES * TD_CELLS * sizeof(float));
    for (int oy = 0; oy < TD_SIZE; oy++) {
        for (int ox = 0; ox < TD_SIZE; ox++) {
            /* Each case is fixed by one requirement: stepping one cell up in
             * the observation (oy - 1) must step one cell along the seat's
             * facing on the board. */
            int bx = ox, by = oy;
            if (f == 1) { /* E: oy - 1 raises bx */
                bx = TD_SIZE - 1 - oy;
                by = ox;
            } else if (f == 2) { /* S: oy - 1 raises by */
                bx = TD_SIZE - 1 - ox;
                by = TD_SIZE - 1 - oy;
            } else if (f == 3) { /* W: oy - 1 lowers bx */
                bx = oy;
                by = TD_SIZE - 1 - ox;
            }

            const int cell = oy * TD_SIZE + ox;
            const uint8_t occupant = env->grid[by * TD_SIZE + bx];
            if (occupant == mine) {
                out[0 * TD_CELLS + cell] = 1.0f;
            } else if (occupant != 0) {
                out[1 * TD_CELLS + cell] = 1.0f;
            }
            if (bx == own_x && by == own_y) {
                out[2 * TD_CELLS + cell] = 1.0f;
            } else if (bx == opp_x && by == opp_y) {
                out[3 * TD_CELLS + cell] = 1.0f;
            }
        }
    }
}

/* Every action is always available: the three turns cannot be blocked, only
 * regretted. The mask ships anyway so policy code never branches on the env. */
static inline void td_legal(const TronDuel *env, int seat, uint8_t *out) {
    (void)env;
    (void)seat;
    for (int i = 0; i < TD_ACTIONS; i++) {
        out[i] = 1;
    }
}

#endif /* POLICYCLASH_TRON_DUEL_H */
