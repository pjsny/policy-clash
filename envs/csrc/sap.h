/* Super Auto Pets, Tier-1-only single-round MVP. Pure C, no Python, no
 * allocation, no global state.
 *
 * One round: both seats build a 5-slot team from a Tier-1-only shop, acting
 * simultaneously (neither sees the other's team or shop), then one battle
 * resolves deterministically and the episode ends. No freeze, no multi-turn
 * tier progression - see docs/envs/sap-v1.md for the full design rationale
 * this header implements.
 *
 * Every value in here is an integer. Floats appear only in the observation
 * buffer, which nothing in the rules reads back - same rule connect4 and
 * tron_duel follow, for the same reason: "same seed, same env version, same
 * policies, same bytes out" is the property the leaderboard rests on.
 *
 * Kept free of Python so it can be compiled standalone for fuzzing and,
 * later, to wasm for the replay viewer.
 */

#ifndef POLICYCLASH_SAP_H
#define POLICYCLASH_SAP_H

#include <stdint.h>
#include <string.h>

#define SAP_TEAM 5
#define SAP_SHOP_PETS 3
#define SAP_STARTING_GOLD 10
#define SAP_MAX_LEVEL 3

/* Shop-buyable species, 1-indexed; 0 is "empty". Order here is the species
 * one-hot order in the observation and in docs/envs/sap-v1.md's appendix. */
enum {
    SAP_SPECIES_EMPTY = 0,
    SAP_ANT = 1,
    SAP_BEAVER = 2,
    SAP_CRICKET = 3,
    SAP_DUCK = 4,
    SAP_FISH = 5,
    SAP_HORSE = 6,
    SAP_MOSQUITO = 7,
    SAP_OTTER = 8,
    SAP_PIG = 9,
    SAP_PIGEON = 10,
    SAP_NUM_SHOP_SPECIES = 10, /* 1..10, i.e. SAP_PIGEON */
    /* Tokens: never a shop offer, only ever reach a team slot via a Faint
     * summon. They need their own species ids because they can sit on a
     * team, and the observation's team-slot species one-hot has to be able
     * to say so - a gap the first draft of sap-v1.md missed by assuming
     * "species one-hot" only needed to cover the 10 shop-buyable pets. */
    SAP_CRICKET_TOKEN = 11,
    SAP_BEE = 12,
    SAP_NUM_ALL_SPECIES = 13 /* 0..12 inclusive */
};

/* Foods. 0 is "empty". Bread Crumbs is never in the normal shop roll pool -
 * it only ever appears via a sold Pigeon stocking it (see sap_sell). */
enum { SAP_FOOD_EMPTY = 0, SAP_APPLE = 1, SAP_HONEY = 2, SAP_BREAD_CRUMBS = 3, SAP_NUM_FOODS = 4 };

static const int SAP_FOOD_COST[SAP_NUM_FOODS] = {0, 3, 3, 0};

/* Ability trigger a species fires on. Tier-1's actual battle-relevant
 * triggers are only FAINT and START_OF_BATTLE - nothing here has Hurt,
 * FriendFainted, KnockOut, or the ahead/behind triggers later tiers use, so
 * this header implements only the subset of docs/adding-an-env.md's trigger
 * taxonomy that Tier 1 actually exercises. */
enum {
    SAP_TRIG_NONE = 0,
    SAP_TRIG_FAINT = 1,
    SAP_TRIG_SELL = 2,
    SAP_TRIG_BUY = 3,
    SAP_TRIG_LEVELUP = 4,
    SAP_TRIG_FRIEND_SUMMONED = 5,
    SAP_TRIG_START_OF_BATTLE = 6
};

/* Base stats and trigger, indexed by species id. Tokens (11, 12) have no
 * fixed base stats (Cricket Token's is set by the summoning Cricket's
 * level; Bee is always 1/1, set directly) and no ability, so their rows are
 * unused placeholders. Source: data/turtle_pack/pets.json, tier 1. */
static const int8_t SAP_BASE_ATK[SAP_NUM_ALL_SPECIES] = {0, 2, 3, 1, 2, 2, 2, 2, 1, 4, 3, 0, 1};
static const int8_t SAP_BASE_HP[SAP_NUM_ALL_SPECIES] = {0, 2, 2, 3, 2, 3, 1, 2, 4, 1, 2, 0, 1};
static const uint8_t SAP_TRIGGER[SAP_NUM_ALL_SPECIES] = {
    SAP_TRIG_NONE,            /* empty */
    SAP_TRIG_FAINT,           /* Ant */
    SAP_TRIG_SELL,            /* Beaver */
    SAP_TRIG_FAINT,           /* Cricket */
    SAP_TRIG_SELL,            /* Duck */
    SAP_TRIG_LEVELUP,         /* Fish */
    SAP_TRIG_FRIEND_SUMMONED, /* Horse */
    SAP_TRIG_START_OF_BATTLE, /* Mosquito */
    SAP_TRIG_BUY,             /* Otter */
    SAP_TRIG_SELL,            /* Pig */
    SAP_TRIG_SELL,            /* Pigeon */
    SAP_TRIG_NONE,            /* Cricket Token */
    SAP_TRIG_NONE             /* Bee */
};

