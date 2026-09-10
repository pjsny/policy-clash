/* Super Auto Pets, full-match engine (sap-v2). Pure C, no Python, no
 * allocation, no global state. See docs/envs/sap-v2.md for the design this
 * implements and the wiki sources every real-game rule below is cited
 * from.
 *
 * Where sap.h (sap-v1) is one shop phase + one battle, this is the actual
 * Arena match: many rounds of shop-then-battle, team state persisting
 * round to round, lives and trophies, a tier-gated shop that grows with
 * the turn number, and freeze. Roster is still Tier 1 only (10 pets, 2
 * foods) - the match *engine* is the full game; the roster is a separate,
 * later expansion (sap-v2.md's appendix), and shipping both unverified
 * at once is exactly the failure mode sap-v1's own build caught
 * repeatedly at a sixth of this scope.
 *
 * A new file, not an edit to sap.h: "environments are versioned and never
 * mutated" (policy-clash's own README). sap-v1 stays exactly as it was.
 *
 * Every value in here is an integer, for the same reason sap.h states it:
 * floats belong only in the observation buffer, nowhere a rules decision
 * reads them.
 */

#ifndef POLICYCLASH_SAP2_H
#define POLICYCLASH_SAP2_H

#include <stdint.h>
#include <string.h>

#define SAP2_TEAM 5
#define SAP2_MAX_SHOP_PETS 5   /* the largest shop ever gets, turn 5+ */
#define SAP2_MAX_SHOP_FOOD 2   /* likewise */
#define SAP2_STARTING_GOLD 10  /* every round, does not carry over */
#define SAP2_MAX_LEVEL 3
#define SAP2_STARTING_LIVES 5      /* Normal Arena mode */
#define SAP2_TROPHIES_TO_WIN 10
#define SAP2_MAX_ROUNDS 30         /* see docs/envs/sap-v2.md's step-limit note -
                                     * genuinely reachable here, unlike sap-v1 */

/* Species/food/trigger tables: identical to sap.h - same 10 shop species,
 * same 2 tokens, same 3 foods. Roster is still Tier 1 only; see the file
 * header. Kept as a separate copy (not shared with sap.h) for the same
 * reason connect4.h and tron_duel.h don't share code with each other -
 * each env file is self-contained. */
enum {
    SAP2_SPECIES_EMPTY = 0,
    SAP2_ANT = 1, SAP2_BEAVER = 2, SAP2_CRICKET = 3, SAP2_DUCK = 4, SAP2_FISH = 5,
    SAP2_HORSE = 6, SAP2_MOSQUITO = 7, SAP2_OTTER = 8, SAP2_PIG = 9, SAP2_PIGEON = 10,
    SAP2_NUM_SHOP_SPECIES = 10,
    SAP2_CRICKET_TOKEN = 11,
    SAP2_BEE = 12,
    SAP2_NUM_ALL_SPECIES = 13
};
enum { SAP2_FOOD_EMPTY = 0, SAP2_APPLE = 1, SAP2_HONEY = 2, SAP2_BREAD_CRUMBS = 3, SAP2_NUM_FOODS = 4 };
static const int SAP2_FOOD_COST[SAP2_NUM_FOODS] = {0, 3, 3, 0};

static const int8_t SAP2_BASE_ATK[SAP2_NUM_ALL_SPECIES] = {0, 2, 3, 1, 2, 2, 2, 2, 1, 4, 3, 0, 1};
static const int8_t SAP2_BASE_HP[SAP2_NUM_ALL_SPECIES] = {0, 2, 2, 3, 2, 3, 1, 2, 4, 1, 2, 0, 1};

/* Shop size by turn. The tier schedule (1/3/5/7/9/11) is wiki-confirmed
 * (superautopets.wiki.gg, "The Basics") and matches SAP_clone.md exactly,
 * but is a no-op while the roster is Tier 1 only - every species already
 * fits under Tier 1, so nothing here needs to gate by tier yet; that gate
 * is where a later tier-expansion phase hooks in, not before.
 *
 * The slot-count numbers below (3/1, 4/1, 5/2) are the widely-documented
 * defaults, NOT pinned to a specific wiki paragraph this session found -
 * see docs/envs/sap-v2.md's explicit flag on this. Change only this
 * function if that table turns out to be wrong; nothing else depends on
 * the exact numbers. */
static inline void sap2_shop_size(int turn, int *pet_slots, int *food_slots) {
    if (turn <= 2) {
        *pet_slots = 3;
        *food_slots = 1;
    } else if (turn <= 4) {
        *pet_slots = 4;
        *food_slots = 1;
    } else {
        *pet_slots = 5;
        *food_slots = 2;
    }
}

/* Action layout. 49 actions - see docs/envs/sap-v2.md "Action space
 * changes". Sized to the largest shop (5 pet, 2 food slots); a smaller
 * shop just masks the unused indices, same pattern sap-v1 uses for
 * everything. */
enum {
    SAP2_ACT_END_TURN = 0,
    SAP2_ACT_BUY_PET_BASE = 1,       /* +0..4: shop pet slot */
    SAP2_ACT_SELL_BASE = 6,          /* +0..4: team slot */
    SAP2_ACT_COMBINE_BASE = 11,      /* +0..9: team slot pair */
    SAP2_ACT_REROLL = 21,
    SAP2_ACT_REPOSITION_BASE = 22,   /* +0..9: team slot pair */
    SAP2_ACT_BUY_FOOD_BASE = 32,     /* +0..9: food_slot*5 + team_target */
    SAP2_ACT_FREEZE_PET_BASE = 42,   /* +0..4: shop pet slot, toggles */
    SAP2_ACT_FREEZE_FOOD_BASE = 47,  /* +0..1: food slot, toggles */
    SAP2_NUM_ACTIONS = 49
};

