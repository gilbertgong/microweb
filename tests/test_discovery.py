import importlib.util
import json
import shutil
import tempfile
import threading
import unittest
import uuid
from pathlib import Path

import microweb

spec = importlib.util.spec_from_file_location('component_console_example',
    Path(__file__).resolve().parents[1] / 'examples/component_console.py')
console = importlib.util.module_from_spec(spec)
spec.loader.exec_module(console)


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.components, self.data = self.root / 'components', self.root / 'data'
        self.components.mkdir()

    def install(self, name='tool', source=None, **changes):
        folder = self.components / name
        folder.mkdir()
        module = 'fixture_' + uuid.uuid4().hex
        code = source or '''from pathlib import Path
from microweb import App, Component
def create_component(settings):
    app = App()
    home = Path(settings['settings_dir'])
    def start():
        (home / settings['session_file']).write_text(settings.get('message', 'default'))
    def stop():
        (home / 'stopped').write_text('yes')
    app.get('/api/settings')(lambda req: {**settings, 'settings_dir': str(home)})
    return Component('tool', 'Internal label', app, start, stop)
'''
        (folder / (module + '.py')).write_text(code, encoding='utf-8')
        manifest = {'id': 'tool', 'label': 'Example Tool',
                    'factory': module + ':create_component', 'defaults': {'session_file': 'session.json'}}
        api = changes.pop('component_api', 1)
        manifest.update(changes)
        (folder / console.MANIFEST).write_text(json.dumps({'component_api': api, 'components': [manifest]}), encoding='utf-8')
        return folder

    def test_empty_and_missing_directories_show_help_without_writes(self):
        for path in [self.components, self.root / 'missing']:
            shell = console.build_shell(path, self.data)
            self.assertEqual(shell.components, [])
            body = shell.handle('GET', '/')[2]
            self.assertIn(b'Clone a tool repository', body)
            self.assertIn(b'No components found yet', body)
            self.assertFalse(self.data.exists())

    def test_metadata_scan_does_not_import_or_recurse(self):
        self.install(source="raise AssertionError('metadata scan imported code')")
        nested = self.components / 'container/nested'
        nested.mkdir(parents=True)
        (nested / console.MANIFEST).write_text('bad JSON')
        entries, problems = console.discover(self.components)
        self.assertEqual(len(entries), 1)
        self.assertEqual(problems, [])

    def test_factory_defaults_override_and_lifecycle_data_outside_checkout(self):
        folder = self.install()
        before = {p.name: p.read_bytes() for p in folder.iterdir()}
        shell = console.build_shell(self.components, self.data, {'tool': {'message': 'overridden'}})
        self.assertEqual(shell.problems, [])
        self.assertFalse(self.data.exists())
        values = json.loads(shell.handle('GET', '/tool/api/settings')[2])
        self.assertEqual(values['settings_dir'], str(self.data / 'tool'))
        self.assertEqual(values['session_file'], 'session.json')
        self.assertEqual(values['message'], 'overridden')
        self.assertEqual(shell.tools['/tool'], 'Example Tool')
        done = threading.Event()
        shell.run('127.0.0.1', 0, done.set, stop_event=done)
        self.assertEqual((self.data / 'tool/session.json').read_text(), 'overridden')
        self.assertTrue((self.data / 'tool/stopped').is_file())
        self.assertEqual({p.name: p.read_bytes() for p in folder.iterdir()}, before)

    def test_bind_failure_creates_no_data(self):
        self.install()
        shell = console.build_shell(self.components, self.data)
        with microweb._Server(('127.0.0.1', 0), microweb.App()._handler_class()) as occupied:
            with self.assertRaises(SystemExit):
                shell.run('127.0.0.1', occupied.server_port)
        self.assertFalse(self.data.exists())

    def test_invalid_manifest_and_missing_dependency_leave_other_apps_usable(self):
        self.install()
        bad = self.components / 'bad'
        bad.mkdir()
        (bad / console.MANIFEST).write_text('not JSON')
        self.install('missing', id='missing', source='import dependency_not_installed_123456789\n')
        shell = console.build_shell(self.components, self.data)
        self.assertEqual(len(shell.components), 1)
        self.assertEqual(len(shell.problems), 2)
        body = shell.handle('GET', '/')[2]
        self.assertIn(b'Components not loaded', body)
        self.assertIn(b'dependency_not_installed', body)
        self.assertIn(b'Example Tool', body)

    def test_duplicate_ids_rejected_before_import(self):
        for name in ['first', 'second']:
            self.install(name, source="raise AssertionError('duplicate imported')")
        shell = console.build_shell(self.components, self.data)
        self.assertEqual(shell.components, [])
        self.assertIn('duplicate component id tool', shell.problems[0])

    def test_unsupported_api_and_path_like_id_are_not_imported(self):
        self.install('future', component_api=2, source="raise AssertionError('future imported')")
        self.install('unsafe', id='../outside', source="raise AssertionError('bad id imported')")
        shell = console.build_shell(self.components, self.data)
        self.assertEqual(shell.components, [])
        self.assertEqual(len(shell.problems), 2)
        self.assertFalse(self.data.exists())

    def test_factory_id_must_match_manifest(self):
        self.install(id='another')
        shell = console.build_shell(self.components, self.data)
        self.assertEqual(shell.components, [])
        self.assertIn('manifest id', shell.problems[0])

    def demo(self):
        folder = self.components / 'demo'
        shutil.copytree(Path(console.__file__).parent / 'demo_components', folder)
        # Each test gets a distinct module name; production checkouts use stable package names.
        module = 'demo_' + uuid.uuid4().hex
        (folder / 'microweb_demo_components.py').rename(folder / (module + '.py'))
        path = folder / console.MANIFEST
        path.write_text(path.read_text().replace('microweb_demo_components:', module + ':'))
        return path

    def test_one_checkout_two_ordered_panels_and_banner_on_every_shell_page(self):
        self.demo()
        shell = console.build_shell(self.components, self.data)
        self.assertEqual(shell.problems, [])
        self.assertEqual(list(shell.tools), ['/demo-library', '/demo-workbench'])
        self.assertEqual(list(shell.banners), ['/demo-machine'])
        self.assertEqual(len(shell.components), 3)
        for route in ['/', '/?tool=%2Fdemo-library', '/?tool=%2Fdemo-workbench']:
            status, _, body = shell.handle('GET', route)
            self.assertEqual(status, 200)
            self.assertIn(b'class="banner" title="Machine (demo)"', body)
            self.assertIn(b'style="height:196px"', body)
            self.assertNotIn(b'?tool=%2Fdemo-machine', body)
            self.assertLess(body.index(b'Library (demo)'), body.index(b'Workbench (demo)'))
        self.assertIn(b'fabricated metrics', shell.handle('GET', '/demo-machine/')[2])
        self.assertEqual(shell.handle('GET', '/?tool=%2Fdemo-machine')[0], 404)
        self.assertFalse(self.data.exists())
        done = threading.Event()
        shell.run('127.0.0.1', 0, done.set, stop_event=done)
        self.assertEqual(sorted(p.name for p in self.data.iterdir()),
                         ['demo-library', 'demo-machine', 'demo-workbench'])

    def test_order_across_checkouts_with_id_tiebreak_and_bad_entry_isolation(self):
        path = self.demo()
        manifest = json.loads(path.read_text())
        manifest['components'][0]['order'] = 500
        manifest['components'][1]['order'] = 30
        manifest['components'].extend([{'id': 'broken', 'placement': 'sideways'}, None])
        path.write_text(json.dumps(manifest))
        self.install(order=5)
        shell = console.build_shell(self.components, self.data)
        self.assertEqual(list(shell.tools), ['/tool', '/demo-library', '/demo-workbench'])
        self.assertEqual([c.id for c in shell.components],
                         ['tool', 'demo-library', 'demo-workbench', 'demo-machine'])
        self.assertEqual(len(shell.problems), 2)

    def test_invalid_presentation_metadata_not_imported(self):
        for name, change in [('position', {'placement': 'sideways'}),
                             ('priority', {'order': True}), ('size', {'height': -1})]:
            self.install(name, source="raise AssertionError('invalid metadata imported')", **change)
        shell = console.build_shell(self.components, self.data)
        self.assertEqual(shell.components, [])
        self.assertEqual(len(shell.problems), 3)

    def test_optional_descriptions_populate_overview_and_invalid_values_are_isolated(self):
        self.install(description='Read <local> examples')
        shell = console.build_shell(self.components, self.data)
        self.assertIn(b'Read &lt;local&gt; examples', shell.handle('GET', '/')[2])
        self.install('invalid', description={'unexpected': 'object'})
        entries, problems = console.discover(self.components)
        self.assertEqual(len(entries), 1)
        self.assertIn('description must be a string', problems[0])


if __name__ == '__main__':
    unittest.main()
