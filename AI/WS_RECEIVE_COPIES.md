# WebSocket receive-copy findings

## Change

A complete single-frame binary message can pass from the socket read through unmasking
into the incoming queue with fewer intermediate copies. Two small changes target that path:

- `_read_exact()` returns a complete socket read directly when no buffered prefix exists.
  Partial/buffered reads still accumulate as needed, but snapshot through a memoryview rather
  than first creating a bytearray slice. The view is released before resizing the buffer.
- `_next_message()` reuses an unmasked payload for a complete single-frame message. Binary
  delivery keeps that bytes object; text still decodes and validates UTF-8. Fragmented messages
  retain their existing assembly path, including interleaved control-frame handling.

On the complete-read/unfragmented binary path, this can avoid five full-payload copies:
accumulation, bytearray slicing, conversion to bytes, fragment accumulation and final conversion
to bytes. A partial read can still require accumulation. Initial HTTP-buffered data is preserved.
The existing bulk-XOR unmasking algorithm, protocol limits, queue accounting and threading model
are unchanged. These optimizations do not claim end-to-end zero-copy socket/TLS operation.

## Correctness evidence

Three added regressions check direct socket-byte identity, partial/buffered read leftovers and
buffer resizing after snapshot, and identity of the unmasked binary payload through receive
at 1/521/1545/65536-byte sizes. Existing wire-level tests exercise fragmentation, invalid UTF-8,
message/queue limits, heartbeat, close, multipart sends, HTTP upgrade leftovers and host shutdown.

All 115 tests (including 48 WebSocket tests) pass on Python 3.12.10 and Python 3.14.5
(MSYS2/UCRT64) on Windows with site packages disabled. These tests use isolated socket pairs, ephemeral loopback servers and disposable files/
repositories, not running application instances. No browser, TLS or deployed-service benchmark.

## Reproducing the parser benchmark

From this repository root, compare the candidate with the base revision:

```text
python -B scripts/benchmark_ws_receive.py --baseline 9da4a23
```

The benchmark uses synthetic complete masked frames and fake socket reads, retaining the real
frame parser and unmasking code. It excludes actual network I/O, TLS, waiting, message queues,
application handlers and fan-out. Three interleaved before/after repeats use 40,000 messages
after warmup; results report median process CPU microseconds per message.

One local Python 3.12.10 run in the PR checkout produced:

| WebSocket payload | Base | Candidate | Parser CPU reduction |
|---|---:|---:|---:|
| 521 bytes (16 kHz / 16 ms mono PCM16 plus 9-byte stream header) | 4.297 us | 3.125 us | 27.3% |
| 1545 bytes (48 kHz / 16 ms mono PCM16 plus 9-byte stream header) | 5.469 us | 4.297 us | 21.4% |

An earlier isolated run measured 36.4% and 21.4% respectively. The absolute differences are
small (roughly 1–1.5 us per packet), and the measurements vary with process-timer granularity,
scheduling, interpreter and hardware. They demonstrate reduced parser overhead, not a production
latency/throughput improvement or an allocation profiler's measurements. The identity regressions
are the direct evidence for eliminating the intended intermediate objects.
