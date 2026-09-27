"""Execute the real recovery code and patched layer callbacks with host stubs."""
from pathlib import Path
import subprocess
import sys
import tempfile

from prepare_runtime_processor import prepare

ROOT = Path(__file__).resolve().parents[1]


def function(source, signature):
    start = source.index(signature)
    brace = source.index('{', start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


def run(directory, name, source):
    path = directory / (name + '.c')
    path.write_text(source, encoding='utf-8')
    executable = directory / name
    subprocess.run(['cc', '-std=c11', '-Wall', '-Werror=implicit-function-declaration',
                    '-I', str(directory), str(path), '-o', str(executable)], check=True)
    subprocess.run([str(executable)], check=True)


with tempfile.TemporaryDirectory() as temporary:
    directory = Path(temporary)
    for header in ['zephyr/settings/settings.h', 'zephyr/logging/log.h',
                   'zmk/behavior.h', 'zmk/keymap.h', 'zmk/matrix.h']:
        path = directory / header
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('', encoding='utf-8')
    run(directory, 'keymap', r'''
#include <assert.h>
#include <stddef.h>
#include <errno.h>
#define LOG_MODULE_DECLARE(...)
#define LOG_WRN(...) ((void)0)
#define SETTINGS_STATIC_HANDLER_DEFINE(...)
#define ZMK_KEYMAP_LAYERS_LEN 2
#define ZMK_KEYMAP_LEN 3
typedef int (*settings_read_cb)(void *, void *, size_t);
struct zmk_behavior_binding { const char *behavior_dev; int param1; };
static struct zmk_behavior_binding current[2][3], stock[2][3];
static int writes;
static const void *zmk_behavior_get_binding(const char *name) {
    return name && name[0] == 'v' ? name : NULL;
}
static const struct zmk_behavior_binding *zmk_keymap_get_layer_binding_at_idx(int l, int p) {
    return &current[l][p];
}
static const struct zmk_behavior_binding *zmk_stock_keymap_get_layer_binding_at_idx(int l, int p) {
    return &stock[l][p];
}
static int zmk_keymap_set_layer_binding_at_idx(int l, int p, struct zmk_behavior_binding b) {
    if (l == 1 && p == 2) return -EIO;
    current[l][p] = b;
    writes++;
    return 0;
}
''' + (ROOT / 'src/keymap_compat.c').read_text(encoding='utf-8') + r'''
int main(void) {
    for (int l = 0; l < 2; l++) for (int p = 0; p < 3; p++) {
        stock[l][p] = (struct zmk_behavior_binding){"valid_stock", l * 10 + p};
    }
    current[0][0] = (struct zmk_behavior_binding){"valid_custom", 99};
    current[0][1] = (struct zmk_behavior_binding){"missing", 88};
    stock[1][1].behavior_dev = NULL;
    assert(repair_unresolved_bindings() == 0);
    assert(current[0][0].param1 == 99); /* preserve valid custom binding */
    assert(current[0][1].param1 == 1);  /* unresolved name */
    assert(current[0][2].param1 == 2);  /* unresolved saved ID -> NULL */
    assert(current[1][0].param1 == 10);
    assert(current[1][1].behavior_dev == NULL); /* no valid fallback */
    assert(current[1][2].behavior_dev == NULL); /* setter failed */
    assert(writes == 3);
    repair_unresolved_bindings();
    assert(writes == 3); /* repeated settings commit is harmless */
    return 0;
}
''')
    patched = prepare(Path(sys.argv[1]).read_text(encoding='utf-8'))
    callbacks = '\n'.join(function(patched, signature) for signature in [
        'static void temp_layer_activation_work_handler(',
        'static void temp_layer_deactivation_work_handler(',
        'static int prepare_temp_layer_change('])
    run(directory, 'layers', r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <errno.h>
#define ZMK_KEYMAP_LAYERS_LEN 8
#define LOG_INF(...) ((void)0)
#define LOG_ERR(...) ((void)0)
#define K_MSEC(x) (x)
#define CONTAINER_OF(p,t,m) ((t *)((char *)(p) - offsetof(t,m)))
struct k_work { int unused; };
struct k_work_delayable { struct k_work work; int delay; bool pending; };
struct runtime_processor_data {
    bool temp_layer_enabled, temp_layer_layer_active, temp_layer_keep_active;
    uint8_t temp_layer_layer;
    int temp_layer_deactivation_delay_ms;
    struct k_work_delayable temp_layer_activation_work, temp_layer_deactivation_work;
};
static int active = -1, fail_deactivate;
static struct k_work_delayable *k_work_delayable_from_work(struct k_work *w) {
    return CONTAINER_OF(w, struct k_work_delayable, work);
}
static int k_work_reschedule(struct k_work_delayable *w, int delay) {
    w->pending = true; w->delay = delay; return 0;
}
static int k_work_cancel_delayable(struct k_work_delayable *w) {
    w->pending = false; return 0;
}
static int zmk_keymap_layer_activate(int layer, bool unused) { active = layer; return 0; }
static int zmk_keymap_layer_deactivate(int layer, bool unused) {
    if (fail_deactivate) return -EIO;
    assert(active == layer); active = -1; return 0;
}
''' + callbacks + r'''
int main(void) {
    struct runtime_processor_data d = {
        .temp_layer_enabled = true, .temp_layer_layer = 2,
        .temp_layer_deactivation_delay_ms = 400
    };
    temp_layer_activation_work_handler(&d.temp_layer_activation_work.work);
    assert(active == 2 && d.temp_layer_deactivation_work.pending);
    assert(d.temp_layer_deactivation_work.delay == 400);
    temp_layer_deactivation_work_handler(&d.temp_layer_deactivation_work.work);
    assert(active == -1 && !d.temp_layer_layer_active); /* single movement expires */
    temp_layer_activation_work_handler(&d.temp_layer_activation_work.work);
    assert(prepare_temp_layer_change(&d, true, 8) == -EINVAL);
    assert(active == 2); /* reject invalid target without disturbing current one */
    assert(prepare_temp_layer_change(&d, true, 2) == 0 && active == 2);
    assert(prepare_temp_layer_change(&d, true, 4) == 0);
    assert(active == -1 && !d.temp_layer_layer_active);
    assert(!d.temp_layer_deactivation_work.pending);
    d.temp_layer_layer = 4;
    temp_layer_activation_work_handler(&d.temp_layer_activation_work.work);
    fail_deactivate = 1;
    assert(prepare_temp_layer_change(&d, false, 4) == -EIO);
    assert(active == 4 && d.temp_layer_layer_active);
    fail_deactivate = 0;
    assert(prepare_temp_layer_change(&d, false, 4) == 0 && active == -1);
    return 0;
}
''')
print('PASS: unresolved binding recovery; single-event timeout; target change and disable')
