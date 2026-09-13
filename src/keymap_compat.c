#include <errno.h>
#include <zephyr/settings/settings.h>
#include <zephyr/logging/log.h>
#include <zmk/behavior.h>
#include <zmk/keymap.h>
#include <zmk/matrix.h>

LOG_MODULE_DECLARE(zmk, CONFIG_ZMK_LOG_LEVEL);

static int compat_settings_set(const char *name, size_t len,
                               settings_read_cb read_cb, void *cb_arg) {
    return -ENOENT;
}

// settings commits run after all saved values have been loaded. Older builds
// used table IDs; CRC16 builds cannot resolve those IDs. Restore only unresolved
// bindings in RAM so input remains usable without erasing the user's settings.
static int repair_unresolved_bindings(void) {
    unsigned int repaired = 0;
    for (int layer = 0; layer < ZMK_KEYMAP_LAYERS_LEN; layer++) {
        for (int position = 0; position < ZMK_KEYMAP_LEN; position++) {
            const struct zmk_behavior_binding *binding =
                zmk_keymap_get_layer_binding_at_idx(layer, position);
            if (!binding || zmk_behavior_get_binding(binding->behavior_dev)) {
                continue;
            }
            const struct zmk_behavior_binding *stock =
                zmk_stock_keymap_get_layer_binding_at_idx(layer, position);
            if (!stock || !zmk_behavior_get_binding(stock->behavior_dev)) {
                continue;
            }
            int err = zmk_keymap_set_layer_binding_at_idx(layer, position, *stock);
            if (err < 0) {
                LOG_WRN("LiTom: cannot recover layer %d position %d: %d", layer, position, err);
                continue;
            }
            repaired++;
        }
    }
    if (repaired) {
        LOG_WRN("LiTom: recovered %u unresolved bindings in RAM; review and save in Studio",
                repaired);
    }
    return 0;
}

SETTINGS_STATIC_HANDLER_DEFINE(litom_keymap_compat, "litom_keymap_compat", NULL,
                               compat_settings_set, repair_unresolved_bindings, NULL);
