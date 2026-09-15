/* Super Auto Pets, full-match engine (sap-v2). Pure C, no Python, no
 * allocation, no global state. See docs/envs/sap-v2.md for the design this
 * implements. The shop-phase numbers (level requirements, sell value, shop
 * capacity by tier, Pigeon's crumbs) are not wiki folklore: they were read
 * out of the shipped build by hosting its own IL2CPP runtime and driving
 * its BoardResolver - see policy-clash-re-tools. Each is cited where it is used.
 *
 * Rather than one shop phase + one battle, this is the actual Arena
 * match: many rounds of shop-then-battle, team state persisting round to
 * round, lives and trophies, a tier-gated shop that grows with the turn
 * number, and freeze. Roster is still Tier 1 only (10 pets, 2 foods) -
 * the match *engine* is the full game; the roster is a separate, later
 * expansion (sap-v2.md's appendix), and shipping both unverified at once
 * risks exactly the kind of bug a smaller, single-round build of this
 * same engine caught repeatedly during development, at a sixth of this
 * scope - see sap-v2.md for that history.
 *
 * Self-contained: its own species/food tables, its own RNG, its own
 * battle resolution - not built on top of another file, so it can be
 * added to this repo on its own.
 *
 * Every value in here is an integer: floats belong only in the
 * observation buffer, nowhere a rules decision reads them - same rule
 * connect4.h and tron_duel.h already follow, for the same reason: "same
 * seed, same env version, same policies, same bytes out" is the property
 * the whole leaderboard rests on.
 */

#ifndef POLICYCLASH_SAP2_H
#define POLICYCLASH_SAP2_H

#include <stdint.h>
#include <string.h>

#define SAP2_TEAM 5
#define SAP2_MAX_SHOP_PETS 5   /* the largest shop a roll ever fills, turn 9+ */
#define SAP2_MAX_SHOP_FOOD 2   /* likewise, for food - see SAP2_FOOD_SLOTS */
/* The food shop can hold far more than a roll ever puts in it: selling a
 * Pigeon PREPENDS `level` free Bread Crumbs to whatever is already there,
 * and nothing is evicted - measured from the shipped build via
 * policy-clash-re-tools, five level-1 Pigeons sold in one shop phase left
 * SEVEN food items (five crumbs plus the two rolled), and the item in the
 * last slot is still buyable (`CanPlaySpell` = Ok, and feeding it worked).
 * A whole team of level-3 Pigeons is the worst case, so the array is the
 * largest rolled capacity plus SAP2_TEAM * SAP2_MAX_LEVEL crumbs. The next
 * roll truncates it back to the rolled capacity - see sap2_roll_shop. */
#define SAP2_FOOD_SLOTS (SAP2_MAX_SHOP_FOOD + SAP2_TEAM * SAP2_MAX_LEVEL)
#define SAP2_STARTING_GOLD 10  /* every round, does not carry over */
#define SAP2_MAX_LEVEL 3
#define SAP2_MAX_EXP 5         /* the last SAP2_LEVEL_REQUIREMENTS entry */
#define SAP2_MAX_STATS 50      /* BoardConstants.MaxStats, measured from the
                                * shipped build via policy-clash-re-tools */
#define SAP2_STARTING_LIVES 5      /* Normal Arena mode */
#define SAP2_TROPHIES_TO_WIN 10
#define SAP2_MAX_ROUNDS 30         /* see docs/envs/sap-v2.md's step-limit note -
                                     * genuinely reachable here, unlike sap-v1 */
#define SAP2_MAX_EXCHANGES 71      /* measured battle cap, see sap2_battle */

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

/* Perks - what a food leaves ON a pet, as opposed to the stat change it
 * applies once and forgets. Honey is the only one this roster can
 * produce.
 *
 * The shipped build's perk template (read via policy-clash-re-tools)
 * carries Name, Durability, Positive, MidBattle and Aura. Honey fills
 * in none of them beyond the name - it has no durability, so there is
 * no charge counter to model and inventing one would be fiction - which
 * leaves the id as the whole of the perk here. The next perk in line is
 * Meat Bone at Tier 2, which does use more of the template; it hooks in
 * as a second non-zero id plus a table of exactly the template fields
 * it needs, and the pet's `perk` field is already wide enough for it. */
enum { SAP2_PERK_NONE = 0, SAP2_PERK_HONEY = 1, SAP2_NUM_PERKS = 2 };

static const int8_t SAP2_BASE_ATK[SAP2_NUM_ALL_SPECIES] = {0, 2, 3, 1, 2, 2, 2, 2, 1, 4, 3, 0, 1};
static const int8_t SAP2_BASE_HP[SAP2_NUM_ALL_SPECIES] = {0, 2, 2, 3, 2, 3, 1, 2, 4, 1, 2, 0, 1};

/* Experience and levels. Measured from the shipped build via
 * policy-clash-re-tools (BoardConstants.LevelRequirements = [0, 2, 5],
 * LevelupAmount = 2, MaxLevel = 3): a pet is bought at exp 0 / level 1,
 * and every extra copy stacked onto it is worth exactly one exp point,
 * so the level is a pure function of the exp counter rather than a
 * separate quantity - see sap2_combine. SAP2_LEVEL_REQUIREMENTS[n] is
 * the exp a pet needs to be level n+1. */
static const uint8_t SAP2_LEVEL_REQUIREMENTS[SAP2_MAX_LEVEL] = {0, 2, 5};

static inline uint8_t sap2_level_for_exp(uint8_t exp) {
    uint8_t level = 1;
    for (int n = 1; n < SAP2_MAX_LEVEL; n++) {
        if (exp >= SAP2_LEVEL_REQUIREMENTS[n]) {
            level = (uint8_t)(n + 1);
        }
    }
    return level;
}

/* Shop tier and shop size, both measured from the shipped build via
 * policy-clash-re-tools. The tier schedule is
 * BoardConstants.DefaultShopUpgradeTierOnTurn = [3, 5, 7, 9, 11]: entry
 * i is the turn the shop reaches tier i+2. Capacity is gated by that
 * TIER, not by the turn directly, which is why the gate lives in one
 * place here - DefaultShopUpgradeMinionCapacityOnTier = [3, 5] and
 * DefaultShopUpgradeSpellCapacityOnTier = [3] list the tiers at which
 * the pet and food capacities step up from their 3/1 base. Turn by
 * turn that gives 3/1 for turns 1-4, 4/2 for turns 5-8 and 5/2 from
 * turn 9 on, which is exactly what the oracle reports.
 *
 * The tier does NOT yet select which species can roll: the roster is
 * Tier 1 only, so every shop species is already legal at tier 1. A
 * later tier-expansion phase hooks its roster filter onto
 * sap2_tier_for_turn; nothing else needs to change. */
static const int SAP2_TIER_ON_TURN[] = {3, 5, 7, 9, 11};
static const int SAP2_PET_CAPACITY_ON_TIER[] = {3, 5};
static const int SAP2_FOOD_CAPACITY_ON_TIER[] = {3};

static inline int sap2_tier_for_turn(int turn) {
    int tier = 1;
    for (size_t i = 0; i < sizeof(SAP2_TIER_ON_TURN) / sizeof(SAP2_TIER_ON_TURN[0]); i++) {
        if (turn >= SAP2_TIER_ON_TURN[i]) {
            tier = (int)i + 2;
        }
    }
    return tier;
}

