"""Offline wire-level checks: real sockets, no third-party WebSocket client."""
import base64
import contextlib
import json
import socket
import struct
import threading
import time
import unittest
from unittest.mock import patch

from microweb import App, Component, WebSocket, _Server


def frame(opcode, payload=b"", fin=True, masked=True, length_kind=None):
    length = len(payload)
    prefix = bytes([(128 if fin else 0) | opcode])
    mask_bit = 128 if masked else 0
    if length_kind == 127 or length > 65535:
        prefix += bytes([mask_bit | 127]) + struct.pack("!Q", length)
    elif length_kind == 126 or length > 125:
        prefix += bytes([mask_bit | 126]) + struct.pack("!H", length)
    else:
        prefix += bytes([mask_bit | length])
    if masked:
        mask = b"abcd"
        return prefix + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    return prefix + payload


def exact(sock, n):
    result = b""
    while len(result) < n:
        chunk = sock.recv(n - len(result))
        if not chunk:
            raise EOFError
        result += chunk
    return result


def read_frame(sock):
    first, second = exact(sock, 2)
    if second & 128:
        raise AssertionError("server frames must not be masked")
    size = second & 127
    if size == 126:
        size = struct.unpack("!H", exact(sock, 2))[0]
    elif size == 127:
        size = struct.unpack("!Q", exact(sock, 8))[0]
    return first & 15, exact(sock, size)


def headers(host="localhost"):
    return {"Host": host, "Upgrade": "websocket", "Connection": "keep-alive, Upgrade",
            "Sec-WebSocket-Version": "13", "Sec-WebSocket-Key": "dGhlIHNhbXBsZSBub25jZQ==",
            "Origin": "http://" + host}


@contextlib.contextmanager
def serving(app):
    with _Server(("127.0.0.1", 0), app._handler_class()) as server:
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
        thread.start()
        try:
            yield server
        finally:
            server.shutdown()
            server.stop_websockets()
            server.drain_requests()
            thread.join(3)


def connect(server, path="/ws", extra=b""):
    sock = socket.create_connection(server.server_address, timeout=3)
    values = headers(f"127.0.0.1:{server.server_port}")
    request = f"GET {path} HTTP/1.1\r\n" + "".join(f"{k}: {v}\r\n" for k, v in values.items()) + "\r\n"
    sock.sendall(request.encode("ascii") + extra)
    response = b""
    while not response.endswith(b"\r\n\r\n"):
        response += exact(sock, 1)
    if not response.startswith(b"HTTP/1.1 101 "):
        sock.close()
        raise AssertionError(response)
    return sock


class HandshakeTests(unittest.TestCase):
    def setUp(self):
        self.app = App()
        self.app.websocket("/ws")(lambda ws: None)

    def test_handshake_and_extension_not_negotiated(self):
        values = {**headers(), "Sec-WebSocket-Extensions": "permessage-deflate"}
        status, result, body = self.app.handle("GET", "/ws", headers=values)
        self.assertEqual(status, 101)
        self.assertEqual(result["Sec-WebSocket-Accept"], "s3pPLMBiTxaQ9kYGzzhZRbK+xOo=")
        self.assertNotIn("Content-Length", result)
        self.assertNotIn("Sec-WebSocket-Extensions", result)
        self.assertEqual(body, b"")

    def test_reject_bad_handshake(self):
        for changes, expected in [({"Sec-WebSocket-Version": "12"}, 426),
                                  ({"Sec-WebSocket-Key": "bad"}, 400),
                                  ({"Sec-WebSocket-Key": base64.b64encode(b"short").decode()}, 400),
                                  ({"Connection": "keep-alive"}, 400),
                                  ({"Origin": "https://elsewhere.invalid"}, 403),
                                  ({"Content-Length": "2"}, 400),
                                  ({"Transfer-Encoding": "chunked"}, 400)]:
            with self.subTest(changes=changes):
                self.assertEqual(self.app.handle("GET", "/ws", headers={**headers(), **changes})[0], expected)
        self.assertEqual(self.app.handle("POST", "/ws", headers=headers())[0], 405)

    def test_mount_origin_policy_and_same_path_http(self):
        child = App(same_origin=False)
        child.websocket("/ws")(lambda ws: None)
        child.get("/ws")(lambda req: "HTTP still works")
        self.app.mount("/child", child)
        self.assertEqual(self.app.handle("GET", "/child/ws")[2], b"HTTP still works")
        self.assertEqual(self.app.handle("GET", "/child/ws", headers={**headers(), "Origin": "null"})[0], 101)

    def test_registration_validation(self):
        for kw in ({"max_bytes": 0}, {"max_bytes": True}, {"timeout": 0}, {"timeout": float("nan")},
                   {"ping_interval": 0}, {"ping_timeout": -1}, {"max_queue": 0}):
            with self.assertRaises(ValueError):
                self.app.websocket("/bad", **kw)
        with self.assertRaises(ValueError):
            self.app.websocket("/ws")(lambda ws: None)