#define SAP2_SHOP_ACTION_BUDGET 20 /* per round - same bound and same
                                     * unreachable-by-construction proof as
                                     * sap-v1's, applied within each round */
#define SAP2_MAX_TICKS (SAP2_MAX_ROUNDS * SAP2_SHOP_ACTION_BUDGET)

/* Observation layout (float32, C-order). Adds to sap-v1's per-slot
 * layout: a frozen flag on every shop slot, and own lives/trophies/turn.
 * No opponent-state block - same reasoning as sap-v1, the shop phase
 * still hides the opponent's team and shop entirely. */
enum {
    SAP2_TEAM_SLOT_FLOATS = SAP2_NUM_ALL_SPECIES + 1 /* atk */ + 1 /* hp */ + SAP2_MAX_LEVEL + 1 /* honey */,
    SAP2_SHOP_PET_SLOT_FLOATS = (SAP2_NUM_SHOP_SPECIES + 1) + 1 /* hp bonus */ + 1 /* frozen */,
    SAP2_SHOP_FOOD_SLOT_FLOATS = SAP2_NUM_FOODS + 1 /* frozen */,
    SAP2_OBS_FLOATS = 1 /* gold */ + 1 /* lives */ + 1 /* trophies */ + 1 /* turn */
                      + SAP2_TEAM * SAP2_TEAM_SLOT_FLOATS
                      + SAP2_MAX_SHOP_PETS * SAP2_SHOP_PET_SLOT_FLOATS
                      + SAP2_MAX_SHOP_FOOD * SAP2_SHOP_FOOD_SLOT_FLOATS
};

/* Step status. Three families now, not two: NATURAL (someone hit 10
 * trophies or 0 lives), ILLEGAL (an out-of-range action, same as sap-v1),
 * and STEP_LIMIT (SAP2_MAX_ROUNDS reached with neither - genuinely
 * reachable here, unlike every prior env in this project). */
enum {
    SAP2_ONGOING = 0,
    SAP2_P0_WIN = 1, SAP2_P1_WIN = 2, SAP2_DRAW = 3,
    SAP2_P0_WIN_ILLEGAL = 4, SAP2_P1_WIN_ILLEGAL = 5, SAP2_DRAW_ILLEGAL = 6,
    SAP2_P0_WIN_STEP_LIMIT = 7, SAP2_P1_WIN_STEP_LIMIT = 8, SAP2_DRAW_STEP_LIMIT = 9
};

typedef struct {
    uint8_t species;
    int8_t attack;
    int8_t health;
    uint8_t level;
    uint8_t xp;
    uint8_t honey_perk;
} SapPet2;

typedef struct {
    uint8_t species;
    int8_t hp_bonus;
    uint8_t frozen;
} SapShopPet2;

typedef struct {
    uint8_t species;
    uint8_t frozen;
} SapShopFood2;

typedef struct {
    SapPet2 team[SAP2_TEAM];
    SapShopPet2 shop_pets[SAP2_MAX_SHOP_PETS];
    SapShopFood2 shop_food[SAP2_MAX_SHOP_FOOD];
    int16_t gold;
    int16_t lives;
    int16_t trophies;
    uint64_t rng;
    int ended;
    int actions_taken;
} SapSeat2;

typedef struct {
    SapSeat2 seat[2];
    uint64_t battle_rng;
    int turn;  /* starts at 1; shared - both seats always play the same round's turn */
    int round; /* starts at 0; counts completed rounds, for SAP2_MAX_ROUNDS */
    int done;
    int num_ticks;
    int32_t moves[2 * SAP2_MAX_TICKS];
} SAP2;

/* -------------------------------------------------------------------- */
/* RNG - identical technique to sap.h, own copy per env-file-independence. */

static inline uint64_t sap2_splitmix64(uint64_t *state) {
    uint64_t z = (*state += 0x9E3779B97F4A7C15ull);
    z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ull;
    z = (z ^ (z >> 27)) * 0x94D049BB133111EBull;
    return z ^ (z >> 31);
}

static inline int sap2_pick_random(uint64_t *rng, const int *candidates, int count, int k, int *out) {
    int pool[SAP2_TEAM];
    int n = count;
    if (n > SAP2_TEAM) {
        n = SAP2_TEAM;
    }
    for (int i = 0; i < n; i++) {
        pool[i] = candidates[i];
    }
    if (k > n) {
        k = n;
    }
    for (int i = 0; i < k; i++) {
        const int j = i + (int)(sap2_splitmix64(rng) % (uint64_t)(n - i));
        const int tmp = pool[i];
        pool[i] = pool[j];
        pool[j] = tmp;
        out[i] = pool[i];
    }
    return k;
}

/* -------------------------------------------------------------------- */
/* Shop */

static inline void sap2_roll_shop(SapSeat2 *s, int pet_slots, int food_slots) {
    for (int i = 0; i < pet_slots; i++) {
        if (s->shop_pets[i].frozen) {
            continue; /* frozen items stay put through any roll - paid
                       * reroll or the free start-of-round one alike */
        }
        s->shop_pets[i].species = (uint8_t)(1 + sap2_splitmix64(&s->rng) % SAP2_NUM_SHOP_SPECIES);
        s->shop_pets[i].hp_bonus = 0;
    }
    for (int i = 0; i < food_slots; i++) {
        if (s->shop_food[i].frozen) {
            continue;
        }
        /* Only Apple/Honey roll naturally - Bread Crumbs is Pigeon-only. */
        s->shop_food[i].species = (uint8_t)(1 + sap2_splitmix64(&s->rng) % 2);
    }
}

