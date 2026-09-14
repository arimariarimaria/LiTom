"""Reduce left OLED work in a build copy of the pinned tom_oled source."""
from pathlib import Path
import sys


def replace_once(source, old, new):
    if source.count(old) != 1:
        raise ValueError('Peripheral OLED source changed; review the LiTom display patch')
    return source.replace(old, new, 1)


def prepare(source):
    start = source.index('static void set_px(')
    end = source.index('static void draw_icon(', start)
    source = replace_once(source, source[start:end], '''static void draw_bitmap(struct zmk_widget_peripheral_status *widget,
                        const uint32_t rows[TOM_OLED_ICON_HEIGHT][2]) {
    /* I1 palette: 0 = black, 1 = white. Assets use 1 for black, MSB first.
     * goto_xy skips the palette and respects LVGL's row stride. Overwrite the
     * complete image, avoiding both a pixel-by-pixel clear and invalidations. */
    for (uint8_t y = 0; y < TOM_OLED_ICON_HEIGHT; y++) {
        uint8_t *pixels = lv_draw_buf_goto_xy(&widget->draw_buf, 0, y);
        for (uint8_t word = 0; word < 2; word++) {
            uint32_t bits = ~rows[y][word];
            for (uint8_t byte = 0; byte < 4; byte++) {
                pixels[word * 4 + byte] = (uint8_t)(bits >> (24 - byte * 8));
            }
        }
    }
    lv_obj_invalidate(widget->canvas);
}

''')
    for old, new in [
        ('    lv_canvas_fill_bg(widget->canvas, lv_color_white(), LV_OPA_COVER);\n\n', ''),
        ('draw_bitmap(widget->canvas, frames[widget->frame % 2]);',
         'draw_bitmap(widget, frames[widget->frame % 2]);'),
        ('        widget->moving = layer == 1;\n', ''),
        ('widget->moving && widget->layer != 1 && now >= widget->moving_until',
         'widget->moving && now >= widget->moving_until'),
        ('''    if (refresh) {
        refresh_widget(widget);
    }

    widget->frame++;
    draw_icon(widget);''', '''    widget->frame++;
    if (refresh) {
        refresh_widget(widget);
    } else {
        draw_icon(widget);
    }'''),
        ('''    widget->typing = true;
    widget->typing_until = k_uptime_get() + TOM_OLED_TYPE_HOLD_MS;
    refresh_widget(widget);''', '''    /* Key events only extend the indicator lifetime. The cat frame is
     * unchanged; redraw it on the animation timer, not on every key press. */
    bool was_typing = widget->typing;
    widget->typing = true;
    widget->typing_until = k_uptime_get() + TOM_OLED_TYPE_HOLD_MS;
    if (!was_typing && !widget->moving) {
        lv_label_set_text(widget->mode_label, "KEY");
    }'''),
        ('    widget->moving = widget->layer == 1;',
         '    widget->moving = false; /* Layer 1 is Windows, not trackball activity. */'),
    ]:
        source = replace_once(source, old, new)
    return source


if __name__ == '__main__':
    result = prepare(Path(sys.argv[1]).read_text(encoding='utf-8'))
    destination = Path(sys.argv[2])
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(result, encoding='utf-8')
