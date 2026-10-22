"""microweb - a tiny Flask-style web framework. Standard library only.

Flask-style, not Flask-compatible: just enough for a small local app.

    from microweb import App, HTTPError

    app = App(static_dir="static")

    @app.get("/api/hello")
    def hello(req):
        name = req.query.get("name", "world")
        return {"message": f"hello {name}"}

    @app.post("/api/echo")
    def echo(req):
        data = req.json()
        if not isinstance(data, dict):
            raise HTTPError(400, "expected a JSON object")
        return data, 201

    app.run("127.0.0.1", 8080, on_ready=lambda: print("listening"))

Handlers take one argument, the Request (req), and return:
    dict or list      -> JSON, status 200
    str               -> text/plain, status 200
    bytes             -> application/octet-stream, status 200
    None              -> 204 No Content
    Stream(chunks, content_type)
                      -> the chunks sent one by one as they're produced
    Response(body, status, content_type, headers)
                      -> explicit response metadata around any supported body
    (body, status)    -> any of the above with that status
raise HTTPError(status, message, **extra) -> JSON {"error": message, **extra}.
Any other exception -> 500 {"error": "internal error"}, traceback logged.

Lookup order: exact-path route; mounted app; for GET/HEAD, a file from static_dir ("/" serves
index.html; no directory listings); else 404. A known path with the wrong
method gets 405 with an Allow header. Request bodies need a Content-Length
(411 otherwise) and are limited to max_body bytes (1 MB by default, raised per
call with req.body(max_bytes=...)).

Each request runs in its own thread, and each connection serves one request
(HTTP/1.0 style). Logging goes to the "microweb" logger: unexpected exceptions
as errors with a traceback; request lines and HTTPErrors at debug level (a
handler that raises HTTPError logs what's worth logging itself).

App.mount(prefix, child) composes independent apps; req.url(path) builds links
using their mounting prefix. Shell is an optional landing page and navigation
around those apps. No shell, update checks, or server starts on import.
"""

import argparse
import ast
import copy
import errno
import hashlib
import html
import http.client
import io
import json
import logging
import os
import re
import socket
import tempfile
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

__version__ = "v0.1.0"
UPDATE_URL = ""  # Set by scripts/release.sh to the raw manifest on main.

# Copyright (c) 2026, Gilbert Gong
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
# 1. Redistributions of source code must retain the above copyright notice,
#    this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

log = logging.getLogger("microweb")

# Explicit content types: Windows' registry can map .js to text/plain, which
# breaks JavaScript modules.
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json",
    ".txt": "text/plain; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".ico": "image/x-icon",
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
    ".woff2": "font/woff2",
}


class HTTPError(Exception):
    """Raise in a handler to send an error response: JSON {"error": message, **extra}."""

    def __init__(self, status, message, **extra):
        super().__init__(message)
        self.status = status
        self.message = message
        self.extra = extra


class Stream:
    """Return from a handler to send the body in pieces as they're produced.

    chunks: an iterable (e.g. a generator) of bytes or str. Each piece is sent
    as soon as it's produced; the response ends when the iterable does (the
    connection closes, so no Content-Length is needed).
    """

    def __init__(self, chunks, content_type="application/octet-stream"):
        self.chunks = chunks
        self.content_type = content_type

    def __iter__(self):
        for chunk in self.chunks:
            yield chunk.encode("utf-8") if isinstance(chunk, str) else chunk