class TransportTests(unittest.TestCase):
    def pair(self, **kw):
        server, client = socket.socketpair()
        client.settimeout(3)
        ws = WebSocket(server, None, **kw)
        self.addCleanup(client.close)
        self.addCleanup(ws._abort)
        return ws, client

    def test_text_binary_and_all_length_encodings(self):
        for payload in (b"", b"hello", b"x" * 126, b"x" * 65536):
            ws, client = self.pair()
            sender = threading.Thread(target=client.sendall, args=(frame(2, payload),))
            sender.start()
            self.assertEqual(ws.receive(), payload)
            sender.join(3)
            sender = threading.Thread(target=ws.send, args=(payload,))
            sender.start()
            self.assertEqual(read_frame(client), (2, payload))
            sender.join(3)
        ws, client = self.pair()
        client.sendall(frame(1, "café".encode()))
        self.assertEqual(ws.receive(), "café")
        ws.send("hi")
        self.assertEqual(read_frame(client), (1, b"hi"))

    def test_fragmented_utf8_with_interleaved_ping_and_pong(self):
        ws, client = self.pair()
        client.sendall(frame(1, b"caf\xc3", fin=False) + frame(9, b"check") +
                       frame(10, b"ignored") + frame(0, b"\xa9"))
        self.assertEqual(ws.receive(), "café")
        self.assertEqual(read_frame(client), (10, b"check"))

    def test_fragment_limit_applies_to_whole_message(self):
        ws, client = self.pair(max_bytes=5)
        client.sendall(frame(2, b"123", fin=False) + frame(0, b"456"))
        self.assertIsNone(ws.receive())
        self.assertEqual(read_frame(client), (8, struct.pack("!H", 1009)))

    def test_invalid_frames_and_close_payloads(self):
        cases = [(frame(1, b"x", masked=False), 1002),
                 (bytes([0xC1, 0x80]) + b"abcd", 1002),
                 (frame(3), 1002), (frame(0), 1002),
                 (frame(1, b"a", fin=False) + frame(2, b"b"), 1002),
                 (frame(9, b"x", fin=False), 1002), (frame(9, b"x" * 126), 1002),
                 (frame(1, b"x", length_kind=126), 1002),
                 (bytes([0x82, 0xFF]) + struct.pack("!Q", 1 << 63), 1002),
                 (frame(1, b"\xff"), 1007), (frame(8, b"x"), 1002),
                 (frame(8, struct.pack("!H", 1006)), 1002),
                 (frame(8, struct.pack("!H", 1000) + b"\xff"), 1007)]
        for data, code in cases:
            with self.subTest(data=data[:12]):
                ws, client = self.pair()
                client.sendall(data)
                self.assertIsNone(ws.receive())
                self.assertEqual(read_frame(client), (8, struct.pack("!H", code)))
                self.assertTrue(ws.closed)

    def test_size_limit_rejects_before_reading_payload(self):
        ws, client = self.pair(max_bytes=10)
        client.sendall(bytes([0x82, 0xFE]) + struct.pack("!H", 1000))
        self.assertIsNone(ws.receive())
        self.assertEqual(ws.close_code, 1009)

    def test_split_header_waits_and_idle_has_no_deadline(self):
        ws, client = self.pair(timeout=0.3)
        received = []
        receiver = threading.Thread(target=lambda: received.append(ws.receive()))
        receiver.start()
        time.sleep(0.4)
        wire = frame(1, b"hello")
        client.sendall(wire[:1])
        time.sleep(0.05)
        client.sendall(wire[1:])
        receiver.join(2)
        self.assertEqual(received, ["hello"])

    def test_partial_frame_timeout_closes_without_retry_desynchronization(self):
        ws, client = self.pair(timeout=0.05)
        client.sendall(b"\x81")
        self.assertIsNone(ws.receive())
        self.assertTrue(ws.closed)

    def test_close_echo_and_empty_close(self):
        for payload in (b"", struct.pack("!H", 1000) + b"done"):
            ws, client = self.pair()
            client.sendall(frame(8, payload))
            self.assertIsNone(ws.receive())
            self.assertEqual(read_frame(client), (8, payload))
            ws.close()

    def test_server_close_waits_for_peer_and_wakes_receiver(self):
        ws, client = self.pair()
        receiver = threading.Thread(target=ws.receive)
        receiver.start()
        closer = threading.Thread(target=lambda: ws.close(1000, "done"))
        closer.start()
        self.assertEqual(read_frame(client), (8, struct.pack("!H", 1000) + b"done"))
        client.sendall(frame(8, struct.pack("!H", 1000)))
        closer.join(2); receiver.join(2)
        self.assertFalse(closer.is_alive())
        self.assertFalse(receiver.is_alive())

    def test_send_validation_and_closed_send(self):
        ws, client = self.pair(max_bytes=10)
        for fn in (lambda: ws.send("x" * 11), lambda: ws.ping(b"x" * 126),
                   lambda: ws.close(1006), lambda: ws.close(reason="é" * 62)):
            with self.assertRaises(ValueError): fn()
        with self.assertRaises(TypeError): ws.send({})
        ws._abort()
        with self.assertRaises(ConnectionError): ws.send("x")

    def test_blocked_send_and_close_are_bounded(self):
        ws, client = self.pair(timeout=0.1)
        real = ws._sock
        class StalledSocket:
            def __getattr__(self, name): return getattr(real, name)
            def send(self, data): raise BlockingIOError("fixture backpressure")
        ws._sock = StalledSocket()
        with self.assertRaises(OSError): ws.send(b"hello")
        self.assertTrue(ws.closed)

    def test_close_does_not_wait_forever_for_send_lock(self):
        ws, client = self.pair()
        ws._send_lock.acquire()
        try:
            started = time.monotonic()
            ws.close(timeout=0.05)
            self.assertLess(time.monotonic() - started, 1)
            self.assertTrue(ws.closed)
        finally:
            ws._send_lock.release()

    def test_control_frames_are_automatic_without_application_receives(self):
        ws, client = self.pair()
        client.sendall(frame(9, b"automatic"))
        self.assertEqual(read_frame(client), (10, b"automatic"))
        self.assertFalse(ws.closed)

    def test_keepalive_requires_matching_pong(self):
        ws, client = self.pair(ping_interval=0.05, ping_timeout=0.1)
        opcode, token = read_frame(client)
        self.assertEqual(opcode, 9)
        client.sendall(frame(10, b"wrong"))
        self.assertEqual(read_frame(client), (8, struct.pack("!H", 1011)))
        self.assertIsNone(ws.receive())

    def test_matching_pong_keeps_connection_alive_without_application_receive(self):
        ws, client = self.pair(ping_interval=0.05, ping_timeout=0.3)
        for _ in range(3):
            opcode, token = read_frame(client)
            self.assertEqual(opcode, 9)
            client.sendall(frame(10, token))
        client.sendall(frame(1, b"still alive"))
        self.assertEqual(ws.receive(), "still alive")

    def test_keepalive_only_and_disabled_modes(self):
        ws, client = self.pair(ping_interval=0.05, ping_timeout=None)
        for _ in range(2):
            self.assertEqual(read_frame(client)[0], 9)
        self.assertFalse(ws.closed)
        ws2, client2 = self.pair(ping_interval=None, ping_timeout=0.01)
        client2.settimeout(0.3)
        with self.assertRaises(socket.timeout): client2.recv(1)
        self.assertFalse(ws2.closed)

    def test_incoming_queue_is_bounded(self):
        ws, client = self.pair(max_queue=1)
        client.sendall(frame(1, b"first") + frame(1, b"second"))
        self.assertEqual(read_frame(client), (8, struct.pack("!H", 1013)))
        self.assertEqual(ws.receive(), "first")
        self.assertIsNone(ws.receive())


