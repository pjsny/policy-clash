/* CPython binding for the SAP2 (full-match) rules core.
 *
 * Observations and legal masks come back as bytes objects, which the Python
 * layer wraps with numpy.frombuffer. Same convention as sap_binding.c and
 * tron_duel_binding.c.
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include "sap2.h"

typedef struct {
    PyObject_HEAD
    SAP2 env;
} Sap2Object;

static PyObject *Sap2_new(PyTypeObject *type, PyObject *args, PyObject *kwds) {
    (void)args;
    (void)kwds;
    Sap2Object *self = (Sap2Object *)type->tp_alloc(type, 0);
    if (self != NULL) {
        sap2_reset(&self->env, 0);
        self->env.done = 1; /* not playable until reset() is called */
    }
    return (PyObject *)self;
}

static PyObject *Sap2_reset(Sap2Object *self, PyObject *arg) {
    const unsigned long long seed = PyLong_AsUnsignedLongLong(arg);
    if (seed == (unsigned long long)-1 && PyErr_Occurred()) {
        return NULL;
    }
    sap2_reset(&self->env, (uint64_t)seed);
    Py_RETURN_NONE;
}

static int sap2_clamp_action(PyObject *arg, int *out) {
    const long action = PyLong_AsLong(arg);
    if (action == -1 && PyErr_Occurred()) {
        return -1;
    }
    *out = (action < INT32_MIN || action > INT32_MAX) ? -1 : (int)action;
    return 0;
}

static PyObject *Sap2_step(Sap2Object *self, PyObject *args) {
    PyObject *first = NULL;
    PyObject *second = NULL;
    if (!PyArg_ParseTuple(args, "OO", &first, &second)) {
        return NULL;
    }

    int action_0 = 0;
    int action_1 = 0;
    if (sap2_clamp_action(first, &action_0) < 0 || sap2_clamp_action(second, &action_1) < 0) {
        return NULL;
    }

    if (self->env.done) {
        PyErr_SetString(PyExc_RuntimeError, "step() after the episode ended; call reset()");
        return NULL;
    }

    if (self->env.num_ticks >= SAP2_MAX_TICKS) {
        PyErr_SetString(PyExc_RuntimeError,
                        "tick bound reached without the match ending; rules core is broken");
        return NULL;
    }

    return PyLong_FromLong(sap2_step(&self->env, action_0, action_1));
}

static int sap2_parse_seat(PyObject *arg, int *out) {
    const long seat = PyLong_AsLong(arg);
    if (seat == -1 && PyErr_Occurred()) {
        return -1;
    }
    if (seat < 0 || seat > 1) {
        PyErr_SetString(PyExc_ValueError, "seat must be 0 or 1");
        return -1;
    }
    *out = (int)seat;
    return 0;
}

static PyObject *Sap2_observe(Sap2Object *self, PyObject *arg) {
    int seat = 0;
    if (sap2_parse_seat(arg, &seat) < 0) {
        return NULL;
    }
    float buffer[SAP2_OBS_FLOATS];
    sap2_observe(&self->env, seat, buffer);
    return PyBytes_FromStringAndSize((const char *)buffer, sizeof(buffer));
}

static PyObject *Sap2_legal(Sap2Object *self, PyObject *arg) {
    int seat = 0;
    if (sap2_parse_seat(arg, &seat) < 0) {
        return NULL;
    }
    uint8_t buffer[SAP2_NUM_ACTIONS];
    sap2_legal(&self->env, seat, buffer);
    return PyBytes_FromStringAndSize((const char *)buffer, sizeof(buffer));
}

static PyObject *Sap2_ended(Sap2Object *self, PyObject *arg) {
    int seat = 0;
    if (sap2_parse_seat(arg, &seat) < 0) {
        return NULL;
    }
    return PyBool_FromLong(self->env.seat[seat].ended);
}

static PyObject *Sap2_replay(Sap2Object *self, PyObject *Py_UNUSED(ignored)) {
    const Py_ssize_t count = (Py_ssize_t)self->env.num_ticks * 2;
    PyObject *list = PyList_New(count);
    if (list == NULL) {
        return NULL;
    }
    for (Py_ssize_t i = 0; i < count; i++) {
        PyObject *item = PyLong_FromLong(self->env.moves[i]);
        if (item == NULL) {
            Py_DECREF(list);
            return NULL;
        }
        PyList_SET_ITEM(list, i, item);
    }
    return list;
}

