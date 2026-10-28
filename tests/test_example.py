"""The primary demo runs with stdlib Python and bundled files only."""
import shutil
import importlib.util
import subprocess
import sys
import tempfile
import unittest
import types
from pathlib import Path
from unittest.mock import patch

from microweb import App, Component, _Server


class ExampleTests(unittest.TestCase):
    def integration_launcher(self):
        examples = Path(__file__).resolve().parents[1] / 'examples'
        spec = importlib.util.spec_from_file_location('downloader_example', examples/'downloader_console.py')
        module = importlib.util.module_from_spec(spec)
        with patch.object(sys, 'path', [str(examples)] + sys.path):
            spec.loader.exec_module(module)
        return module

    def test_advanced_example_prepares_storage_after_bind_and_delegates_cleanup(self):
        import threading
        launcher = self.integration_launcher()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)/'state'
            events = []
            tool = Component('test','Test',App(),
                             lambda: events.append(('start',root.is_dir())),lambda:events.append(('stop',True)))
            prepared = launcher.prepare_state(tool,root)
            self.assertFalse(root.exists())
            with _Server(('127.0.0.1',0),App()._handler_class()) as occupied:
                with self.assertRaises(SystemExit):
                    prepared.run('127.0.0.1',occupied.server_port)
            self.assertFalse(root.exists())
            done = threading.Event()
            prepared.run('127.0.0.1',0,done.set,stop_event=done)
            self.assertEqual(events,[('start',True),('stop',True)])

    def test_advanced_example_default_state_needs_no_flag_or_directory_creation(self):
        launcher = self.integration_launcher()
        args = launcher.parse_args(['--downloader-dir',str(launcher.ROOT)])
        self.assertEqual(args.state_dir,launcher.ROOT/'data/downloader-console')
        fake = types.ModuleType('librivox_web')
        fake.create_component = lambda settings: Component('downloads','Downloads',App())
        with patch.object(sys,'argv',['downloader_console.py','--downloader-dir',str(launcher.ROOT)]), \
             patch.dict(sys.modules,{'librivox_web':fake}), \
             patch.object(sys,'path',list(sys.path)), \
             patch.object(launcher,'prepare_state',wraps=launcher.prepare_state) as prepare, \
             patch.object(launcher.Shell,'run',autospec=True) as run:
            launcher.main()
        self.assertEqual(prepare.call_args.args[1],launcher.ROOT/'data/downloader-console')
        self.assertEqual(list(run.call_args.args[0].tools),['/downloads','/voices'])

    def test_copied_example_without_packages_or_other_workspace_projects(self):
        upstream = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'microweb'
            (root / 'examples').mkdir(parents=True)
            shutil.copy2(upstream / 'microweb.py', root / 'microweb.py')
            shutil.copy2(upstream / 'examples/console.py', root / 'examples/console.py')
            shutil.copytree(upstream / 'examples/demo_components', root / 'examples/demo_components',
                            ignore=shutil.ignore_patterns('__pycache__'))
            before = {p.relative_to(root):p.read_bytes() for p in root.rglob('*') if p.is_file()}
            code = '''import importlib.util,json,sys
spec=importlib.util.spec_from_file_location('bundled_example',sys.argv[1])
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
shell=module.build_shell()
assert list(shell.tools)==['/demo-library','/demo-workbench']
assert list(shell.banners)==['/demo-machine']
assert shell.handle('GET','/')[0]==200
assert shell.handle('GET','/demo-library/')[0]==200
assert shell.handle('GET','/demo-machine/')[0]==200
data=json.loads(shell.handle('GET','/demo-machine/api/machine')[2])
assert 'cpu' in data and 'memory' in data and 'gpus' not in data
assert shell.handle('POST','/demo-workbench/api/run')[0]==200
assert len(json.loads(shell.handle('GET','/demo-workbench/api/status')[2])['completed'])==1
assert not any(n in sys.modules for n in ['numpy','psutil','torch','kokoro'])
assert module.demo.library({}).app.handle('GET','/')[0]==200
'''
            run = subprocess.run([sys.executable,'-S','-B','-c',code,str(root/'examples/console.py')],
                                 cwd=tmp,capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)
            self.assertEqual(before,{p.relative_to(root):p.read_bytes() for p in root.rglob('*') if p.is_file()})

    def test_standalone_cli_help_needs_no_packages(self):
        source = Path(__file__).resolve().parents[1] / 'examples/console.py'
        run = subprocess.run([sys.executable,'-S','-B',str(source),'--help'],
                             capture_output=True,text=True)
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertIn('library,workbench,machine',run.stdout)


if __name__ == '__main__':
    unittest.main()