static inline void sap2_shop_size(int turn, int *pet_slots, int *food_slots) {
    const int tier = sap2_tier_for_turn(turn);
    int pets = 3;
    int foods = 1;
    for (size_t i = 0; i < sizeof(SAP2_PET_CAPACITY_ON_TIER) / sizeof(SAP2_PET_CAPACITY_ON_TIER[0]); i++) {
        if (tier >= SAP2_PET_CAPACITY_ON_TIER[i]) {
            pets++;
        }
    }
    for (size_t i = 0; i < sizeof(SAP2_FOOD_CAPACITY_ON_TIER) / sizeof(SAP2_FOOD_CAPACITY_ON_TIER[0]); i++) {
        if (tier >= SAP2_FOOD_CAPACITY_ON_TIER[i]) {
            foods++;
        }
    }
    *pet_slots = pets;
    *food_slots = foods;
}

/* Action layout, derived from the block widths rather than written out, so
 * that widening a shop block cannot leave a stale base behind. Sized to
 * the widest each block ever gets: 5 shop pet slots, 5 team positions, and
 * SAP2_FOOD_SLOTS food slots - 2 that a roll fills plus the crumbs a team
 * of Pigeons can stock, every one of which the real game lets you buy. A
 * narrower shop just masks the unused indices, same pattern sap-v1 uses
 * for everything.
 *
 * BUY_PET carries a destination because the real game's buy does: measured
 * via policy-clash-re-tools, `BoardEvents.PlayMinion` takes the point you
 * dropped the pet on, and that point decides between three outcomes -
 * place, stack, or insert-and-shift. See sap2_buy_pet. */
enum {
    SAP2_ACT_END_TURN = 0,
    SAP2_ACT_BUY_PET_BASE = 1,                 /* shop_slot*TEAM + position */
    SAP2_ACT_SELL_BASE = SAP2_ACT_BUY_PET_BASE + SAP2_MAX_SHOP_PETS * SAP2_TEAM,
    SAP2_ACT_COMBINE_BASE = SAP2_ACT_SELL_BASE + SAP2_TEAM,      /* +0..9 pair */
    SAP2_ACT_REROLL = SAP2_ACT_COMBINE_BASE + 10,
    SAP2_ACT_REPOSITION_BASE = SAP2_ACT_REROLL + 1,              /* +0..9 pair */
    SAP2_ACT_BUY_FOOD_BASE = SAP2_ACT_REPOSITION_BASE + 10,      /* food*TEAM + target */
    SAP2_ACT_FREEZE_PET_BASE = SAP2_ACT_BUY_FOOD_BASE + SAP2_FOOD_SLOTS * SAP2_TEAM,
    SAP2_ACT_FREEZE_FOOD_BASE = SAP2_ACT_FREEZE_PET_BASE + SAP2_MAX_SHOP_PETS,
    SAP2_NUM_ACTIONS = SAP2_ACT_FREEZE_FOOD_BASE + SAP2_FOOD_SLOTS
};

#define SAP2_SHOP_ACTION_BUDGET 20 /* per round - same bound and same
                                     * unreachable-by-construction proof as
                                     * sap-v1's, applied within each round */
#define SAP2_MAX_TICKS (SAP2_MAX_ROUNDS * SAP2_SHOP_ACTION_BUDGET)

/* Observation layout (float32, C-order). Adds to sap-v1's per-slot
 * layout: a frozen flag on every shop slot, and own lives/trophies/turn.
 * No opponent-state block - same reasoning as sap-v1, the shop phase
 * still hides the opponent's team and shop entirely.
 *
 * A team slot carries the exp counter as well as the level one-hot,
 * because the real game draws exp pips on the card: a level-2 pet at
 * exp 2 and a level-2 pet at exp 4 are one and two copies from level 3
 * respectively, visibly different to a human player, and used to be the
 * same observation here. The perk is a one-hot rather than a honey
 * flag, so a second perk widens a block instead of adding a field. The
 * attack/health cells are the TOTALS the card shows - permanent plus
 * any live temporary buff, see sap2_pet_attack. */
