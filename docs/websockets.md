# WebSocket routes

This is an independent, intentionally cut-down WebSocket implementation, **not a fully RFC 6455
compliant implementation** or a general replacement for the third-party `websockets` package. It is not
suitable for every WebSocket use case. Local dashboards and low-latency PCM relays motivated its scope;
the protocol limits below and PCM examples help assess whether it fits another application.

WebSockets are optional to use and need no additional packages. HTTP routes and upgraded connections
share one server and port; ordinary HTTP apps keep working as before.

```python
from microweb import App

app = App()

@app.websocket('/events')
def events(ws):
    for message in ws:
        ws.send(message)  # str stays text; bytes stay binary

app.run('127.0.0.1', 8765)
```

Run `python examples/websocket_echo.py` for a browser example, including a 500 KB message and a mounted
`/demo/events` endpoint. It uses only the standard library.

## Connection API

- `ws.req`: the opening request, including query parameters and mount-aware `req.url()`.
- `ws.send(data)`: send one complete, unfragmented text or binary message. Accepts a string, a binary
  buffer (`bytes`, `bytearray`, contiguous `memoryview`), or a list/tuple of up to 256 binary buffers.
  A buffer sequence is one binary message in one frame, not a series of messages or fragments.
  Every part and the combined size are checked before sending any bytes. Oversized messages raise
  `ValueError`; unsupported types/non-contiguous views raise `TypeError`; closed connections or
  stalled sends raise `OSError`.
- `ws.receive()`: wait for one complete message, returning `str` or `bytes`. After buffered messages
  have been delivered, closure returns `None`. Empty text and empty binary messages remain distinct.
- `ws.recv()`: the same message delivery, but raises `ConnectionError("WebSocket closed")` when
  `receive()` would return `None`. This convenience supports familiar blocking-client style; it doesn't
  implement the `websockets` package's exception hierarchy or optional recv arguments.
- `for message in ws`: iterate until closure. Fragment reassembly and control frames are internal.
- `ws.closed`, `ws.close_code`, `ws.close_reason`: connection state. Unexpected I/O loss uses code 1006
  locally; that reserved code is never sent on the wire. An empty peer close uses local code 1005.
- `ws.close(code=1000, reason='', timeout=1)`: perform a bounded closing handshake and release the
  socket. Close reasons must fit 123 UTF-8 bytes; invalid codes or oversized reasons raise `ValueError`.
- `ws.ping(payload=b'')`: optional manual ping, with at most 125 payload bytes. Applications normally
  rely on automatic keepalive instead. Only automatic heartbeat pings are tracked for timeout detection.

Complete single-frame binary messages reuse their unmasked payload as the queued `bytes`
object. Fragmented messages are assembled before delivery. This avoids extra message-assembly
copies in the common path; receive still performs WebSocket unmasking and socket/buffer work.

Sends are serialized across threads. Only one application receiver may wait at a time. Application
code should stop its connection-specific work when the connection closes. The host closes connections
when handlers return, stop iterating or raise; handler errors use close code 1011.

## Automatic protocol handling

```python
@app.websocket('/events', max_bytes=1048576, max_queue_bytes=None, max_queue=256,
               timeout=10, ping_interval=20, ping_timeout=20)
def events(ws):
    for message in ws:
        ...
```

Each connection has one protocol reader thread in addition to its existing application request thread.
The reader assembles incoming fragments, replies to pings and processes pong/close frames even while
the application handler is busy. Completed messages enter a bounded queue.

- `max_bytes`: maximum incoming **whole-message** size, including all fragments; also limits outgoing
  messages. Default 1 MiB. Incoming excess closes with 1009 before the excess payload is allocated.
- `max_queue_bytes`: maximum sum of queued message payload bytes. Default `None` derives a budget of
  `4 * max_bytes` (4 MiB with the default message limit). Text counts UTF-8 bytes, not characters;
  consuming a message releases its byte budget. This bounds queued payload, not total process memory:
  Python objects, decoding/reassembly buffers and the current message also use memory.
- `max_queue`: separate maximum number of completed messages awaiting application consumption;
  default 256. This caps object overhead even for empty messages. Either limit closes the connection
  with 1013 rather than buffering indefinitely or blocking control-frame handling. Queued messages
  remain readable before `receive()` returns `None`; the overflowing message isn't delivered.
- `timeout`: maximum wait for a partial-frame read or send operation to progress to completion;
  default 10 seconds. Idle receives are allowed indefinitely. Bytes already received are retained
  across polling waits; a timed-out partial frame closes instead of restarting at the wrong byte.
- `ping_interval`: send a heartbeat ping every 20 seconds by default. `None` disables automatic
  heartbeat entirely. An outstanding timed heartbeat must complete before the next one is sent.
