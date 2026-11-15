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

from microweb import App, Component, WebSocket, _Server, _ws_unmask


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
                   {"ping_interval": 0}, {"ping_timeout": -1}, {"max_queue": 0},
                   {"max_queue_bytes": 0}, {"max_queue_bytes": True},
                   {"origins": "https://example.test"}, {"origins": ["https://example.test/path"]}):
            with self.assertRaises(ValueError):
                self.app.websocket("/bad", **kw)
        with self.assertRaises(ValueError):
            self.app.websocket("/ws")(lambda ws: None)

    def test_explicit_https_origin_works_with_backend_host_and_preserves_http_policy(self):
        child = App()
        child.websocket("/ws", origins=["https://talklink.pro"])(lambda ws: None)
        child.post("/command")(lambda req: {"ok": True})
        self.app.mount("/child", child)
        values = {**headers("127.0.0.1:8765"), "Origin": "https://talklink.pro"}
        self.assertEqual(self.app.handle("GET", "/child/ws", headers=values)[0], 101)
        for origin in ("http://talklink.pro", "https://other.test", "https://talklink.pro:8443", "null"):
            with self.subTest(origin=origin):
                self.assertEqual(self.app.handle("GET", "/child/ws", headers={**values, "Origin": origin})[0], 403)
        values.pop("Origin")
        values.update({"X-Forwarded-Proto": "https", "X-Forwarded-Host": "talklink.pro"})
        self.assertEqual(self.app.handle("GET", "/child/ws", headers=values)[0], 403)
        self.assertEqual(self.app.handle("POST", "/child/command", headers={**headers(), "Origin": "https://talklink.pro"})[0], 403)

    def test_explicit_origin_policy_covers_absent_origin_and_does_not_trust_forwarded_headers(self):
        self.app.websocket("/allowed", origins=["https://example.test", None])(lambda ws: None)
        values = headers(); values.pop("Origin")
        self.assertEqual(self.app.handle("GET", "/allowed", headers=values)[0], 101)
        spoofed = {**headers(), "Origin": "https://elsewhere.test", "X-Forwarded-Host": "example.test", "X-Forwarded-Proto": "https"}
        self.assertEqual(self.app.handle("GET", "/allowed", headers=spoofed)[0], 403)
        self.app.websocket("/none", origins=[])(lambda ws: None)
        self.assertEqual(self.app.handle("GET", "/none", headers=values)[0], 403)


class ReceiveCopyTests(unittest.TestCase):
    def test_complete_read_reuses_socket_bytes(self):
        payload = bytes(range(251)) * 3
        class Socket:
            def recv(self, size):
                assert size == len(payload)
                return payload
        ws = WebSocket.__new__(WebSocket)
        ws._buffer, ws.timeout, ws._sock = bytearray(), 1, Socket()
        ws._wait = lambda **kwargs: None
        self.assertIs(ws._read_exact(len(payload)), payload)
        self.assertEqual(ws._buffer, b"")

    def test_partial_and_buffered_reads_preserve_leftovers(self):
        class Socket:
            def __init__(self): self.chunks = iter([b"ab", b"cde"])
            def recv(self, size): return next(self.chunks)
        ws = WebSocket.__new__(WebSocket)
        ws._buffer, ws.timeout, ws._sock = bytearray(), 1, Socket()
        ws._wait = lambda **kwargs: None
        self.assertEqual(ws._read_exact(5), b"abcde")
        ws._buffer.extend(b"headerpayload")
        self.assertEqual(ws._read_exact(6), b"header")
        self.assertEqual(ws._buffer, b"payload")
        self.assertEqual(ws._read_exact(0), b"")
        self.assertEqual(ws._read_exact(7), b"payload")
        ws._buffer.extend(b"still resizable")