static inline int sap2_leftmost_empty(const SapSeat2 *s) {
    for (int i = 0; i < SAP2_TEAM; i++) {
        if (s->team[i].species == SAP2_SPECIES_EMPTY) {
            return i;
        }
    }
    return -1;
}

static inline int sap2_friends(const SapSeat2 *s, int exclude, int *out) {
    int n = 0;
    for (int i = 0; i < SAP2_TEAM; i++) {
        if (i != exclude && s->team[i].species != SAP2_SPECIES_EMPTY) {
            out[n++] = i;
        }
    }
    return n;
}

static inline void sap2_clamp_stats(SapPet2 *p) {
    if (p->attack < 0) {
        p->attack = 0;
    }
    if (p->attack > 50) {
        p->attack = 50;
    }
    if (p->health > 50) {
        p->health = 50;
    }
}

/* "Until next turn" is a real deadline now, unlike sap-v1's single round -
 * but this env's temporary/permanent split already discards every
 * battle-time change on the persistent team every round (see the file
 * header and sap2_resolve_round), so Horse's buff, granted during the
 * shop phase, is the one temporary effect that needs an explicit expiry
 * rather than getting it for free from "battle doesn't touch persistent
 * state." Simplest correct handling: Horse's buff is written directly
 * onto the persistent team (same as sap-v1), and sap2_resolve_round's
 * round-advance clears it back off at the start of the *next* round -
 * "until next turn" read literally, expiring when the next turn starts,
 * not when battle ends. */
static inline void sap2_fire_friend_summoned(SapSeat2 *s, int slot) {
    for (int i = 0; i < SAP2_TEAM; i++) {
        if (i == slot || s->team[i].species != SAP2_HORSE) {
            continue;
        }
        s->team[slot].attack = (int8_t)(s->team[slot].attack + s->team[i].level);
        sap2_clamp_stats(&s->team[slot]);
    }
}

static inline void sap2_buy_pet(SapSeat2 *s, int shop_slot) {
    const int dest = sap2_leftmost_empty(s);
    const uint8_t species = s->shop_pets[shop_slot].species;

    s->gold = (int16_t)(s->gold - 3);
    s->team[dest].species = species;
    s->team[dest].attack = SAP2_BASE_ATK[species];
    s->team[dest].health = SAP2_BASE_HP[species];
    s->team[dest].level = 1;
    s->team[dest].xp = 1;
    s->team[dest].honey_perk = 0;
    s->shop_pets[shop_slot].species = SAP2_SPECIES_EMPTY;
    s->shop_pets[shop_slot].hp_bonus = 0;
    s->shop_pets[shop_slot].frozen = 0; /* bought - nothing left to freeze */

    sap2_fire_friend_summoned(s, dest);

    if (species == SAP2_OTTER) {
        int friends[SAP2_TEAM];
        const int n = sap2_friends(s, dest, friends);
        int picked[SAP2_TEAM];
        const int k = sap2_pick_random(&s->rng, friends, n, s->team[dest].level, picked);
        for (int i = 0; i < k; i++) {
            s->team[picked[i]].health = (int8_t)(s->team[picked[i]].health + 1);
            sap2_clamp_stats(&s->team[picked[i]]);
        }
    }
}

static inline void sap2_sell(SapSeat2 *s, int slot) {
    SapPet2 sold = s->team[slot];
    s->gold = (int16_t)(s->gold + sold.level);
    s->team[slot].species = SAP2_SPECIES_EMPTY;

    switch (sold.species) {
    case SAP2_BEAVER: {
        int friends[SAP2_TEAM];
        const int n = sap2_friends(s, slot, friends);
        int picked[SAP2_TEAM];
        const int k = sap2_pick_random(&s->rng, friends, n, 2, picked);
        for (int i = 0; i < k; i++) {
            s->team[picked[i]].attack = (int8_t)(s->team[picked[i]].attack + sold.level);
            sap2_clamp_stats(&s->team[picked[i]]);
        }
        break;
    }
    case SAP2_DUCK:
        for (int i = 0; i < SAP2_MAX_SHOP_PETS; i++) {
            if (s->shop_pets[i].species != SAP2_SPECIES_EMPTY) {
                s->shop_pets[i].hp_bonus = (int8_t)(s->shop_pets[i].hp_bonus + sold.level);
            }
        }
        break;
    case SAP2_PIG:
        s->gold = (int16_t)(s->gold + sold.level);
        break;
    case SAP2_PIGEON:
        /* Two food slots can exist now (turn 5+), unlike sap-v1's fixed
         * one - still resolved with an explicit, documented default
         * rather than a confirmed rule: always targets food slot 0. See
         * docs/envs/sap-v2.md. */
        s->shop_food[0].species = SAP2_BREAD_CRUMBS;
        s->shop_food[0].frozen = 0;
        break;
    default:
        break;
    }
}