- `ping_timeout`: close with 1011 if a matching pong is not received within 20 seconds of a heartbeat
  ping. `None` keeps periodic pings but disables pong timeout enforcement. Long stalls can trigger
  a timeout; adjust this for the application's environment.

Keepalive is checked by the reader; it does not need another timer thread. Timing checks are periodic,
not real-time guarantees. Browsers handle protocol pongs without application JavaScript. Browser
reconnection and application-level retry remain the application's responsibility; microweb does not
replay messages or jobs. Applications may need their own browser-side heartbeat for prompt detection
when the network disappears and no server close frame can reach the browser.

## Mounts, origin policy and lifecycle

`App.mount` and `Shell.add` preserve WebSocket routing and `ws.req.root_path`. The browser example
constructs its endpoint relative to the mounted page. HTTP and WebSocket handlers may share a path:
an upgrade selects the WebSocket handler; an ordinary HTTP request selects the HTTP handler.

With no route override and the default `same_origin=True`, a supplied `Origin` must match `https://`
plus the incoming Host header. HTTP is also accepted when Host names `localhost`, `127.0.0.1` or
`[::1]`. Scheme, host spelling and explicit port must match exactly. Malformed Hosts are rejected.
This same policy applies to HTTP mutation requests. Requests without Origin remain allowed.
HTTPS behind a proxy works by default when the public Host is preserved. If the proxy rewrites Host,
or a route needs a different set of origins, configure it explicitly:

```python
@app.websocket('/events', origins=['https://talklink.pro'])
def events(ws):
    ...
```

`origins` replaces only this WebSocket route's default origin policy with an exact allowlist. Origins
include scheme and any explicit port, without a path; `https://talklink.pro` doesn't allow
`http://talklink.pro` or `https://talklink.pro:8443`. Host may be rewritten by the proxy; the explicit
allowlist is matched against Origin directly. No forwarded headers are trusted automatically.
Include `None` in the list to permit missing Origin headers; an empty list refuses all upgrades.
Ordinary HTTP mutation checks stay unchanged. Explicit `same_origin=False` disables the default app
check but doesn't bypass a route's explicit allowlist. Origin checks are not authentication.

Import, factory construction and route registration start no threads or services. The reader thread
starts only after an actual upgrade. Shutdown closes WebSockets before draining requests and stopping
components. Idle receives and blocked sends are interrupted; arbitrary application code that ignores
closure cannot be forcibly canceled by the framework. Independently launched jobs remain owned by the app.

Supported: protocol version 13, masked client frames, text/binary messages, bounded fragmentation,
UTF-8 and control-frame validation, ping/pong and bounded closing handshakes. Compression/extensions
and subprotocol negotiation are not implemented or advertised. Outgoing messages are not fragmented.
These supported features do not imply full RFC compliance. Applications needing broader protocol or
deployment support should evaluate a full-featured WebSocket implementation.

## Streaming PCM

TCP sockets use `TCP_NODELAY` after upgrade to avoid Nagle buffering of small outgoing messages.
Client payload unmasking uses bulk integer XOR rather than a Python loop over individual bytes.

For continuous audio, size limits should reflect the audio format and tolerable consumer backlog.
The maximum message size and the queued-byte budget are independently configurable:

```python
@app.websocket('/audio', max_bytes=4096, max_queue_bytes=32768)
def audio(ws):
    for packet in ws:
        ...
```

For 16 kHz mono 16-bit PCM, a 20 ms packet is 640 bytes; a 32 KiB queue holds about 1.024 seconds of
audio. At 48 kHz mono, the same byte budget holds about 341 ms. This is an illustrative configuration,
not a format negotiation mechanism; channels, sample rate, endianness and packet format belong to the
application. A large memory budget can also mean undesirable latency. Configure it deliberately.
The transport doesn't silently drop audio on overflow or interpret an audio format. Tests exercise
a 400 ms consumer pause during paced 20 ms PCM traffic, and bounded disconnection for sustained backlog.

## Sending a header and shared payload

```python
import struct

header = struct.pack('!BII', 1, stream_id, packet_id)
payload = memoryview(packet)[9:]
for target in destinations:
    target.send((header, payload))
```

The transport calculates one combined frame length and writes its frame header and each application
buffer separately, without joining them or copying the binary payload into another Python buffer.
The same payload memoryview can be reused across recipients. These are synchronous writes: callers
must keep backing buffers unchanged until send returns. Internally created views are released on
success or failure; caller-owned views remain usable. The OS may still copy data into network buffers.

The send lock and one send deadline cover the entire message, so concurrent data or control sends
cannot split its parts. A transport failure after writing part of a frame closes the connection.
This may use several socket writes; it doesn't imply a single system call or zero-copy networking.

This produces the same received binary message as `websockets.send((header, payload))`, but differs
in wire framing: that package treats iterable items as separate fragments. Microweb sends one final
binary frame. Arbitrary generators and sequences of text fragments are not supported.
