/* CPython binding for the Tron Duel rules core.
 *
 * Observations and legal masks come back as bytes objects, which the Python
 * layer wraps with numpy.frombuffer. That keeps numpy out of the build
 * entirely and makes the returned arrays read-only, so an observation cannot
 * be mutated by the policy that receives it.
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include "tron_duel.h"

typedef struct {
    PyObject_HEAD
    TronDuel env;
} TronDuelObject;

static PyObject *TronDuel_new(PyTypeObject *type, PyObject *args, PyObject *kwds) {
    (void)args;
    (void)kwds;
    TronDuelObject *self = (TronDuelObject *)type->tp_alloc(type, 0);
    if (self != NULL) {
        td_reset(&self->env, 0);
        self->env.done = 1; /* not playable until reset() is called */
    }
    return (PyObject *)self;
}

static PyObject *TronDuel_reset(TronDuelObject *self, PyObject *arg) {
    const unsigned long long seed = PyLong_AsUnsignedLongLong(arg);
    if (seed == (unsigned long long)-1 && PyErr_Occurred()) {
        return NULL;
    }
    td_reset(&self->env, (uint64_t)seed);
    Py_RETURN_NONE;
}

/* Out-of-range actions are a forfeit, not an error, so they are clamped into
 * int range here rather than rejected. */
static int td_clamp_action(PyObject *arg, int *out) {
    const long action = PyLong_AsLong(arg);
    if (action == -1 && PyErr_Occurred()) {
        return -1;
    }
    *out = (action < INT32_MIN || action > INT32_MAX) ? -1 : (int)action;
    return 0;
}

static PyObject *TronDuel_step(TronDuelObject *self, PyObject *args) {
    PyObject *first = NULL;
    PyObject *second = NULL;
    if (!PyArg_ParseTuple(args, "OO", &first, &second)) {
        return NULL;
    }

    int action_0 = 0;
    int action_1 = 0;
    if (td_clamp_action(first, &action_0) < 0 || td_clamp_action(second, &action_1) < 0) {
        return NULL;
    }

    if (self->env.done) {
        PyErr_SetString(PyExc_RuntimeError, "step() after the episode ended; call reset()");
        return NULL;
    }

    /* Not a rules path. Reaching TD_MAX_TICKS means the cell-consumption
     * argument in the header is wrong and a crash was not forced, so this is
     * a bug detector for the rules core rather than a step limit. */
    if (self->env.num_ticks >= TD_MAX_TICKS) {
        PyErr_SetString(PyExc_RuntimeError,
                        "tick bound reached without a forced crash; rules core is broken");
        return NULL;
    }

    return PyLong_FromLong(td_step(&self->env, action_0, action_1));
}

static int td_parse_seat(PyObject *arg, int *out) {
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

static PyObject *TronDuel_observe(TronDuelObject *self, PyObject *arg) {
    int seat = 0;
    if (td_parse_seat(arg, &seat) < 0) {
        return NULL;
    }
    float buffer[TD_PLANES * TD_CELLS];
    td_observe(&self->env, seat, buffer);
    return PyBytes_FromStringAndSize((const char *)buffer, sizeof(buffer));
}

static PyObject *TronDuel_legal(TronDuelObject *self, PyObject *arg) {
    int seat = 0;
    if (td_parse_seat(arg, &seat) < 0) {
        return NULL;
    }
    uint8_t buffer[TD_ACTIONS];
    td_legal(&self->env, seat, buffer);
    return PyBytes_FromStringAndSize((const char *)buffer, sizeof(buffer));
}

static PyObject *TronDuel_replay(TronDuelObject *self, PyObject *Py_UNUSED(ignored)) {
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

static PyObject *TronDuel_get_done(TronDuelObject *self, void *closure) {
    (void)closure;
    return PyBool_FromLong(self->env.done);
}

static PyMethodDef TronDuel_methods[] = {
    {"reset", (PyCFunction)TronDuel_reset, METH_O, "Start a new episode from a seed."},
    {"step", (PyCFunction)TronDuel_step, METH_VARARGS,
     "Apply one action per seat, return a status code."},
    {"observe", (PyCFunction)TronDuel_observe, METH_O, "676 float32 cells as bytes."},
    {"legal", (PyCFunction)TronDuel_legal, METH_O, "3 bool cells as bytes."},
    {"replay", (PyCFunction)TronDuel_replay, METH_NOARGS, "Actions played so far, flat."},
    {NULL, NULL, 0, NULL}};

static PyGetSetDef TronDuel_getset[] = {
    {"done", (getter)TronDuel_get_done, NULL, "Whether the episode ended.", NULL},
    {NULL, NULL, NULL, NULL, NULL}};

static PyTypeObject TronDuelType = {
    PyVarObject_HEAD_INIT(NULL, 0).tp_name = "policyclash_envs._tron_duel.TronDuel",
    .tp_basicsize = sizeof(TronDuelObject),
    .tp_flags = Py_TPFLAGS_DEFAULT,
    .tp_doc = "Tron Duel rules core.",
    .tp_methods = TronDuel_methods,
    .tp_getset = TronDuel_getset,
    .tp_new = TronDuel_new,
};

static struct PyModuleDef tron_duel_module = {
    PyModuleDef_HEAD_INIT,
    .m_name = "policyclash_envs._tron_duel",
    .m_doc = "Tron Duel rules compiled from C.",
    .m_size = -1,
};

PyMODINIT_FUNC PyInit__tron_duel(void) {
    if (PyType_Ready(&TronDuelType) < 0) {
        return NULL;
    }

    PyObject *module = PyModule_Create(&tron_duel_module);
    if (module == NULL) {
        return NULL;
    }

    Py_INCREF(&TronDuelType);
    if (PyModule_AddObject(module, "TronDuel", (PyObject *)&TronDuelType) < 0) {
        Py_DECREF(&TronDuelType);
        Py_DECREF(module);
        return NULL;
    }

    /* Status codes and board shape, so the Python layer never hardcodes
     * integers. */
    if (PyModule_AddIntConstant(module, "ONGOING", TD_ONGOING) < 0 ||
        PyModule_AddIntConstant(module, "P0_WIN", TD_P0_WIN) < 0 ||
        PyModule_AddIntConstant(module, "P1_WIN", TD_P1_WIN) < 0 ||
        PyModule_AddIntConstant(module, "DRAW", TD_DRAW) < 0 ||
        PyModule_AddIntConstant(module, "P0_WIN_ILLEGAL", TD_P0_WIN_ILLEGAL) < 0 ||
        PyModule_AddIntConstant(module, "P1_WIN_ILLEGAL", TD_P1_WIN_ILLEGAL) < 0 ||
        PyModule_AddIntConstant(module, "DRAW_ILLEGAL", TD_DRAW_ILLEGAL) < 0 ||
        PyModule_AddIntConstant(module, "SIZE", TD_SIZE) < 0 ||
        PyModule_AddIntConstant(module, "CELLS", TD_CELLS) < 0 ||
        PyModule_AddIntConstant(module, "PLANES", TD_PLANES) < 0 ||
        PyModule_AddIntConstant(module, "ACTIONS", TD_ACTIONS) < 0 ||
        PyModule_AddIntConstant(module, "MAX_TICKS", TD_MAX_TICKS) < 0) {
        Py_DECREF(module);
        return NULL;
    }

    return module;
}
