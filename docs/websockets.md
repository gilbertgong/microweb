# WebSocket routes

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
- `ws.send(str_or_bytes)`: send one complete, unfragmented text or binary message. Bytes-like objects
  are accepted. Oversized messages raise `ValueError`; closed connections or stalled sends raise `OSError`.
- `ws.receive()`: wait for one complete message, returning `str` or `bytes`. After buffered messages
  have been delivered, closure returns `None`. Empty text and empty binary messages remain distinct.
- `for message in ws`: iterate until closure. Fragment reassembly and control frames are internal.
- `ws.closed`, `ws.close_code`, `ws.close_reason`: connection state. Unexpected I/O loss uses code 1006
  locally; that reserved code is never sent on the wire. An empty peer close uses local code 1005.
- `ws.close(code=1000, reason='', timeout=1)`: perform a bounded closing handshake and release the
  socket. Close reasons must fit 123 UTF-8 bytes; invalid codes or oversized reasons raise `ValueError`.
- `ws.ping(payload=b'')`: optional manual ping, with at most 125 payload bytes. Applications normally
  rely on automatic keepalive instead. Only automatic heartbeat pings are tracked for timeout detection.

Sends are serialized across threads. Only one application receiver may wait at a time. Application
code should stop its connection-specific work when the connection closes. The host closes connections
when handlers return, stop iterating or raise; handler errors use close code 1011.

## Automatic protocol handling

```python
@app.websocket('/events', max_bytes=1048576, max_queue=16,
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
- `max_queue`: maximum number of completed messages awaiting application consumption; default 16.
  A full queue closes the connection with 1013 rather than buffering indefinitely or blocking control
  frame handling. Applications that need larger bursts can increase it explicitly. Queue storage is
  bounded by the message count and message limit, plus the message currently being assembled.
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

With the default `same_origin=True`, a supplied `Origin` must match `http://` plus the incoming Host
header. Requests without Origin are allowed for non-browser clients. This follows microweb's plain-HTTP
hosting model; TLS termination/proxy deployments must account for their external origin. Explicit
`same_origin=False` disables this check for an app. Origin checks are not authentication.

Import, factory construction and route registration start no threads or services. The reader thread
starts only after an actual upgrade. Shutdown closes WebSockets before draining requests and stopping
components. Idle receives and blocked sends are interrupted; arbitrary application code that ignores
closure cannot be forcibly canceled by the framework. Independently launched jobs remain owned by the app.

Supported: protocol version 13, masked client frames, text/binary messages, bounded fragmentation,
UTF-8 and control-frame validation, ping/pong and bounded closing handshakes. Compression/extensions
and subprotocol negotiation are not implemented or advertised. Outgoing messages are not fragmented.
This is a small local-server transport, not a claim of exhaustive protocol conformance certification.
