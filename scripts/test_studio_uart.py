"""Run the real UART callback against a bounded FIFO and wrapping ring buffer.

Original code must spin when the FIFO reports zero progress. The probe aborts
after eight calls to avoid hanging CI; patched callbacks return and retry later.
"""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
from prepare_studio_uart import prepare


def function(source, signature):
    start = source.index(signature)
    brace = source.index("{", start)
    depth, end = 1, brace + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


PROBE = r"""
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#define MAX(a,b) ((a) > (b) ? (a) : (b))
#define LOG_ERR(...) ((void)0)
struct device { int unused; };
static const struct device device;
static const struct device *uart_dev = &device;
struct ring_buf { uint8_t data[16]; uint32_t size, head, len, claim; };
static struct ring_buf tx = {.size = 16}, rx = {.size = 16};
static int fifo_space, fifo_calls, callback_calls, enables, disables, rx_notifies;
static bool tx_enabled, rx_ready, empty_claim, inject_producer;
static unsigned output_len;
static uint8_t output[128];
static void uart_irq_tx_enable(const struct device *d) { (void)d; tx_enabled = true; enables++; }
static void uart_irq_tx_disable(const struct device *d) { (void)d; tx_enabled = false; disables++; }
static void enqueue(const char *s) {
    while (*s) {
        assert(tx.len < tx.size);
        tx.data[(tx.head + tx.len) % tx.size] = *s++;
        tx.len++;
    }
}
static struct ring_buf *zmk_rpc_get_tx_buf(void) { return &tx; }
static struct ring_buf *zmk_rpc_get_rx_buf(void) { return &rx; }
static int uart_irq_update(const struct device *d) { (void)d; return 1; }
static int uart_irq_rx_ready(const struct device *d) { (void)d; return rx_ready; }
static int uart_irq_tx_ready(const struct device *d) { (void)d; return tx_enabled; }
static uint32_t ring_buf_size_get(struct ring_buf *r) {
    unsigned count = r->len;
    if (r == &tx && count == 0 && inject_producer) {
        inject_producer = false;
        enqueue("new");
        uart_irq_tx_enable(uart_dev); /* tx_notify after a concurrent put */
    }
    return count;
}
static uint32_t ring_buf_get_claim(struct ring_buf *r, uint8_t **b, uint32_t n) {
    if (++callback_calls > 8) exit(77);
    *b = r->data + r->head;
    r->claim = empty_claim ? 0 : (r->len < r->size - r->head ? r->len : r->size - r->head);
    if (r->claim > n) r->claim = n;
    return r->claim;
}
static void ring_buf_get_finish(struct ring_buf *r, uint32_t n) {
    assert(n <= r->claim);
    r->head = (r->head + n) % r->size;
    r->len -= n; r->claim = 0;
}
static int uart_fifo_fill(const struct device *d, const uint8_t *data, unsigned n) {
    (void)d;
    if (++fifo_calls > 8) exit(77);
    if (fifo_space < 0) return -5;
    unsigned wrote = n < (unsigned)fifo_space ? n : (unsigned)fifo_space;
    memcpy(output + output_len, data, wrote);
    output_len += wrote; fifo_space -= wrote;
    return wrote;
}
/* RX remains in the real callback and must still be serviced before TX. */
static uint32_t ring_buf_put_claim(struct ring_buf *r, uint8_t **b, uint32_t n) {
    (void)n; *b = r->data; return 1;
}
static int uart_fifo_read(const struct device *d, uint8_t *b, unsigned n) {
    (void)d; (void)n;
    if (!rx_ready) return 0;
    *b = 42; rx_ready = false; return 1;
}
static void ring_buf_put_finish(struct ring_buf *r, uint32_t n) { r->len += n; }
static void zmk_rpc_rx_notify(void) { rx_notifies++; }
"""