static inline void sap2_combine(SapSeat2 *s, int i, int j) {
    SapPet2 *a = &s->team[i];
    const SapPet2 *b = &s->team[j];
    const uint8_t prev_level = a->level;

    a->attack = (int8_t)((a->attack > b->attack ? a->attack : b->attack) + 1);
    a->health = (int8_t)((a->health > b->health ? a->health : b->health) + 1);
    sap2_clamp_stats(a);
    uint8_t xp = (uint8_t)(a->xp + b->xp);
    if (xp > SAP2_MAX_LEVEL) {
        xp = SAP2_MAX_LEVEL;
    }
    a->xp = xp;
    a->level = xp;
    a->honey_perk = (uint8_t)(a->honey_perk || b->honey_perk);
    s->team[j].species = SAP2_SPECIES_EMPTY;

    if (a->species == SAP2_FISH && a->level > prev_level && a->level >= 2) {
        int friends[SAP2_TEAM];
        const int n = sap2_friends(s, i, friends);
        int picked[SAP2_TEAM];
        const int k = sap2_pick_random(&s->rng, friends, n, a->level, picked);
        for (int p = 0; p < k; p++) {
            s->team[picked[p]].attack = (int8_t)(s->team[picked[p]].attack + a->level);
            s->team[picked[p]].health = (int8_t)(s->team[picked[p]].health + a->level);
            sap2_clamp_stats(&s->team[picked[p]]);
        }
    }
}

static inline void sap2_reposition(SapSeat2 *s, int i, int j) {
    const SapPet2 tmp = s->team[i];
    s->team[i] = s->team[j];
    s->team[j] = tmp;
}

static inline void sap2_buy_food(SapSeat2 *s, int food_slot, int target) {
    const uint8_t food = s->shop_food[food_slot].species;
    s->gold = (int16_t)(s->gold - SAP2_FOOD_COST[food]);
    s->shop_food[food_slot].species = SAP2_FOOD_EMPTY;
    s->shop_food[food_slot].frozen = 0;

    SapPet2 *p = &s->team[target];
    if (food == SAP2_APPLE || food == SAP2_BREAD_CRUMBS) {
        p->attack = (int8_t)(p->attack + 1);
        if (food == SAP2_APPLE) {
            p->health = (int8_t)(p->health + 1);
        }
        sap2_clamp_stats(p);
    } else if (food == SAP2_HONEY) {
        p->honey_perk = 1;
    }
}

static inline void sap2_toggle_freeze_pet(SapSeat2 *s, int slot) {
    s->shop_pets[slot].frozen = (uint8_t)!s->shop_pets[slot].frozen;
}
static inline void sap2_toggle_freeze_food(SapSeat2 *s, int slot) {
    s->shop_food[slot].frozen = (uint8_t)!s->shop_food[slot].frozen;
}

/* -------------------------------------------------------------------- */
/* Action dispatch */

static inline void sap2_pair(int index, int *i, int *j) {
    static const int PI[10] = {0, 0, 0, 0, 1, 1, 1, 2, 2, 3};
    static const int PJ[10] = {1, 2, 3, 4, 2, 3, 4, 3, 4, 4};
    *i = PI[index];
    *j = PJ[index];
}

static inline int sap2_can_combine(const SapSeat2 *s, int i, int j) {
    return s->team[i].species != SAP2_SPECIES_EMPTY && s->team[i].species == s->team[j].species &&
           s->team[i].level < SAP2_MAX_LEVEL;
}

static inline void sap2_legal_for(const SapSeat2 *s, int pet_slots, int food_slots, uint8_t *out) {
    memset(out, 0, SAP2_NUM_ACTIONS);
    out[SAP2_ACT_END_TURN] = 1;

    for (int k = 0; k < pet_slots; k++) {
        out[SAP2_ACT_BUY_PET_BASE + k] =
            (uint8_t)(s->shop_pets[k].species != SAP2_SPECIES_EMPTY && s->gold >= 3 &&
                      sap2_leftmost_empty(s) >= 0);
    }
    for (int t = 0; t < SAP2_TEAM; t++) {
        out[SAP2_ACT_SELL_BASE + t] = (uint8_t)(s->team[t].species != SAP2_SPECIES_EMPTY);
    }
    for (int p = 0; p < 10; p++) {
        int i, j;
        sap2_pair(p, &i, &j);
        out[SAP2_ACT_COMBINE_BASE + p] = (uint8_t)sap2_can_combine(s, i, j);
    }
    out[SAP2_ACT_REROLL] = (uint8_t)(s->gold >= 1);
    for (int p = 0; p < 10; p++) {
        int i, j;
        sap2_pair(p, &i, &j);
        out[SAP2_ACT_REPOSITION_BASE + p] =
            (uint8_t)(s->team[i].species != SAP2_SPECIES_EMPTY || s->team[j].species != SAP2_SPECIES_EMPTY);
    }
    for (int f = 0; f < food_slots; f++) {
        for (int t = 0; t < SAP2_TEAM; t++) {
            const uint8_t food = s->shop_food[f].species;
            out[SAP2_ACT_BUY_FOOD_BASE + f * SAP2_TEAM + t] =
                (uint8_t)(food != SAP2_FOOD_EMPTY && s->gold >= SAP2_FOOD_COST[food] &&
                          s->team[t].species != SAP2_SPECIES_EMPTY);
        }
    }
    for (int k = 0; k < pet_slots; k++) {
        out[SAP2_ACT_FREEZE_PET_BASE + k] = (uint8_t)(s->shop_pets[k].species != SAP2_SPECIES_EMPTY);
    }
    for (int f = 0; f < food_slots; f++) {
        out[SAP2_ACT_FREEZE_FOOD_BASE + f] = (uint8_t)(s->shop_food[f].species != SAP2_FOOD_EMPTY);
    }
}

