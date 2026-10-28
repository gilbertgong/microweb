"""Run the bundled stdlib-only demo: python examples/console.py."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from microweb import Shell
from demo_components import microweb_demo_components as demo


def build_shell():
    """Explicit registration of bundled components; no discovery or installation."""
    shell = Shell(title='Microweb example')
    manifest = json.loads((Path(__file__).parent / 'demo_components/microweb-component.json').read_text(encoding='utf-8'))
    for entry in sorted(manifest['components'], key=lambda item: item.get('order', 100)):
        factory = getattr(demo, entry['factory'].split(':')[1])
        shell.add(factory({}), '/' + entry['id'], placement=entry.get('placement', 'panel'),
                  height=entry.get('height', 96), description=entry.get('description', ''))
    return shell


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--standalone", nargs='?', const='library', choices=['library', 'workbench', 'machine'],
                        help='run one bundled view at /; defaults to library when no name is given')
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = getattr(demo, args.standalone)({}) if args.standalone else build_shell()
    server.run("127.0.0.1", args.port, on_ready=lambda: print(f"Open http://127.0.0.1:{args.port}", flush=True))
