"""Bracket combo RPC dispatch with the pinned custom-settings notification API."""
from pathlib import Path
import sys


def prepare(source):
    signature = "static bool runtime_combo_rpc_handle_request("
    start = source.rfind(signature)
    if start < 0:
        raise ValueError("runtime combo RPC entry point not found")
    prefix, handler = source[:start], source[start:]
    begin = "    int ret = 0;\n    switch (req.which_request_type) {"
    end = '\n    if (ret < 0) {\n        set_errno_error(resp, "Runtime combo request", ret);\n'
    if handler.count(begin) != 1 or handler.count(end) != 1:
        raise ValueError("unexpected runtime combo RPC dispatch; review upstream changes")
    handler = handler.replace(
        begin,
        "    int ret = 0;\n"
        "    /* The RPC response confirms these changes. Avoid competing custom-settings\n"
        "     * notifications, as the runtime-macro RPC handler already does. */\n"
        "    zmk_custom_settings_notify_suppress_begin();\n"
        "    switch (req.which_request_type) {",
        1,
    ).replace(
        end,
        "\n    zmk_custom_settings_notify_suppress_end();\n" + end,
        1,
    )
    return prefix + handler


if __name__ == "__main__":
    original, output = map(Path, sys.argv[1:3])
    patched = prepare(original.read_text(encoding="utf-8"))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(patched, encoding="utf-8")
