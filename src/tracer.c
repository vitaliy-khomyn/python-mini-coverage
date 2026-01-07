#include <Python.h>
#include <frameobject.h>

typedef struct {
    PyObject_HEAD
    PyObject *engine;
    PyObject *trace_data_lines;
    PyObject *trace_data_arcs;
    PyObject *trace_data_instr_arcs;
    PyObject *engine_thread_local;
    PyObject *cache_traceable;
} Tracer;

static PyObject* get_context_id(Tracer *self) {
    return PyObject_CallMethod(self->engine, "_get_current_context_id", NULL);
}

static int handle_call_or_return(Tracer *self, PyFrameObject *frame, int what) {
    if (what == PyTrace_CALL) {
        if (PyObject_SetAttrString((PyObject*)frame, "f_trace_opcodes", Py_True) < 0) {
            return -1;
        }
    }
    // clear history to prevent cross-function arcs for both CALL and RETURN
    if (PyObject_SetAttrString(self->engine_thread_local, "last_line", Py_None) < 0) return -1;
    if (PyObject_SetAttrString(self->engine_thread_local, "last_file", Py_None) < 0) return -1;
    if (PyObject_SetAttrString(self->engine_thread_local, "last_lasti", Py_None) < 0) return -1;
    return 0;
}

static int trace_logic(Tracer *self, PyFrameObject *frame, int what, PyObject *arg) {

    if (what == PyTrace_CALL || what == PyTrace_RETURN)
        return handle_call_or_return(self, frame, what);

    if (what != PyTrace_LINE && what != PyTrace_OPCODE) {
        return 0;
    }

    // get filename
    PyObject *code = PyObject_GetAttrString((PyObject*)frame, "f_code");
    if (!code) return -1;

    PyObject *filename = PyObject_GetAttrString(code, "co_filename");
    Py_DECREF(code);
    if (!filename) return -1;

    // cache check
    int cached = PyDict_Contains(self->cache_traceable, filename);
    if (cached == -1) {
        Py_DECREF(filename);
        return -1;
    }

    if (cached == 0) {
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

    PyObject *is_traceable = PyDict_GetItem(self->cache_traceable, filename);
    if (is_traceable != Py_True) {
        Py_DECREF(filename);
        return 0;
    }

    // get context ID
    PyObject *cid = get_context_id(self);
    if (!cid) {
        Py_DECREF(filename);
        return -1;
    }

    // initialize thread local if needed
    if (!PyObject_HasAttrString(self->engine_thread_local, "last_line")) {
        PyObject_SetAttrString(self->engine_thread_local, "last_line", Py_None);
        PyObject_SetAttrString(self->engine_thread_local, "last_file", Py_None);
        PyObject_SetAttrString(self->engine_thread_local, "last_lasti", Py_None);
    }

    if (what == PyTrace_LINE) {
        if (handle_line_event(self, frame, filename, cid) < 0) {
            Py_DECREF(cid);
            Py_DECREF(filename);
            return -1;
        }
    }

    // handle OPCODE event (MC/DC) - runs for both LINE and OPCODE events
    if (handle_opcode_event(self, frame, filename, cid) < 0) {
        Py_DECREF(cid);
        Py_DECREF(filename);
        return -1;
    }

    Py_DECREF(cid);
    Py_DECREF(filename);

    return 0;
}

static int handle_line_event(Tracer *self, PyFrameObject *frame, PyObject *filename, PyObject *cid) {
    int lineno = PyFrame_GetLineNumber(frame);
    PyObject *py_lineno = PyLong_FromLong(lineno);

    // update lines
    PyObject *file_dict = PyObject_GetItem(self->trace_data_lines, filename);
    if (file_dict) {
        PyObject *lines_set = PyObject_GetItem(file_dict, cid);
        if (lines_set) {
            PySet_Add(lines_set, py_lineno);
            Py_DECREF(lines_set);
        }
        Py_DECREF(file_dict);
    }

    // update arcs
    PyObject *last_file = PyObject_GetAttrString(self->engine_thread_local, "last_file");
    PyObject *last_line = PyObject_GetAttrString(self->engine_thread_local, "last_line");

    if (last_file && last_line && last_file != Py_None && last_line != Py_None) {
        int cmp = PyObject_RichCompareBool(last_file, filename, Py_EQ);
        if (cmp == 1) {
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

    PyObject_SetAttrString(self->engine_thread_local, "last_line", py_lineno);
    PyObject_SetAttrString(self->engine_thread_local, "last_file", filename);
    Py_DECREF(py_lineno);
    return 0;
}

static int handle_opcode_event(Tracer *self, PyFrameObject *frame, PyObject *filename, PyObject *cid) {
    // track instruction arcs: last_lasti -> current_lasti
    int current_lasti_int = PyFrame_GetLasti(frame);
    PyObject *current_lasti = PyLong_FromLong(current_lasti_int);

    PyObject *last_lasti = PyObject_GetAttrString(self->engine_thread_local, "last_lasti");
    PyObject *last_file_op = PyObject_GetAttrString(self->engine_thread_local, "last_file");

    if (last_lasti && last_file_op && last_lasti != Py_None && last_file_op != Py_None) {
        int cmp = PyObject_RichCompareBool(last_file_op, filename, Py_EQ);
        if (cmp == 1) {
            PyObject *file_instr_dict = PyObject_GetItem(self->trace_data_instr_arcs, filename);
            if (file_instr_dict) {
                PyObject *instr_set = PyObject_GetItem(file_instr_dict, cid);
                if (instr_set) {
                    PyObject *arc = PyTuple_Pack(2, last_lasti, current_lasti);
                    PySet_Add(instr_set, arc);
                    Py_DECREF(arc);
                    Py_DECREF(instr_set);
                }
                Py_DECREF(file_instr_dict);
            }
        }
    }
    Py_XDECREF(last_lasti);
    Py_XDECREF(last_file_op);

    // update state
    PyObject_SetAttrString(self->engine_thread_local, "last_lasti", current_lasti);
    PyObject_SetAttrString(self->engine_thread_local, "last_file", filename);

    Py_DECREF(current_lasti);
    return 0;
}

static PyObject *
Tracer_call(Tracer *self, PyObject *args) {
    PyObject *frame;
    PyObject *event;
    PyObject *arg;

    if (!PyArg_ParseTuple(args, "OOO", &frame, &event, &arg)) {
        return NULL;
    }

    const char *event_str = PyUnicode_AsUTF8(event);
    int what = -1;
    if (strcmp(event_str, "line") == 0) what = PyTrace_LINE;
    else if (strcmp(event_str, "call") == 0) what = PyTrace_CALL;
    else if (strcmp(event_str, "return") == 0) what = PyTrace_RETURN;
    else if (strcmp(event_str, "exception") == 0) what = PyTrace_EXCEPTION;
    else if (strcmp(event_str, "opcode") == 0) what = PyTrace_OPCODE;

    if (trace_logic(self, (PyFrameObject*)frame, what, arg) < 0) {
        return NULL;
    }

    Py_INCREF(self);
    return (PyObject *)self;
}

static int
Tracer_init(Tracer *self, PyObject *args, PyObject *kwds) {
    PyObject *engine = NULL;
    if (!PyArg_ParseTuple(args, "O", &engine)) {
        return -1;
    }

    Py_INCREF(engine);
    self->engine = engine;

    PyObject *trace_data = PyObject_GetAttrString(engine, "trace_data");
    if (!trace_data) return -1;

    PyObject *key_lines = PyUnicode_FromString("lines");
    self->trace_data_lines = PyObject_GetItem(trace_data, key_lines);
    Py_DECREF(key_lines);

    PyObject *key_arcs = PyUnicode_FromString("arcs");
    self->trace_data_arcs = PyObject_GetItem(trace_data, key_arcs);
    Py_DECREF(key_arcs);

    PyObject *key_instr = PyUnicode_FromString("instruction_arcs");
    self->trace_data_instr_arcs = PyObject_GetItem(trace_data, key_instr);
    Py_DECREF(key_instr);

    Py_DECREF(trace_data);

    self->engine_thread_local = PyObject_GetAttrString(engine, "thread_local");
    self->cache_traceable = PyObject_GetAttrString(engine, "_cache_traceable");

    if (!self->trace_data_lines || !self->trace_data_arcs || !self->trace_data_instr_arcs || !self->engine_thread_local || !self->cache_traceable) {
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
    Py_XDECREF(self->trace_data_instr_arcs);
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