enum {
    SAP2_TEAM_SLOT_FLOATS = SAP2_NUM_ALL_SPECIES + 1 /* atk */ + 1 /* hp */ + SAP2_MAX_LEVEL
                            + 1 /* exp */ + SAP2_NUM_PERKS,
    SAP2_SHOP_PET_SLOT_FLOATS = (SAP2_NUM_SHOP_SPECIES + 1) + 1 /* hp bonus */ + 1 /* frozen */,
    SAP2_SHOP_FOOD_SLOT_FLOATS = SAP2_NUM_FOODS + 1 /* frozen */,
    SAP2_OBS_FLOATS = 1 /* gold */ + 1 /* lives */ + 1 /* trophies */ + 1 /* turn */
                      + SAP2_TEAM * SAP2_TEAM_SLOT_FLOATS
                      + SAP2_MAX_SHOP_PETS * SAP2_SHOP_PET_SLOT_FLOATS
                      + SAP2_FOOD_SLOTS * SAP2_SHOP_FOOD_SLOT_FLOATS
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

/* xp is the exp counter the real game keeps (0..SAP2_MAX_EXP); level is
 * never stored independently of it - every write goes through
 * sap2_level_for_exp, so the two can never disagree. It is kept as a
 * field rather than recomputed at every read because level is what the
 * abilities, the sell price and the observation all want.
 *
 * attack/health are the PERMANENT stats; temp_attack/temp_health carry
 * the part that expires at the start of the next turn. Measured from
 * the shipped build via policy-clash-re-tools, Horse is the only pet in
 * this roster whose effect is temporary - its ability carries
 * Duration = Temp(1), while Ant, Otter, Beaver, Duck and Fish all carry
 * Duration = Perm(0) - and Horse buffs attack only, so nothing here
 * writes temp_health yet; the two components are kept symmetric because
 * expiry and reading treat them identically.
 *
 * Nothing outside reads the components: every reader goes through
 * sap2_pet_attack/sap2_pet_health. Keeping the components unclamped
 * against each other is the point - the permanent stats stay whatever
 * they earned, so an expiring buff can never leave a pet below them. */
typedef struct {
    uint8_t species;
    int8_t attack;
    int8_t health;
    int8_t temp_attack;
    int8_t temp_health;
    uint8_t level;
    uint8_t xp;
    uint8_t perk;
} SapPet2;

/* What "attack"/"health" mean everywhere else: the two components
 * summed and clamped. Attack floors at 0 - the sum can go negative once
 * a debuff outlives the buff it cancelled, and no card shows less than
 * zero - and both cap at SAP2_MAX_STATS. Health has no floor claimed
 * for it: nothing in this roster reduces a pet's health outside battle
 * (battle works on its own copy), so what the shipped build does with a
 * zero-or-less persistent health has not been measured. */
static inline int8_t sap2_pet_attack(const SapPet2 *p) {
    int total = (int)p->attack + (int)p->temp_attack;
    if (total < 0) {
        total = 0;
    }
    if (total > SAP2_MAX_STATS) {
        total = SAP2_MAX_STATS;
    }
    return (int8_t)total;
}

static inline int8_t sap2_pet_health(const SapPet2 *p) {
    int total = (int)p->health + (int)p->temp_health;
    if (total > SAP2_MAX_STATS) {
        total = SAP2_MAX_STATS;
    }
    return (int8_t)total;
}

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
    SapShopFood2 shop_food[SAP2_FOOD_SLOTS];
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

/* A roll refills the shop, and frozen items SLIDE LEFT: measured from the
 * shipped build via policy-clash-re-tools, a shop [Otter, Cricket,
 * Mosquito] with the Mosquito frozen rerolls to [Mosquito(frozen), *, *],
 * and freezing slots 1 and 3 of four leaves them at 0 and 1 in that same
 * relative order. Same for food: a frozen Garlic in slot 1 comes back in
 * slot 0. sap2 used to leave frozen items where they sat, which kept the
 * offers right but put them behind different action indices than the real
 * game does. */
static inline void sap2_roll_shop(SapSeat2 *s, int pet_slots, int food_slots) {
    SapShopPet2 kept_pets[SAP2_MAX_SHOP_PETS];
    int n_pets = 0;
    for (int i = 0; i < pet_slots; i++) {
        if (s->shop_pets[i].frozen) {
            kept_pets[n_pets++] = s->shop_pets[i];
        }
    }
    for (int i = 0; i < n_pets; i++) {
        s->shop_pets[i] = kept_pets[i];
    }
    for (int i = n_pets; i < pet_slots; i++) {
        s->shop_pets[i].species = (uint8_t)(1 + sap2_splitmix64(&s->rng) % SAP2_NUM_SHOP_SPECIES);
        s->shop_pets[i].hp_bonus = 0;
        s->shop_pets[i].frozen = 0;
    }

    /* Every frozen food item survives a roll, wherever it sits; the rolled
     * capacity bounds only the REFILL. Measured from the shipped build via
     * policy-clash-re-tools: a turn-1 shop (capacity 1) holding a frozen
     * Apple plus two frozen crumbs came back from a roll with all three
     * still frozen and in order, while a shop with one frozen crumb and an
     * unfrozen Apple came back as just the crumb. Unfrozen stock past the
     * capacity is cleared: those slots are this phase's Pigeon stock, not a
     * permanent widening. */
    SapShopFood2 kept_food[SAP2_FOOD_SLOTS];
    int n_food = 0;
    for (int i = 0; i < SAP2_FOOD_SLOTS; i++) {
        if (s->shop_food[i].frozen) {
            kept_food[n_food++] = s->shop_food[i];
        }
    }
    for (int i = 0; i < n_food; i++) {
        s->shop_food[i] = kept_food[i];
    }
    for (int i = n_food; i < SAP2_FOOD_SLOTS; i++) {
        /* Only Apple/Honey roll naturally - Bread Crumbs is Pigeon-only. */
        s->shop_food[i].species =
            (i < food_slots) ? (uint8_t)(1 + sap2_splitmix64(&s->rng) % 2) : SAP2_FOOD_EMPTY;
        s->shop_food[i].frozen = 0;
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

/* Clamps the PERMANENT components, which is all any ability, food or
 * stack writes. The temporary components are added on top and clamped
 * again at read time (sap2_pet_attack), so a temporary buff can raise
 * what a pet hits for without raising the permanent stats it falls back
 * to when the buff expires. */
static inline void sap2_clamp_stats(SapPet2 *p) {
    if (p->attack < 0) {
        p->attack = 0;
    }
    if (p->attack > SAP2_MAX_STATS) {
        p->attack = SAP2_MAX_STATS;
    }
    if (p->health > SAP2_MAX_STATS) {
        p->health = SAP2_MAX_STATS;
    }
}

/* -------------------------------------------------------------------- */
/* Abilities, as data
 *
 * The shipped build does not write an ability as code either: every one is
 * an `Ability` object carrying a Trigger, an Aim (target selector) and a
 * list of (condition, effect) pairs, looked up per level through
 * `AbilityUtility.GetTemplate`. policy-clash-re-tools' sap/spec.py dumps
 * that graph for all 186 Turtle-pack ability templates, and the table
 * below is the same shape, narrowed to what this roster uses.
 *
 * Writing it this way is not tidiness: the remaining five tiers are 50
 * pets built from 17 trigger families, 18 effects and 9 selectors, so the
 * machinery is the work and each pet after it is a row.
 *
 * Amount conventions, so one row can serve all three levels:
 *   SAP2_BY_LEVEL       the pet's level
 *   SAP2_BY_LEVEL_LESS1 the pet's level minus one (Fish's level-up)
 * anything >= 0 is a flat amount. */
#define SAP2_BY_LEVEL (-1)
#define SAP2_BY_LEVEL_LESS1 (-2)
#define SAP2_MAX_ABILITIES 2 /* Whale and Cow carry two; nothing here does yet */

enum {
    SAP2_TRIG_NONE = 0,
    SAP2_TRIG_PLAY,          /* this pet was bought onto the team */
    SAP2_TRIG_SELL,          /* this pet was sold */
    SAP2_TRIG_BEFORE_SELL,   /* ditto, but before the gold is paid out */
    SAP2_TRIG_LEVELUP,       /* this pet's level just went up */
    SAP2_TRIG_SUMMON,        /* a FRIEND was summoned - fires on the watcher */
    SAP2_TRIG_START_BATTLE,  /* queued once, before the first exchange */
    SAP2_TRIG_BEFORE_DEATH,  /* fainting, body still on the board */
    SAP2_TRIG_DEATH,         /* fainted, body gone - a summon takes the slot */
    SAP2_TRIG_HURT,          /* took damage and lived */
    SAP2_TRIG_ATTACK,        /* this pet attacked */
    SAP2_TRIG_KILL           /* this pet's attack fainted its target */
};

enum {
    SAP2_SEL_NONE = 0,
    SAP2_SEL_SELF,
    SAP2_SEL_RANDOM_FRIEND,  /* uniform over living friends, excluding self */
    SAP2_SEL_RANDOM_ENEMY,   /* battle only */
    SAP2_SEL_TRIGGER_TARGET, /* the pet the trigger was about (Horse) */
    SAP2_SEL_SHOP_PETS,      /* every occupied shop pet slot */
    SAP2_SEL_SHOP_FOOD,      /* the food shop, as a list to prepend to */
    SAP2_SEL_SUMMON_SLOT     /* the position the fainting body just left */
};

enum {
    SAP2_EFF_NONE = 0,
    SAP2_EFF_BUFF,           /* attack/health onto the target, perm or temp */
    SAP2_EFF_BUFF_SHOP,      /* health onto shop pets, carried by the buy */
    SAP2_EFF_GAIN_GOLD,
    SAP2_EFF_ADD_SHOP_SPELL, /* prepend `count` copies of `param`, free */
    SAP2_EFF_DAMAGE,
    SAP2_EFF_SUMMON
};

enum { SAP2_DUR_PERM = 0, SAP2_DUR_TEMP = 1 };

typedef struct {
    uint8_t trigger;
    uint8_t selector;
    uint8_t effect;
    int8_t count;   /* how many targets, or the summon's level */
    int8_t attack;  /* amount, or SAP2_BY_LEVEL* */
    int8_t health;
    uint8_t param;  /* species / food id, effect-dependent */
    uint8_t duration;
} Sap2Ability;

static const Sap2Ability SAP2_ABILITY[SAP2_NUM_ALL_SPECIES][SAP2_MAX_ABILITIES] = {
    /* EMPTY   */ {{0}, {0}},
    /* ANT     */ {{SAP2_TRIG_BEFORE_DEATH, SAP2_SEL_RANDOM_FRIEND, SAP2_EFF_BUFF,
                    1, SAP2_BY_LEVEL, SAP2_BY_LEVEL, 0, SAP2_DUR_PERM}, {0}},
    /* BEAVER  */ {{SAP2_TRIG_SELL, SAP2_SEL_RANDOM_FRIEND, SAP2_EFF_BUFF,
                    2, SAP2_BY_LEVEL, 0, 0, SAP2_DUR_PERM}, {0}},
    /* CRICKET */ {{SAP2_TRIG_DEATH, SAP2_SEL_SUMMON_SLOT, SAP2_EFF_SUMMON,
                    SAP2_BY_LEVEL, SAP2_BY_LEVEL, SAP2_BY_LEVEL, SAP2_CRICKET_TOKEN,
                    SAP2_DUR_PERM}, {0}},
    /* DUCK    */ {{SAP2_TRIG_SELL, SAP2_SEL_SHOP_PETS, SAP2_EFF_BUFF_SHOP,
                    0, 0, SAP2_BY_LEVEL, 0, SAP2_DUR_PERM}, {0}},
    /* FISH    */ {{SAP2_TRIG_LEVELUP, SAP2_SEL_RANDOM_FRIEND, SAP2_EFF_BUFF,
                    2, SAP2_BY_LEVEL_LESS1, SAP2_BY_LEVEL_LESS1, 0, SAP2_DUR_PERM}, {0}},
    /* HORSE   */ {{SAP2_TRIG_SUMMON, SAP2_SEL_TRIGGER_TARGET, SAP2_EFF_BUFF,
                    1, SAP2_BY_LEVEL, 0, 0, SAP2_DUR_TEMP}, {0}},
    /* MOSQUITO*/ {{SAP2_TRIG_START_BATTLE, SAP2_SEL_RANDOM_ENEMY, SAP2_EFF_DAMAGE,
                    SAP2_BY_LEVEL, 1, 0, 0, SAP2_DUR_PERM}, {0}},
    /* OTTER   */ {{SAP2_TRIG_PLAY, SAP2_SEL_RANDOM_FRIEND, SAP2_EFF_BUFF,
                    SAP2_BY_LEVEL, 0, 1, 0, SAP2_DUR_PERM}, {0}},
    /* PIG     */ {{SAP2_TRIG_BEFORE_SELL, SAP2_SEL_SELF, SAP2_EFF_GAIN_GOLD,
                    1, SAP2_BY_LEVEL, 0, 0, SAP2_DUR_PERM}, {0}},
    /* PIGEON  */ {{SAP2_TRIG_SELL, SAP2_SEL_SHOP_FOOD, SAP2_EFF_ADD_SHOP_SPELL,
                    SAP2_BY_LEVEL, 0, 0, SAP2_BREAD_CRUMBS, SAP2_DUR_PERM}, {0}},
    /* C.TOKEN */ {{0}, {0}},
    /* BEE     */ {{0}, {0}}
};

/* Perks carry abilities too, on the pet rather than the species. Honey is
 * the only one this roster produces; Meat Bone (Tier 2) and Melon (Tier 3)
 * hook in here, and Melon is also the first perk with a durability. */
static const Sap2Ability SAP2_PERK_ABILITY[SAP2_NUM_PERKS] = {
    /* NONE  */ {0},
    /* HONEY */ {SAP2_TRIG_DEATH, SAP2_SEL_SUMMON_SLOT, SAP2_EFF_SUMMON,
                 1, 1, 1, SAP2_BEE, SAP2_DUR_PERM}
};

/* Resolves an amount against the firing pet's level. */
static inline int sap2_amount(int8_t spec, int level) {
    if (spec == SAP2_BY_LEVEL) {
        return level;
    }
    if (spec == SAP2_BY_LEVEL_LESS1) {
        return level - 1;
    }
    return spec;
}

/* What a shop-phase ability fires against: the seat, the pet firing it, and
 * (for SAP2_TRIG_SUMMON) the pet the trigger was about. */
typedef struct {
    SapSeat2 *seat;
    int self_slot;     /* the firing pet, or -1 once it has left the team */
    int trigger_slot;  /* the pet the trigger concerns */
    int level;         /* the firing pet's level */
} Sap2Ctx;

static inline void sap2_apply_buff(SapPet2 *p, int attack, int health, int duration) {
    if (duration == SAP2_DUR_TEMP) {
        int ta = (int)p->temp_attack + attack, th = (int)p->temp_health + health;
        if (ta > SAP2_MAX_STATS) {
            ta = SAP2_MAX_STATS; /* the sum is clamped again on read */
        }
        if (th > SAP2_MAX_STATS) {
            th = SAP2_MAX_STATS;
        }
        p->temp_attack = (int8_t)ta;
        p->temp_health = (int8_t)th;
        return;
    }
    p->attack = (int8_t)(p->attack + attack);
    p->health = (int8_t)(p->health + health);
    sap2_clamp_stats(p);
}

/* Fires `species`'s abilities that listen for `trigger`, against a seat.
 * The battle-phase half of the same table is sap2_battle_fire. */
static inline void sap2_fire(uint8_t species, int trigger, Sap2Ctx *ctx) {
    for (int slot = 0; slot < SAP2_MAX_ABILITIES; slot++) {
    const Sap2Ability *ab = &SAP2_ABILITY[species][slot];
    if (ab->trigger != trigger || ab->effect == SAP2_EFF_NONE) {
        continue;
    }
    SapSeat2 *s = ctx->seat;
    const int attack = sap2_amount(ab->attack, ctx->level);
    const int health = sap2_amount(ab->health, ctx->level);
    const int count = sap2_amount(ab->count, ctx->level);

    switch (ab->selector) {
    case SAP2_SEL_SELF:
        if (ab->effect == SAP2_EFF_GAIN_GOLD) {
            s->gold = (int16_t)(s->gold + attack);
        }
        break;
    case SAP2_SEL_TRIGGER_TARGET:
        if (ctx->trigger_slot >= 0 && s->team[ctx->trigger_slot].species != SAP2_SPECIES_EMPTY) {
            sap2_apply_buff(&s->team[ctx->trigger_slot], attack, health, ab->duration);
        }
        break;
    case SAP2_SEL_RANDOM_FRIEND: {
        int friends[SAP2_TEAM];
        const int n = sap2_friends(s, ctx->self_slot, friends);
        int picked[SAP2_TEAM];
        const int k = sap2_pick_random(&s->rng, friends, n, count, picked);
        for (int i = 0; i < k; i++) {
            sap2_apply_buff(&s->team[picked[i]], attack, health, ab->duration);
        }
        break;
    }
    case SAP2_SEL_SHOP_PETS:
        for (int i = 0; i < SAP2_MAX_SHOP_PETS; i++) {
            if (s->shop_pets[i].species != SAP2_SPECIES_EMPTY) {
                s->shop_pets[i].hp_bonus = (int8_t)(s->shop_pets[i].hp_bonus + health);
            }
        }
        break;
    case SAP2_SEL_SHOP_FOOD: {
        /* Prepend `count` free copies; the rolled stock survives, pushed
         * right. SAP2_FOOD_SLOTS is sized for the worst case, so nothing
         * real can fall off the end. */
        for (int f = SAP2_FOOD_SLOTS - 1; f >= count; f--) {
            s->shop_food[f] = s->shop_food[f - count];
        }
        for (int f = 0; f < count; f++) {
            s->shop_food[f].species = ab->param;
            s->shop_food[f].frozen = 0;
        }
        break;
    }
    default:
        break;
    }
    }
}

/* Every pet on the team gets a chance at a trigger that is about someone
 * else - the watcher pattern, which is how the shipped build's trigger bus
 * works (TriggerMinions fans an event out over the board). */
static inline void sap2_fire_watchers(SapSeat2 *s, int trigger, int trigger_slot) {
    for (int i = 0; i < SAP2_TEAM; i++) {
        if (i == trigger_slot || s->team[i].species == SAP2_SPECIES_EMPTY) {
            continue;
        }
        Sap2Ctx ctx = {s, i, trigger_slot, s->team[i].level};
        sap2_fire(s->team[i].species, trigger, &ctx);
    }
}

/* A friend was summoned - fan the trigger out over the board.
 *
 * Horse is the only pet in this roster that listens, and its buff is the
 * one temporary effect: measured from the shipped build via
 * policy-clash-re-tools, Horse's effect carries Duration = Temp(1) while
 * Ant, Otter, Beaver, Duck and Fish all carry Perm(0), and the deadline
 * Temp(1) names is the START OF THE NEXT TURN, not the end of battle - a
 * Horse plus a freshly bought Ant showed Ant 3/2 for all of turn 1,
 * including that turn's battle, and 2/2 from turn 2 onwards. So it lands
 * in temp_attack, where the battle still reads it (sap2_battle_load goes
 * through sap2_pet_attack) and sap2_resolve_round's round advance - which
 * runs after that battle - clears it. */
static inline void sap2_fire_friend_summoned(SapSeat2 *s, int slot) {
    sap2_fire_watchers(s, SAP2_TRIG_SUMMON, slot);
}

/* Stacking a copy onto a pet - the one implementation both the shop-stack
 * buy and the team-to-team merge go through. Measured from the shipped
 * build via policy-clash-re-tools (`BoardEvents.PlayMinion` with
 * PlayType.Stack, and `BoardEvents.StackMinion`):
 *
 *   stats: the higher of each stat, then +1 - stacking a 4/4 copy onto a
 *          5/2 pet yields 6/5, not 6/3 and not 5/5.
 *   exp:   the two pets' exp, summed, plus one - stacking an exp-4 (6/6,
 *          level 2) copy onto an exp-0 (2/2, level 1) pet yields 7/7 at
 *          exp 5, level 3.
 *
 * For the common case of two freshly bought copies both formulas
 * degenerate to +1/+1 and +1 exp, which is why an Ant walks 2/2 exp0 L1,
 * 3/3 exp1 L1, 4/4 exp2 L2, ... 7/7 exp5 L3. Callers refuse the stack
 * once exp is SAP2_MAX_EXP, so xp never runs past it.
 *
 * The permanent components stack as above; the TEMPORARY components take
 * the higher of the two, with no +1. Measured from the shipped build via
 * policy-clash-re-tools against `IntegerStat.Permanent`/`.Temporary`, with
 * an Ant and a Horse so nothing is random - merging pos1 onto pos0 gives
 * (perm 3, temp 1) whichever copy carried Horse's buff, and (3, 1) when
 * both did. sap2 used to keep only the survivor's temporary component,
 * which silently dropped the buff when the absorbed copy was the buffed
 * one. Only a team-to-team merge can show this on this roster: a shop copy
 * always arrives with no temporary component. Horse buffs attack only, so
 * the same rule for temporary HEALTH is an extension of the measured one,
 * not itself measured.
 *
 * The perk survives from either copy - Honey fed to a pet and then
 * merged into its twin keeps the Bee. With one perk that is an OR; the
 * precedence between two *different* perks is unmeasured, so this takes
 * the incoming one only into an empty slot.
 *
 * `incoming` is a copy: the caller has already vacated its slot (merge) or
 * its shop slot (buy), so this never has to know where it came from. */
static inline void sap2_stack_onto(SapSeat2 *s, int target, const SapPet2 *incoming) {
    SapPet2 *a = &s->team[target];
    const uint8_t prev_level = a->level;

    a->attack = (int8_t)((a->attack > incoming->attack ? a->attack : incoming->attack) + 1);
    a->health = (int8_t)((a->health > incoming->health ? a->health : incoming->health) + 1);
    a->temp_attack = a->temp_attack > incoming->temp_attack ? a->temp_attack
                                                            : incoming->temp_attack;
    a->temp_health = a->temp_health > incoming->temp_health ? a->temp_health
                                                           : incoming->temp_health;
    sap2_clamp_stats(a);
    unsigned exp = (unsigned)a->xp + (unsigned)incoming->xp + 1u;
    if (exp > SAP2_MAX_EXP) {
        exp = SAP2_MAX_EXP;
    }
    a->xp = (uint8_t)exp;
    a->level = sap2_level_for_exp(a->xp);
    if (a->perk == SAP2_PERK_NONE) {
        a->perk = incoming->perk;
    }

    /* The level-up trigger, fired on the pet that just levelled. Measured:
     * Fish gives exactly TWO random friends +(new level - 1), so a Fish
     * hitting level 2 gave two friends +1/+1 and level 3 gave +2/+2 - not
     * level-many friends, and not +level/+level. Fires on either stack
     * path. */
    if (a->level > prev_level && a->level >= 2) {
        Sap2Ctx ctx = {s, target, target, a->level};
        sap2_fire(a->species, SAP2_TRIG_LEVELUP, &ctx);
    }
}

/* A bought pet's own on-play trigger. Split out of sap2_buy_pet because a
 * stack fires it too, and at the level the pet has AFTER stacking:
 * measured via policy-clash-re-tools, stacking a second Otter onto a
 * level-1 Otter gave one friend +1 health, and the copy that took it to
 * level 2 gave two friends +1 health. */
static inline void sap2_fire_on_play(SapSeat2 *s, int slot) {
    Sap2Ctx ctx = {s, slot, slot, s->team[slot].level};
    sap2_fire(s->team[slot].species, SAP2_TRIG_PLAY, &ctx);
}

static inline int sap2_has_empty(const SapSeat2 *s) {
    return sap2_leftmost_empty(s) >= 0;
}

/* Can a shop pet be dropped on team position `dest`? Three outcomes, all
 * measured from the shipped build:
 *   - empty position: it just goes there (holes are legal; the real board
 *     keeps them, it does not compact),
 *   - same species with room to grow: a stack, which needs no free slot,
 *   - anything else: an insert, which needs a free slot somewhere; with a
 *     full team the real game refuses with FailureReason.NoSpace. */
static inline int sap2_buy_is_stack(const SapSeat2 *s, int shop_slot, int dest) {
    return s->team[dest].species != SAP2_SPECIES_EMPTY &&
           s->team[dest].species == s->shop_pets[shop_slot].species &&
           s->team[dest].xp < SAP2_MAX_EXP;
}

static inline int sap2_can_buy_at(const SapSeat2 *s, int shop_slot, int dest) {
    if (s->shop_pets[shop_slot].species == SAP2_SPECIES_EMPTY || s->gold < 3) {
        return 0;
    }
    if (s->team[dest].species == SAP2_SPECIES_EMPTY) {
        return 1;
    }
    return sap2_buy_is_stack(s, shop_slot, dest) || sap2_has_empty(s);
}

/* Frees `dest` by sliding the smallest block of pets that has somewhere to
 * go. Measured: with room behind the drop point the block from `dest`
 * backwards shifts back (pets at 1,2,3 + a drop on 2 -> 1, [new]2, 3, 4);
 * with no room behind, the block in front shifts forward instead (pets at
 * 2,3,4 + a drop on 3 -> 1, 2, [new]3, 4). Caller guarantees a free slot
 * exists. */
static inline void sap2_insert_gap(SapSeat2 *s, int dest) {
    int behind = -1;
    for (int i = dest + 1; i < SAP2_TEAM; i++) {
        if (s->team[i].species == SAP2_SPECIES_EMPTY) {
            behind = i;
            break;
        }
    }
    if (behind >= 0) {
        for (int i = behind; i > dest; i--) {
            s->team[i] = s->team[i - 1];
        }
    } else {
        int front = -1;
        for (int i = dest - 1; i >= 0; i--) {
            if (s->team[i].species == SAP2_SPECIES_EMPTY) {
                front = i;
                break;
            }
        }
        for (int i = front; i < dest; i++) {
            s->team[i] = s->team[i + 1];
        }
    }
    s->team[dest].species = SAP2_SPECIES_EMPTY;
}

/* Buys the shop pet in `shop_slot` onto team position `dest`. One action,
 * exactly as the real game's drag is one action - including the stack
 * case, which sap2 used to make the agent spell out as buy-then-merge. */
static inline void sap2_buy_pet(SapSeat2 *s, int shop_slot, int dest) {
    const uint8_t species = s->shop_pets[shop_slot].species;
    const int8_t hp_bonus = s->shop_pets[shop_slot].hp_bonus;
    const int stacking = sap2_buy_is_stack(s, shop_slot, dest);

    s->gold = (int16_t)(s->gold - 3);
    s->shop_pets[shop_slot].species = SAP2_SPECIES_EMPTY;
    s->shop_pets[shop_slot].hp_bonus = 0;
    s->shop_pets[shop_slot].frozen = 0; /* bought - nothing left to freeze */

    if (stacking) {
        SapPet2 incoming;
        incoming.species = species;
        incoming.attack = SAP2_BASE_ATK[species];
        incoming.health = (int8_t)(SAP2_BASE_HP[species] + hp_bonus);
        incoming.temp_attack = 0; /* a shop pet has no buff of its own yet */
        incoming.temp_health = 0;
        incoming.level = 1;
        incoming.xp = 0;
        incoming.perk = SAP2_PERK_NONE;
        sap2_stack_onto(s, dest, &incoming);
        /* The pet that was played is the stacked one, and its on-play
         * ability fires at its new level. A stack is not a summon, so
         * Horse stays out of it - measured. */
        sap2_fire_on_play(s, dest);
        return;
    }

    if (s->team[dest].species != SAP2_SPECIES_EMPTY) {
        sap2_insert_gap(s, dest);
    }
    s->team[dest].species = species;
    s->team[dest].attack = SAP2_BASE_ATK[species];
    s->team[dest].health = (int8_t)(SAP2_BASE_HP[species] + hp_bonus);
    /* A team slot is reused, not cleared, when its pet is sold or slides
     * (see sap2_sell and sap2_insert_gap), so every field of the new pet
     * is written here - a leftover temporary buff or perk would
     * otherwise be inherited by whoever moves in. */
    s->team[dest].temp_attack = 0;
    s->team[dest].temp_health = 0;
    s->team[dest].level = 1;
    s->team[dest].xp = 0; /* measured: a bought pet starts at exp 0, not 1 */
    s->team[dest].perk = SAP2_PERK_NONE;

    sap2_fire_friend_summoned(s, dest);
    sap2_fire_on_play(s, dest);
}

/* Sell value is the pet's LEVEL, 1/2/3 - measured from the shipped build
 * via policy-clash-re-tools, and independent of how big the pet's stats got.
 *
 * Two triggers fire here, in the order the shipped build names them:
 * BEFORE_SELL first (Pig, which doubles the sale by handing over another
 * `level`), then SELL once the pet has left the board (Beaver's attack
 * onto two friends, Duck's health onto the shop, Pigeon's free Bread
 * Crumbs). The sold pet's own slot is already empty by then, which is why
 * SAP2_SEL_RANDOM_FRIEND excluding `self_slot` still reads correctly.
 *
 * Pigeon's crumbs come in UNFROZEN. A reading that said otherwise on a
 * turn>=2 board was an artifact of the oracle, not the game: the flag keys
 * off BoardModel.TurnOver, and the harness's faked Ready->PreBuild handoff
 * left TurnOver set. With it cleared the crumbs are unfrozen at every turn
 * and tier. A crumb the player freezes by hand behaves like any other
 * frozen item. */
static inline void sap2_sell(SapSeat2 *s, int slot) {
    const SapPet2 sold = s->team[slot];
    Sap2Ctx ctx = {s, slot, slot, sold.level};

    sap2_fire(sold.species, SAP2_TRIG_BEFORE_SELL, &ctx);
    s->gold = (int16_t)(s->gold + sold.level);
    s->team[slot].species = SAP2_SPECIES_EMPTY;
    sap2_fire(sold.species, SAP2_TRIG_SELL, &ctx);
}

/* A team-to-team merge: drag one of your pets onto another of the same
 * species. Same rule as the shop stack - see sap2_stack_onto - which is
 * exactly how the shipped build behaves (`BoardEvents.StackMinion` and a
 * PlayType.Stack buy produce the same stats and exp). */
static inline void sap2_combine(SapSeat2 *s, int i, int j) {
    const SapPet2 incoming = s->team[j];
    s->team[j].species = SAP2_SPECIES_EMPTY;
    sap2_stack_onto(s, i, &incoming);
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

    /* Apple and Bread Crumbs change stats permanently; Honey changes no
     * stat at all and leaves a perk on the pet instead - that is the
     * whole of what it does until the pet faints in battle. */
    SapPet2 *p = &s->team[target];
    if (food == SAP2_APPLE || food == SAP2_BREAD_CRUMBS) {
        p->attack = (int8_t)(p->attack + 1);
        if (food == SAP2_APPLE) {
            p->health = (int8_t)(p->health + 1);
        }
        sap2_clamp_stats(p);
    } else if (food == SAP2_HONEY) {
        p->perk = SAP2_PERK_HONEY;
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

/* A stack is legal only while the survivor still has room for exp. At
 * SAP2_MAX_EXP the pet is maxed and the shipped build drops the extra
 * copy into its own level-1 slot instead of merging, so this has to test
 * the exp counter, not the level: a level-3 pet is always at exp 5, but
 * a level-2 pet at exp 4 still stacks. */
static inline int sap2_can_combine(const SapSeat2 *s, int i, int j) {
    return s->team[i].species != SAP2_SPECIES_EMPTY && s->team[i].species == s->team[j].species &&
           s->team[i].xp < SAP2_MAX_EXP;
}

/* food_slots is not a parameter: a food slot is buyable/freezable
 * exactly when something is in it, and Pigeon can stock slots past the
 * rolled capacity (see sap2_sell), so occupancy - not the turn's
 * capacity - is the live bound. Shop pets have no such case. */
static inline void sap2_legal_for(const SapSeat2 *s, int pet_slots, uint8_t *out) {
    memset(out, 0, SAP2_NUM_ACTIONS);
    out[SAP2_ACT_END_TURN] = 1;

    for (int k = 0; k < pet_slots; k++) {
        for (int t = 0; t < SAP2_TEAM; t++) {
            out[SAP2_ACT_BUY_PET_BASE + k * SAP2_TEAM + t] =
                (uint8_t)sap2_can_buy_at(s, k, t);
        }
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
    for (int f = 0; f < SAP2_FOOD_SLOTS; f++) {
        const uint8_t food = s->shop_food[f].species;
        for (int t = 0; t < SAP2_TEAM; t++) {
            out[SAP2_ACT_BUY_FOOD_BASE + f * SAP2_TEAM + t] =
                (uint8_t)(food != SAP2_FOOD_EMPTY && s->gold >= SAP2_FOOD_COST[food] &&
                          s->team[t].species != SAP2_SPECIES_EMPTY);
        }
    }
    for (int k = 0; k < pet_slots; k++) {
        out[SAP2_ACT_FREEZE_PET_BASE + k] = (uint8_t)(s->shop_pets[k].species != SAP2_SPECIES_EMPTY);
    }
    for (int f = 0; f < SAP2_FOOD_SLOTS; f++) {
        out[SAP2_ACT_FREEZE_FOOD_BASE + f] = (uint8_t)(s->shop_food[f].species != SAP2_FOOD_EMPTY);
    }
}

static inline void sap2_apply(SapSeat2 *s, int action, int pet_slots, int food_slots) {
    if (action == SAP2_ACT_END_TURN) {
        s->ended = 1;
    } else if (action >= SAP2_ACT_BUY_PET_BASE &&
               action < SAP2_ACT_BUY_PET_BASE + SAP2_MAX_SHOP_PETS * SAP2_TEAM) {
        const int off = action - SAP2_ACT_BUY_PET_BASE;
        sap2_buy_pet(s, off / SAP2_TEAM, off % SAP2_TEAM);
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
    } else if (action >= SAP2_ACT_BUY_FOOD_BASE && action < SAP2_ACT_BUY_FOOD_BASE + SAP2_FOOD_SLOTS * SAP2_TEAM) {
        const int off = action - SAP2_ACT_BUY_FOOD_BASE;
        sap2_buy_food(s, off / SAP2_TEAM, off % SAP2_TEAM);
    } else if (action >= SAP2_ACT_FREEZE_PET_BASE && action < SAP2_ACT_FREEZE_PET_BASE + SAP2_MAX_SHOP_PETS) {
        sap2_toggle_freeze_pet(s, action - SAP2_ACT_FREEZE_PET_BASE);
    } else if (action >= SAP2_ACT_FREEZE_FOOD_BASE && action < SAP2_ACT_FREEZE_FOOD_BASE + SAP2_FOOD_SLOTS) {
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
    uint8_t perk[2][SAP2_TEAM]; /* the perk id, not a honey flag - see SapPet2 */
    int count[2];
} SapBattle2;

static inline void sap2_battle_load(SapBattle2 *b, const SapSeat2 *s, int side) {
    int n = 0;
    for (int i = 0; i < SAP2_TEAM; i++) {
        if (s->team[i].species == SAP2_SPECIES_EMPTY) {
            continue;
        }
        /* The totals, not the permanent components: a Horse buff granted
         * this turn is still live during this turn's battle (measured -
         * see sap2_fire_friend_summoned). */
        b->attack[side][n] = sap2_pet_attack(&s->team[i]);
        b->health[side][n] = sap2_pet_health(&s->team[i]);
        b->species[side][n] = s->team[i].species;
        b->level[side][n] = s->team[i].level;
        b->perk[side][n] = s->team[i].perk;
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
        b->perk[side][i] = b->perk[side][i + 1];
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
        b->perk[side][i] = b->perk[side][i - 1];
    }
    b->attack[side][0] = atk;
    b->health[side][0] = hp;
    b->species[side][0] = species;
    b->level[side][0] = level;
    b->perk[side][0] = SAP2_PERK_NONE; /* a summoned token carries no perk */
    b->count[side]++;

    for (int i = 1; i < b->count[side]; i++) {
        if (b->species[side][i] == SAP2_HORSE) {
            b->attack[side][0] = (int8_t)(b->attack[side][0] + b->level[side][i]);
            if (b->attack[side][0] > SAP2_MAX_STATS) {
                b->attack[side][0] = SAP2_MAX_STATS;
            }
        }
    }
}

/* -------------------------------------------------------------------- */
/* Abilities in battle
 *
 * Same table as the shop phase, resolved against SapBattle2 instead of
 * SapSeat2. The two containers are genuinely different - a battle line is
 * packed and mutates as bodies leave, a seat has fixed slots and holes -
 * so the selectors and effects are implemented twice while the DATA
 * describing each ability stays in one place.
 *
 * The faint sequence is BEFORE_DEATH, then the body leaves, then DEATH:
 * Ant's buff lands while it is still on the board (so it cannot pick
 * itself), and Cricket's token and the Honey Bee take the vacated front
 * position. That ordering is what the shipped build's
 * BeforeDeath/DeathEarly/Death events do, and it is what 200 boards of
 * exact surviving line-ups verified. */
typedef struct {
    SapBattle2 *b;
    uint64_t *rng;
    int side;   /* the firing pet's side */
    int idx;    /* its position, or -1 if its body has already left */
    int level;
    uint8_t perk;
} Sap2BattleCtx;

static inline void sap2_battle_clamp(SapBattle2 *b, int side, int i) {
    if (b->attack[side][i] > SAP2_MAX_STATS) {
        b->attack[side][i] = SAP2_MAX_STATS;
    }
    if (b->attack[side][i] < 0) {
        b->attack[side][i] = 0;
    }
    if (b->health[side][i] > SAP2_MAX_STATS) {
        b->health[side][i] = SAP2_MAX_STATS;
    }
}

/* Damage to one battle pet. Returns 1 if it fainted, so the caller can
 * resolve the faint in the order the phase requires. */
static inline int sap2_battle_hurt(SapBattle2 *b, int side, int i, int amount) {
    b->health[side][i] = (int8_t)(b->health[side][i] - amount);
    return b->health[side][i] <= 0;
}

static inline void sap2_battle_fire(uint8_t species, uint8_t perk, int trigger,
                                     Sap2BattleCtx *ctx);

/* A pet's body leaves the line. BEFORE_DEATH has already fired; DEATH
 * fires once the slot is gone, because a summon takes its place. */
static inline void sap2_battle_resolve_faint(SapBattle2 *b, uint64_t *rng, int side, int idx) {
    const uint8_t species = b->species[side][idx];
    const uint8_t perk = b->perk[side][idx];
    Sap2BattleCtx ctx = {b, rng, side, idx, b->level[side][idx], perk};

    sap2_battle_fire(species, perk, SAP2_TRIG_BEFORE_DEATH, &ctx);
    sap2_battle_remove(b, side, idx);
    ctx.idx = -1;
    sap2_battle_fire(species, perk, SAP2_TRIG_DEATH, &ctx);
}

static inline void sap2_battle_fire(uint8_t species, uint8_t perk, int trigger,
                                     Sap2BattleCtx *ctx) {
    SapBattle2 *b = ctx->b;
    const int side = ctx->side;
    const int enemy = side ^ 1;

    for (int slot = 0; slot < SAP2_MAX_ABILITIES; slot++) {
        const Sap2Ability *ab = &SAP2_ABILITY[species][slot];
        if (ab->trigger != trigger || ab->effect == SAP2_EFF_NONE) {
            continue;
        }
        const int attack = sap2_amount(ab->attack, ctx->level);
        const int health = sap2_amount(ab->health, ctx->level);
        const int count = sap2_amount(ab->count, ctx->level);

        switch (ab->selector) {
        case SAP2_SEL_RANDOM_FRIEND: {
            int friends[SAP2_TEAM];
            int n = 0;
            for (int i = 0; i < b->count[side]; i++) {
                if (i != ctx->idx) {
                    friends[n++] = i;
                }
            }
            int picked[SAP2_TEAM];
            const int k = sap2_pick_random(ctx->rng, friends, n, count, picked);
            for (int p = 0; p < k; p++) {
                const int t = picked[p];
                b->attack[side][t] = (int8_t)(b->attack[side][t] + attack);
                b->health[side][t] = (int8_t)(b->health[side][t] + health);
                sap2_battle_clamp(b, side, t);
            }
            break;
        }
        case SAP2_SEL_RANDOM_ENEMY: {
            /* Damage picks its targets from the enemies standing when the
             * ability resolves, hits the highest index first so removals
             * do not shift the rest, and resolves every faint afterwards. */
            if (b->count[enemy] == 0) {
                break;
            }
            const int n_hits = count < b->count[enemy] ? count : b->count[enemy];
            int candidates[SAP2_TEAM];
            for (int i = 0; i < b->count[enemy]; i++) {
                candidates[i] = i;
            }
            int picked[SAP2_TEAM];
            const int k = sap2_pick_random(ctx->rng, candidates, b->count[enemy], n_hits, picked);
            for (int a = 0; a < k; a++) {
                for (int c = a + 1; c < k; c++) {
                    if (picked[c] > picked[a]) {
                        const int tmp = picked[a];
                        picked[a] = picked[c];
                        picked[c] = tmp;
                    }
                }
            }
            int fainted[SAP2_TEAM];
            int fc = 0;
            for (int p = 0; p < k; p++) {
                if (sap2_battle_hurt(b, enemy, picked[p], attack)) {
                    fainted[fc++] = picked[p];
                }
            }
            for (int i = 0; i < fc; i++) {
                sap2_battle_resolve_faint(b, ctx->rng, enemy, fainted[i]);
            }
            break;
        }
        case SAP2_SEL_SUMMON_SLOT:
            /* The summon takes the vacated position at the front of the
             * line. `param` names the species; its stats scale with the
             * summoner's level unless the row gives flat ones. */
            sap2_battle_insert_front(b, side, ab->param, (int8_t)attack, (int8_t)health,
                                     (uint8_t)(ab->count == SAP2_BY_LEVEL ? ctx->level : 1));
            break;
        default:
            break;
        }
    }

    /* Perk abilities ride on the pet, not the species - Honey's Bee. */
    if (perk != SAP2_PERK_NONE) {
        const Sap2Ability *pa = &SAP2_PERK_ABILITY[perk];
        if (pa->trigger == trigger && pa->effect == SAP2_EFF_SUMMON) {
            sap2_battle_insert_front(b, side, pa->param, pa->attack, pa->health, 1);
        }
    }
}

/* Start-of-battle abilities are QUEUED, then resolved.
 *
 * Verified against the shipped build (policy-clash-re-tools): a Mosquito
 * that is killed by another Mosquito's start-of-battle damage still deals
 * its own damage. Mosquito 5/1 vs Mosquito 1/1 is a draw for every seed -
 * the 5-attack one fires first and kills the 1/1, and the dead 1/1's
 * queued shot still lands and kills it back. So the list is taken once, up
 * front, in attack order with ties broken at random, and every entry fires
 * even if its owner is already gone when its turn comes.
 *
 * The queue holds what an entry needs in order to fire without its body:
 * side, level, species and perk. WHICH species listen is the table's
 * business, not this function's. */
static inline void sap2_battle_start(SapBattle2 *b, uint64_t *rng) {
    int q_side[2 * SAP2_TEAM];
    int q_level[2 * SAP2_TEAM];
    uint8_t q_species[2 * SAP2_TEAM];
    uint8_t q_perk[2 * SAP2_TEAM];
    int8_t q_atk[2 * SAP2_TEAM];
    int qn = 0;
    for (int side = 0; side < 2; side++) {
        for (int i = 0; i < b->count[side]; i++) {
            int listens = 0;
            for (int slot = 0; slot < SAP2_MAX_ABILITIES; slot++) {
                if (SAP2_ABILITY[b->species[side][i]][slot].trigger == SAP2_TRIG_START_BATTLE) {
                    listens = 1;
                }
            }
            if (!listens) {
                continue;
            }
            q_side[qn] = side;
            q_level[qn] = b->level[side][i];
            q_species[qn] = b->species[side][i];
            q_perk[qn] = b->perk[side][i];
            q_atk[qn] = b->attack[side][i];
            qn++;
        }
    }
    if (qn == 0) {
        return;
    }

    /* Highest attack first; a tie is resolved by a coin flip, which is the
     * only place this phase consumes randomness besides target picking. */
    for (int i = 0; i < qn; i++) {
        int pick = i;
        int tied = 1;
        for (int j = i + 1; j < qn; j++) {
            if (q_atk[j] > q_atk[pick]) {
                pick = j;
                tied = 1;
            } else if (q_atk[j] == q_atk[pick]) {
                tied++;
                if ((int)(sap2_splitmix64(rng) % (uint64_t)tied) == 0) {
                    pick = j;
                }
            }
        }
        if (pick != i) {
            const int ts = q_side[i], tl = q_level[i];
            const uint8_t tsp = q_species[i], tpk = q_perk[i];
            const int8_t ta = q_atk[i];
            q_side[i] = q_side[pick];
            q_level[i] = q_level[pick];
            q_species[i] = q_species[pick];
            q_perk[i] = q_perk[pick];
            q_atk[i] = q_atk[pick];
            q_side[pick] = ts;
            q_level[pick] = tl;
            q_species[pick] = tsp;
            q_perk[pick] = tpk;
            q_atk[pick] = ta;
        }
    }

    for (int t = 0; t < qn; t++) {
        /* idx -1: the owner may already be gone, and no start-of-battle
         * ability in this roster targets its own body. The perk is passed
         * as NONE because a perk ability firing here would belong to the
         * queue entry, not to this trigger. */
        Sap2BattleCtx ctx = {b, rng, q_side[t], -1, q_level[t], q_perk[t]};
        sap2_battle_fire(q_species[t], SAP2_PERK_NONE, SAP2_TRIG_START_BATTLE, &ctx);
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

    /* The shipped build caps a battle at SAP2_MAX_EXCHANGES front-vs-front
     * exchanges and calls whatever is left a draw - measured via
     * policy-clash-re-tools: two 0-attack pets fight for exactly 71
     * exchanges (142 Attack events, independent of team size and health)
     * and the resolver reports Draw with both lines still standing. This
     * roster cannot reach it (every species has base attack >= 1 and
     * nothing reduces attack), but without the cap a 0-attack stalemate
     * would spin here forever instead of ending the way the real game
     * ends it. */
    int exchanges = 0;
    while (b.count[0] > 0 && b.count[1] > 0 && exchanges < SAP2_MAX_EXCHANGES) {
        exchanges++;
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
        /* The new turn starts here, so every temporary buff granted
         * during the last one expires here: Horse's, in this roster.
         * The battle that just ran (sap2_battle, above) already read the
         * buffed totals, which is the measured behaviour - a Horse plus
         * a freshly bought Ant fights turn 1 as 3/2 and turns up in
         * turn 2's shop phase as 2/2. Everything else about a pet -
         * species, level, xp, perk, permanent stat changes - persists
         * untouched; only the temporary components are dropped, and the
         * permanent ones were never mixed with them, so what is left is
         * exactly what the pet earned. */
        for (int t = 0; t < SAP2_TEAM; t++) {
            s->team[t].temp_attack = 0;
            s->team[t].temp_health = 0;
        }
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
        sap2_legal_for(&env->seat[seat], pet_slots, mask);
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
        /* Everything else is zero for an empty slot. A team slot is reused
         * rather than cleared when its pet is sold or slides (see
         * sap2_buy_pet), so those fields can still hold the previous
         * occupant's numbers - stale, not state, and not observable.
         *
         * attack/health are the totals the card shows, buffs included;
         * exp sits next to the level one-hot because the real game draws
         * it as pips and it is what decides whether the next copy levels
         * the pet; the perk is a one-hot, so PERK_NONE on a live pet is a
         * set bit and an empty slot is all zeros. */
        if (pet->species != SAP2_SPECIES_EMPTY) {
            p[0] = (float)sap2_pet_attack(pet);
            p[1] = (float)sap2_pet_health(pet);
            p[2 + pet->level - 1] = 1.0f;
            p[2 + SAP2_MAX_LEVEL] = (float)pet->xp;
            p[2 + SAP2_MAX_LEVEL + 1 + pet->perk] = 1.0f;
        }
        p += SAP2_TEAM_SLOT_FLOATS - SAP2_NUM_ALL_SPECIES;
    }

    for (int k = 0; k < SAP2_MAX_SHOP_PETS; k++) {
        const SapShopPet2 *sp = &s->shop_pets[k];
        p[sp->species] = 1.0f;
        p += SAP2_NUM_SHOP_SPECIES + 1;
        *p++ = (float)sp->hp_bonus;
        *p++ = (float)sp->frozen;
    }

    for (int f = 0; f < SAP2_FOOD_SLOTS; f++) {
        const SapShopFood2 *sf = &s->shop_food[f];
        p[sf->species] = 1.0f;
        p += SAP2_NUM_FOODS;
        *p++ = (float)sf->frozen;
    }
}

static inline void sap2_legal(const SAP2 *env, int seat, uint8_t *out) {
    int pet_slots, food_slots;
    sap2_shop_size(env->turn, &pet_slots, &food_slots); /* food_slots: see sap2_legal_for */
    sap2_legal_for(&env->seat[seat], pet_slots, out);
}

#endif /* POLICYCLASH_SAP2_H */