/* An independent copy of the whole rules core. SAP2 is POD - fixed seat
 * arrays, a fixed moves array, three uint64_t RNG words, no pointers and
 * nothing heap-owned - so a struct assignment is a complete, correct deep
 * copy, and the copy's RNG streams continue from the fork point rather than
 * restarting. Deliberately clone-only: no set_state counterpart, because
 * accepting a caller-supplied SAP2 image would mean trusting num_ticks and
 * the per-seat counts that index these arrays. See base.py's Forkable. */
static PyObject *Sap2_clone(Sap2Object *self, PyObject *Py_UNUSED(ignored)) {
    Sap2Object *copy = (Sap2Object *)Py_TYPE(self)->tp_alloc(Py_TYPE(self), 0);
    if (copy == NULL) {
        return NULL;
    }
    copy->env = self->env;
    return (PyObject *)copy;
}

static PyObject *Sap2_get_done(Sap2Object *self, void *closure) {
    (void)closure;
    return PyBool_FromLong(self->env.done);
}

static PyObject *Sap2_get_turn(Sap2Object *self, void *closure) {
    (void)closure;
    return PyLong_FromLong(self->env.turn);
}

/* DEBUG/TEST ENTRY POINT - not part of the env's agent-facing API.
 *
 * One battle, resolved from two explicit line-ups. It exists because the
 * match API cannot address a battle rule: reaching a named board through
 * reset/buy/end_turn means searching seeds for a shop that offers the
 * right pets at the right stats, which for a five-pet fixture is not
 * reachable at all. The battle rules are the half of this env the shipped
 * game was measured hardest against (policy-clash-re-tools'
 * sap/difftest.py resolves thousands of boards in both engines), so they
 * get an entry point of their own rather than no in-repo test at all.
 *
 * team0/team1 are front-to-back sequences of (species, level, attack,
 * health) or (species, level, attack, health, perk). Returns
 * (winner, side0, side1) - winner 0, 1 or -1 for a draw - with each side
 * a list of (species, attack, health, level), front to back.
 *
 * Every field is range-checked before it reaches the rules core. This is
 * a public C entry point reachable from Python, so a bad argument has to
 * raise rather than index past an array or wrap an int8_t into a stat the
 * engine can never produce. */
