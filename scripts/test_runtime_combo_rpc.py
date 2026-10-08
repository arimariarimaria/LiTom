"""Run real combo RPC dispatch/save with stubs for storage and notifications.

The original must fail the same assertions. USB, protobuf and flash timing
remain outside this host test.
"""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
from prepare_runtime_combo import prepare


def function(source, signature):
    start = source.rindex(signature)
    brace = source.index("{", start)
    depth, end = 1, brace + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


names = [
    "list_combos", "get_combo", "set_combo", "set_combo_name", "delete_combo",
    "get_global_settings", "set_timeout_ms", "set_slow_release", "save",
    "discard", "set_require_prior_idle_ms", "reset_combo",
]
no_arg = {"list_combos", "get_global_settings", "save", "discard"}
read_only = {"list_combos", "get_combo", "get_global_settings"}
tags = "\n".join(f"#define cormoran_runtime_combo_Request_{n}_tag {i + 1}"
                 for i, n in enumerate(names)) + "\n"
members = "\n".join(f"int {n};" for n in names if n not in no_arg)
stubs = []
for name in names:
    if name == "save":
        continue
    params = "" if name in no_arg else "const int *req, "
    unused = "" if name in no_arg else "(void)req;"
    effect = "" if name in read_only else "setting_changed();"
    stubs.append(
        f"static int handle_{name}({params}cormoran_runtime_combo_Response *resp) {{"
        f"{unused} (void)resp; calls++; {effect} return operation_error; }}"
    )

preamble = r"""
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <errno.h>
#include <string.h>
typedef int pb_callback_t;
typedef int pb_istream_t;
typedef struct { struct { unsigned char bytes[1]; size_t size; } payload; } zmk_custom_CallRequest;
typedef struct { int error; unsigned affected; bool status; } cormoran_runtime_combo_Response;
static cormoran_runtime_combo_Response response;
static int selected_tag, operation_error, calls, notifications, begins, ends, depth;
static int saves, rebuilds;
static bool decode_ok = true;
#define ZMK_RUNTIME_COMBO_SUBSYSTEM_ID "runtime_combo"
#define cormoran_runtime_combo_Request_init_zero {0}
#define cormoran_runtime_combo_Request_fields 0
#define LOG_WRN(...) ((void)0)
#define PB_GET_ERROR(...) ""
#define ZMK_RPC_CUSTOM_SUBSYSTEM_RESPONSE_BUFFER_ALLOCATE(subsystem, cb) (&response)
static pb_istream_t pb_istream_from_buffer(const void *p, size_t n) { (void)p; (void)n; return 0; }
static void setting_changed(void) { if (depth == 0) notifications++; }
static void zmk_custom_settings_notify_suppress_begin(void) { depth++; begins++; }
static void zmk_custom_settings_notify_suppress_end(void) { assert(depth > 0); depth--; ends++; }
static void set_error(cormoran_runtime_combo_Response *r, const char *s) {
    (void)s; r->error = -EBADMSG;
}
static void set_errno_error(cormoran_runtime_combo_Response *r, const char *s, int e) {
    (void)s; r->error = e;
}
static void set_status(cormoran_runtime_combo_Response *r, const char *s, uint32_t n) {
    (void)s; r->status = true; r->affected = n;
}
static int zmk_custom_settings_save_scope(const char *sub, const char *key,
                                         const char *prefix, uint32_t *affected) {
    assert(strcmp(sub, ZMK_RUNTIME_COMBO_SUBSYSTEM_ID) == 0);
    assert(key == NULL && prefix == NULL);
    calls++; saves++;
    for (int i = 0; i < 24; i++) setting_changed();
    *affected = 24;
    return operation_error;
}
static void zmk_runtime_combo_invalidate_cache(void) { rebuilds++; }
"""
request_type = (
    "typedef struct { int which_request_type; struct {" + members
    + "} request_type; } cormoran_runtime_combo_Request;\n"
    + "static bool pb_decode(pb_istream_t *s, int f, cormoran_runtime_combo_Request *r) {"
    + "(void)s; (void)f; r->which_request_type = selected_tag; return decode_ok; }\n"
)
main = r"""
static void reset_case(void) {
    response = (cormoran_runtime_combo_Response){0};
    calls = notifications = begins = ends = depth = saves = rebuilds = 0;
    decode_ok = true;
}
static void dispatch(void) {
    zmk_custom_CallRequest raw = {0};
    pb_callback_t encoded = 0;
    assert(runtime_combo_rpc_handle_request(&raw, &encoded));
}
int main(void) {
    for (int tag = 1; tag <= 12; tag++) {
        for (int error = 0; error < 2; error++) {
            reset_case();
            selected_tag = tag == 1 ? 9 : tag == 9 ? 1 : tag;
            operation_error = error ? -EIO : 0;
            dispatch();
            assert(calls == 1);
            assert(notifications == 0);
            assert(begins == 1 && ends == 1 && depth == 0);
            assert(response.error == operation_error);
            if (selected_tag == cormoran_runtime_combo_Request_save_tag) {
                assert(saves == 1 && rebuilds == 1);
                assert(response.status == !error);
                if (!error) assert(response.affected == 24);
            }
            setting_changed(); /* Non-RPC updates must still notify. */
            assert(notifications == 1);
        }
    }
    reset_case();
    selected_tag = 99;
    operation_error = 0;
    dispatch();
    assert(response.error == -ENOTSUP && calls == 0 && depth == 0);
    assert(begins == 1 && ends == 1);
    reset_case();
    decode_ok = false;
    dispatch();
    assert(response.error == -EBADMSG && calls == 0);
    assert(begins == 0 && ends == 0 && depth == 0);
    reset_case();
    depth = 1; /* Nesting must preserve the caller's suppression. */
    selected_tag = cormoran_runtime_combo_Request_save_tag;
    dispatch();
    assert(depth == 1 && begins == 1 && ends == 1 && notifications == 0);
    zmk_custom_settings_notify_suppress_end();
    setting_changed();
    assert(depth == 0 && notifications == 1);
    return 0;
}
"""


def program(source):
    return (
        preamble + tags + request_type + "\n".join(stubs)
        + function(source, "static int handle_save(")
        + function(source, "static bool runtime_combo_rpc_handle_request(")
        + main
    )


source = Path(sys.argv[1]).read_text(encoding="utf-8")
patched = prepare(source)
with tempfile.TemporaryDirectory() as tmp:
    for name, contents, succeeds in [("original", source, False), ("patched", patched, True)]:
        c_file = Path(tmp) / f"{name}.c"
        binary = Path(tmp) / name
        c_file.write_text(program(contents), encoding="utf-8")
        subprocess.run(
            [os.environ.get("CC", "cc"), "-std=c11", "-Wall", "-Wextra",
             "-Werror=implicit-function-declaration", "-Wno-unused-parameter",
             str(c_file), "-o", str(binary)], check=True,
        )
        result = subprocess.run([str(binary)], capture_output=True, text=True)
        if succeeds:
            assert result.returncode == 0, result.stderr
        else:
            assert result.returncode != 0 and "notifications == 0" in result.stderr, result.stderr
        print(f"{name}: {'passes' if succeeds else 'regression reproduced'}")

for unsupported in [patched, source.replace("    int ret = 0;\n    switch", "    int ret = 1;\n    switch")]:
    try:
        prepare(unsupported)
    except ValueError:
        pass
    else:
        raise AssertionError("unexpected upstream source accepted")
print("combo RPC regression checks passed")
