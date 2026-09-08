/* CPython binding for the Connect4 rules core.
 *
 * Observations and legal masks come back as bytes objects, which the Python
 * layer wraps with numpy.frombuffer. That keeps numpy out of the build
 * entirely and makes the returned arrays read-only, so an observation cannot
 * be mutated by the policy that receives it.
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include "connect4.h"

typedef struct {
    PyObject_HEAD
    Connect4 env;
} Connect4Object;

static PyObject *Connect4_new(PyTypeObject *type, PyObject *args, PyObject *kwds) {
    (void)args;
    (void)kwds;
    Connect4Object *self = (Connect4Object *)type->tp_alloc(type, 0);
    if (self != NULL) {
        c4_reset(&self->env);
        self->env.done = 1; /* not playable until reset() is called */
    }
    return (PyObject *)self;
}

static PyObject *Connect4_reset(Connect4Object *self, PyObject *Py_UNUSED(ignored)) {
    c4_reset(&self->env);
    Py_RETURN_NONE;
}

static PyObject *Connect4_step(Connect4Object *self, PyObject *arg) {
    const long action = PyLong_AsLong(arg);
    if (action == -1 && PyErr_Occurred()) {
        return NULL;
    }
    if (self->env.done) {
        PyErr_SetString(PyExc_RuntimeError, "step() after the episode ended; call reset()");
        return NULL;
    }
    /* Out-of-range actions are a forfeit, not an error, so they are clamped
     * into int range here rather than rejected. */
    const int clamped = (action < INT32_MIN || action > INT32_MAX) ? -1 : (int)action;
    return PyLong_FromLong(c4_step(&self->env, clamped));
}

static PyObject *Connect4_observe(Connect4Object *self, PyObject *Py_UNUSED(ignored)) {
    float buffer[C4_CELLS];
    c4_observe(&self->env, buffer);
    return PyBytes_FromStringAndSize((const char *)buffer, sizeof(buffer));
}

static PyObject *Connect4_legal(Connect4Object *self, PyObject *Py_UNUSED(ignored)) {
    uint8_t buffer[C4_COLS];
    c4_legal(&self->env, buffer);
    return PyBytes_FromStringAndSize((const char *)buffer, sizeof(buffer));
}

static PyObject *Connect4_replay(Connect4Object *self, PyObject *Py_UNUSED(ignored)) {
    PyObject *list = PyList_New(self->env.num_moves);
    if (list == NULL) {
        return NULL;
    }
    for (int i = 0; i < self->env.num_moves; i++) {
        PyObject *item = PyLong_FromLong(self->env.moves[i]);
        if (item == NULL) {
            Py_DECREF(list);
            return NULL;
        }
        PyList_SET_ITEM(list, i, item);
    }
    return list;
}

static PyObject *Connect4_get_to_move(Connect4Object *self, void *closure) {
    (void)closure;
    return PyLong_FromLong(self->env.to_move);
}

static PyObject *Connect4_get_done(Connect4Object *self, void *closure) {
    (void)closure;
    return PyBool_FromLong(self->env.done);
}

static PyMethodDef Connect4_methods[] = {
    {"reset", (PyCFunction)Connect4_reset, METH_NOARGS, "Start a new episode."},
    {"step", (PyCFunction)Connect4_step, METH_O, "Apply an action, return a status code."},
    {"observe", (PyCFunction)Connect4_observe, METH_NOARGS, "42 float32 cells as bytes."},
    {"legal", (PyCFunction)Connect4_legal, METH_NOARGS, "7 bool cells as bytes."},
    {"replay", (PyCFunction)Connect4_replay, METH_NOARGS, "Actions played so far."},
    {NULL, NULL, 0, NULL}};

static PyGetSetDef Connect4_getset[] = {
    {"to_move", (getter)Connect4_get_to_move, NULL, "Player on move.", NULL},
    {"done", (getter)Connect4_get_done, NULL, "Whether the episode ended.", NULL},
    {NULL, NULL, NULL, NULL, NULL}};

static PyTypeObject Connect4Type = {
    PyVarObject_HEAD_INIT(NULL, 0).tp_name = "policyclash_envs._connect4.Connect4",
    .tp_basicsize = sizeof(Connect4Object),
    .tp_flags = Py_TPFLAGS_DEFAULT,
    .tp_doc = "Connect4 rules core.",
    .tp_methods = Connect4_methods,
    .tp_getset = Connect4_getset,
    .tp_new = Connect4_new,
};

static struct PyModuleDef connect4_module = {
    PyModuleDef_HEAD_INIT,
    .m_name = "policyclash_envs._connect4",
    .m_doc = "Connect4 rules compiled from C.",
    .m_size = -1,
};

PyMODINIT_FUNC PyInit__connect4(void) {
    if (PyType_Ready(&Connect4Type) < 0) {
        return NULL;
    }

    PyObject *module = PyModule_Create(&connect4_module);
    if (module == NULL) {
        return NULL;
    }

    Py_INCREF(&Connect4Type);
    if (PyModule_AddObject(module, "Connect4", (PyObject *)&Connect4Type) < 0) {
        Py_DECREF(&Connect4Type);
        Py_DECREF(module);
        return NULL;
    }

    /* Status codes, so the Python layer never hardcodes integers. */
    if (PyModule_AddIntConstant(module, "ONGOING", C4_ONGOING) < 0 ||
        PyModule_AddIntConstant(module, "P0_WIN", C4_P0_WIN) < 0 ||
        PyModule_AddIntConstant(module, "P1_WIN", C4_P1_WIN) < 0 ||
        PyModule_AddIntConstant(module, "DRAW", C4_DRAW) < 0 ||
        PyModule_AddIntConstant(module, "P0_WIN_ILLEGAL", C4_P0_WIN_ILLEGAL) < 0 ||
        PyModule_AddIntConstant(module, "P1_WIN_ILLEGAL", C4_P1_WIN_ILLEGAL) < 0 ||
        PyModule_AddIntConstant(module, "COLS", C4_COLS) < 0 ||
        PyModule_AddIntConstant(module, "ROWS", C4_ROWS) < 0) {
        Py_DECREF(module);
        return NULL;
    }

    return module;
}
