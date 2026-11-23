"""Optional local component-discovery example. Never downloads or installs code.

Clone tools into components/, then run python examples/component_console.py.
Or run python examples/component_console.py manifest.json to list checkouts anywhere.
Each tool supplies microweb-component.json. Data stays separately under data/.
"""
import argparse
import html
import importlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from microweb import Component, Shell

MANIFEST = 'microweb-component.json'


def discover(directory=None, *, manifest=None):
    """Read metadata only; a console manifest selects explicit checkout manifests."""
    manifests, _ = _select_manifests(directory, manifest)
    return _discover_manifests(manifests)


def _validate_settings(settings):
    if not isinstance(settings, dict):
        raise ValueError('settings must be an object mapping component ids to settings objects')
    if any(not isinstance(value, dict) for value in settings.values()):
        raise ValueError('each component settings entry must be an object')
    return settings


def _select_manifests(directory, manifest):
    settings = {}
    if manifest is not None:
        if directory is not None:
            raise ValueError('choose a console manifest or a components directory, not both')
        manifest = Path(manifest).resolve()
        data = json.loads(manifest.read_text(encoding='utf-8'))
        if not isinstance(data, dict) or not isinstance(data.get('manifests'), list):
            raise ValueError('console manifest must be an object with a manifests array')
        if any(not isinstance(item, str) or not item.strip() for item in data['manifests']):
            raise ValueError('each manifests entry must be a nonempty file path string')
        manifests = [(manifest.parent / item).resolve() for item in data['manifests']]
        settings = _validate_settings(data.get('settings', {}))
    else:
        directory = Path(directory) if directory is not None else ROOT / 'components'
        if not directory.exists():
            return [], settings
        manifests = [child / MANIFEST for child in sorted(directory.iterdir())
                     if child.is_dir() and (child / MANIFEST).is_file()]
    return manifests, settings


def _discover_manifests(manifests):
    entries, problems = [], []
    for manifest in manifests:
        try:
            data = json.loads(manifest.read_text(encoding='utf-8'))
            if not isinstance(data, dict):
                raise ValueError('manifest must be an object')
            if type(data.get('component_api')) is not int or data['component_api'] != 1:
                raise ValueError('requires component_api 1')
            if not isinstance(data.get('components'), list):
                raise ValueError('components must be an array')
            for index, item in enumerate(data['components']):
                try:
                    if not isinstance(item, dict):
                        raise ValueError('component must be an object')
                    if not isinstance(item.get('id'), str) or not re.fullmatch(r'[a-z][a-z0-9_-]*', item['id']):
                        raise ValueError('id must be a lowercase name such as downloads')
                    if not isinstance(item.get('label'), str) or not item['label'].strip():
                        raise ValueError('label is required')
                    if not isinstance(item.get('description', ''), str):
                        raise ValueError('description must be a string')
                    if not re.fullmatch(r'[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*:[A-Za-z_]\w*', str(item.get('factory', ''))):
                        raise ValueError('factory must be module:function')
                    if not isinstance(item.get('defaults', {}), dict):
                        raise ValueError('defaults must be an object')
                    if item.get('placement', 'panel') not in ('panel', 'banner'):
                        raise ValueError('placement must be panel or banner')
                    if type(item.get('order', 100)) is not int:
                        raise ValueError('order must be an integer')
                    if type(item.get('height', 96)) is not int or item.get('height', 96) <= 0:
                        raise ValueError('height must be a positive integer in pixels')
                    entries.append({**item, 'directory': manifest.parent.resolve()})
                except ValueError as error:
                    problems.append(f'{manifest} components[{index}]: {error}')
        except (OSError, ValueError) as error:
            problems.append(f'{manifest}: {error}')
    duplicates = {entry['id'] for entry in entries if sum(other['id'] == entry['id'] for other in entries) > 1}
    for name in sorted(duplicates):
        problems.append(f'duplicate component id {name}; none of its conflicting entries will load')
    return sorted((entry for entry in entries if entry['id'] not in duplicates),
                  key=lambda entry: (entry.get('order', 100), entry['id'])), problems