static int sap2_load_debug_team(PyObject *rows, SapSeat2 *seat) {
    PyObject *fast = PySequence_Fast(rows, "team must be a sequence");
    if (fast == NULL) {
        return -1;
    }
    const Py_ssize_t n = PySequence_Fast_GET_SIZE(fast);
    if (n > SAP2_TEAM) {
        PyErr_Format(PyExc_ValueError, "team of %zd pets exceeds the %d team slots", n,
                     SAP2_TEAM);
        Py_DECREF(fast);
        return -1;
    }
    for (Py_ssize_t i = 0; i < n; i++) {
        /* Parsed as a SEQUENCE, not with PyArg_ParseTuple: that raises
         * SystemError on a row that is not a tuple, and "internal error"
         * is the wrong answer to a caller who passed a list or an int. */
        PyObject *row = PySequence_Fast(PySequence_Fast_GET_ITEM(fast, i),
                                        "each team entry must be a sequence");
        if (row == NULL) {
            Py_DECREF(fast);
            return -1;
        }
        const Py_ssize_t width = PySequence_Fast_GET_SIZE(row);
        if (width < 4 || width > 5) {
            PyErr_Format(PyExc_ValueError,
                         "team slot %zd: %zd fields, want (species, level, attack, "
                         "health) or (species, level, attack, health, perk)",
                         i, width);
            Py_DECREF(row);
            Py_DECREF(fast);
            return -1;
        }
        long field[5] = {0, 0, 0, 0, SAP2_PERK_NONE};
        for (Py_ssize_t f = 0; f < width; f++) {
            PyObject *value = PySequence_Fast_GET_ITEM(row, f);
            if (!PyLong_Check(value)) {
                PyErr_Format(PyExc_TypeError, "team slot %zd field %zd is not an int", i, f);
                Py_DECREF(row);
                Py_DECREF(fast);
                return -1;
            }
            field[f] = PyLong_AsLong(value);
            if (field[f] == -1 && PyErr_Occurred()) { /* an int too big for a long */
                Py_DECREF(row);
                Py_DECREF(fast);
                return -1;
            }
        }
        Py_DECREF(row);
        /* Widened to long above so that a huge value is REJECTED below
         * rather than truncated into range on the way in. */
        const long species = field[0], level = field[1];
        const long attack = field[2], health = field[3], perk = field[4];
        /* A species of 0 is SAP2_SPECIES_EMPTY - a hole, which this entry
         * point does not take: pass a shorter list instead. The battle
         * loads a seat by compacting it, so a hole would be invisible
         * anyway and a caller expecting one would be misled. */
        if (species <= 0 || species >= SAP2_NUM_ALL_SPECIES) {
            PyErr_Format(PyExc_ValueError,
                         "team slot %zd: species %ld is outside 1..%d", i, species,
                         SAP2_NUM_ALL_SPECIES - 1);
            Py_DECREF(fast);
            return -1;
        }
        if (level < 1 || level > SAP2_MAX_LEVEL) {
            PyErr_Format(PyExc_ValueError, "team slot %zd: level %ld is outside 1..%d", i,
                         level, SAP2_MAX_LEVEL);
            Py_DECREF(fast);
            return -1;
        }
        if (attack < 0 || attack > SAP2_MAX_STATS || health < 1
            || health > SAP2_MAX_STATS) {
            PyErr_Format(PyExc_ValueError,
                         "team slot %zd: %ld/%ld is outside attack 0..%d, health 1..%d", i,
                         attack, health, SAP2_MAX_STATS, SAP2_MAX_STATS);
            Py_DECREF(fast);
            return -1;
        }
        if (perk < 0 || perk >= SAP2_NUM_PERKS) {
            PyErr_Format(PyExc_ValueError, "team slot %zd: perk %ld is outside 0..%d", i,
                         perk, SAP2_NUM_PERKS - 1);
            Py_DECREF(fast);
            return -1;
        }
        SapPet2 *p = &seat->team[i];
        p->species = (uint8_t)species;
        p->level = (uint8_t)level;
        p->xp = SAP2_LEVEL_REQUIREMENTS[level - 1];
        p->attack = (int8_t)attack;
        p->health = (int8_t)health;
        p->perk = (uint8_t)perk;
    }
    Py_DECREF(fast);
    return 0;
}

static PyObject *sap2_line_out(const SapBattle2 *b, int side) {
    PyObject *out = PyList_New(b->count[side]);
    if (out == NULL) {
        return NULL;
    }
    for (int i = 0; i < b->count[side]; i++) {
        PyObject *row = Py_BuildValue("(iiii)", (int)b->species[side][i],
                                      (int)b->attack[side][i], (int)b->health[side][i],
                                      (int)b->level[side][i]);
        if (row == NULL) {
            Py_DECREF(out);
            return NULL;
        }
        PyList_SET_ITEM(out, i, row);
    }
    return out;
}

static PyObject *Sap2_debug_resolve_battle(PyObject *Py_UNUSED(self), PyObject *args) {
    PyObject *rows0 = NULL, *rows1 = NULL;
    unsigned long long seed = 0;
    if (!PyArg_ParseTuple(args, "OOK:debug_resolve_battle", &rows0, &rows1, &seed)) {
        return NULL;
    }
    SAP2 env;
    memset(&env, 0, sizeof(env));
    if (sap2_load_debug_team(rows0, &env.seat[0]) < 0
        || sap2_load_debug_team(rows1, &env.seat[1]) < 0) {
        return NULL;
    }
    env.battle_rng = seed;

    SapBattle2 b;
    memset(&b, 0, sizeof(b));
    const int winner = sap2_battle_ex(&env, &b);

    PyObject *side0 = sap2_line_out(&b, 0);
    PyObject *side1 = side0 == NULL ? NULL : sap2_line_out(&b, 1);
    if (side1 == NULL) {
        Py_XDECREF(side0);
        return NULL;
    }
    return Py_BuildValue("(iNN)", winner, side0, side1);
}

static PyMethodDef sap2_functions[] = {
    {"debug_resolve_battle", (PyCFunction)Sap2_debug_resolve_battle, METH_VARARGS,
     "FOR TESTS AND DIFFERENTIAL HARNESSES, not for agents: resolve one "
     "battle from two explicit line-ups. (winner, side0, side1)."},
    {NULL, NULL, 0, NULL}};

