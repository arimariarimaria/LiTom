#include <zephyr/input/input.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>

#include <zmk/event_manager.h>
#include <zmk/events/layer_state_changed.h>
#include <zmk/keymap.h>

LOG_MODULE_REGISTER(litom_auto_mouse_layer, CONFIG_LITOM_AUTO_MOUSE_LAYER_LOG_LEVEL);

#define TARGET_LAYER CONFIG_LITOM_AUTO_MOUSE_LAYER_TARGET
#define SCROLL_LAYER CONFIG_LITOM_AUTO_MOUSE_LAYER_SCROLL
#define TIMEOUT_MS CONFIG_LITOM_AUTO_MOUSE_LAYER_TIMEOUT_MS

static bool layer_owned;

static void deactivate_work_handler(struct k_work *work) {
    if (zmk_keymap_layer_active(SCROLL_LAYER)) {
        return;
    }

    if (layer_owned && zmk_keymap_layer_active(TARGET_LAYER)) {
        int err = zmk_keymap_layer_deactivate(TARGET_LAYER, false);
        if (err < 0) {
            LOG_WRN("Failed to deactivate auto mouse layer %d: %d", TARGET_LAYER, err);
            return;
        }
        LOG_DBG("Auto mouse layer %d deactivated", TARGET_LAYER);
    }

    layer_owned = false;
}

K_WORK_DELAYABLE_DEFINE(deactivate_work, deactivate_work_handler);

static bool is_trackball_motion(const struct input_event *ev) {
    return ev->type == INPUT_EV_REL && ev->value != 0 &&
           (ev->code == INPUT_REL_X || ev->code == INPUT_REL_Y);
}

static void auto_mouse_layer_input_listener(struct input_event *ev) {
    if (!is_trackball_motion(ev)) {
        return;
    }

    if (zmk_keymap_layer_active(SCROLL_LAYER)) {
        return;
    }

    if (!zmk_keymap_layer_active(TARGET_LAYER)) {
        int err = zmk_keymap_layer_activate(TARGET_LAYER, false);
        if (err < 0) {
            LOG_WRN("Failed to activate auto mouse layer %d: %d", TARGET_LAYER, err);
            return;
        }
        LOG_DBG("Auto mouse layer %d activated", TARGET_LAYER);
    }

    layer_owned = true;
    k_work_reschedule(&deactivate_work, K_MSEC(TIMEOUT_MS));
}

INPUT_CALLBACK_DEFINE(NULL, auto_mouse_layer_input_listener);

static int auto_mouse_layer_state_listener(const zmk_event_t *eh) {
    const struct zmk_layer_state_changed *ev = as_zmk_layer_state_changed(eh);
    if (ev == NULL || ev->layer != SCROLL_LAYER || ev->state || !layer_owned) {
        return ZMK_EV_EVENT_BUBBLE;
    }

    k_work_reschedule(&deactivate_work, K_MSEC(TIMEOUT_MS));
    return ZMK_EV_EVENT_BUBBLE;
}

ZMK_LISTENER(litom_auto_mouse_layer, auto_mouse_layer_state_listener);
ZMK_SUBSCRIPTION(litom_auto_mouse_layer, zmk_layer_state_changed);
