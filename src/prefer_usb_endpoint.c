#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>

#include <zmk/endpoints.h>
#include <zmk/event_manager.h>
#include <zmk/events/usb_conn_state_changed.h>
#include <zmk/usb.h>

LOG_MODULE_DECLARE(zmk, CONFIG_ZMK_LOG_LEVEL);

static void prefer_usb_endpoint_work_handler(struct k_work *work) {
    if (!zmk_usb_is_hid_ready()) {
        return;
    }

    // Native endpoint routing sends reports only to the selected host.
    // After attachment the user can still explicitly select a BLE host.
    int err = zmk_endpoint_set_preferred_transport(ZMK_TRANSPORT_USB);
    if (err < 0) {
        LOG_WRN("Failed to prefer USB endpoint: %d", err);
    }
}

K_WORK_DELAYABLE_DEFINE(prefer_usb_endpoint_work, prefer_usb_endpoint_work_handler);

static int prefer_usb_endpoint_listener(const zmk_event_t *eh) {
    const struct zmk_usb_conn_state_changed *ev = as_zmk_usb_conn_state_changed(eh);
    if (ev != NULL && ev->conn_state == ZMK_USB_CONN_HID) {
        k_work_reschedule(&prefer_usb_endpoint_work, K_MSEC(100));
    }
    return ZMK_EV_EVENT_BUBBLE;
}

ZMK_LISTENER(prefer_usb_endpoint_listener, prefer_usb_endpoint_listener);
ZMK_SUBSCRIPTION(prefer_usb_endpoint_listener, zmk_usb_conn_state_changed);

static int prefer_usb_endpoint_init(void) {
    k_work_reschedule(&prefer_usb_endpoint_work, K_SECONDS(1));
    return 0;
}

SYS_INIT(prefer_usb_endpoint_init, APPLICATION, CONFIG_APPLICATION_INIT_PRIORITY);
