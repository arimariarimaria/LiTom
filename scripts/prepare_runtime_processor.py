"""Apply bounded fixes to a build-directory copy of the pinned runtime module."""
from pathlib import Path
import sys

def prepare(source):
    def replace_once(old, new):
        nonlocal source
        if source.count(old) != 1:
            raise ValueError('Runtime processor changed: review the LiTom compatibility patch')
        source = source.replace(old, new, 1)

    # A single movement event can activate after event processing has returned.
    # Arm its timeout here too, without waiting for a second movement event.
    replace_once('''        data->temp_layer_layer_active = true;
        LOG_INF("Temp-layer layer %d activated", data->temp_layer_layer);''', '''        data->temp_layer_layer_active = true;
        if (!data->temp_layer_keep_active) {
            k_work_reschedule(&data->temp_layer_deactivation_work,
                              K_MSEC(data->temp_layer_deactivation_delay_ms));
        }
        LOG_INF("Temp-layer layer %d activated", data->temp_layer_layer);''')

    helper = '''static int prepare_temp_layer_change(struct runtime_processor_data *data,
                                     bool enabled, uint8_t layer) {
    if (enabled && layer >= ZMK_KEYMAP_LAYERS_LEN) {
        return -EINVAL;
    }
    if (enabled == data->temp_layer_enabled && layer == data->temp_layer_layer) {
        return 0;
    }
    k_work_cancel_delayable(&data->temp_layer_activation_work);
    k_work_cancel_delayable(&data->temp_layer_deactivation_work);
    if (data->temp_layer_layer_active) {
        int err = zmk_keymap_layer_deactivate(data->temp_layer_layer, false);
        if (err < 0) {
            return err;
        }
        data->temp_layer_layer_active = false;
    }
    data->temp_layer_keep_active = false;
    return 0;
}

'''
    replace_once('// Temp-layer layer configuration API', helper + '// Temp-layer layer configuration API')
    for name, args in [('set_temp_layer', 'enabled, layer'),
                       ('set_temp_layer_enabled', 'enabled, data->temp_layer_layer'),
                       ('set_temp_layer_layer', 'data->temp_layer_enabled, layer')]:
        start = source.index('int zmk_input_processor_runtime_' + name + '(')
        marker = '    struct runtime_processor_data *data = dev->data;'
        pos = source.index(marker, start) + len(marker)
        source = source[:pos] + f'''
    int prepare_err = prepare_temp_layer_change(data, {args});
    if (prepare_err < 0) {{
        return prepare_err;
    }}
''' + source[pos:]
    return source

if __name__ == '__main__':
    destination = Path(sys.argv[2])
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(prepare(Path(sys.argv[1]).read_text(encoding='utf-8')), encoding='utf-8')
