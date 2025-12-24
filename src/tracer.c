#include <Python.h>
#include <frameobject.h>

/* * Structure for the Tracer object.
 * Holds references to the engine and its key attributes to avoid repeated lookups.
 */
typedef struct {
    PyObject_HEAD
    PyObject *engine;          // The MiniCoverage instance
    PyObject *trace_data_lines; // engine.trace_data['lines']
    PyObject *trace_data_arcs;  // engine.trace_data['arcs']
    PyObject *engine_thread_local; // engine.thread_local (Renamed to avoid C keyword conflict)
    PyObject *cache_traceable;  // engine._cache_traceable
} Tracer;

/*
 * Helper to get current context ID from engine.
 * Equivalent to: engine._get_current_context_id()
 */
static PyObject*
get_context_id(Tracer *self) {
    return PyObject_CallMethod(self->engine, "_get_current_context_id", NULL);
}

/*
 * The core trace logic.
 * Equivalent to MiniCoverage.trace_function
 */
static int
trace_logic(Tracer *self, PyFrameObject *frame, int what, PyObject *arg) {
    // 1. Only handle LINE events
    if (what != PyTrace_LINE) {
        return 0;
    }

    // 2. Get Filename
    // PyFrame_GetCode returns a new reference in 3.11+, but borrowing f_code is standard in C extensions for older versions.
    // For safety across versions, we access the attribute.
    PyObject *code = PyObject_GetAttrString((PyObject*)frame, "f_code");
    if (!code) return -1;

    PyObject *filename = PyObject_GetAttrString(code, "co_filename");
    Py_DECREF(code);
    if (!filename) return -1;

    // 3. Check Cache (_cache_traceable)
    // if filename not in self._cache_traceable:
    int cached = PyDict_Contains(self->cache_traceable, filename);
    if (cached == -1) { // Error
        Py_DECREF(filename);
        return -1;
    }

    if (cached == 0) {
        // self._cache_traceable[filename] = self._should_trace(filename)
        PyObject *should = PyObject_CallMethod(self->engine, "_should_trace", "O", filename);
        if (!should) {
            Py_DECREF(filename);
            return -1;
        }
        if (PyDict_SetItem(self->cache_traceable, filename, should) < 0) {
            Py_DECREF(should);
            Py_DECREF(filename);
            return -1;
        }
        Py_DECREF(should);
    }

    // Check if we should trace
    PyObject *is_traceable = PyDict_GetItem(self->cache_traceable, filename); // Borrowed
    if (is_traceable != Py_True) {
        Py_DECREF(filename);
        return 0;
    }

    // 4. Get Line Number
    int lineno = PyFrame_GetLineNumber(frame);
    PyObject *py_lineno = PyLong_FromLong(lineno);

    // 5. Get Context ID
    PyObject *cid = get_context_id(self);
    if (!cid) {
        Py_DECREF(filename);
        Py_DECREF(py_lineno);
        return -1;
    }

    // 6. Update Lines: self.trace_data['lines'][filename][cid].add(lineno)
    // trace_data_lines is a defaultdict(defaultdict(set))
    // Get file dict
    PyObject *file_dict = PyObject_GetItem(self->trace_data_lines, filename); // New Ref
    if (!file_dict) {
        Py_DECREF(filename);
        Py_DECREF(py_lineno);
        Py_DECREF(cid);
        return -1;
    }

    // Get context set
    PyObject *lines_set = PyObject_GetItem(file_dict, cid); // New Ref
    if (!lines_set) {
        Py_DECREF(file_dict);
        Py_DECREF(filename);
        Py_DECREF(py_lineno);
        Py_DECREF(cid);
        return -1;
    }

    // Add line
    PySet_Add(lines_set, py_lineno);
    Py_DECREF(lines_set);
    Py_DECREF(file_dict);

    // 7. Update Arcs (Thread Local Logic)
    // Using engine_thread_local instead of thread_local
    if (!PyObject_HasAttrString(self->engine_thread_local, "last_line")) {
        PyObject_SetAttrString(self->engine_thread_local, "last_line", Py_None);
        PyObject_SetAttrString(self->engine_thread_local, "last_file", Py_None);
    }

    // last_file = self.thread_local.last_file
    // last_line = self.thread_local.last_line
    PyObject *last_file = PyObject_GetAttrString(self->engine_thread_local, "last_file");
    PyObject *last_line = PyObject_GetAttrString(self->engine_thread_local, "last_line");

    if (last_file && last_line && last_file != Py_None && last_line != Py_None) {
        // if last_file == filename:
        int cmp = PyObject_RichCompareBool(last_file, filename, Py_EQ);
        if (cmp == 1) {
            // self.trace_data['arcs'][filename][cid].add((last_line, lineno))
            PyObject *file_arcs_dict = PyObject_GetItem(self->trace_data_arcs, filename);
            if (file_arcs_dict) {
                PyObject *arcs_set = PyObject_GetItem(file_arcs_dict, cid);
                if (arcs_set) {
                    PyObject *arc = PyTuple_Pack(2, last_line, py_lineno);
                    PySet_Add(arcs_set, arc);
                    Py_DECREF(arc);
                    Py_DECREF(arcs_set);
                }
                Py_DECREF(file_arcs_dict);
            }
        }
    }
    Py_XDECREF(last_file);
    Py_XDECREF(last_line);

    // self.thread_local.last_line = lineno
    // self.thread_local.last_file = filename
    PyObject_SetAttrString(self->engine_thread_local, "last_line", py_lineno);
    PyObject_SetAttrString(self->engine_thread_local, "last_file", filename);

    Py_DECREF(py_lineno);
    Py_DECREF(cid);
    Py_DECREF(filename);

    return 0;
}