static PyMethodDef Sap2_methods[] = {
    {"reset", (PyCFunction)Sap2_reset, METH_O, "Start a new match from a seed."},
    {"step", (PyCFunction)Sap2_step, METH_VARARGS,
     "Apply one action per seat, return a status code."},
    {"observe", (PyCFunction)Sap2_observe, METH_O, "SAP2_OBS_FLOATS float32 cells as bytes."},
    {"legal", (PyCFunction)Sap2_legal, METH_O, "SAP2_NUM_ACTIONS bool cells as bytes."},
    {"ended", (PyCFunction)Sap2_ended, METH_O, "Whether this seat has stopped acting this round."},
    {"replay", (PyCFunction)Sap2_replay, METH_NOARGS, "Actions played so far, flat."},
    {"clone", (PyCFunction)Sap2_clone, METH_NOARGS, "An independent copy of the full state."},
    {NULL, NULL, 0, NULL}};

static PyGetSetDef Sap2_getset[] = {
    {"done", (getter)Sap2_get_done, NULL, "Whether the match ended.", NULL},
    {"turn", (getter)Sap2_get_turn, NULL, "Current turn number (1-indexed).", NULL},
    {NULL, NULL, NULL, NULL, NULL}};

static PyTypeObject Sap2Type = {
    PyVarObject_HEAD_INIT(NULL, 0).tp_name = "policyclash_envs._sap2.Sap2",
    .tp_basicsize = sizeof(Sap2Object),
    .tp_flags = Py_TPFLAGS_DEFAULT,
    .tp_doc = "SAP2 (full-match, Tier-1 roster) rules core.",
    .tp_methods = Sap2_methods,
    .tp_getset = Sap2_getset,
    .tp_new = Sap2_new,
};

static struct PyModuleDef sap2_module = {
    PyModuleDef_HEAD_INIT,
    .m_name = "policyclash_envs._sap2",
    .m_doc = "SAP2 (Super Auto Pets, full match) rules compiled from C.",
    .m_size = -1,
    .m_methods = sap2_functions,
};