/* Action layout. See docs/envs/sap-v1.md "Actions" for the full table this
 * mirrors exactly - index math here must match that doc's block boundaries. */
enum {
    SAP_ACT_END_TURN = 0,
    SAP_ACT_BUY_PET_BASE = 1,      /* +0..2: shop pet slot */
    SAP_ACT_SELL_BASE = 4,         /* +0..4: team slot */
    SAP_ACT_COMBINE_BASE = 9,      /* +0..9: team slot pair, see sap_pair() */
    SAP_ACT_REROLL = 19,
    SAP_ACT_REPOSITION_BASE = 20,  /* +0..9: team slot pair */
    SAP_ACT_BUY_FOOD_BASE = 30,    /* +0..4: team slot */
    SAP_NUM_ACTIONS = 35
};

#define SAP_SHOP_ACTION_BUDGET 20
/* A seat's actions_taken rises by at most 1 per tick it is active, starting
 * at tick 1, so it cannot reach SAP_SHOP_ACTION_BUDGET before tick
 * SAP_SHOP_ACTION_BUDGET itself - both seats are therefore guaranteed
 * `ended` by that tick's step() call at the latest, which is exactly the
 * call that resolves the battle (there is no separate battle tick - see
 * sap-v1.md). No "+1" belongs here: that would double-count the same tick
 * this bound already covers. */
#define SAP_MAX_TICKS SAP_SHOP_ACTION_BUDGET

/* Observation layout (float32, C-order). See docs/envs/sap-v1.md. */
enum {
    SAP_TEAM_SLOT_FLOATS = SAP_NUM_ALL_SPECIES /* species one-hot */
                            + 1                /* attack */
                            + 1                /* health */
                            + SAP_MAX_LEVEL     /* level one-hot */
                            + 1,                /* honey perk flag */
    SAP_SHOP_PET_SLOT_FLOATS = (SAP_NUM_SHOP_SPECIES + 1) /* species one-hot, 0..10 */
                               + 1,                        /* Duck's hp bonus */
    SAP_SHOP_FOOD_FLOATS = SAP_NUM_FOODS, /* food one-hot */
    SAP_OBS_FLOATS = 1 /* gold */
                      + SAP_TEAM * SAP_TEAM_SLOT_FLOATS
                      + SAP_SHOP_PETS * SAP_SHOP_PET_SLOT_FLOATS
                      + SAP_SHOP_FOOD_FLOATS
};

/* Step status. Outcome and termination folded into one code, same pattern
 * connect4 and tron_duel use so the step function has no out-parameters. */
enum {
    SAP_ONGOING = 0,
    SAP_P0_WIN = 1,
    SAP_P1_WIN = 2,
    SAP_DRAW = 3,
    SAP_P0_WIN_ILLEGAL = 4, /* seat 1 submitted an out-of-range action */
    SAP_P1_WIN_ILLEGAL = 5, /* seat 0 did */
    SAP_DRAW_ILLEGAL = 6    /* both did, same tick */
};

typedef struct {
    uint8_t species; /* SAP_SPECIES_EMPTY if the slot is empty */
    int8_t attack;
    int8_t health;
    uint8_t level;       /* 1..3, meaningless when species is empty */
    uint8_t xp;           /* 1..3, combine-accumulated; xp == level always here */
    uint8_t honey_perk;   /* 1 if this pet was fed Honey and hasn't fainted since */
} SapPet;

typedef struct {
    uint8_t species; /* 0 (empty) or one of the 10 shop species */
    int8_t hp_bonus;  /* Duck's Sell ability accumulates here; see sap_sell */
} SapShopPet;

typedef struct {
    SapPet team[SAP_TEAM];
    SapShopPet shop_pets[SAP_SHOP_PETS];
    uint8_t shop_food; /* 0 (empty) or a SAP_FOOD_* id */
    int16_t gold;
    uint64_t rng;        /* this seat's own shop RNG stream, fully independent
                           * of the other seat's - see sap-v1.md's note on why
                           * each seat's shop is rolled independently rather
                           * than from one shared pool. */
    int ended;            /* 1 once this seat has stopped acting this episode */
    int actions_taken;    /* counts toward SAP_SHOP_ACTION_BUDGET */
} SapSeat;

typedef struct {
    SapSeat seat[2];
    uint64_t battle_rng; /* separate stream: start-of-battle target/tiebreak
                           * draws, kept apart from either seat's shop RNG so
                           * a seat's own reroll count never perturbs battle
                           * randomness or vice versa. */
    int done;
    int num_ticks;
    int32_t moves[2 * SAP_MAX_TICKS];
} SAP;

