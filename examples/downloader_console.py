"""Host the real downloader and a synthetic workbench, together or independently.

Use an existing empty --state-dir for an isolated demonstration. No collection starts
automatically; downloading through the real tool's controls remains an explicit action.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from microweb import Shell
from synthetic_workbench import create_component as workbench


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--downloader-dir', type=Path, help='checkout containing librivox_web.py')
    parser.add_argument('--state-dir', type=Path, required=True, help='existing directory for example state')
    parser.add_argument('--standalone', choices=['downloads', 'voices'])
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    root = args.state_dir.resolve()
    if not root.is_dir():
        parser.error('--state-dir must be an existing directory; create an empty one for an isolated demo')
    components = []
    if args.standalone != 'voices':
        if args.downloader_dir is None:
            parser.error('--downloader-dir is required when including the downloader')
        sys.path.insert(0, str(args.downloader_dir.resolve()))
        from librivox_web import create_component
        components.append(create_component({'session_file': root / 'downloads.json', 'collect': False}))
    if args.standalone != 'downloads':
        components.append(workbench({'data_dir': root / 'workbench', 'download_sources': [root / 'downloads']}))
    if args.standalone:
        host = components[0]
    else:
        host = Shell(title='Voice tools example')
        for component in components:
            host.add(component, prefix='/' + component.id)
    host.run('127.0.0.1', args.port,
             on_ready=lambda: print(f'Console: http://127.0.0.1:{args.port}/ | State: {root}', flush=True))


if __name__ == '__main__':
    main()
