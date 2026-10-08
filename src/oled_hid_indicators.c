/* SPDX-License-Identifier: MIT */
#include <zephyr/kernel.h>
#include <zmk/display.h>
#include <zmk/event_manager.h>
#include <zmk/events/hid_indicators_changed.h>
#include <zmk/hid_indicators.h>
#include "widgets/hid_indicators.h"

/* Bottom strip: x=62..76, y=27..31 on the 128x32 display.
 * Keep fixed slots for Caps, Num and Scroll; no text can grow into neighbors. */
#define LOCK_WIDTH 15
#define LOCK_HEIGHT 5
static uint8_t canvas_buffer[LV_CANVAS_BUF_SIZE(
    LOCK_WIDTH, LOCK_HEIGHT, LV_COLOR_FORMAT_GET_BPP(LV_COLOR_FORMAT_L8),
    LV_DRAW_BUF_STRIDE_ALIGN)];
static sys_slist_t widgets = SYS_SLIST_STATIC_INIT(&widgets);

static void draw_locks(lv_obj_t *canvas, uint8_t state) {
    static const uint8_t masks[] = {0x02, 0x01, 0x04};
    static const uint8_t glyphs[][5] = {
        {7, 4, 4, 4, 7}, /* C */
        {17, 25, 21, 19, 17}, /* N */
        {7, 4, 7, 1, 7}, /* S */
    };
    static const uint8_t widths[] = {3, 5, 3};
    static const uint8_t offsets[] = {0, 5, 12};
    lv_canvas_fill_bg(canvas, lv_color_white(), LV_OPA_COVER);
    for (int slot = 0; slot < 3; slot++) {
        if (!(state & masks[slot])) {
            continue;
        }
        for (int y = 0; y < LOCK_HEIGHT; y++) {
            for (int x = 0; x < widths[slot]; x++) {
                if (glyphs[slot][y] & (1 << (widths[slot] - x - 1))) {
                    lv_canvas_set_px(canvas, offsets[slot] + x, y,
                                     lv_color_black(), LV_OPA_COVER);
                }
            }
        }
    }
}

static void update_locks(uint8_t state) {
    struct zmk_widget_hid_indicators *widget;
    SYS_SLIST_FOR_EACH_CONTAINER(&widgets, widget, node) {
        draw_locks(widget->obj, state);
    }
}

static uint8_t get_locks(const zmk_event_t *eh) {
    /* The display listener calls this with NULL during initialization. */
    return zmk_hid_indicators_get_current_profile();
}

ZMK_DISPLAY_WIDGET_LISTENER(widget_litom_locks, uint8_t, update_locks, get_locks)
ZMK_SUBSCRIPTION(widget_litom_locks, zmk_hid_indicators_changed);

int zmk_widget_hid_indicators_init(struct zmk_widget_hid_indicators *widget, lv_obj_t *parent) {
    widget->obj = lv_canvas_create(parent);
    lv_canvas_set_buffer(widget->obj, canvas_buffer, LOCK_WIDTH, LOCK_HEIGHT, LV_COLOR_FORMAT_L8);
    sys_slist_append(&widgets, &widget->node);
    widget_litom_locks_init();
    return 0;
}

lv_obj_t *zmk_widget_hid_indicators_obj(struct zmk_widget_hid_indicators *widget) {
    return widget->obj;
}