static inline void sap2_apply(SapSeat2 *s, int action, int pet_slots, int food_slots) {
    if (action == SAP2_ACT_END_TURN) {
        s->ended = 1;
    } else if (action >= SAP2_ACT_BUY_PET_BASE && action < SAP2_ACT_BUY_PET_BASE + SAP2_MAX_SHOP_PETS) {
        sap2_buy_pet(s, action - SAP2_ACT_BUY_PET_BASE);
    } else if (action >= SAP2_ACT_SELL_BASE && action < SAP2_ACT_SELL_BASE + SAP2_TEAM) {
        sap2_sell(s, action - SAP2_ACT_SELL_BASE);
    } else if (action >= SAP2_ACT_COMBINE_BASE && action < SAP2_ACT_COMBINE_BASE + 10) {
        int i, j;
        sap2_pair(action - SAP2_ACT_COMBINE_BASE, &i, &j);
        sap2_combine(s, i, j);
    } else if (action == SAP2_ACT_REROLL) {
        s->gold = (int16_t)(s->gold - 1);
        sap2_roll_shop(s, pet_slots, food_slots);
    } else if (action >= SAP2_ACT_REPOSITION_BASE && action < SAP2_ACT_REPOSITION_BASE + 10) {
        int i, j;
        sap2_pair(action - SAP2_ACT_REPOSITION_BASE, &i, &j);
        sap2_reposition(s, i, j);
    } else if (action >= SAP2_ACT_BUY_FOOD_BASE && action < SAP2_ACT_BUY_FOOD_BASE + SAP2_MAX_SHOP_FOOD * SAP2_TEAM) {
        const int off = action - SAP2_ACT_BUY_FOOD_BASE;
        sap2_buy_food(s, off / SAP2_TEAM, off % SAP2_TEAM);
    } else if (action >= SAP2_ACT_FREEZE_PET_BASE && action < SAP2_ACT_FREEZE_PET_BASE + SAP2_MAX_SHOP_PETS) {
        sap2_toggle_freeze_pet(s, action - SAP2_ACT_FREEZE_PET_BASE);
    } else if (action >= SAP2_ACT_FREEZE_FOOD_BASE && action < SAP2_ACT_FREEZE_FOOD_BASE + SAP2_MAX_SHOP_FOOD) {
        sap2_toggle_freeze_food(s, action - SAP2_ACT_FREEZE_FOOD_BASE);
    }

    if (!s->ended) {
        s->actions_taken++;
        if (s->actions_taken >= SAP2_SHOP_ACTION_BUDGET) {
            s->ended = 1;
        }
    }
}

/* -------------------------------------------------------------------- */
/* Battle
 *
 * Correction worth recording: an earlier draft of this file had a faint
 * during battle permanently clear that pet's persistent team slot,
 * carried over into the next round. That's wrong - confirmed directly:
 * a defeat costs exactly one life (already the only consequence "The
 * Basics" page states), and fainting is not permanent for the team that
 * suffered it; a pet lost in battle is back, at full health, for the next
 * round's shop phase. The only thing that removes a pet from the roster
 * for good is an explicit effect that says so - Sleeping Pill is the
 * example (Tier 2, not in this phase's roster) - not simply losing a
 * fight. So: battle-time changes never touch the persistent team
 * (SapSeat2.team[]) at all, full stop - it's loaded into a throwaway
 * SapBattle2 copy and nothing about that copy, win or lose, fainted or
 * not, writes back. This is exactly sap-v1's original approach; the
 * multi-round wrapper around it doesn't change what a single battle does
 * to a team, only what happens to lives/trophies afterward. */

typedef struct {
    int8_t attack[2][SAP2_TEAM];
    int8_t health[2][SAP2_TEAM];
    uint8_t species[2][SAP2_TEAM];
    uint8_t level[2][SAP2_TEAM];
    uint8_t honey[2][SAP2_TEAM];
    int count[2];
} SapBattle2;

static inline void sap2_battle_load(SapBattle2 *b, const SapSeat2 *s, int side) {
    int n = 0;
    for (int i = 0; i < SAP2_TEAM; i++) {
        if (s->team[i].species == SAP2_SPECIES_EMPTY) {
            continue;
        }
        b->attack[side][n] = s->team[i].attack;
        b->health[side][n] = s->team[i].health;
        b->species[side][n] = s->team[i].species;
        b->level[side][n] = s->team[i].level;
        b->honey[side][n] = s->team[i].honey_perk;
        n++;
    }
    b->count[side] = n;
}

static inline void sap2_battle_remove(SapBattle2 *b, int side, int idx) {
    for (int i = idx; i + 1 < b->count[side]; i++) {
        b->attack[side][i] = b->attack[side][i + 1];
        b->health[side][i] = b->health[side][i + 1];
        b->species[side][i] = b->species[side][i + 1];
        b->level[side][i] = b->level[side][i + 1];
        b->honey[side][i] = b->honey[side][i + 1];
    }
    b->count[side]--;
}

