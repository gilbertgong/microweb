"""Optional local component-discovery example. Never downloads or installs code.

Clone tools into components/, then run python examples/component_console.py.
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


def discover(directory):
    """Read metadata only, before importing any installed component code."""
    entries, problems = [], []
    if not directory.exists():
        return entries, problems
    for child in sorted(directory.iterdir()):
        manifest = child / MANIFEST
        if not child.is_dir() or not manifest.is_file():
            continue
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
                    entries.append({**item, 'directory': child.resolve()})
                except ValueError as error:
                    problems.append(f'{child.name} components[{index}]: {error}')
        except (OSError, ValueError) as error:
            problems.append(f'{child.name}: {error}')
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
                     'Tools supply <code>microweb-component.json</code>. No code is downloaded or installed by this launcher.</p>')
            if self.problems:
                intro += '<h2>Components not loaded</h2><ul>'
                intro += ''.join('<li>' + html.escape(item) + '</li>' for item in self.problems) + '</ul>'
            response.body = response.body.replace('<main>', '<main>' + intro, 1)
        return response


def build_shell(components_dir, data_dir, overrides=None):
    """Construct apps without creating data directories or starting services."""
    entries, problems = discover(Path(components_dir).resolve())
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
            settings = {**entry.get('defaults', {}), **(overrides or {}).get(entry['id'], {}),
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--components-dir', type=Path, default=ROOT / 'components')
    parser.add_argument('--data-dir', type=Path, default=ROOT / 'data')
    parser.add_argument('--settings', type=Path, help='optional JSON component settings overrides')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    try:
        config = json.loads(args.settings.read_text(encoding='utf-8')) if args.settings else {}
        if not isinstance(config, dict):
            raise ValueError('settings must be an object mapping component ids to settings objects')
        if any(not isinstance(value, dict) for value in config.values()):
            raise ValueError('each component settings entry must be an object')
        shell = build_shell(args.components_dir, args.data_dir, config)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    for problem in shell.problems:
        print('Not loaded:', problem, file=sys.stderr)
    shell.run('127.0.0.1', args.port,
              on_ready=lambda: print(f'Component console: http://127.0.0.1:{args.port}/ | Data: {args.data_dir.resolve()}', flush=True))


if __name__ == '__main__':
    main()
