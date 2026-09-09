/* CPython binding for the SAP (Tier-1 MVP) rules core.
 *
 * Observations and legal masks come back as bytes objects, which the Python
 * layer wraps with numpy.frombuffer. That keeps numpy out of the build
 * entirely and makes the returned arrays read-only, so an observation cannot
 * be mutated by the policy that receives it.
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include "sap.h"

typedef struct {
    PyObject_HEAD
    SAP env;
} SapObject;

static PyObject *Sap_new(PyTypeObject *type, PyObject *args, PyObject *kwds) {
    (void)args;
    (void)kwds;
    SapObject *self = (SapObject *)type->tp_alloc(type, 0);
    if (self != NULL) {
        sap_reset(&self->env, 0);
        self->env.done = 1; /* not playable until reset() is called */
    }
    return (PyObject *)self;
}

static PyObject *Sap_reset(SapObject *self, PyObject *arg) {
    const unsigned long long seed = PyLong_AsUnsignedLongLong(arg);
    if (seed == (unsigned long long)-1 && PyErr_Occurred()) {
        return NULL;
    }
    sap_reset(&self->env, (uint64_t)seed);
    Py_RETURN_NONE;
}

/* Out-of-range actions are a forfeit, not an error, so they are clamped into
 * int range here rather than rejected. Same convention tron_duel_binding.c
 * uses. */
static int sap_clamp_action(PyObject *arg, int *out) {
    const long action = PyLong_AsLong(arg);
    if (action == -1 && PyErr_Occurred()) {
        return -1;
    }
    *out = (action < INT32_MIN || action > INT32_MAX) ? -1 : (int)action;
    return 0;
}

static PyObject *Sap_step(SapObject *self, PyObject *args) {
    PyObject *first = NULL;
    PyObject *second = NULL;
    if (!PyArg_ParseTuple(args, "OO", &first, &second)) {
        return NULL;
    }

    int action_0 = 0;
    int action_1 = 0;
    if (sap_clamp_action(first, &action_0) < 0 || sap_clamp_action(second, &action_1) < 0) {
        return NULL;
    }

    if (self->env.done) {
        PyErr_SetString(PyExc_RuntimeError, "step() after the episode ended; call reset()");
        return NULL;
    }

    /* Not a rules path. Reaching SAP_MAX_TICKS means the budget argument in
     * sap.h is wrong and both seats were not forced to end in time, so this
     * is a bug detector for the rules core rather than a step limit - same
     * convention as tron_duel_binding.c's TD_MAX_TICKS guard. */
    if (self->env.num_ticks >= SAP_MAX_TICKS) {
        PyErr_SetString(PyExc_RuntimeError,
                        "tick bound reached without both seats ending; rules core is broken");
        return NULL;
    }

    return PyLong_FromLong(sap_step(&self->env, action_0, action_1));
}