class TransportTests(unittest.TestCase):
    def pair(self, **kw):
        server, client = socket.socketpair()
        client.settimeout(3)
        ws = WebSocket(server, None, **kw)
        self.addCleanup(client.close)
        self.addCleanup(ws._abort)
        return ws, client

    def test_unfragmented_receive_reuses_unmasked_payload(self):
        for size in (1, 521, 1545, 65536):
            observed = []
            def unmask(payload, mask):
                result = _ws_unmask(payload, mask)
                observed.append(result)
                return result
            with patch("microweb._ws_unmask", side_effect=unmask):
                ws, client = self.pair(ping_interval=None)
                payload = b"x" * size
                worker = threading.Thread(target=client.sendall, args=(frame(2, payload),))
                worker.start()
                message = ws.receive()
                worker.join(3)
                self.assertFalse(worker.is_alive())
                self.assertEqual(message, payload)
                self.assertIs(message, observed[0])

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

    def test_bulk_unmask_matches_reference_for_empty_odd_and_pcm_sizes(self):
        for size in (0, 1, 3, 4, 5, 125, 126, 512, 640, 1024, 1536, 3072, 65536):
            data = bytes(i % 256 for i in range(size))
            for mask in (b"\0\0\0\0", b"abcd", b"\xff\x80\x01\xfe"):
                self.assertEqual(_ws_unmask(data, mask), bytes(v ^ mask[i % 4] for i, v in enumerate(data)))

    def test_multipart_send_is_one_final_binary_frame(self):
        ws, client = self.pair()
        header, payload = struct.pack("!BII", 1, 42, 7), bytearray(b"\x12\x34" * 320)
        view = memoryview(payload)
        self.addCleanup(view.release)
        ws.send((header, view))
        first, second = exact(client, 2)
        self.assertEqual(first, 0x82)  # FIN=1, binary; not two fragmented frames.
        self.assertEqual(second, 126)
        length = struct.unpack("!H", exact(client, 2))[0]
        self.assertEqual(length, len(header) + len(payload))
        self.assertEqual(exact(client, length), header + payload)

    def test_multipart_writes_reuse_original_payload_across_recipients(self):
        backing = bytearray(b"__audio payload__")
        payload = memoryview(backing)[2:-2]
        self.addCleanup(payload.release)
        header = b"header"
        for _ in range(2):
            ws, client = self.pair()
            real, objects = ws._sock, []
            class ObservedSocket:
                def __init__(self, transport, records):
                    self.transport, self.records = transport, records
                def __getattr__(self, name): return getattr(self.transport, name)
                def send(self, data):
                    self.records.append(data.obj)
                    return self.transport.send(data)
            ws._sock = ObservedSocket(real, objects)
            ws.send((header, payload))
            self.assertEqual(read_frame(client), (2, header + bytes(payload)))
            self.assertTrue(any(obj is backing for obj in objects))
            self.assertTrue(any(obj is header for obj in objects))

    def test_multipart_handles_partial_socket_writes(self):
        ws, client = self.pair()
        real = ws._sock
        class PartialSocket:
            def __getattr__(self, name): return getattr(real, name)
            def send(self, data): return real.send(data[:3])
        ws._sock = PartialSocket()
        ws.send([b"header", memoryview(b"payload"), bytearray(b"tail")])
        self.assertEqual(read_frame(client), (2, b"headerpayloadtail"))

    def test_multipart_extended_lengths_and_empty_parts(self):
        for size in (0, 125, 126, 65535, 65536):
            ws, client = self.pair()
            payload = b"x" * size
            errors = []
            def send():
                try: ws.send([b"", payload[:size // 2], memoryview(payload)[size // 2:], b""])
                except Exception as error: errors.append(error)
            worker = threading.Thread(target=send)
            worker.start()
            self.assertEqual(read_frame(client), (2, payload))
            worker.join(3)
            self.assertFalse(worker.is_alive())
            self.assertEqual(errors, [])
        ws, client = self.pair()
        ws.send(())
        self.assertEqual(read_frame(client), (2, b""))

    def test_multipart_validation_happens_before_any_bytes_are_sent(self):
        ws, client = self.pair(max_bytes=8)
        for data, error in [((b"ok", "text"), TypeError), ((b"12345", b"6789"), ValueError),
                            ([b""] * 257, ValueError), ((memoryview(b"abcdef")[::2],), TypeError),
                            (iter([b"payload"]), TypeError)]:
            with self.subTest(data=type(data).__name__):
                with self.assertRaises(error): ws.send(data)
        client.settimeout(0.05)
        with self.assertRaises(socket.timeout): client.recv(1)
        ws.send((b"fine", b"good"))
        self.assertEqual(read_frame(client), (2, b"finegood"))

    def test_concurrent_multipart_sends_cannot_interleave_messages(self):
        ws, client = self.pair()
        errors = []
        def send(prefix):
            try:
                for _ in range(10): ws.send((prefix, b"payload", prefix))
            except Exception as error: errors.append(error)
        workers = [threading.Thread(target=send, args=(prefix,)) for prefix in (b"A", b"B")]
        for worker in workers: worker.start()
        messages = [read_frame(client) for _ in range(20)]
        for worker in workers:
            worker.join(3)
            self.assertFalse(worker.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(messages.count((2, b"ApayloadA")), 10)
        self.assertEqual(messages.count((2, b"BpayloadB")), 10)

    def test_recv_preserves_empty_messages_and_raises_after_buffered_messages(self):
        ws, client = self.pair()
        client.sendall(frame(1, b"") + frame(2, b"") + frame(8, struct.pack("!H", 1000)))
        self.assertEqual(ws.recv(), "")
        self.assertEqual(ws.recv(), b"")
        with self.assertRaisesRegex(ConnectionError, "WebSocket closed"): ws.recv()
        self.assertIsNone(ws.receive())

    def test_multipart_failure_after_header_closes_connection(self):
        ws, client = self.pair()
        real = ws._sock
        class FailingSocket:
            calls = 0
            def __getattr__(self, name): return getattr(real, name)
            def send(self, data):
                self.calls += 1
                if self.calls > 1: raise ConnectionResetError("fixture lost peer")
                return real.send(data)
        ws._sock = FailingSocket()
        with self.assertRaises(ConnectionResetError): ws.send((b"header", b"payload"))
        self.assertTrue(ws.closed)

    def test_partial_payload_failure_releases_exported_buffer_views(self):
        ws, client = self.pair()
        real, payload = ws._sock, bytearray(b"audio")
        class FailingPartialSocket:
            calls = 0
            def __getattr__(self, name): return getattr(real, name)
            def send(self, data):
                self.calls += 1
                if self.calls > 2: raise ConnectionResetError("fixture partial payload failure")
                return real.send(data[:1] if self.calls == 2 else data)
        ws._sock = FailingPartialSocket()
        saved_error = None
        try:
            ws.send((payload,))
        except ConnectionResetError as error:
            saved_error = error
        self.assertIsNotNone(saved_error)
        # A retained exception traceback must not leave our internal memoryviews
        # pinning mutable input after send has returned/raised.
        payload.extend(b" resized")
        self.assertTrue(ws.closed)

    def test_byte_queue_defaults_to_four_max_messages(self):
        ws, client = self.pair(max_bytes=2)
        client.sendall(frame(2, b"ab") * 5)
        self.assertEqual(read_frame(client), (8, struct.pack("!H", 1013)))
        self.assertEqual([ws.receive() for _ in range(4)], [b"ab"] * 4)
        self.assertIsNone(ws.receive())

    def test_byte_queue_counts_utf8_not_characters(self):
        ws, client = self.pair(max_bytes=16, max_queue_bytes=3)
        client.sendall(frame(1, "é".encode()) * 2)
        self.assertEqual(read_frame(client), (8, struct.pack("!H", 1013)))
        self.assertEqual(ws.receive(), "é")
        self.assertIsNone(ws.receive())

    def test_byte_budget_is_released_when_messages_are_consumed(self):
        ws, client = self.pair(max_bytes=16, max_queue_bytes=6)
        client.sendall(frame(2, b"abc") * 2 + frame(9, b"barrier"))
        self.assertEqual(read_frame(client), (10, b"barrier"))
        self.assertEqual(ws.receive(), b"abc")
        client.sendall(frame(2, b"xyz") + frame(9, b"barrier"))
        self.assertEqual(read_frame(client), (10, b"barrier"))
        self.assertEqual([ws.receive(), ws.receive()], [b"abc", b"xyz"])
        self.assertFalse(ws.closed)

    def test_fragmented_messages_count_completed_wire_bytes(self):
        ws, client = self.pair(max_bytes=16, max_queue_bytes=3)
        client.sendall(frame(1, b"\xc3", fin=False) + frame(0, b"\xa9") +
                       frame(2, b"x") + frame(9, b"barrier"))
        self.assertEqual(read_frame(client), (10, b"barrier"))
        self.assertEqual([ws.receive(), ws.receive()], ["é", b"x"])

    def test_empty_messages_are_still_count_bounded(self):
        ws, client = self.pair(max_queue=4, max_queue_bytes=100)
        client.sendall(frame(2, b"") * 5)
        self.assertEqual(read_frame(client), (8, struct.pack("!H", 1013)))
        self.assertEqual([ws.receive() for _ in range(4)], [b""] * 4)
        self.assertIsNone(ws.receive())

    def test_paced_pcm_tolerates_consumer_pause_without_loss(self):
        # 16 kHz mono L16, 20 ms (640 bytes) per message. A 400 ms consumer
        # pause exceeds the old 16-message limit but fits the explicit 32 KiB budget.
        ws, client = self.pair(max_bytes=1024, max_queue_bytes=32768)
        resume, paused, received, errors = threading.Event(), threading.Event(), [], []
        packets = [i.to_bytes(2, "big") * 320 for i in range(40)]
        def consumer():
            try:
                for i in range(len(packets)):
                    if i == 5:
                        paused.set()
                        if not resume.wait(3): raise AssertionError("consumer was not resumed")
                    received.append(ws.receive())
            except Exception as error: errors.append(error)
        worker = threading.Thread(target=consumer)
        worker.start()
        try:
            for i, packet in enumerate(packets):
                client.sendall(frame(2, packet))
                if i == 4:
                    self.assertTrue(paused.wait(2))
                if i == 24:
                    client.sendall(frame(9, b"pcm heartbeat"))
                    self.assertEqual(read_frame(client), (10, b"pcm heartbeat"))
                    self.assertFalse(ws.closed)
                    resume.set()
                time.sleep(0.02)
            worker.join(3)
            self.assertFalse(worker.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(received, packets)
        finally:
            resume.set(); ws._abort(); worker.join(3)

    def test_sustained_pcm_backlog_closes_without_exceeding_byte_budget(self):
        ws, client = self.pair(max_bytes=1024, max_queue_bytes=2560)
        packet = b"\x12\x34" * 320
        for _ in range(5):
            client.sendall(frame(2, packet))
            time.sleep(0.02)
        self.assertEqual(read_frame(client), (8, struct.pack("!H", 1013)))
        self.assertEqual([ws.receive() for _ in range(4)], [packet] * 4)
        self.assertIsNone(ws.receive())


class HostTests(unittest.TestCase):
    def test_upgraded_tcp_socket_disables_nagle(self):
        app = App()
        @app.websocket("/ws")
        def handler(ws):
            ws.send(str(ws._sock.getsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY)))
        with serving(app) as server:
            with connect(server) as client:
                self.assertEqual(read_frame(client), (1, b"1"))
                self.assertEqual(read_frame(client)[0], 8)
                client.sendall(frame(8, struct.pack("!H", 1000)))

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
