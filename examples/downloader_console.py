"""Mount the real downloader and a synthetic workbench in one console.

State defaults to the repository's ignored data/downloader-console/ directory. No collection starts
automatically; downloading through the real tool's controls remains an explicit action.
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from microweb import Component, Shell
from synthetic_workbench import create_component as workbench


def prepare_state(component, root):
    """Prepare example storage after socket binding, then start the tool normally."""
    def start():
        root.mkdir(parents=True, exist_ok=True)
        component.start()
    return Component(component.id, component.label, component.app, start, component.stop)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--downloader-dir', type=Path, required=True, help='checkout containing librivox_web.py')
    parser.add_argument('--state-dir', type=Path, default=ROOT / 'data/downloader-console',
                        help='optional state override (default: repository data/downloader-console/)')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args(argv)
    args.state_dir = args.state_dir.resolve()
    args.downloader_dir = args.downloader_dir.resolve()
    if args.state_dir.exists() and not args.state_dir.is_dir():
        parser.error('--state-dir must be a directory')
    return args


def main():
    args = parse_args()
    root = args.state_dir
    sys.path.insert(0, str(args.downloader_dir))
    from librivox_web import create_component as downloader

    downloads = downloader({'session_file': root / 'downloads.json', 'collect': False})
    voices = workbench({'data_dir': root / 'workbench', 'download_sources': [root / 'downloads']})

    host = Shell(title='Voice tools example')
    host.add(prepare_state(downloads, root), prefix='/downloads')
    host.add(prepare_state(voices, root), prefix='/voices')
    host.run('127.0.0.1', args.port,
             on_ready=lambda: print(f'Console: http://127.0.0.1:{args.port}/ | State: {root}', flush=True))


if __name__ == '__main__':
    main()