class HostTests(unittest.TestCase):
    def test_mounted_echo_and_http_buffered_bytes(self):
        app, child = App(), App()
        @child.websocket("/echo")
        def echo(ws):
            for message in ws:
                ws.send(ws.req.url("/echo") + ":" + message)
        app.mount("/tool", child)
        with serving(app) as server:
            with connect(server, "/tool/echo", extra=frame(1, b"hello")) as client:
                self.assertEqual(read_frame(client), (1, b"/tool/echo:hello"))
                client.sendall(frame(8, struct.pack("!H", 1000)))
                self.assertEqual(read_frame(client)[0], 8)

    def test_reject_http10_and_duplicate_handshake_headers(self):
        app = App()
        app.websocket("/ws")(lambda ws: None)
        with serving(app) as server:
            values = headers(f"127.0.0.1:{server.server_port}")
            for version, extra in (("HTTP/1.0", ""), ("HTTP/1.1", "Sec-WebSocket-Key: invalid\r\n")):
                with socket.create_connection(server.server_address, timeout=3) as client:
                    request = f"GET /ws {version}\r\n" + "".join(f"{k}: {v}\r\n" for k, v in values.items()) + extra + "\r\n"
                    client.sendall(request.encode())
                    self.assertIn(b" 400 ", client.recv(4096))

    def test_handler_early_return_and_exception_cleanup(self):
        for fails in (False, True):
            app = App()
            @app.websocket("/ws")
            def handler(ws):
                if fails: raise RuntimeError("fixture failure")
                for message in ws: break
            with serving(app) as server:
                with self.assertLogs("microweb", level="ERROR") if fails else contextlib.nullcontext():
                    with connect(server, extra=frame(1, b"hello")) as client:
                        op, payload = read_frame(client)
                        self.assertEqual(op, 8)
                        self.assertEqual(struct.unpack("!H", payload[:2])[0], 1011 if fails else 1000)
                        client.sendall(frame(8, struct.pack("!H", 1000)))

    def test_run_shutdown_closes_idle_websocket_before_component_stop(self):
        app, stop, ready, entered = App(), threading.Event(), threading.Event(), threading.Event()
        stopped = []
        @app.websocket("/ws")
        def handler(ws):
            entered.set()
            for message in ws: pass
        app.components.append(Component("fixture", "Fixture", App(), stop=lambda: stopped.append(True)))
        servers = []
        def server_factory(*args):
            server = _Server(*args); servers.append(server); return server
        with patch("microweb._Server", side_effect=server_factory):
            runner = threading.Thread(target=app.run, args=("127.0.0.1", 0),
                                      kwargs={"stop_event": stop, "on_ready": ready.set})
            runner.start()
            try:
                self.assertTrue(ready.wait(3))
                with connect(servers[0]) as client:
                    self.assertTrue(entered.wait(3))
                    stop.set()
                    self.assertEqual(read_frame(client)[0], 8)
                    runner.join(3)
                    self.assertFalse(runner.is_alive())
                    self.assertEqual(stopped, [True])
            finally:
                stop.set()
                if servers: servers[0].stop_websockets()
                runner.join(3)


if __name__ == "__main__":
    unittest.main()