static inline void sap2_battle_insert_front(SapBattle2 *b, int side, uint8_t species, int8_t atk,
                                             int8_t hp, uint8_t level) {
    if (b->count[side] >= SAP2_TEAM) {
        return;
    }
    for (int i = b->count[side]; i > 0; i--) {
        b->attack[side][i] = b->attack[side][i - 1];
        b->health[side][i] = b->health[side][i - 1];
        b->species[side][i] = b->species[side][i - 1];
        b->level[side][i] = b->level[side][i - 1];
        b->honey[side][i] = b->honey[side][i - 1];
    }
    b->attack[side][0] = atk;
    b->health[side][0] = hp;
    b->species[side][0] = species;
    b->level[side][0] = level;
    b->honey[side][0] = 0;
    b->count[side]++;

    for (int i = 1; i < b->count[side]; i++) {
        if (b->species[side][i] == SAP2_HORSE) {
            b->attack[side][0] = (int8_t)(b->attack[side][0] + b->level[side][i]);
            if (b->attack[side][0] > 50) {
                b->attack[side][0] = 50;
            }
        }
    }
}

static inline void sap2_battle_resolve_faint(SapBattle2 *b, uint64_t *rng, int side, int idx) {
    const uint8_t species = b->species[side][idx];
    const uint8_t level = b->level[side][idx];
    const uint8_t honey = b->honey[side][idx];

    if (species == SAP2_ANT) {
        int friends[SAP2_TEAM];
        int n = 0;
        for (int i = 0; i < b->count[side]; i++) {
            if (i != idx) {
                friends[n++] = i;
            }
        }
        int picked[SAP2_TEAM];
        const int k = sap2_pick_random(rng, friends, n, 1, picked);
        for (int p = 0; p < k; p++) {
            const int t = picked[p];
            b->attack[side][t] = (int8_t)(b->attack[side][t] + level);
            b->health[side][t] = (int8_t)(b->health[side][t] + level);
            if (b->attack[side][t] > 50) {
                b->attack[side][t] = 50;
            }
            if (b->health[side][t] > 50) {
                b->health[side][t] = 50;
            }
        }
    } else if (species == SAP2_CRICKET) {
        sap2_battle_remove(b, side, idx);
        sap2_battle_insert_front(b, side, SAP2_CRICKET_TOKEN, level, level, level);
        return;
    }

    if (honey) {
        sap2_battle_remove(b, side, idx);
        sap2_battle_insert_front(b, side, SAP2_BEE, 1, 1, 1);
        return;
    }

    sap2_battle_remove(b, side, idx);
}

static inline void sap2_battle_start(SapBattle2 *b, uint64_t *rng) {
    for (;;) {
        int best = -1, best_side = -1;
        int8_t best_atk = -1;
        int candidates_at_best = 0;

        for (int side = 0; side < 2; side++) {
            for (int i = 0; i < b->count[side]; i++) {
                if (b->species[side][i] != SAP2_MOSQUITO) {
                    continue;
                }
                if (b->attack[side][i] > best_atk) {
                    best_atk = b->attack[side][i];
                    candidates_at_best = 1;
                } else if (b->attack[side][i] == best_atk) {
                    candidates_at_best++;
                }
            }
        }
        if (best_atk < 0) {
            return;
        }

        int r = candidates_at_best > 1 ? (int)(sap2_splitmix64(rng) % (uint64_t)candidates_at_best) : 0;
        for (int side = 0; side < 2 && best_side < 0; side++) {
            for (int i = 0; i < b->count[side]; i++) {
                if (b->species[side][i] == SAP2_MOSQUITO && b->attack[side][i] == best_atk) {
                    if (r == 0) {
                        best_side = side;
                        best = i;
                        break;
                    }
                    r--;
                }
            }
        }

        const int mosquito_side = best_side;
        const int mosquito_idx = best;
        const int enemy = mosquito_side ^ 1;
        const int n_hits = b->level[mosquito_side][mosquito_idx] < b->count[enemy]
                                ? b->level[mosquito_side][mosquito_idx]
                                : b->count[enemy];
        int candidates[SAP2_TEAM];
        for (int i = 0; i < b->count[enemy]; i++) {
            candidates[i] = i;
        }
        int picked[SAP2_TEAM];
        const int k = sap2_pick_random(rng, candidates, b->count[enemy], n_hits, picked);
        for (int a = 0; a < k; a++) {
            for (int c = a + 1; c < k; c++) {
                if (picked[c] > picked[a]) {
                    const int tmp = picked[a];
                    picked[a] = picked[c];
                    picked[c] = tmp;
                }
            }
        }

        uint8_t f_species[SAP2_TEAM];
        uint8_t f_level[SAP2_TEAM];
        uint8_t f_honey[SAP2_TEAM];
        int f_idx[SAP2_TEAM];
        int fc = 0;
        for (int p = 0; p < k; p++) {
            const int t = picked[p];
            b->health[enemy][t] = (int8_t)(b->health[enemy][t] - 1);
            if (b->health[enemy][t] <= 0) {
                f_idx[fc] = t;
                f_species[fc] = b->species[enemy][t];
                f_level[fc] = b->level[enemy][t];
                f_honey[fc] = b->honey[enemy][t];
                fc++;
            }
        }
        for (int i = 0; i < fc; i++) {
            sap2_battle_remove(b, enemy, f_idx[i]);
        }
        for (int i = 0; i < fc; i++) {
            if (f_species[i] == SAP2_ANT) {
                int friends[SAP2_TEAM];
                for (int q = 0; q < b->count[enemy]; q++) {
                    friends[q] = q;
                }
                int picked2[SAP2_TEAM];
                const int k2 = sap2_pick_random(rng, friends, b->count[enemy], 1, picked2);
                for (int pp = 0; pp < k2; pp++) {
                    const int t2 = picked2[pp];
                    b->attack[enemy][t2] = (int8_t)(b->attack[enemy][t2] + f_level[i]);
                    b->health[enemy][t2] = (int8_t)(b->health[enemy][t2] + f_level[i]);
                    if (b->attack[enemy][t2] > 50) {
                        b->attack[enemy][t2] = 50;
                    }
                    if (b->health[enemy][t2] > 50) {
                        b->health[enemy][t2] = 50;
                    }
                }
            } else if (f_species[i] == SAP2_CRICKET) {
                sap2_battle_insert_front(b, enemy, SAP2_CRICKET_TOKEN, (int8_t)f_level[i], (int8_t)f_level[i],
                                          f_level[i]);
                continue;
            }
            if (f_honey[i]) {
                sap2_battle_insert_front(b, enemy, SAP2_BEE, 1, 1, 1);
            }
        }

        b->species[mosquito_side][mosquito_idx] = SAP2_SPECIES_EMPTY + SAP2_NUM_ALL_SPECIES; /* sentinel */
    }
}