static int sap_parse_seat(PyObject *arg, int *out) {
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

static PyObject *Sap_observe(SapObject *self, PyObject *arg) {
    int seat = 0;
    if (sap_parse_seat(arg, &seat) < 0) {
        return NULL;
    }
    float buffer[SAP_OBS_FLOATS];
    sap_observe(&self->env, seat, buffer);
    return PyBytes_FromStringAndSize((const char *)buffer, sizeof(buffer));
}

static PyObject *Sap_legal(SapObject *self, PyObject *arg) {
    int seat = 0;
    if (sap_parse_seat(arg, &seat) < 0) {
        return NULL;
    }
    uint8_t buffer[SAP_NUM_ACTIONS];
    sap_legal(&self->env, seat, buffer);
    return PyBytes_FromStringAndSize((const char *)buffer, sizeof(buffer));
}

/* Whether `seat` has stopped acting for the rest of the episode (ended its
 * shop turn voluntarily, or hit its action budget) - the adapter needs this
 * to decide which seats' StepResult.observations entries go None, the same
 * role connect4's `to_move` getter plays for its turn-based case. */
static PyObject *Sap_ended(SapObject *self, PyObject *arg) {
    int seat = 0;
    if (sap_parse_seat(arg, &seat) < 0) {
        return NULL;
    }
    return PyBool_FromLong(self->env.seat[seat].ended);
}

static PyObject *Sap_replay(SapObject *self, PyObject *Py_UNUSED(ignored)) {
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

static PyObject *Sap_get_done(SapObject *self, void *closure) {
    (void)closure;
    return PyBool_FromLong(self->env.done);
}

static PyMethodDef Sap_methods[] = {
    {"reset", (PyCFunction)Sap_reset, METH_O, "Start a new episode from a seed."},
    {"step", (PyCFunction)Sap_step, METH_VARARGS,
     "Apply one action per seat, return a status code."},
    {"observe", (PyCFunction)Sap_observe, METH_O, "SAP_OBS_FLOATS float32 cells as bytes."},
    {"legal", (PyCFunction)Sap_legal, METH_O, "SAP_NUM_ACTIONS bool cells as bytes."},
    {"ended", (PyCFunction)Sap_ended, METH_O, "Whether this seat has stopped acting."},
    {"replay", (PyCFunction)Sap_replay, METH_NOARGS, "Actions played so far, flat."},
    {NULL, NULL, 0, NULL}};

static PyGetSetDef Sap_getset[] = {
    {"done", (getter)Sap_get_done, NULL, "Whether the episode ended.", NULL},
    {NULL, NULL, NULL, NULL, NULL}};

static PyTypeObject SapType = {
    PyVarObject_HEAD_INIT(NULL, 0).tp_name = "policyclash_envs._sap.Sap",
    .tp_basicsize = sizeof(SapObject),
    .tp_flags = Py_TPFLAGS_DEFAULT,
    .tp_doc = "SAP (Tier-1 MVP) rules core.",
    .tp_methods = Sap_methods,
    .tp_getset = Sap_getset,
    .tp_new = Sap_new,
};

static struct PyModuleDef sap_module = {
    PyModuleDef_HEAD_INIT,
    .m_name = "policyclash_envs._sap",
    .m_doc = "SAP (Super Auto Pets, Tier-1 MVP) rules compiled from C.",
    .m_size = -1,
};

PyMODINIT_FUNC PyInit__sap(void) {
    if (PyType_Ready(&SapType) < 0) {
        return NULL;
    }

    PyObject *module = PyModule_Create(&sap_module);
    if (module == NULL) {
        return NULL;
    }

    Py_INCREF(&SapType);
    if (PyModule_AddObject(module, "Sap", (PyObject *)&SapType) < 0) {
        Py_DECREF(&SapType);
        Py_DECREF(module);
        return NULL;
    }

    /* Status codes and shape constants, so the Python layer never hardcodes
     * integers - same convention as the other two envs. */
    if (PyModule_AddIntConstant(module, "ONGOING", SAP_ONGOING) < 0 ||
        PyModule_AddIntConstant(module, "P0_WIN", SAP_P0_WIN) < 0 ||
        PyModule_AddIntConstant(module, "P1_WIN", SAP_P1_WIN) < 0 ||
        PyModule_AddIntConstant(module, "DRAW", SAP_DRAW) < 0 ||
        PyModule_AddIntConstant(module, "P0_WIN_ILLEGAL", SAP_P0_WIN_ILLEGAL) < 0 ||
        PyModule_AddIntConstant(module, "P1_WIN_ILLEGAL", SAP_P1_WIN_ILLEGAL) < 0 ||
        PyModule_AddIntConstant(module, "DRAW_ILLEGAL", SAP_DRAW_ILLEGAL) < 0 ||
        PyModule_AddIntConstant(module, "OBS_FLOATS", SAP_OBS_FLOATS) < 0 ||
        PyModule_AddIntConstant(module, "NUM_ACTIONS", SAP_NUM_ACTIONS) < 0 ||
        PyModule_AddIntConstant(module, "MAX_TICKS", SAP_MAX_TICKS) < 0 ||
        PyModule_AddIntConstant(module, "TEAM_SLOTS", SAP_TEAM) < 0 ||
        PyModule_AddIntConstant(module, "SHOP_PET_SLOTS", SAP_SHOP_PETS) < 0 ||
        PyModule_AddIntConstant(module, "STARTING_GOLD", SAP_STARTING_GOLD) < 0) {
        Py_DECREF(module);
        return NULL;
    }

    return module;
}