/* -------------------------------------------------------------------- */
/* RNG: same splitmix64 tron_duel.h uses, for the same reason - integer,
 * deterministic, no library dependency. */

static inline uint64_t sap_splitmix64(uint64_t *state) {
    uint64_t z = (*state += 0x9E3779B97F4A7C15ull);
    z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ull;
    z = (z ^ (z >> 27)) * 0x94D049BB133111EBull;
    return z ^ (z >> 31);
}

/* Picks up to k distinct indices from candidates[0..count), without
 * replacement, writing them into out[] and returning how many were picked
 * (min(k, count)). Used for every "N random friends/enemies" effect. Partial
 * Fisher-Yates over a local copy so candidates[] itself is untouched. */
static inline int sap_pick_random(uint64_t *rng, const int *candidates, int count, int k, int *out) {
    int pool[SAP_TEAM];
    int n = count;
    if (n > SAP_TEAM) {
        n = SAP_TEAM; /* never true in this env (team caps at 5), just a guard */
    }
    for (int i = 0; i < n; i++) {
        pool[i] = candidates[i];
    }
    if (k > n) {
        k = n;
    }
    for (int i = 0; i < k; i++) {
        const int j = i + (int)(sap_splitmix64(rng) % (uint64_t)(n - i));
        const int tmp = pool[i];
        pool[i] = pool[j];
        pool[j] = tmp;
        out[i] = pool[i];
    }
    return k;
}

/* -------------------------------------------------------------------- */
/* Shop */

static inline void sap_roll_shop(SapSeat *s) {
    for (int i = 0; i < SAP_SHOP_PETS; i++) {
        s->shop_pets[i].species = (uint8_t)(1 + sap_splitmix64(&s->rng) % SAP_NUM_SHOP_SPECIES);
        s->shop_pets[i].hp_bonus = 0;
    }
    /* Normal rolls only ever offer Apple or Honey - Bread Crumbs is never
     * rolled, only stocked by a sold Pigeon. */
    s->shop_food = (uint8_t)(1 + sap_splitmix64(&s->rng) % 2);
}

static inline int sap_team_count(const SapSeat *s) {
    int n = 0;
    for (int i = 0; i < SAP_TEAM; i++) {
        if (s->team[i].species != SAP_SPECIES_EMPTY) {
            n++;
        }
    }
    return n;
}

static inline int sap_leftmost_empty(const SapSeat *s) {
    for (int i = 0; i < SAP_TEAM; i++) {
        if (s->team[i].species == SAP_SPECIES_EMPTY) {
            return i;
        }
    }
    return -1;
}

/* Every occupied team slot except `exclude` (a "friend", never self). */
static inline int sap_friends(const SapSeat *s, int exclude, int *out) {
    int n = 0;
    for (int i = 0; i < SAP_TEAM; i++) {
        if (i != exclude && s->team[i].species != SAP_SPECIES_EMPTY) {
            out[n++] = i;
        }
    }
    return n;
}

