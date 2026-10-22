import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from microweb import App, HTTPError, Response, Shell, Stream, _Server


class RoutingTests(unittest.TestCase):
    def setUp(self):
        self.app = App()

    def test_json_and_query(self):
        self.app.get("/q")(lambda req: req.query)
        status, headers, body = self.app.handle("GET", "/q?a=1&a=2")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {"a": "2"})
        self.assertEqual(headers["Content-Type"], "application/json")

    def test_json_body_and_custom_response(self):
        self.app.post("/p")(lambda req: Response(req.json(), 201, headers={"X-Test": "yes"}))
        status, headers, body = self.app.handle("POST", "/p", b'{"ok":true}')
        self.assertEqual((status, headers["X-Test"], json.loads(body)), (201, "yes", {"ok": True}))

    def test_invalid_body(self):
        self.app.post("/p")(lambda req: req.json())
        self.assertEqual(self.app.handle("POST", "/p")[0], 411)
        self.assertEqual(self.app.handle("POST", "/p", b"bad")[0], 400)
        self.assertEqual(self.app.handle("POST", "/p", b"{}", {"Content-Length": "-1"})[0], 400)
        self.assertEqual(self.app.handle("POST", "/p", b"{}", {"Transfer-Encoding": "chunked"})[0], 411)
        self.assertEqual(self.app.handle("POST", "/p", b"{}", {"Content-Length": "8"})[0], 400)

    def test_size_limit_override(self):
        app = App(max_body=1)
        app.post("/limit")(lambda req: req.json())
        app.post("/override")(lambda req: req.json(max_bytes=10))
        self.assertEqual(app.handle("POST", "/limit", b"{}")[0], 413)
        self.assertEqual(app.handle("POST", "/override", b"{}")[0], 200)

    def test_methods_head_and_errors(self):
        self.app.get("/")(lambda req: "hello")
        self.assertEqual(self.app.handle("HEAD", "/")[2], b"")
        self.assertEqual(self.app.handle("POST", "/")[0], 405)
        self.assertEqual(self.app.handle("GET", "/missing")[0], 404)
        def fail(req):
            raise HTTPError(409, "conflict", detail="test")
        self.app.get("/fail")(fail)
        self.assertEqual(json.loads(self.app.handle("GET", "/fail")[2])["detail"], "test")

    def test_handler_exception_is_private(self):
        def fail(req):
            raise RuntimeError("private details")
        self.app.get("/")(fail)
        with self.assertLogs("microweb", level="ERROR"):
            status, _, body = self.app.handle("GET", "/")
        self.assertEqual(status, 500)
        self.assertNotIn(b"private", body)

    def test_origin(self):
        self.app.post("/")(lambda req: {})
        headers = {"Origin": "http://evil.example", "Host": "localhost:8765"}
        self.assertEqual(self.app.handle("POST", "/", headers=headers)[0], 403)
        headers["Origin"] = "http://localhost:8765"
        self.assertEqual(self.app.handle("POST", "/", headers=headers)[0], 200)
        self.assertEqual(self.app.handle("POST", "/")[0], 200)

    def test_stream_and_legacy_responses(self):
        self.app.get("/s")(lambda req: Stream(iter(["hello", b" world"]), "text/plain"))
        self.assertEqual(self.app.handle("GET", "/s")[2], b"hello world")
        self.app.get("/none")(lambda req: None)
        self.app.get("/tuple")(lambda req: ({"created": True}, 201))
        self.assertEqual(self.app.handle("GET", "/none")[0], 204)
        self.assertEqual(self.app.handle("GET", "/tuple")[0], 201)

    def test_mounts_boundary_redirect_nested(self):
        child = App()
        child.get("/")(lambda req: {"url": req.url("api"), "query": req.query})
        parent = App()
        parent.mount("/child", child)
        self.app.mount("/outer", parent)
        self.assertEqual(self.app.handle("GET", "/outer/child?x=1")[1]["Location"], "/outer/child/?x=1")
        result = json.loads(self.app.handle("GET", "/outer/child/?x=1")[2])
        self.assertEqual(result, {"url": "/outer/child/api", "query": {"x": "1"}})
        self.assertEqual(self.app.handle("GET", "/outer/children/")[0], 404)
        self.assertEqual(json.loads(child.handle("GET", "/")[2])["url"], "/api")

    def test_mount_uses_child_limit(self):
        child = App(max_body=1)
        child.post("/")(lambda req: req.json())
        self.app.mount("/child", child)
        self.assertEqual(self.app.handle("POST", "/child/", b"{}")[0], 413)

    def test_longest_mount_and_exact_routes(self):
        first, second = App(), App()
        first.get("/b/")(lambda req: "first")
        second.get("/")(lambda req: "second")
        self.app.mount("/a", first)
        self.app.mount("/a/b", second)
        self.assertEqual(self.app.handle("GET", "/a/b/")[2], b"second")
        self.app.get("/a/b/")(lambda req: "exact")
        self.assertEqual(self.app.handle("GET", "/a/b/")[2], b"exact")

    def test_shell_empty_selected_escaped_nested(self):
        shell = Shell(title="<Tools>")
        self.assertIn(b"No tools registered", shell.handle("GET", "/")[2])
        shell.mount("/tool", App(), label="<Example>")
        self.assertIn(b"&lt;Example&gt;", shell.handle("GET", "/")[2])
        self.assertIn(b'<iframe title="&lt;Example&gt;" src="/tool/"', shell.handle("GET", "/?tool=/tool")[2])
        self.assertEqual(shell.handle("GET", "/?tool=/unknown")[0], 404)
        self.app.mount("/console", shell)
        self.assertIn(b'src="/console/tool/"', self.app.handle("GET", "/console/?tool=/tool")[2])


class FileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "audio.mp3").write_bytes(b"0123456789")
        (self.root / "index.html").write_bytes(b"home")
        self.app = App(static_dir=self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_full_and_head(self):
        status, headers, body = self.app.handle("GET", "/audio.mp3")
        self.assertEqual((status, body), (200, b"0123456789"))
        self.assertEqual(headers["Content-Length"], "10")
        self.assertEqual(headers["Content-Type"], "audio/mpeg")
        self.assertEqual(self.app.handle("HEAD", "/audio.mp3")[2], b"")
        self.assertEqual(self.app.handle("GET", "/")[2], b"home")

    def test_ranges(self):
        for byte_range, expected in [("bytes=2-5", b"2345"), ("bytes=8-", b"89"),
                                     ("bytes=-3", b"789"), ("bytes=8-99", b"89")]:
            with self.subTest(byte_range=byte_range):
                status, headers, body = self.app.handle("GET", "/audio.mp3", headers={"Range": byte_range})
                self.assertEqual(status, 206)
                self.assertEqual(body, expected)
                self.assertEqual(int(headers["Content-Length"]), len(body))
        for invalid in ["bytes=99-", "bytes=4-2", "bytes=-0", "bytes=0-1,3-4", "bad"]:
            self.assertEqual(self.app.handle("GET", "/audio.mp3", headers={"Range": invalid})[0], 416)

    def test_traversal_and_empty_file(self):
        self.assertEqual(self.app.handle("GET", "/%2e%2e/LICENSE")[0], 404)
        (self.root / "empty").write_bytes(b"")
        self.assertEqual(self.app.handle("GET", "/empty")[2], b"")
        self.assertEqual(self.app.handle("GET", "/empty", headers={"Range": "bytes=0-"})[0], 416)

    def test_live_http_range_head_and_post(self):
        self.app.post("/api/echo")(lambda req: req.json())
        server = _Server(("127.0.0.1", 0), self.app._handler_class())
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            request = urllib.request.Request(base + "/audio.mp3", headers={"Range": "bytes=2-4"})
            with urllib.request.urlopen(request, timeout=5) as response:
                self.assertEqual(response.status, 206)
                self.assertEqual(response.read(), b"234")
                self.assertEqual(response.headers.get_all("Content-Length"), ["3"])
            with urllib.request.urlopen(urllib.request.Request(base + "/audio.mp3", method="HEAD"), timeout=5) as response:
                self.assertEqual(response.headers["Content-Length"], "10")
                self.assertEqual(response.read(), b"")
            with urllib.request.urlopen(urllib.request.Request(base + "/api/echo", data=b'{"ok":true}'), timeout=5) as response:
                self.assertEqual(json.load(response), {"ok": True})
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
