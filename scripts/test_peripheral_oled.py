"""Run patched C callbacks and all six real sprites against host LVGL stubs."""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from prepare_peripheral_oled import prepare


def function(source, signature):
    start = source.index(signature)
    brace = source.index('{', start)
    end, depth = brace + 1, 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


widgets = Path(sys.argv[1]).resolve()
patched = prepare((widgets / 'peripheral_status.c').read_text(encoding='utf-8'))
callbacks = '\n'.join(function(patched, signature) for signature in [
    'static void draw_bitmap(', 'static void draw_icon(', 'static void update_labels(',
    'static void refresh_widget(', 'static void anim_timer_cb(', 'static void set_key_status(',
    'static void set_connection_status(',
])
constants = '\n'.join(re.findall(r'^#define TOM_OLED_.*$', patched, re.M))

with tempfile.TemporaryDirectory() as temporary:
    directory = Path(temporary)
    (directory / 'zephyr').mkdir()
    (directory / 'zephyr/kernel.h').write_text('', encoding='utf-8')
    (directory / 'lvgl.h').write_text(r'''
#pragma once
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
typedef int sys_snode_t;
typedef struct { char text[32]; int writes, invalidations; } lv_obj_t;
typedef struct { void *user; int period; } lv_timer_t;
typedef struct { uint8_t *data; unsigned stride; } lv_draw_buf_t;
#define LV_ATTRIBUTE_MEM_ALIGN
#define LV_COLOR_FORMAT_I1 1
/* Deliberately pad each row: the renderer must use LVGL's row accessor. */
#define LV_DRAW_BUF_SIZE(w,h,cf) (8 + 12 * (h))
static void *lv_draw_buf_goto_xy(const lv_draw_buf_t *buf, uint32_t x, uint32_t y) {
    return buf->data + 8 + y * buf->stride + x / 8;
}
static void lv_obj_invalidate(lv_obj_t *obj) { obj->invalidations++; }
static void lv_label_set_text(lv_obj_t *obj, const char *text) {
    snprintf(obj->text, sizeof(obj->text), "%s", text); obj->writes++;
}
static void lv_label_set_text_fmt(lv_obj_t *obj, const char *fmt, ...) {
    va_list args; va_start(args, fmt);
    vsnprintf(obj->text, sizeof(obj->text), fmt, args); va_end(args); obj->writes++;
}
static void lv_timer_set_period(lv_timer_t *timer, int period) { timer->period = period; }
static void *lv_timer_get_user_data(lv_timer_t *timer) { return timer->user; }
''', encoding='utf-8')
    source = r'''
#include "peripheral_status.h"
#include "assets/peripheral_cat_images.h"
static int active_layer, trackball_activity;
static int64_t now;
static int64_t k_uptime_get(void) { return now; }
static int atomic_get(int *value) { return *value; }
static bool atomic_cas(int *value, int old, int replacement) {
    if (*value != old) return false;
    *value = replacement; return true;
}
struct peripheral_key_state { bool pressed; };
struct peripheral_status_state { bool connected; };
''' + constants + '\n' + callbacks + r'''
int main(void) {
    lv_obj_t canvas = {0}, connection = {0}, mode = {0}, layer = {0};
    struct zmk_widget_peripheral_status w = {
        .canvas = &canvas, .connection_label = &connection,
        .mode_label = &mode, .layer_label = &layer, .connected = true,
    };
    lv_timer_t timer = {.user = &w};
    w.anim_timer = &timer;
    w.draw_buf = (lv_draw_buf_t){.data = w.cbuf, .stride = 12};
    const uint32_t (*images[])[2] = {
        tom_oled_cat_idle_1, tom_oled_cat_idle_2, tom_oled_cat_move_1,
        tom_oled_cat_move_2, tom_oled_cat_disconnect_1, tom_oled_cat_disconnect_2,
    };
    for (int image = 0; image < 6; image++) {
        memset(w.cbuf, 0xA5, sizeof(w.cbuf));
        int before = canvas.invalidations;
        draw_bitmap(&w, images[image]);
        assert(canvas.invalidations == before + 1);
        for (int i = 0; i < 8; i++) assert(w.cbuf[i] == 0xA5); /* palette */
        for (int y = 0; y < 32; y++) {
            for (int x = 0; x < 64; x++) {
                bool black = (images[image][y][x / 32] >> (31 - x % 32)) & 1;
                bool white = (w.cbuf[8 + y * 12 + x / 8] >> (7 - x % 8)) & 1;
                assert(black != white);
            }
            for (int x = 8; x < 12; x++) assert(w.cbuf[8 + y * 12 + x] == 0xA5);
        }
    }
    int before = canvas.invalidations;
    set_key_status(&w, (struct peripheral_key_state){true});
    assert(w.typing && w.typing_until == 500 && !strcmp(mode.text, "KEY"));
    assert(mode.writes == 1 && connection.writes == 0 && layer.writes == 0);
    for (now = 1; now <= 100; now++) {
        set_key_status(&w, (struct peripheral_key_state){true});
        set_key_status(&w, (struct peripheral_key_state){false});
    }
    assert(w.typing_until == 600 && mode.writes == 1);
    assert(canvas.invalidations == before); /* typing never redraws the cat */

    now = 150; active_layer = 1; /* Windows is not mouse movement */
    anim_timer_cb(&timer);
    assert(w.layer == 1 && !w.moving && timer.period == TOM_OLED_ANIM_CONNECTED_MS);
    assert(canvas.invalidations == ++before && !strcmp(mode.text, "KEY"));
    assert(!strcmp(layer.text, "L1"));
    now = 600;
    anim_timer_cb(&timer);
    assert(!w.typing && !strcmp(mode.text, "PTR"));
    assert(canvas.invalidations == ++before); /* one draw even when state changes */
    anim_timer_cb(&timer);
    assert(canvas.invalidations == ++before); /* one draw for ordinary animation */

    now = 700; trackball_activity = 1;
    anim_timer_cb(&timer);
    assert(w.moving && w.moving_until == 1900 && !strcmp(mode.text, "MOVE"));
    assert(timer.period == TOM_OLED_ANIM_MOVING_MS && trackball_activity == 0);
    assert(canvas.invalidations == ++before);
    int writes = mode.writes;
    set_key_status(&w, (struct peripheral_key_state){true});
    assert(mode.writes == writes && canvas.invalidations == before);
    now = 1900;
    anim_timer_cb(&timer);
    assert(!w.moving && !w.typing && timer.period == TOM_OLED_ANIM_CONNECTED_MS);
    assert(canvas.invalidations == ++before); /* movement expires on Windows too */

    set_connection_status(&w, (struct peripheral_status_state){false});
    assert(!w.connected && !strcmp(connection.text, "CONN --"));
    assert(timer.period == TOM_OLED_ANIM_DISCONNECTED_MS);
    assert(canvas.invalidations == ++before);
    set_connection_status(&w, (struct peripheral_status_state){true});
    assert(w.connected && !strcmp(connection.text, "CONN OK"));
    assert(timer.period == TOM_OLED_ANIM_CONNECTED_MS);
    assert(canvas.invalidations == ++before);
    puts("Peripheral OLED: all six sprites, typing bursts, layers, motion and connection passed");
    return 0;
}
'''
    test_file = directory / 'test.c'
    test_file.write_text(source, encoding='utf-8')
    executable = directory / 'test'
    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                    '-I', str(directory), '-I', str(widgets), str(test_file),
                    str(widgets / 'assets/peripheral_cat_images.c'),
                    '-o', str(executable)], check=True)
    subprocess.run([str(executable)], check=True)