class Request:
    """An incoming request.

    method   "GET", "POST", ...
    path     the URL path, without the query string
    query    dict of query-string values (the last one wins if repeated)
    headers  case-insensitive mapping
    client   the client's IP address
    body()   the raw body (bytes); json() parses it
    """

    def __init__(self, method, target, headers, rfile, client, max_body):
        url = urllib.parse.urlsplit(target)
        self.method = method
        self.path = urllib.parse.unquote(url.path)
        self.query_string = url.query
        self.root_path = ""
        self.query = dict(urllib.parse.parse_qsl(url.query))
        self.headers = headers
        self.client = client
        self._rfile = rfile
        self._max_body = max_body
        self._body = None

    def url(self, path="/"):
        """A URL within this app, including its mounting prefix."""
        return self.root_path + "/" + path.lstrip("/")

    def body(self, max_bytes=None):
        """The raw request body, read once (later calls return the same bytes).

        Raises HTTPError 411 without a Content-Length, 413 if it's larger than
        max_bytes (default: the app's max_body), 400 if it's malformed.
        """
        if self._body is not None:
            return self._body
        limit = self._max_body if max_bytes is None else max_bytes
        if "Transfer-Encoding" in self.headers:
            raise HTTPError(411, "chunked request bodies are not supported; send a Content-Length")
        length = self.headers.get("Content-Length")
        if length is None:
            if self.method in ("GET", "HEAD"):
                self._body = b""
                return self._body
            raise HTTPError(411, "Content-Length required")
        try:
            length = int(length)
            if length < 0:
                raise ValueError
        except ValueError:
            raise HTTPError(400, "invalid Content-Length") from None
        if length > limit:
            raise HTTPError(413, f"request body too large ({length} bytes; limit {limit})")
        self._body = self._rfile.read(length)
        if len(self._body) < length:
            raise HTTPError(400, "request body incomplete")
        return self._body

    def json(self, max_bytes=None):
        """The body parsed as JSON (any JSON value). Raises HTTPError 400 if it isn't valid JSON."""
        try:
            return json.loads(self.body(max_bytes))
        except ValueError:
            raise HTTPError(400, "invalid JSON") from None


class _Server(ThreadingHTTPServer):
    daemon_threads = True  # don't wait for open requests on shutdown
    # On Windows, SO_REUSEADDR lets a second server bind a port that's already
    # in use, so only use it elsewhere (where it allows quick restarts).
    allow_reuse_address = os.name != "nt"

    def server_bind(self):
        if os.name == "nt":
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


# Responses and large files ---------------------------------------------------

class Response:
    """A body with explicit status, content type and optional headers."""

    def __init__(self, body=b"", status=200, content_type=None, headers=None):
        self.body, self.status = body, status
        self.headers = dict(headers or {})
        if content_type:
            self.headers["Content-Type"] = content_type