PyMODINIT_FUNC PyInit__sap2(void) {
    if (PyType_Ready(&Sap2Type) < 0) {
        return NULL;
    }

    PyObject *module = PyModule_Create(&sap2_module);
    if (module == NULL) {
        return NULL;
    }

    Py_INCREF(&Sap2Type);
    if (PyModule_AddObject(module, "Sap2", (PyObject *)&Sap2Type) < 0) {
        Py_DECREF(&Sap2Type);
        Py_DECREF(module);
        return NULL;
    }

    if (PyModule_AddIntConstant(module, "ONGOING", SAP2_ONGOING) < 0 ||
        PyModule_AddIntConstant(module, "P0_WIN", SAP2_P0_WIN) < 0 ||
        PyModule_AddIntConstant(module, "P1_WIN", SAP2_P1_WIN) < 0 ||
        PyModule_AddIntConstant(module, "DRAW", SAP2_DRAW) < 0 ||
        PyModule_AddIntConstant(module, "P0_WIN_ILLEGAL", SAP2_P0_WIN_ILLEGAL) < 0 ||
        PyModule_AddIntConstant(module, "P1_WIN_ILLEGAL", SAP2_P1_WIN_ILLEGAL) < 0 ||
        PyModule_AddIntConstant(module, "DRAW_ILLEGAL", SAP2_DRAW_ILLEGAL) < 0 ||
        PyModule_AddIntConstant(module, "P0_WIN_STEP_LIMIT", SAP2_P0_WIN_STEP_LIMIT) < 0 ||
        PyModule_AddIntConstant(module, "P1_WIN_STEP_LIMIT", SAP2_P1_WIN_STEP_LIMIT) < 0 ||
        PyModule_AddIntConstant(module, "DRAW_STEP_LIMIT", SAP2_DRAW_STEP_LIMIT) < 0 ||
        PyModule_AddIntConstant(module, "OBS_FLOATS", SAP2_OBS_FLOATS) < 0 ||
        PyModule_AddIntConstant(module, "NUM_ACTIONS", SAP2_NUM_ACTIONS) < 0 ||
        PyModule_AddIntConstant(module, "MAX_TICKS", SAP2_MAX_TICKS) < 0 ||
        PyModule_AddIntConstant(module, "TEAM_SLOTS", SAP2_TEAM) < 0 ||
        PyModule_AddIntConstant(module, "MAX_SHOP_PETS", SAP2_MAX_SHOP_PETS) < 0 ||
        PyModule_AddIntConstant(module, "ROSTER_TIER", SAP2_ROSTER_TIER) < 0 ||
        PyModule_AddIntConstant(module, "MAX_SHOP_FOOD", SAP2_MAX_SHOP_FOOD) < 0 ||
        PyModule_AddIntConstant(module, "FOOD_SLOTS", SAP2_FOOD_SLOTS) < 0 ||
        /* Slot widths and action bases, so that layout-aware consumers
         * (tests, the visualizer, bots) can derive offsets instead of
         * hardcoding them and drifting when a block widens. */
        PyModule_AddIntConstant(module, "TEAM_SLOT_FLOATS", SAP2_TEAM_SLOT_FLOATS) < 0 ||
        PyModule_AddIntConstant(module, "SHOP_PET_SLOT_FLOATS", SAP2_SHOP_PET_SLOT_FLOATS) < 0 ||
        PyModule_AddIntConstant(module, "SHOP_FOOD_SLOT_FLOATS", SAP2_SHOP_FOOD_SLOT_FLOATS) < 0 ||
        PyModule_AddIntConstant(module, "ACT_BUY_PET_BASE", SAP2_ACT_BUY_PET_BASE) < 0 ||
        PyModule_AddIntConstant(module, "ACT_SELL_BASE", SAP2_ACT_SELL_BASE) < 0 ||
        PyModule_AddIntConstant(module, "ACT_COMBINE_BASE", SAP2_ACT_COMBINE_BASE) < 0 ||
        PyModule_AddIntConstant(module, "ACT_REROLL", SAP2_ACT_REROLL) < 0 ||
        PyModule_AddIntConstant(module, "ACT_REPOSITION_BASE", SAP2_ACT_REPOSITION_BASE) < 0 ||
        PyModule_AddIntConstant(module, "ACT_BUY_FOOD_BASE", SAP2_ACT_BUY_FOOD_BASE) < 0 ||
        PyModule_AddIntConstant(module, "ACT_FREEZE_PET_BASE", SAP2_ACT_FREEZE_PET_BASE) < 0 ||
        PyModule_AddIntConstant(module, "ACT_FREEZE_FOOD_BASE", SAP2_ACT_FREEZE_FOOD_BASE) < 0 ||
        PyModule_AddIntConstant(module, "MAX_LEVEL", SAP2_MAX_LEVEL) < 0 ||
        PyModule_AddIntConstant(module, "MAX_EXP", SAP2_MAX_EXP) < 0 ||
        PyModule_AddIntConstant(module, "MAX_STATS", SAP2_MAX_STATS) < 0 ||
        PyModule_AddIntConstant(module, "NUM_PERKS", SAP2_NUM_PERKS) < 0 ||
        PyModule_AddIntConstant(module, "PERK_NONE", SAP2_PERK_NONE) < 0 ||
        PyModule_AddIntConstant(module, "PERK_HONEY", SAP2_PERK_HONEY) < 0 ||
        PyModule_AddIntConstant(module, "PERK_MEAT_BONE", SAP2_PERK_MEAT_BONE) < 0 ||
        PyModule_AddIntConstant(module, "PERK_GARLIC", SAP2_PERK_GARLIC) < 0 ||
        PyModule_AddIntConstant(module, "PERK_MELON", SAP2_PERK_MELON) < 0 ||
        PyModule_AddIntConstant(module, "PERK_BIRTHDAY_CAKE", SAP2_PERK_BIRTHDAY_CAKE) < 0 ||
        PyModule_AddIntConstant(module, "STARTING_GOLD", SAP2_STARTING_GOLD) < 0 ||
        PyModule_AddIntConstant(module, "STARTING_LIVES", SAP2_STARTING_LIVES) < 0 ||
        PyModule_AddIntConstant(module, "TROPHIES_TO_WIN", SAP2_TROPHIES_TO_WIN) < 0 ||
        PyModule_AddIntConstant(module, "MAX_ROUNDS", SAP2_MAX_ROUNDS) < 0) {
        Py_DECREF(module);
        return NULL;
    }

    return module;
}