/*
 * __call__ implementation makes the instance callable.
 * trace(frame, event, arg)
 */
static PyObject *
Tracer_call(Tracer *self, PyObject *args) {
    PyObject *frame;
    PyObject *event;
    PyObject *arg;

    if (!PyArg_ParseTuple(args, "OOO", &frame, &event, &arg)) {
        return NULL;
    }

    // Check event type string
    const char *event_str = PyUnicode_AsUTF8(event);
    int what = -1;
    if (strcmp(event_str, "line") == 0) what = PyTrace_LINE;
    else if (strcmp(event_str, "call") == 0) what = PyTrace_CALL;
    else if (strcmp(event_str, "return") == 0) what = PyTrace_RETURN;
    else if (strcmp(event_str, "exception") == 0) what = PyTrace_EXCEPTION;

    if (trace_logic(self, (PyFrameObject*)frame, what, arg) < 0) {
        return NULL;
    }

    // Must return self to continue tracing
    Py_INCREF(self);
    return (PyObject *)self;
}

static int
Tracer_init(Tracer *self, PyObject *args, PyObject *kwds) {
    PyObject *engine = NULL;
    if (!PyArg_ParseTuple(args, "O", &engine)) {
        return -1;
    }

    // Store Engine
    Py_INCREF(engine);
    self->engine = engine;

    // Cache dicts for speed
    PyObject *trace_data = PyObject_GetAttrString(engine, "trace_data");
    if (!trace_data) return -1;

    self->trace_data_lines = PyObject_GetItem(trace_data, PyUnicode_FromString("lines"));
    self->trace_data_arcs = PyObject_GetItem(trace_data, PyUnicode_FromString("arcs"));
    Py_DECREF(trace_data);

    // Retrieve thread_local from engine, but store it as engine_thread_local
    self->engine_thread_local = PyObject_GetAttrString(engine, "thread_local");
    self->cache_traceable = PyObject_GetAttrString(engine, "_cache_traceable");

    if (!self->trace_data_lines || !self->trace_data_arcs || !self->engine_thread_local || !self->cache_traceable) {
        Py_XDECREF(self->engine);
        return -1;
    }

    return 0;
}

static void
Tracer_dealloc(Tracer *self) {
    Py_XDECREF(self->engine);
    Py_XDECREF(self->trace_data_lines);
    Py_XDECREF(self->trace_data_arcs);
    Py_XDECREF(self->engine_thread_local);
    Py_XDECREF(self->cache_traceable);
    Py_TYPE(self)->tp_free((PyObject *)self);
}

static PyTypeObject TracerType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "minicov_tracer.Tracer",
    .tp_doc = "C-based Tracer for MiniCoverage",
    .tp_basicsize = sizeof(Tracer),
    .tp_itemsize = 0,
    .tp_flags = Py_TPFLAGS_DEFAULT,
    .tp_new = PyType_GenericNew,
    .tp_init = (initproc)Tracer_init,
    .tp_dealloc = (destructor)Tracer_dealloc,
    .tp_call = (ternaryfunc)Tracer_call,
};

static PyModuleDef minicov_tracer_module = {
    PyModuleDef_HEAD_INIT,
    .m_name = "minicov_tracer",
    .m_doc = "C extension for MiniCoverage tracer.",
    .m_size = -1,
};

PyMODINIT_FUNC
PyInit_minicov_tracer(void) {
    PyObject *m;
    if (PyType_Ready(&TracerType) < 0)
        return NULL;

    m = PyModule_Create(&minicov_tracer_module);
    if (m == NULL)
        return NULL;

    Py_INCREF(&TracerType);
    if (PyModule_AddObject(m, "Tracer", (PyObject *)&TracerType) < 0) {
        Py_DECREF(&TracerType);
        Py_DECREF(m);
        return NULL;
    }

    return m;
}