/* Resolves one round's battle. Returns which SEAT won *this round*
 * (0/1/-1 for draw) - not a match-level status code, that's
 * sap2_resolve_round's job once lives/trophies are applied. Does not
 * touch either seat's persistent team - see the file comment above
 * SapBattle2: fainting in battle costs a life, not the pet. */
static inline int sap2_battle(SAP2 *env) {
    SapBattle2 b;
    memset(&b, 0, sizeof(b));
    sap2_battle_load(&b, &env->seat[0], 0);
    sap2_battle_load(&b, &env->seat[1], 1);

    sap2_battle_start(&b, &env->battle_rng);
    for (int side = 0; side < 2; side++) {
        for (int i = 0; i < b.count[side]; i++) {
            if (b.species[side][i] >= SAP2_NUM_ALL_SPECIES) {
                b.species[side][i] = SAP2_MOSQUITO;
            }
        }
    }

    while (b.count[0] > 0 && b.count[1] > 0) {
        const int8_t a0 = b.attack[0][0], a1 = b.attack[1][0];
        b.health[0][0] = (int8_t)(b.health[0][0] - a1);
        b.health[1][0] = (int8_t)(b.health[1][0] - a0);

        const int faint0 = b.health[0][0] <= 0;
        const int faint1 = b.health[1][0] <= 0;
        if (!faint0 && !faint1) {
            continue;
        }
        if (faint0 && faint1) {
            if (a0 == a1 ? (sap2_splitmix64(&env->battle_rng) & 1) : a0 > a1) {
                sap2_battle_resolve_faint(&b, &env->battle_rng, 0, 0);
                sap2_battle_resolve_faint(&b, &env->battle_rng, 1, 0);
            } else {
                sap2_battle_resolve_faint(&b, &env->battle_rng, 1, 0);
                sap2_battle_resolve_faint(&b, &env->battle_rng, 0, 0);
            }
        } else if (faint0) {
            sap2_battle_resolve_faint(&b, &env->battle_rng, 0, 0);
        } else {
            sap2_battle_resolve_faint(&b, &env->battle_rng, 1, 0);
        }
    }

    if (b.count[0] > 0 && b.count[1] == 0) {
        return 0;
    }
    if (b.count[1] > 0 && b.count[0] == 0) {
        return 1;
    }
    return -1;
}

/* Applies this round's life/trophy changes, advances turn/round, and
 * either rolls the next round's shop (returns SAP2_ONGOING - the match
 * continues) or ends the match (returns a terminal status). See
 * docs/envs/sap-v2.md "Match rules". */
static inline int sap2_resolve_round(SAP2 *env) {
    const int round_winner = sap2_battle(env); /* 0, 1, or -1 for a draw */

    if (round_winner == 0) {
        env->seat[0].trophies++;
        env->seat[1].lives--;
    } else if (round_winner == 1) {
        env->seat[1].trophies++;
        env->seat[0].lives--;
    }
    env->round++;

    if (env->seat[0].trophies >= SAP2_TROPHIES_TO_WIN) {
        env->done = 1;
        return SAP2_P0_WIN;
    }
    if (env->seat[1].trophies >= SAP2_TROPHIES_TO_WIN) {
        env->done = 1;
        return SAP2_P1_WIN;
    }
    if (env->seat[0].lives <= 0) {
        env->done = 1;
        return SAP2_P1_WIN;
    }
    if (env->seat[1].lives <= 0) {
        env->done = 1;
        return SAP2_P0_WIN;
    }

    if (env->round >= SAP2_MAX_ROUNDS) {
        env->done = 1;
        if (env->seat[0].trophies != env->seat[1].trophies) {
            return env->seat[0].trophies > env->seat[1].trophies ? SAP2_P0_WIN_STEP_LIMIT : SAP2_P1_WIN_STEP_LIMIT;
        }
        if (env->seat[0].lives != env->seat[1].lives) {
            return env->seat[0].lives > env->seat[1].lives ? SAP2_P0_WIN_STEP_LIMIT : SAP2_P1_WIN_STEP_LIMIT;
        }
        return SAP2_DRAW_STEP_LIMIT;
    }

    /* Match continues: advance to the next round. */
    env->turn++;
    if (env->turn == 3) {
        /* "Players will gain one life at the start of turn 3 if they have
         * lost any so far" - a one-time correction, checked only here,
         * capped at the starting total. */
        for (int side = 0; side < 2; side++) {
            if (env->seat[side].lives < SAP2_STARTING_LIVES) {
                env->seat[side].lives++;
            }
        }
    }

    int pet_slots, food_slots;
    sap2_shop_size(env->turn, &pet_slots, &food_slots);
    for (int side = 0; side < 2; side++) {
        SapSeat2 *s = &env->seat[side];
        s->gold = SAP2_STARTING_GOLD;
        s->ended = 0;
        s->actions_taken = 0;
        /* Horse's "until next turn" buff expires here - see
         * sap2_fire_friend_summoned's comment. Everything else about a
         * surviving pet (species/level/xp/honey/permanent stat changes)
         * persists untouched; only clear what Horse specifically granted
         * is not tracked separately from a pet's base stats in this
         * representation, so this round-advance does not attempt to
         * subtract it back out - a known simplification, flagged rather
         * than silently wrong: Horse's buff is effectively permanent here
         * too, same as sap-v1, until a later phase tracks temporary and
         * permanent stat components separately. */
        sap2_roll_shop(s, pet_slots, food_slots);
    }
    return SAP2_ONGOING;
}