def file_response(req, path):
    """Stream a trusted file path, with HEAD and a single byte range for seeking.

    The caller must restrict paths to files it intends to expose. Static-file
    serving does its own containment check before calling this function.
    """
    path = Path(path)
    if not path.is_file():
        raise HTTPError(404, "file not found")
    size = path.stat().st_size
    start, end, status = 0, size - 1, 200
    headers = {"Accept-Ranges": "bytes", "Cache-Control": "no-cache"}
    byte_range = req.headers.get("Range")
    if byte_range:
        match = re.fullmatch(r"bytes=(\d*)-(\d*)", byte_range)
        try:
            if not match or not any(match.groups()) or not size:
                raise ValueError
            first, last = match.groups()
            if first:
                start = int(first)
                end = min(int(last), end) if last else end
            else:
                suffix = int(last)
                if suffix <= 0:
                    raise ValueError
                start = max(0, size - suffix)
            if start > end or start >= size:
                raise ValueError
        except ValueError:
            return Response(status=416, headers={"Content-Range": f"bytes */{size}"})
        status = 206
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    headers["Content-Length"] = str(max(0, end - start + 1))

    def chunks():
        with path.open("rb") as source:
            source.seek(start)
            remaining = end - start + 1
            while remaining > 0:
                chunk = source.read(min(65536, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    kind = CONTENT_TYPES.get(path.suffix.lower(), "application/octet-stream")
    return Response(Stream(chunks(), kind), status, kind, headers)


class App:
    def __init__(self, static_dir=None, max_body=1024 * 1024, same_origin=True):
        self.static_dir = Path(static_dir).resolve() if static_dir else None
        self.max_body = max_body
        self.routes = {}  # path -> {method: handler}
        self.mounts = {}
        self.same_origin = same_origin

    # Routes

    def route(self, path, methods):
        def decorator(handler):
            for method in methods:
                self.routes.setdefault(path, {})[method] = handler
            return handler
        return decorator

    def get(self, path):
        return self.route(path, ["GET"])

    def post(self, path):
        return self.route(path, ["POST"])

    def mount(self, prefix, app):
        """Mount an app on a path boundary; longest matching prefix wins."""
        prefix = prefix.rstrip("/")
        if not re.fullmatch(r"(?:/[A-Za-z0-9_-]+)+", prefix):
            raise ValueError("mount prefix must be a non-root path such as /downloads")
        if prefix in self.mounts or app is self:
            raise ValueError("duplicate mount or self mount")
        self.mounts[prefix] = app
        return app

    # Running

    def run(self, host, port, on_ready=None):
        """Serve until Ctrl+C. on_ready() is called once the port is open."""
        try:
            server = _Server((host, port), self._handler_class())
        except OSError as err:
            if err.errno == errno.EADDRINUSE or getattr(err, "winerror", None) == 10048:
                raise SystemExit(f"error: port {port} on {host} is already in use") from None
            raise
        try:
            if on_ready:
                on_ready()
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()

    def handle(self, method, path, body=b"", headers=None):
        """Run a request through the app without a network connection, e.g.
        for tests. Returns (status, headers dict, body bytes)."""
        message = http.client.HTTPMessage()
        for name, value in (headers or {}).items():
            message[name] = value
        if body and "Content-Length" not in message:
            message["Content-Length"] = str(len(body))
        req = Request(method, path, message, io.BytesIO(body), "test", self.max_body)
        status, response_headers, data = self._dispatch(req)
        if isinstance(data, Stream):
            data = b"".join(data) if method != "HEAD" else b""
        if method == "HEAD":
            data = b""
        return status, dict(response_headers), data

    # Internals

    def _dispatch(self, req):
        """Route a request; returns (status, [(header, value)], body bytes)."""
        try:
            if self.same_origin and req.method not in ("GET", "HEAD", "OPTIONS"):
                origin = req.headers.get("Origin")
                if origin and origin != "http://" + req.headers.get("Host", ""):
                    raise HTTPError(403, "cross-origin request refused")
            handlers = self.routes.get(req.path)
            if handlers:
                handler = handlers.get(req.method)
                if handler is None and req.method == "HEAD":
                    handler = handlers.get("GET")
                if handler is None:
                    status, headers, body = self._json(405, {"error": "method not allowed"})
                    return status, headers + [("Allow", ", ".join(sorted(handlers)))], body
                return self._response(handler(req))
            for prefix, child in sorted(self.mounts.items(), key=lambda item: -len(item[0])):
                if req.path == prefix:
                    location = req.root_path + prefix + "/"
                    if req.query_string:
                        location += "?" + req.query_string
                    return self._response(Response(status=307, headers={"Location": location}))
                if req.path.startswith(prefix + "/"):
                    mounted = copy.copy(req)
                    mounted.path = req.path[len(prefix):]
                    mounted.root_path = req.root_path + prefix
                    mounted._max_body = child.max_body
                    return child._dispatch(mounted)
            if req.method in ("GET", "HEAD") and self.static_dir:
                static = self._static(req.path)
                if static:
                    return self._response(file_response(req, static))
            return self._json(404, {"error": "not found"})
        except HTTPError as err:
            # Raised on purpose by a handler (which logs anything worth logging).
            log.debug("%s %s -> %d: %s", req.method, req.path, err.status, err.message)
            return self._json(err.status, {"error": err.message, **err.extra})
        except Exception:
            log.exception("%s %s failed", req.method, req.path)
            return self._json(500, {"error": "internal error"})

    def _response(self, result):
        if isinstance(result, Response):
            _, headers, body = self._response(result.body)
            combined = dict(headers)
            for name, value in result.headers.items():
                for old in list(combined):
                    if old.lower() == name.lower():
                        del combined[old]
                combined[name] = value
            return result.status, list(combined.items()), body
        status = 200
        if isinstance(result, tuple):
            result, status = result
        if result is None:
            return (204 if status == 200 else status), [], b""
        if isinstance(result, (dict, list)):
            return self._json(status, result)
        if isinstance(result, str):
            return status, [("Content-Type", "text/plain; charset=utf-8")], result.encode("utf-8")
        if isinstance(result, bytes):
            return status, [("Content-Type", "application/octet-stream")], result
        if isinstance(result, Stream):
            return status, [("Content-Type", result.content_type), ("Cache-Control", "no-cache")], result
        raise TypeError(f"handler returned unsupported type {type(result).__name__}")

    @staticmethod
    def _json(status, payload):
        return status, [("Content-Type", "application/json")], json.dumps(payload).encode("utf-8")

    def _static(self, path):
        """A file from static_dir, or None. Never lists directories or leaves static_dir."""
        relative = "index.html" if path == "/" else path.lstrip("/")
        file = (self.static_dir / relative).resolve()
        if not file.is_relative_to(self.static_dir) or not file.is_file():
            return None
        return file

    def _handler_class(self):
        app = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "microweb"

            def _serve(self):
                req = Request(self.command, self.path, self.headers, self.rfile,
                              self.client_address[0], app.max_body)
                status, headers, body = app._dispatch(req)
                streaming = isinstance(body, Stream)
                try:
                    self.send_response(status)
                    for name, value in headers:
                        self.send_header(name, value)
                    if not streaming and not any(name.lower() == "content-length" for name, _ in headers):
                        self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    if self.command == "HEAD":
                        return
                    if not streaming:
                        self.wfile.write(body)
                        return
                    try:
                        for chunk in body:
                            self.wfile.write(chunk)
                            self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                        raise
                    except Exception:
                        # Headers are already sent, so all we can do is stop.
                        log.exception("%s %s failed while streaming", req.method, req.path)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    log.debug("%s %s: client disconnected", req.method, req.path)

            do_GET = do_HEAD = do_POST = do_PUT = do_PATCH = do_DELETE = _serve

            def log_message(self, format, *args):
                log.debug("%s %s", self.address_string(), format % args)

        return Handler


# Optional console shell -----------------------------------------------------

class Shell(App):
    """A landing page and persistent navigation around independent mounted apps.

    Apps run inside a same-origin iframe, keeping their HTML and assets separate.
    Visiting a mounted URL directly still serves the app without the shell.
    """

    STYLE = """
    body { margin:0; font:16px system-ui,sans-serif; color:#243047; background:#f4f6fa }
    header { padding:16px 24px; background:#fff; border-bottom:1px solid #dce1ea }
    nav { display:flex; flex-wrap:wrap; gap:16px; align-items:center }
    a { color:#2457aa } nav strong { margin-right:12px }
    main { max-width:900px; margin:40px auto; padding:0 24px }
    .tools { display:flex; gap:16px; flex-wrap:wrap }
    .tool { padding:24px; background:#fff; border:1px solid #dce1ea; border-radius:8px }
    iframe { width:100%; flex:1; border:0; background:white }
    body.focus { height:100vh; display:flex; flex-direction:column }
    """

    def __init__(self, title="Tools", **kwargs):
        super().__init__(**kwargs)
        self.title = title
        self.tools = {}
        self.get("/")(self._home)

    def mount(self, prefix, app, label=None):
        super().mount(prefix, app)
        self.tools[prefix.rstrip("/")] = label or prefix.strip("/")
        return app

    def _home(self, req):
        selected = req.query.get("tool")
        if selected is not None and selected not in self.tools:
            raise HTTPError(404, "unknown tool")
        title = html.escape(self.title)
        home = html.escape(req.url(), quote=True)
        links, cards = [], []
        for prefix, label in self.tools.items():
            href = html.escape(req.url() + "?" + urllib.parse.urlencode({"tool": prefix}), quote=True)
            link = f'<a href="{href}">{html.escape(label)}</a>'
            links.append(link)
            cards.append(f'<div class="tool">{link}</div>')
        if selected:
            src = html.escape(req.url(selected + "/"), quote=True)
            content = f'<iframe title="{html.escape(self.tools[selected], quote=True)}" src="{src}"></iframe>'
        else:
            content = f'<main><h1>{title}</h1><div class="tools">' + "".join(cards) + '</div>'
            if not cards:
                content += '<p>No tools registered yet. Mount an App to add one.</p>'
            content += '</main>'
        page = (f'<!doctype html><html lang="en"><meta charset="utf-8">'
                f'<meta name="viewport" content="width=device-width,initial-scale=1">'
                f'<title>{title}</title><style>{self.STYLE}</style>'
                f'<body class="{"focus" if selected else "home"}"><header><nav>'
                f'<strong><a href="{home}">{title}</a></strong>' + "".join(links) +
                '</nav></header>' + content + '</body></html>')
        return Response(page, content_type="text/html; charset=utf-8")


# Explicit version checks and vendored-file updates --------------------------

def _version_parts(version):
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("release versions must be MAJOR.MINOR.PATCH")
    return tuple(int(part) for part in version.split("."))


def _download(url):
    if not url.startswith("https://"):
        raise ValueError("update URLs must use HTTPS")
    request = urllib.request.Request(url, headers={"User-Agent": "microweb-updater"})
    with urllib.request.urlopen(request, timeout=30) as response:
        if not response.url.startswith("https://"):
            raise ValueError("update redirected away from HTTPS")
        data = response.read(2 * 1024 * 1024 + 1)
        if len(data) > 2 * 1024 * 1024:
            raise ValueError("update response exceeds 2 MB")
        return data


def check_update():
    """Read the announcement on main. Never called during import or app startup."""
    if not UPDATE_URL:
        raise ValueError("development copy: no release manifest URL configured")
    manifest = json.loads(_download(UPDATE_URL))
    _version_parts(manifest["version"])
    if not re.fullmatch(r"[0-9a-f]{64}", manifest["sha256"]):
        raise ValueError("invalid release SHA-256")
    return manifest


def install_update(manifest, target=None):
    """Replace an unmodified release copy, retaining a .bak. Restart apps to use it.

    The old tagged manifest establishes the expected local bytes. A modified or
    development copy is never silently overwritten. No downloaded code is run.
    """
    current = _version_parts(__version__)
    if _version_parts(manifest["version"]) <= current:
        return False
    target = Path(target or __file__).resolve()
    if "/main/" not in UPDATE_URL:
        raise ValueError("expected a raw GitHub manifest on main")
    old_url = UPDATE_URL.replace("/main/", f"/refs/tags/v{__version__}/", 1)
    old_manifest = json.loads(_download(old_url))
    original = target.read_bytes()
    if hashlib.sha256(original).hexdigest() != old_manifest["sha256"]:
        raise ValueError("local file has modifications; update manually")
    incoming = _download(manifest["url"])
    if hashlib.sha256(incoming).hexdigest() != manifest["sha256"]:
        raise ValueError("downloaded file does not match release SHA-256")
    tree = ast.parse(incoming)
    versions = [node.value.value for node in tree.body
                if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)
                and any(isinstance(name, ast.Name) and name.id == "__version__" for name in node.targets)]
    if versions != [manifest["version"]]:
        raise ValueError("downloaded file version does not match manifest")
    compile(incoming, str(target), "exec")
    backup = target.with_name(target.name + ".bak")
    if backup.exists():
        raise ValueError(f"backup already exists: {backup}; keep or remove it before updating")
    staged = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".microweb-", delete=False) as output:
            staged = Path(output.name)
            output.write(incoming)
        staged.chmod(target.stat().st_mode)
        if target.read_bytes() != original:
            raise ValueError("local file changed during update")
        with backup.open("xb") as output:
            output.write(original)
        staged.replace(target)
        return True
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description="Single-file local web apps and optional console shell")
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--version", action="store_true")
    actions.add_argument("--check-update", action="store_true")
    actions.add_argument("--update", action="store_true")
    args = parser.parse_args()
    if args.version:
        print(__version__)
        return
    try:
        remote = check_update()
        newer = _version_parts(remote["version"]) > _version_parts(__version__)
        print(f'Installed: {__version__}; latest release: {remote["version"]}')
        if args.update and newer:
            install_update(remote)
            print("Updated. Previous file saved as microweb.py.bak; restart applications to use the new version.")
        elif newer:
            print("An update is available. Run with --update to install it.")
        else:
            print("No newer release available.")
    except (OSError, ValueError, KeyError, TypeError, SyntaxError) as error:
        parser.exit(1, f"Update failed: {error}\n")


if __name__ == "__main__":
    main()
