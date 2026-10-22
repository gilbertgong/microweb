"""Run from the repository root: python examples/console.py [--standalone]."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from microweb import App, Response, Shell

app = App()


@app.get("/")
def home(req):
    return Response(
        '<h1>Example tool</h1><p>This application also runs independently.</p>'
        f'<p><a href="{req.url("api/status")}">View status JSON</a></p>',
        content_type="text/html; charset=utf-8",
    )


@app.get("/api/status")
def status(req):
    return {"ready": True, "mount_prefix": req.root_path}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--standalone", action="store_true")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    console = Shell(title="Example console")
    console.mount("/example", app, label="Example tool")
    server = app if args.standalone else console
    server.run("127.0.0.1", args.port, on_ready=lambda: print(f"Open http://127.0.0.1:{args.port}", flush=True))
