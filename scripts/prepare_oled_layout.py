"""Relocate the pinned OLED lock widget without editing the dependency checkout."""
from pathlib import Path
import sys

source = Path(sys.argv[1]).read_text(encoding='utf-8')
old = 'lv_obj_align_to(zmk_widget_hid_indicators_obj(&hid_indicators_widget), zmk_widget_modifiers_obj(&modifiers_widget), LV_ALIGN_OUT_TOP_LEFT, 0, -2);'
new = 'lv_obj_align(zmk_widget_hid_indicators_obj(&hid_indicators_widget), LV_ALIGN_BOTTOM_LEFT, 62, 0);'
if source.count(old) != 1:
    raise ValueError('OLED layout changed; review the LiTom lock indicator placement')
destination = Path(sys.argv[2])
destination.parent.mkdir(parents=True, exist_ok=True)
destination.write_text(source.replace(old, new, 1), encoding='utf-8')
