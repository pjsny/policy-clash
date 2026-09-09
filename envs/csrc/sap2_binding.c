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

static PyObject *Sap2_get_done(Sap2Object *self, void *closure) {
    (void)closure;
    return PyBool_FromLong(self->env.done);
}

static PyObject *Sap2_get_turn(Sap2Object *self, void *closure) {
    (void)closure;
    return PyLong_FromLong(self->env.turn);
}

static PyMethodDef Sap2_methods[] = {
    {"reset", (PyCFunction)Sap2_reset, METH_O, "Start a new match from a seed."},
    {"step", (PyCFunction)Sap2_step, METH_VARARGS,
     "Apply one action per seat, return a status code."},
    {"observe", (PyCFunction)Sap2_observe, METH_O, "SAP2_OBS_FLOATS float32 cells as bytes."},
    {"legal", (PyCFunction)Sap2_legal, METH_O, "SAP2_NUM_ACTIONS bool cells as bytes."},
    {"ended", (PyCFunction)Sap2_ended, METH_O, "Whether this seat has stopped acting this round."},
    {"replay", (PyCFunction)Sap2_replay, METH_NOARGS, "Actions played so far, flat."},
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
        PyModule_AddIntConstant(module, "MAX_SHOP_FOOD", SAP2_MAX_SHOP_FOOD) < 0 ||
        PyModule_AddIntConstant(module, "STARTING_GOLD", SAP2_STARTING_GOLD) < 0 ||
        PyModule_AddIntConstant(module, "STARTING_LIVES", SAP2_STARTING_LIVES) < 0 ||
        PyModule_AddIntConstant(module, "TROPHIES_TO_WIN", SAP2_TROPHIES_TO_WIN) < 0 ||
        PyModule_AddIntConstant(module, "MAX_ROUNDS", SAP2_MAX_ROUNDS) < 0) {
        Py_DECREF(module);
        return NULL;
    }

    return module;
}