static inline void sap_clamp_stats(SapPet *p) {
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

/* Fires Horse's Friend-summoned trigger on every OTHER team member when
 * `slot` just entered play (bought, or summoned by a Faint ability). Shared
 * by both the shop-phase Buy path and the battle-phase Faint-summon path -
 * Horse cares about a friend entering an empty slot regardless of phase. */
static inline void sap_fire_friend_summoned(SapSeat *s, int slot) {
    for (int i = 0; i < SAP_TEAM; i++) {
        if (i == slot || s->team[i].species != SAP_HORSE) {
            continue;
        }
        /* "Until next turn": there is no next turn in this single-round
         * MVP, so this buff is permanent for the rest of the episode -
         * documented simplification, see docs/envs/sap-v1.md. */
        s->team[slot].attack = (int8_t)(s->team[slot].attack + s->team[i].level);
        sap_clamp_stats(&s->team[slot]);
    }
}

/* Buy: fills the leftmost empty team slot at base stats, fires Buy (Otter)
 * and Friend-summoned (Horse) triggers. Caller has already checked the mask. */
static inline void sap_buy_pet(SapSeat *s, int shop_slot) {
    const int dest = sap_leftmost_empty(s);
    const uint8_t species = s->shop_pets[shop_slot].species;

    s->gold = (int16_t)(s->gold - 3);
    s->team[dest].species = species;
    s->team[dest].attack = SAP_BASE_ATK[species];
    s->team[dest].health = SAP_BASE_HP[species];
    s->team[dest].level = 1;
    s->team[dest].xp = 1;
    s->team[dest].honey_perk = 0;
    s->shop_pets[shop_slot].species = SAP_SPECIES_EMPTY;
    s->shop_pets[shop_slot].hp_bonus = 0;

    sap_fire_friend_summoned(s, dest);

    if (species == SAP_OTTER) {
        int friends[SAP_TEAM];
        const int n = sap_friends(s, dest, friends);
        int picked[SAP_TEAM];
        const int k = sap_pick_random(&s->rng, friends, n, s->team[dest].level, picked);
        for (int i = 0; i < k; i++) {
            s->team[picked[i]].health = (int8_t)(s->team[picked[i]].health + 1);
            sap_clamp_stats(&s->team[picked[i]]);
        }
    }
}

/* Sell: refund = level, fires the sold pet's Sell trigger (which reads the
 * pet's own level for its "N" before the slot is cleared), then empties the
 * slot. Selling is not a Faint - SAP_clone.md's trigger taxonomy keeps them
 * distinct, and nothing here fires FriendFainted or the sold pet's own
 * Faint ability. */
static inline void sap_sell(SapSeat *s, int slot) {
    SapPet sold = s->team[slot];
    s->gold = (int16_t)(s->gold + sold.level);
    s->team[slot].species = SAP_SPECIES_EMPTY;

    switch (sold.species) {
    case SAP_BEAVER: {
        int friends[SAP_TEAM];
        const int n = sap_friends(s, slot, friends);
        int picked[SAP_TEAM];
        const int k = sap_pick_random(&s->rng, friends, n, 2, picked);
        for (int i = 0; i < k; i++) {
            s->team[picked[i]].attack = (int8_t)(s->team[picked[i]].attack + sold.level);
            sap_clamp_stats(&s->team[picked[i]]);
        }
        break;
    }
    case SAP_DUCK:
        for (int i = 0; i < SAP_SHOP_PETS; i++) {
            if (s->shop_pets[i].species != SAP_SPECIES_EMPTY) {
                s->shop_pets[i].hp_bonus = (int8_t)(s->shop_pets[i].hp_bonus + sold.level);
            }
        }
        break;
    case SAP_PIG:
        s->gold = (int16_t)(s->gold + sold.level);
        break;
    case SAP_PIGEON:
        /* Only one food shop slot exists in this MVP, so "stock up to
         * `level` free Bread Crumbs" collapses to "the food slot becomes a
         * free Bread Crumbs", regardless of level - a resolved default for
         * the open question flagged in docs/envs/sap-v1.md, not a game-rule
         * claim about how multi-slot shops behave. */
        s->shop_food = SAP_BREAD_CRUMBS;
        break;
    default:
        break;
    }
}

/* Combine: keep slot i, clear slot j. Stats are max(each side)+1, not a sum
 * - SAP_clone.md section 3's rule, carried over verbatim. xp adds and caps
 * at 3, which is also the level (xp == level throughout this simplified
 * MVP tracking; see docs/envs/sap-v1.md's combine note). */
static inline void sap_combine(SapSeat *s, int i, int j) {
    SapPet *a = &s->team[i];
    const SapPet *b = &s->team[j];
    const uint8_t prev_level = a->level;

    a->attack = (int8_t)((a->attack > b->attack ? a->attack : b->attack) + 1);
    a->health = (int8_t)((a->health > b->health ? a->health : b->health) + 1);
    sap_clamp_stats(a);
    uint8_t xp = (uint8_t)(a->xp + b->xp);
    if (xp > SAP_MAX_LEVEL) {
        xp = SAP_MAX_LEVEL;
    }
    a->xp = xp;
    a->level = xp;
    a->honey_perk = (uint8_t)(a->honey_perk || b->honey_perk);
    s->team[j].species = SAP_SPECIES_EMPTY;

    /* Fish: LevelUp only fires on an actual transition to level 2 or 3 -
     * level 1 is the starting state, never a transition into it, so that
     * row's ability text (see sap-v1.md's appendix note) never fires. */
    if (a->species == SAP_FISH && a->level > prev_level && a->level >= 2) {
        int friends[SAP_TEAM];
        const int n = sap_friends(s, i, friends);
        int picked[SAP_TEAM];
        const int k = sap_pick_random(&s->rng, friends, n, a->level, picked);
        for (int p = 0; p < k; p++) {
            s->team[picked[p]].attack = (int8_t)(s->team[picked[p]].attack + a->level);
            s->team[picked[p]].health = (int8_t)(s->team[picked[p]].health + a->level);
            sap_clamp_stats(&s->team[picked[p]]);
        }
    }
}

static inline void sap_reposition(SapSeat *s, int i, int j) {
    const SapPet tmp = s->team[i];
    s->team[i] = s->team[j];
    s->team[j] = tmp;
}

static inline void sap_buy_food(SapSeat *s, int target) {
    const uint8_t food = s->shop_food;
    s->gold = (int16_t)(s->gold - SAP_FOOD_COST[food]);
    s->shop_food = SAP_FOOD_EMPTY;

    SapPet *p = &s->team[target];
    if (food == SAP_APPLE || food == SAP_BREAD_CRUMBS) {
        p->attack = (int8_t)(p->attack + 1);
        if (food == SAP_APPLE) {
            p->health = (int8_t)(p->health + 1);
        }
        sap_clamp_stats(p);
    } else if (food == SAP_HONEY) {
        p->honey_perk = 1;
    }
}

/* -------------------------------------------------------------------- */
/* Action dispatch */

/* Unordered pair (i, j), i < j, over SAP_TEAM slots, in the lexicographic
 * order docs/envs/sap-v1.md's action table specifies: (0,1) (0,2) (0,3)
 * (0,4) (1,2) (1,3) (1,4) (2,3) (2,4) (3,4). index is 0..9. */
static inline void sap_pair(int index, int *i, int *j) {
    static const int PI[10] = {0, 0, 0, 0, 1, 1, 1, 2, 2, 3};
    static const int PJ[10] = {1, 2, 3, 4, 2, 3, 4, 3, 4, 4};
    *i = PI[index];
    *j = PJ[index];
}

static inline int sap_can_combine(const SapSeat *s, int i, int j) {
    return s->team[i].species != SAP_SPECIES_EMPTY && s->team[i].species == s->team[j].species &&
           s->team[i].level < SAP_MAX_LEVEL;
}

static inline void sap_legal_for(const SapSeat *s, uint8_t *out) {
    memset(out, 0, SAP_NUM_ACTIONS);
    out[SAP_ACT_END_TURN] = 1;

    for (int k = 0; k < SAP_SHOP_PETS; k++) {
        out[SAP_ACT_BUY_PET_BASE + k] =
            (uint8_t)(s->shop_pets[k].species != SAP_SPECIES_EMPTY && s->gold >= 3 &&
                      sap_leftmost_empty(s) >= 0);
    }
    for (int t = 0; t < SAP_TEAM; t++) {
        out[SAP_ACT_SELL_BASE + t] = (uint8_t)(s->team[t].species != SAP_SPECIES_EMPTY);
    }
    for (int p = 0; p < 10; p++) {
        int i, j;
        sap_pair(p, &i, &j);
        out[SAP_ACT_COMBINE_BASE + p] = (uint8_t)sap_can_combine(s, i, j);
    }
    out[SAP_ACT_REROLL] = (uint8_t)(s->gold >= 1);
    for (int p = 0; p < 10; p++) {
        int i, j;
        sap_pair(p, &i, &j);
        out[SAP_ACT_REPOSITION_BASE + p] =
            (uint8_t)(s->team[i].species != SAP_SPECIES_EMPTY || s->team[j].species != SAP_SPECIES_EMPTY);
    }
    for (int t = 0; t < SAP_TEAM; t++) {
        out[SAP_ACT_BUY_FOOD_BASE + t] =
            (uint8_t)(s->shop_food != SAP_FOOD_EMPTY && s->gold >= SAP_FOOD_COST[s->shop_food] &&
                      s->team[t].species != SAP_SPECIES_EMPTY);
    }
}

/* Applies one legal action. Illegality is the caller's responsibility to
 * have already checked (sap_step does, via sap_legal_for, before calling
 * this) - this function trusts its input. */
static inline void sap_apply(SapSeat *s, int action) {
    if (action == SAP_ACT_END_TURN) {
        s->ended = 1;
    } else if (action >= SAP_ACT_BUY_PET_BASE && action < SAP_ACT_BUY_PET_BASE + SAP_SHOP_PETS) {
        sap_buy_pet(s, action - SAP_ACT_BUY_PET_BASE);
    } else if (action >= SAP_ACT_SELL_BASE && action < SAP_ACT_SELL_BASE + SAP_TEAM) {
        sap_sell(s, action - SAP_ACT_SELL_BASE);
    } else if (action >= SAP_ACT_COMBINE_BASE && action < SAP_ACT_COMBINE_BASE + 10) {
        int i, j;
        sap_pair(action - SAP_ACT_COMBINE_BASE, &i, &j);
        sap_combine(s, i, j);
    } else if (action == SAP_ACT_REROLL) {
        s->gold = (int16_t)(s->gold - 1);
        sap_roll_shop(s);
    } else if (action >= SAP_ACT_REPOSITION_BASE && action < SAP_ACT_REPOSITION_BASE + 10) {
        int i, j;
        sap_pair(action - SAP_ACT_REPOSITION_BASE, &i, &j);
        sap_reposition(s, i, j);
    } else if (action >= SAP_ACT_BUY_FOOD_BASE && action < SAP_ACT_BUY_FOOD_BASE + SAP_TEAM) {
        sap_buy_food(s, action - SAP_ACT_BUY_FOOD_BASE);
    }

    if (!s->ended) {
        s->actions_taken++;
        if (s->actions_taken >= SAP_SHOP_ACTION_BUDGET) {
            s->ended = 1; /* budget exhausted - forced end, see sap-v1.md */
        }
    }
}

/* -------------------------------------------------------------------- */
/* Battle */

typedef struct {
    int8_t attack[2][SAP_TEAM];
    int8_t health[2][SAP_TEAM];
    uint8_t species[2][SAP_TEAM];
    uint8_t level[2][SAP_TEAM];
    uint8_t honey[2][SAP_TEAM];
    int count[2]; /* live pets; index 0 of each side's arrays is the front */
} SapBattle;

static inline void sap_battle_load(SapBattle *b, const SapSeat *s, int side) {
    int n = 0;
    for (int i = 0; i < SAP_TEAM; i++) {
        if (s->team[i].species == SAP_SPECIES_EMPTY) {
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

static inline void sap_battle_remove(SapBattle *b, int side, int idx) {
    for (int i = idx; i + 1 < b->count[side]; i++) {
        b->attack[side][i] = b->attack[side][i + 1];
        b->health[side][i] = b->health[side][i + 1];
        b->species[side][i] = b->species[side][i + 1];
        b->level[side][i] = b->level[side][i + 1];
        b->honey[side][i] = b->honey[side][i + 1];
    }
    b->count[side]--;
}

/* Inserts a newly-summoned pet at the front of `side` (position 0), if
 * there is room. SAP_TEAM is the hard cap - a summon into a full side is
 * simply lost, matching the real game's "no room, no summon" rule. Fires
 * Horse's Friend-summoned trigger on the rest of that side, same as a shop
 * Buy does; summon events are phase-agnostic. */
static inline void sap_battle_insert_front(SapBattle *b, int side, uint8_t species, int8_t atk,
                                            int8_t hp, uint8_t level) {
    if (b->count[side] >= SAP_TEAM) {
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
        if (b->species[side][i] == SAP_HORSE) {
            b->attack[side][0] = (int8_t)(b->attack[side][0] + b->level[side][i]);
            if (b->attack[side][0] > 50) {
                b->attack[side][0] = 50;
            }
        }
    }
}

/* Resolves everything a faint at (side, idx) causes - its own Faint ability
 * (Ant, Cricket) and its Honey perk (summon a 1/1 Bee in its place) - then
 * removes it. Both read the fainted pet's own level/attack before removal,
 * so callers must not have removed it yet. `rng` is always battle_rng: Ant
 * and Cricket can only ever faint during battle in this MVP (nothing in
 * the Tier-1+Apple/Honey roster can down a pet during the shop phase), so
 * there is no shop-RNG case to route this through. */
static inline void sap_battle_resolve_faint(SapBattle *b, uint64_t *rng, int side, int idx) {
    const uint8_t species = b->species[side][idx];
    const uint8_t level = b->level[side][idx];
    const uint8_t honey = b->honey[side][idx];

    if (species == SAP_ANT) {
        int friends[SAP_TEAM];
        int n = 0;
        for (int i = 0; i < b->count[side]; i++) {
            if (i != idx) {
                friends[n++] = i;
            }
        }
        int picked[SAP_TEAM];
        const int k = sap_pick_random(rng, friends, n, 1, picked);
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
    } else if (species == SAP_CRICKET) {
        sap_battle_remove(b, side, idx);
        sap_battle_insert_front(b, side, SAP_CRICKET_TOKEN, level, level, level);
        return; /* already removed */
    }

    if (honey) {
        sap_battle_remove(b, side, idx);
        sap_battle_insert_front(b, side, SAP_BEE, 1, 1, 1);
        return;
    }

    sap_battle_remove(b, side, idx);
}

/* Start-of-battle: every Mosquito on either side fires, strict
 * attack-descending order across BOTH sides with a random tiebreak, per
 * SAP_clone.md section 4's canonical ordering rule. A pet already fainted
 * (killed by an earlier Mosquito in this same ordering) does not fire. */
static inline void sap_battle_start(SapBattle *b, uint64_t *rng) {
    for (;;) {
        int best_side = -1, best_idx = -1;
        int8_t best_atk = -1;
        int candidates_at_best = 0;

        for (int side = 0; side < 2; side++) {
            for (int i = 0; i < b->count[side]; i++) {
                if (b->species[side][i] != SAP_MOSQUITO) {
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
            return; /* no un-fired Mosquito left */
        }

        /* Random tiebreak: pick the r-th (0-indexed) Mosquito at best_atk in
         * (side, index) scan order, r drawn from battle_rng. */
        int r = candidates_at_best > 1 ? (int)(sap_splitmix64(rng) % (uint64_t)candidates_at_best) : 0;
        for (int side = 0; side < 2 && best_side < 0; side++) {
            for (int i = 0; i < b->count[side]; i++) {
                if (b->species[side][i] == SAP_MOSQUITO && b->attack[side][i] == best_atk) {
                    if (r == 0) {
                        best_side = side;
                        best_idx = i;
                        break;
                    }
                    r--;
                }
            }
        }

        /* Mark fired by demoting species so the outer loop's scan skips it
         * next pass, without disturbing index order mid-scan. */
        const int mosquito_side = best_side;
        const int mosquito_idx = best_idx;
        const int enemy = mosquito_side ^ 1;
        const int n_hits = b->level[mosquito_side][mosquito_idx] < b->count[enemy]
                                ? b->level[mosquito_side][mosquito_idx]
                                : b->count[enemy];
        int candidates[SAP_TEAM];
        for (int i = 0; i < b->count[enemy]; i++) {
            candidates[i] = i;
        }
        int picked[SAP_TEAM];
        const int k = sap_pick_random(rng, candidates, b->count[enemy], n_hits, picked);
        /* Damage highest-index-first so an earlier removal never shifts an
         * index still queued in `picked`. */
        for (int a = 0; a < k; a++) {
            for (int c = a + 1; c < k; c++) {
                if (picked[c] > picked[a]) {
                    const int tmp = picked[a];
                    picked[a] = picked[c];
                    picked[c] = tmp;
                }
            }
        }
        /* Apply all k hits first, against the still-unmodified array -
         * `picked` indices are only valid together, before any removal or
         * insertion touches the array. Collecting which of them faint (and
         * copying out what their own faint effects need) has to finish
         * before any structural change: sap_battle_resolve_faint's token/Bee
         * insertion shifts every lower index up by one, which would
         * misdirect a still-pending removal at a smaller index in this same
         * batch if the two were interleaved index-by-index instead. */
        uint8_t f_species[SAP_TEAM];
        uint8_t f_level[SAP_TEAM];
        uint8_t f_honey[SAP_TEAM];
        int f_idx[SAP_TEAM]; /* descending, since `picked` already is */
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
        /* Pure removals, descending index order: removing a higher index
         * first never shifts a lower one still queued in f_idx. No
         * insertions happen in this pass, so this part alone would be safe
         * even interleaved - it's kept separate from the insert pass below
         * for the same reason that pass has to run after every removal is
         * done, not because this loop individually needs it. */
        for (int i = 0; i < fc; i++) {
            sap_battle_remove(b, enemy, f_idx[i]);
        }
        /* Now each fainted pet's own effect, using the copied-out data
         * rather than any index into the (already mutated) array. Ability
         * summon takes priority over a Honey perk on the same pet - only
         * one replacement ever occupies the vacated slot, matching "a pet
         * cannot summon two things when it faints once". Order between
         * distinct fainted pets here is insertion order among this batch,
         * not re-sorted by attack - multiple simultaneous faints from one
         * Mosquito volley are a narrow enough case that this is a
         * documented simplification, not the general ordering rule. */
        for (int i = 0; i < fc; i++) {
            if (f_species[i] == SAP_ANT) {
                int friends[SAP_TEAM];
                for (int q = 0; q < b->count[enemy]; q++) {
                    friends[q] = q;
                }
                int picked2[SAP_TEAM];
                const int k2 = sap_pick_random(rng, friends, b->count[enemy], 1, picked2);
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
            } else if (f_species[i] == SAP_CRICKET) {
                sap_battle_insert_front(b, enemy, SAP_CRICKET_TOKEN, (int8_t)f_level[i],
                                        (int8_t)f_level[i], f_level[i]);
                continue; /* ability summon wins; skip the honey check below */
            }
            if (f_honey[i]) {
                sap_battle_insert_front(b, enemy, SAP_BEE, 1, 1, 1);
            }
        }

        /* Demote the fired Mosquito's species so it is not picked again;
         * SAP_MOSQUITO itself never faints from this pass firing (it deals
         * damage, it does not take any), so its slot is still valid. */
        b->species[mosquito_side][mosquito_idx] = SAP_SPECIES_EMPTY + SAP_NUM_ALL_SPECIES; /* sentinel */
    }
}

static inline int sap_resolve_battle(SAP *env) {
    SapBattle b;
    memset(&b, 0, sizeof(b));
    sap_battle_load(&b, &env->seat[0], 0);
    sap_battle_load(&b, &env->seat[1], 1);

    sap_battle_start(&b, &env->battle_rng);
    /* Undo the "fired" sentinel sap_battle_start used - Mosquitoes fight
     * normally in the combat loop below like anything else. */
    for (int side = 0; side < 2; side++) {
        for (int i = 0; i < b.count[side]; i++) {
            if (b.species[side][i] >= SAP_NUM_ALL_SPECIES) {
                b.species[side][i] = SAP_MOSQUITO;
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

        /* Both fronts can only ever be the two pets that just fought, so
         * "attack-descending, random tiebreak" over at most two candidates
         * is just: higher pre-exchange attack goes first, coin-flip on a
         * tie. Pre-exchange attack is a0/a1, captured above. */
        if (faint0 && faint1) {
            if (a0 == a1 ? (sap_splitmix64(&env->battle_rng) & 1) : a0 > a1) {
                sap_battle_resolve_faint(&b, &env->battle_rng, 0, 0);
                sap_battle_resolve_faint(&b, &env->battle_rng, 1, 0);
            } else {
                sap_battle_resolve_faint(&b, &env->battle_rng, 1, 0);
                sap_battle_resolve_faint(&b, &env->battle_rng, 0, 0);
            }
        } else if (faint0) {
            sap_battle_resolve_faint(&b, &env->battle_rng, 0, 0);
        } else {
            sap_battle_resolve_faint(&b, &env->battle_rng, 1, 0);
        }
    }

    env->done = 1;
    if (b.count[0] > 0 && b.count[1] == 0) {
        return SAP_P0_WIN;
    }
    if (b.count[1] > 0 && b.count[0] == 0) {
        return SAP_P1_WIN;
    }
    return SAP_DRAW;
}

/* -------------------------------------------------------------------- */
/* Public interface */

static inline void sap_reset(SAP *env, uint64_t seed) {
    memset(env, 0, sizeof(*env));
    env->done = 0;
    env->num_ticks = 0;
    /* Two independent streams from one seed, decorrelated with distinct odd
     * salts before the first splitmix64 draw - same technique tron_duel.h
     * uses to turn one seed into several draws, applied here to get three
     * independent streams (two shop, one battle) instead of tron-duel's one. */
    env->seat[0].rng = seed ^ 0x9E3779B97F4A7C15ull;
    env->seat[1].rng = seed ^ 0xC2B2AE3D27D4EB4Full;
    env->battle_rng = seed ^ 0x165667B19E3779F9ull;
    env->seat[0].gold = SAP_STARTING_GOLD;
    env->seat[1].gold = SAP_STARTING_GOLD;
    sap_roll_shop(&env->seat[0]);
    sap_roll_shop(&env->seat[1]);
}

static inline int sap_step(SAP *env, int action_0, int action_1) {
    const int actions[2] = {action_0, action_1};

    env->moves[2 * env->num_ticks] = action_0;
    env->moves[2 * env->num_ticks + 1] = action_1;
    env->num_ticks++;

    int illegal[2] = {0, 0};
    for (int seat = 0; seat < 2; seat++) {
        if (env->seat[seat].ended) {
            continue; /* not asked to act; argument ignored, not validated */
        }
        if (actions[seat] < 0 || actions[seat] >= SAP_NUM_ACTIONS) {
            illegal[seat] = 1;
            continue;
        }
        uint8_t mask[SAP_NUM_ACTIONS];
        sap_legal_for(&env->seat[seat], mask);
        if (!mask[actions[seat]]) {
            illegal[seat] = 1;
        }
    }

    if (illegal[0] || illegal[1]) {
        env->done = 1;
        if (illegal[0] && illegal[1]) {
            return SAP_DRAW_ILLEGAL;
        }
        return illegal[0] ? SAP_P1_WIN_ILLEGAL : SAP_P0_WIN_ILLEGAL;
    }

    for (int seat = 0; seat < 2; seat++) {
        if (!env->seat[seat].ended) {
            sap_apply(&env->seat[seat], actions[seat]);
        }
    }

    if (env->seat[0].ended && env->seat[1].ended) {
        return sap_resolve_battle(env);
    }
    return SAP_ONGOING;
}

/* Observation for one seat: SAP_OBS_FLOATS floats, layout documented at the
 * top of this file and in docs/envs/sap-v1.md. No opponent block - the
 * shop phase genuinely hides the opponent's team and shop, so there is
 * nothing to encode for it (see sap-v1.md's "no opponent-state block" note). */
static inline void sap_observe(const SAP *env, int seat, float *out) {
    const SapSeat *s = &env->seat[seat];
    memset(out, 0, SAP_OBS_FLOATS * sizeof(float));
    float *p = out;

    *p++ = (float)s->gold;

    for (int t = 0; t < SAP_TEAM; t++) {
        const SapPet *pet = &s->team[t];
        p[pet->species] = 1.0f; /* index 0 = empty, already correct if empty */
        p += SAP_NUM_ALL_SPECIES;
        *p++ = (float)pet->attack;
        *p++ = (float)pet->health;
        if (pet->species != SAP_SPECIES_EMPTY) {
            p[pet->level - 1] = 1.0f;
        }
        p += SAP_MAX_LEVEL;
        *p++ = (float)pet->honey_perk;
    }

    for (int k = 0; k < SAP_SHOP_PETS; k++) {
        const SapShopPet *sp = &s->shop_pets[k];
        p[sp->species] = 1.0f;
        p += SAP_NUM_SHOP_SPECIES + 1;
        *p++ = (float)sp->hp_bonus;
    }

    p[s->shop_food] = 1.0f;
    p += SAP_NUM_FOODS;

    /* p now points exactly one-past-the-end if every width above matches
     * SAP_OBS_FLOATS - not checked at runtime (this is a hot path with no
     * allocation), but the layout is a static assert away from wrong. */
}

static inline void sap_legal(const SAP *env, int seat, uint8_t *out) {
    sap_legal_for(&env->seat[seat], out);
}

#endif /* POLICYCLASH_SAP_H */