MAIN = r"""
static void reset(unsigned head) {
    tx = (struct ring_buf){.size = 16, .head = head};
    rx = (struct ring_buf){.size = 16};
    fifo_calls = callback_calls = enables = disables = rx_notifies = 0;
    output_len = 0; rx_ready = empty_claim = inject_producer = false;
    tx_enabled = true;
}
static void callback(void) {
    fifo_calls = callback_calls = 0;
    serial_cb(uart_dev, NULL);
    assert(fifo_calls <= 1 && callback_calls <= 1);
}
static void finish(void) {
    for (int i = 0; tx.len && i < 16; i++) {
        fifo_space = 16;
        callback();
    }
    assert(tx.len == 0 && !tx_enabled);
}
int main(void) {
    /* A full CDC FIFO used to spin inside the shared USB workqueue. */
    reset(0); enqueue("abcdef"); fifo_space = 1; rx_ready = true;
    callback();
    assert(tx.len == 5 && output_len == 1 && tx_enabled);
    assert(rx_notifies == 1 && rx.len == 1);
    finish();
    assert(output_len == 6 && memcmp(output, "abcdef", 6) == 0);

    /* A stale ready indication with zero progress must also return. */
    reset(0); enqueue("zero"); fifo_space = 0; callback();
    assert(tx.len == 4 && output_len == 0 && tx_enabled);
    finish();
    assert(output_len == 4 && memcmp(output, "zero", 4) == 0);

    /* Partial writes and a wrapping queue preserve order without loss/duplication. */
    reset(14); enqueue("abcdefg"); fifo_space = 1;
    callback();
    assert(tx.len == 6 && output_len == 1 && tx_enabled);
    finish();
    assert(output_len == 7 && memcmp(output, "abcdefg", 7) == 0);

    /* Driver errors and empty claims must return and retain unsent bytes. */
    reset(0); enqueue("error"); fifo_space = -1;
    callback();
    assert(tx.len == 5 && output_len == 0 && tx_enabled);
    finish();
    assert(memcmp(output, "error", 5) == 0);
    reset(0); enqueue("claim"); empty_claim = true; fifo_space = 16;
    callback();
    assert(tx.len == 5 && tx_enabled);
    empty_claim = false; finish();
    assert(memcmp(output, "claim", 5) == 0);

    /* Drain/no-data must stop TX callbacks; producers can wake it again. */
    reset(0); fifo_space = 16; callback();
    assert(!tx_enabled && disables == 1 && enables == 0);
    enqueue("later"); uart_irq_tx_enable(uart_dev); finish();
    assert(memcmp(output, "later", 5) == 0);

    /* A put racing the final empty check must not lose the producer's wakeup. */
    reset(0); inject_producer = true; fifo_space = 16; callback();
    assert(tx.len == 3 && tx_enabled);
    finish();
    assert(output_len == 3 && memcmp(output, "new", 3) == 0);
    return 0;
}
"""


source = Path(sys.argv[1]).read_text(encoding="utf-8")
patched = prepare(source)
with tempfile.TemporaryDirectory() as tmp:
    for label, contents in [("original", source), ("patched", patched)]:
        cfile = Path(tmp) / f"{label}.c"
        binary = Path(tmp) / label
        cfile.write_text(PROBE + function(contents, "static void serial_cb(") + MAIN,
                         encoding="utf-8")
        subprocess.run([os.environ.get("CC", "cc"), "-std=c11", "-Wall", "-Wextra",
                        "-Werror=implicit-function-declaration", "-Wno-unused-parameter",
                        str(cfile), "-o", str(binary)], check=True)
        result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=5)
        if label == "original":
            assert result.returncode == 77, result.stderr
            print("original: full-FIFO spin reproduced")
        else:
            assert result.returncode == 0, result.stderr
            print("patched: full/partial/error/wrap/idle/producer-race checks passed")
try:
    prepare(patched)
except ValueError:
    pass
else:
    raise AssertionError("double patch accepted")