/* -------------------------------------------------------------------- */
/* Public interface */

static inline void sap2_reset(SAP2 *env, uint64_t seed) {
    memset(env, 0, sizeof(*env));
    env->done = 0;
    env->num_ticks = 0;
    env->turn = 1;
    env->round = 0;
    env->seat[0].rng = seed ^ 0x9E3779B97F4A7C15ull;
    env->seat[1].rng = seed ^ 0xC2B2AE3D27D4EB4Full;
    env->battle_rng = seed ^ 0x165667B19E3779F9ull;
    env->seat[0].gold = SAP2_STARTING_GOLD;
    env->seat[1].gold = SAP2_STARTING_GOLD;
    env->seat[0].lives = SAP2_STARTING_LIVES;
    env->seat[1].lives = SAP2_STARTING_LIVES;

    int pet_slots, food_slots;
    sap2_shop_size(env->turn, &pet_slots, &food_slots);
    sap2_roll_shop(&env->seat[0], pet_slots, food_slots);
    sap2_roll_shop(&env->seat[1], pet_slots, food_slots);
}

static inline int sap2_step(SAP2 *env, int action_0, int action_1) {
    const int actions[2] = {action_0, action_1};

    env->moves[2 * env->num_ticks] = action_0;
    env->moves[2 * env->num_ticks + 1] = action_1;
    env->num_ticks++;

    int pet_slots, food_slots;
    sap2_shop_size(env->turn, &pet_slots, &food_slots);

    int illegal[2] = {0, 0};
    for (int seat = 0; seat < 2; seat++) {
        if (env->seat[seat].ended) {
            continue;
        }
        if (actions[seat] < 0 || actions[seat] >= SAP2_NUM_ACTIONS) {
            illegal[seat] = 1;
            continue;
        }
        uint8_t mask[SAP2_NUM_ACTIONS];
        sap2_legal_for(&env->seat[seat], pet_slots, food_slots, mask);
        if (!mask[actions[seat]]) {
            illegal[seat] = 1;
        }
    }

    if (illegal[0] || illegal[1]) {
        env->done = 1;
        if (illegal[0] && illegal[1]) {
            return SAP2_DRAW_ILLEGAL;
        }
        return illegal[0] ? SAP2_P1_WIN_ILLEGAL : SAP2_P0_WIN_ILLEGAL;
    }

    for (int seat = 0; seat < 2; seat++) {
        if (!env->seat[seat].ended) {
            sap2_apply(&env->seat[seat], actions[seat], pet_slots, food_slots);
        }
    }

    if (env->seat[0].ended && env->seat[1].ended) {
        return sap2_resolve_round(env);
    }
    return SAP2_ONGOING;
}

static inline void sap2_observe(const SAP2 *env, int seat, float *out) {
    const SapSeat2 *s = &env->seat[seat];
    memset(out, 0, SAP2_OBS_FLOATS * sizeof(float));
    float *p = out;

    *p++ = (float)s->gold;
    *p++ = (float)s->lives;
    *p++ = (float)s->trophies;
    *p++ = (float)env->turn;

    for (int t = 0; t < SAP2_TEAM; t++) {
        const SapPet2 *pet = &s->team[t];
        p[pet->species] = 1.0f;
        p += SAP2_NUM_ALL_SPECIES;
        *p++ = (float)pet->attack;
        *p++ = (float)pet->health;
        if (pet->species != SAP2_SPECIES_EMPTY) {
            p[pet->level - 1] = 1.0f;
        }
        p += SAP2_MAX_LEVEL;
        *p++ = (float)pet->honey_perk;
    }

    for (int k = 0; k < SAP2_MAX_SHOP_PETS; k++) {
        const SapShopPet2 *sp = &s->shop_pets[k];
        p[sp->species] = 1.0f;
        p += SAP2_NUM_SHOP_SPECIES + 1;
        *p++ = (float)sp->hp_bonus;
        *p++ = (float)sp->frozen;
    }

    for (int f = 0; f < SAP2_MAX_SHOP_FOOD; f++) {
        const SapShopFood2 *sf = &s->shop_food[f];
        p[sf->species] = 1.0f;
        p += SAP2_NUM_FOODS;
        *p++ = (float)sf->frozen;
    }
}

static inline void sap2_legal(const SAP2 *env, int seat, uint8_t *out) {
    int pet_slots, food_slots;
    sap2_shop_size(env->turn, &pet_slots, &food_slots);
    sap2_legal_for(&env->seat[seat], pet_slots, food_slots, out);
}

#endif /* POLICYCLASH_SAP2_H */
