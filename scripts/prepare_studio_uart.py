"""Bound each UART TX callback so a full CDC FIFO cannot block its workqueue."""
from pathlib import Path
import sys

ORIGINAL = """    if (uart_irq_tx_ready(uart_dev)) {
        struct ring_buf *tx_buf = zmk_rpc_get_tx_buf();
        uint32_t len;
        while ((len = ring_buf_size_get(tx_buf)) > 0) {
            uint8_t *buf;
            uint32_t claim_len = ring_buf_get_claim(tx_buf, &buf, tx_buf->size);

            if (claim_len == 0) {
                continue;
            }

            int sent = uart_fifo_fill(uart_dev, buf, claim_len);

            ring_buf_get_finish(tx_buf, MAX(sent, 0));
        }
    }"""

REPLACEMENT = """    if (uart_irq_tx_ready(uart_dev)) {
        /* CDC callbacks and FIFO draining share a workqueue. Yield after one
         * claim, including a zero/partial write, so the FIFO can drain. Disable
         * first: a producer that adds data later can safely re-enable TX. */
        uart_irq_tx_disable(uart_dev);
        struct ring_buf *tx_buf = zmk_rpc_get_tx_buf();
        uint8_t *buf;
        uint32_t claim_len = ring_buf_get_claim(tx_buf, &buf, tx_buf->size);
        if (claim_len > 0) {
            int sent = uart_fifo_fill(uart_dev, buf, claim_len);
            ring_buf_get_finish(tx_buf, MAX(sent, 0));
        }
        /* Unsent bytes remain queued for a later ready callback. An empty
         * queue leaves TX disabled instead of generating idle callbacks. */
        if (ring_buf_size_get(tx_buf) > 0) {
            uart_irq_tx_enable(uart_dev);
        }
    }"""


def prepare(source):
    if source.count(ORIGINAL) != 1:
        raise ValueError("unexpected Studio UART TX callback; review upstream changes")
    return source.replace(ORIGINAL, REPLACEMENT, 1)


if __name__ == "__main__":
    original, output = map(Path, sys.argv[1:3])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(prepare(original.read_text(encoding="utf-8")), encoding="utf-8")
