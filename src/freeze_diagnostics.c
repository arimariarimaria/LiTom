/* SPDX-License-Identifier: MIT */
#include <zephyr/kernel.h>
#include <zephyr/debug/thread_analyzer.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/sys/printk.h>

#if IS_ENABLED(CONFIG_ZMK_DISPLAY)
#include <zmk/display.h>
#endif

static atomic_t system_completed;
static atomic_t display_completed;

static void system_probe_cb(struct k_work *work) {
    ARG_UNUSED(work);
    atomic_inc(&system_completed);
}
K_WORK_DEFINE(system_probe, system_probe_cb);

#if IS_ENABLED(CONFIG_ZMK_DISPLAY)
static void display_probe_cb(struct k_work *work) {
    ARG_UNUSED(work);
    atomic_inc(&display_completed);
}
K_WORK_DEFINE(display_probe, display_probe_cb);
#endif

static void diagnostics_thread(void *p1, void *p2, void *p3) {
    ARG_UNUSED(p1);
    ARG_UNUSED(p2);
    ARG_UNUSED(p3);
    unsigned int cycle = 0;
    /* Independent of both work queues: a blocked queue leaves its counter
     * unchanged while this thread can still report the other queue's progress. */
    for (;;) {
        k_sleep(K_SECONDS(10));
        printk("[LITOM-DIAG-1] uptime=%llds system=%ld display=%ld\n",
               (long long)(k_uptime_get() / 1000),
               (long)atomic_get(&system_completed),
               (long)atomic_get(&display_completed));
        k_work_submit(&system_probe);
#if IS_ENABLED(CONFIG_ZMK_DISPLAY)
        if (zmk_display_is_initialized()) {
            k_work_submit_to_queue(zmk_display_work_q(), &display_probe);
        }
#endif
        if (++cycle % 3 == 0) {
            thread_analyzer_print(0);
        }
    }
}

K_THREAD_DEFINE(litom_freeze_diag, 2048, diagnostics_thread, NULL, NULL, NULL, 10, 0, 0);