class DiscoveryShell(Shell):
    def __init__(self, problems, **kwargs):
        self.problems = problems
        super().__init__(**kwargs)

    def _home(self, req):
        response = super()._home(req)
        if req.query.get('tool') is None:
            response.body = response.body.replace('No tools registered yet. Mount an App to add one.',
                                                  'No components found yet.')
            intro = ('<p>Clone a tool repository into <code>components/</code>, then restart this example. '
                     'Or pass a console manifest listing component manifest paths from any location. '
                     'Tools supply <code>microweb-component.json</code>. No code is downloaded or installed by this launcher.</p>')
            if self.problems:
                intro += '<h2>Components not loaded</h2><ul>'
                intro += ''.join('<li>' + html.escape(item) + '</li>' for item in self.problems) + '</ul>'
            response.body = response.body.replace('<main>', '<main>' + intro, 1)
        return response


def build_shell(components_dir=None, data_dir=ROOT / 'data', overrides=None, *, manifest=None):
    """Construct apps without creating data directories or starting services."""
    manifests, config = _select_manifests(components_dir, manifest)
    overrides = _validate_settings({} if overrides is None else overrides)
    entries, problems = _discover_manifests(manifests)
    data_dir = Path(data_dir).resolve()
    shell = DiscoveryShell(problems, title='Component console')
    for entry in entries:
        try:
            folder = entry['directory']
            module_name, function = entry['factory'].split(':')
            source = folder.joinpath(*module_name.split('.'))
            if not source.with_suffix('.py').is_file() and not (source / '__init__.py').is_file():
                raise ValueError('factory module is not in this checkout')
            loaded = sys.modules.get(module_name)
            if loaded is not None and not Path(loaded.__file__).resolve().is_relative_to(folder):
                raise ValueError('factory module name is already used by another checkout; use distinct package names')
            location = str(folder)
            if location not in sys.path:
                sys.path.insert(0, location)
            module = importlib.import_module(module_name)
            if not Path(module.__file__).resolve().is_relative_to(folder):
                raise ValueError('factory resolved outside this checkout')
            home = data_dir / entry['id']
            settings = {**entry.get('defaults', {}), **config.get(entry['id'], {}),
                        **overrides.get(entry['id'], {}),
                        'settings_dir': home}
            component = getattr(module, function)(settings)
            if not isinstance(component, Component) or component.id != entry['id']:
                raise ValueError('factory must return a compatible Component with the manifest id')

            def start(component=component, home=home):
                home.mkdir(parents=True, exist_ok=True)
                component.start()

            # The launcher owns display labels; the tool owns its app and callbacks.
            shell.add(Component(component.id, entry['label'], component.app, start, component.stop),
                      prefix='/' + entry['id'], placement=entry.get('placement', 'panel'),
                      height=entry.get('height', 96), description=entry.get('description', ''))
        except Exception as error:
            problems.append(f'{entry["id"]}: {type(error).__name__}: {error}')
    return shell


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument('manifest', nargs='?', type=Path,
                        help='optional JSON object with a manifests array of component manifest paths')
    source.add_argument('--components-dir', type=Path,
                        help='scan checkout directories here instead (default: components/)')
    parser.add_argument('--data-dir', type=Path, default=ROOT / 'data')
    parser.add_argument('--settings', type=Path, help='optional JSON overrides applied after console manifest settings')
    parser.add_argument('--port', type=int, default=8765)
    return parser, parser.parse_args(argv)


def main():
    parser, args = parse_args()
    try:
        config = json.loads(args.settings.read_text(encoding='utf-8')) if args.settings else {}
        shell = build_shell(args.components_dir, args.data_dir, config, manifest=args.manifest)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    for problem in shell.problems:
        print('Not loaded:', problem, file=sys.stderr)
    shell.run('127.0.0.1', args.port,
              on_ready=lambda: print(f'Component console: http://127.0.0.1:{args.port}/ | Data: {args.data_dir.resolve()}', flush=True))


if __name__ == '__main__':
    main()
