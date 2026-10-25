# microweb

A small Flask-style framework for local Python web apps, with an optional console shell.
Standard library only; copy **`microweb.py`** into your project. Python 3.10 or newer.
BSD 2-Clause licensed, including the notice embedded in the file.

```python
from microweb import App

app = App()

@app.get("/api/hello")
def hello(req):
    return {"message": "Hello"}

app.run("127.0.0.1", 8765)
```

## Optional console

```python
from microweb import Shell

console = Shell(title="My tools")
console.mount("/example", app, label="Example")
console.run("127.0.0.1", 8765)
```

The shell supplies a landing page, navigation and default styling. Tools appear in a same-origin
iframe so their pages remain independent. Direct visits to `/example/` serve the tool alone.
An empty shell displays a useful starting page explaining that no tools are registered.
`App.mount()` also works without a shell, including nested mounts.

Try `python examples/console.py`, or add `--standalone` to run exactly the same tool independently.
The shell is ordinary Python in the same file; importing `App` does not create or start one.
It does not discover packages, launch worker processes, or impose a data-sharing format.

## Components and lifecycle

Use a Component when an app owns background services. Construction and registration remain quiet:

```python
from microweb import App, Component, Shell

tool = Component("example", "Example", App(), start=start_services, stop=stop_services)
shell = Shell(title="Tools")
shell.add(tool, prefix="/example")
shell.run("127.0.0.1", 8765)
# Alternatively: tool.run("127.0.0.1", 8765)
```

`start_services` and `stop_services` are your zero-argument functions; either callback can be omitted.
The host binds before starting services, announces readiness afterward, and stops components in reverse order.
Failed partial startup is cleaned up too. Shutdown drains accepted HTTP requests before component teardown;
idle sockets have a 30-second timeout. A component's stop callback joins its owned workers. Independently
owned jobs are untouched. Component instances support one host run; construct a new instance to run again.
An optional `stop_event=threading.Event()` lets an embedding host request shutdown without Ctrl+C.

Ordinary `App.mount()` and `App.run()` continue working without lifecycle callbacks. The
[component contract](docs/component-contract.md) documents configuration and ownership boundaries.

## Real downloader plus synthetic workbench

The [combined example](examples/downloader_console.py) hosts an adapted downloader checkout and a
small [synthetic workbench](examples/synthetic_workbench.py). It uses no models or research code.
Create an empty directory for state, then run:

```sh
python examples/downloader_console.py --downloader-dir /path/to/librivox-download --state-dir /path/to/empty-state
```

The downloader checkout must include `librivox_web.py` with the component adapter. The example explicitly
loads it and uses one common microweb runtime. Add `--standalone downloads` or `--standalone voices` to host
one component at `/`. Use `--port` for an unused port. The example does not automatically collect recordings;
the real downloader controls still perform downloads if requested. The synthetic workbench reads completed,
present, non-rejected recordings and runs only a trivial demonstration task. Its shutdown receipt is written
under the chosen state directory. The actual voice-making application is not integrated by this example.

## Requests and responses

- Decorators: `app.get(path)`, `app.post(path)`, `app.route(path, [methods])`.
- Request: `req.path`, `req.query`, `req.headers`, `req.client`, `req.body()`, `req.json()`.
- Mount-aware URLs: `req.url("api/status")`; `req.root_path` is the current mount prefix.
  In static HTML use relative URLs (`api/status`), rather than root-relative ones (`/api/status`).
  Mounting redirects `/example` to `/example/`, preserving the query string.
- Return dictionaries/lists for JSON, strings for plain text, bytes for binary, `None` for 204,
  or `(body, status)`. Raise `HTTPError(status, message)` for a JSON error.
- `Response(body, status=200, content_type=None, headers=None)` supplies explicit response metadata.
  For HTML use `Response(html, content_type="text/html; charset=utf-8")`.
- `Stream(chunks, content_type)` sends iterable byte/string chunks as produced.
- `file_response(req, trusted_path)` streams a file with HEAD and single-byte-range support for
  audio seeking. The caller decides which files are accessible; do not pass arbitrary user paths.
- `App(static_dir="static")` serves contained files after route/mount lookup, with no directory
  listings. `/` maps to `index.html`; static files also support seeking.
- `app.handle(method, url, body=b"", headers=None)` returns status, headers and bytes for tests.
  Streaming bodies are collected in this test helper; production responses stream in chunks.

Each request has its own thread. Protect shared mutable application state and run long jobs in
your own workers. HEAD falls back to GET handlers, so GET handlers must not change state.
Bodies require Content-Length and default to a 1 MB limit; `req.body(max_bytes=...)` or
`req.json(max_bytes=...)` can override it. Chunked uploads are unsupported.
Origin-bearing mutation requests must match the HTTP Host by default; `same_origin=False`
disables that check. This local HTTP server has no authentication, TLS, proxy handling, or public
deployment support. Bind to loopback for the intended desktop use.

## Copying and updates

Keep application code outside the vendored file so replacement is straightforward. No pip package
or installation step is required. Retain the embedded license when redistributing the file.

```text
python microweb.py --version
python microweb.py --check-update
python microweb.py --update
```

Imports and normal application startup never contact the network. Released copies embed a version
and the raw GitHub URL of `microweb.version` on `main`. That separate manifest announces the latest
release, its tagged download URL and SHA-256. It is created by the release script; an unreleased
development copy has no configured update URL.

Updates verify the installed file against its old tagged manifest, refuse local modifications,
verify downloaded bytes and syntax, save `microweb.py.bak`, and replace only `microweb.py`.
An existing backup must be moved or removed before another update. Restart running applications
after replacement. Update copies in each consuming repository deliberately and test their apps.
Checksums detect mismatched bytes; trust still comes from the repository and HTTPS.
The updater does not update applications using this framework.

## Development and releases

```text
python -B -m unittest discover -s tests -q
bash scripts/release.sh
```

The release script needs Bash, Git, Python, a configured Git author, a committed clean working tree,
and branch `main`. Set `PYTHON` to choose an interpreter. On Windows use Git Bash or another Bash
installation with Git and Python on PATH.

The GitHub repository is detected from `origin` (HTTPS, `git@github.com:OWNER/REPO.git`, or
`ssh://git@github.com/OWNER/REPO.git`). It supplies the location for the release manifest and
download URLs; detection makes no network requests. To override it, or if no remote is configured,
use `bash scripts/release.sh OWNER/REPO`. With no arguments and no usable origin, the script explains
these options and exits without changing files or configuring a remote.

Set `__version__` in `microweb.py` to the intended numeric release (for example `0.1.0`) and commit
that change before running the script. Development suffixes are refused. The version must be newer
than the previous manifest, and its tag must not already exist.

The script reads that embedded version, sets the manifest URL, hashes the final LF Python file, writes
`microweb.version`, runs tests, then creates a release commit and annotated `vVERSION` tag.
It never pushes. If tests fail it restores the source and manifest. A later Git failure leaves
prepared work available for inspection; inspect `git status` and tags before retrying.
The script prints the command to publish the branch and tag together, so the manifest on `main`
does not announce a tag that has not been published. No release or remote is configured initially.

Assistant guides: [usage](AI/USAGE.md), [development context](AI/MEMORY.md), and
[documentation strategy](AI/STRATEGY.md).
