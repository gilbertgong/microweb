import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


class WorkbenchTests(unittest.TestCase):
    def test_read_only_join_and_owned_worker_shutdown(self):
        source = Path(__file__).resolve().parents[1] / 'examples/synthetic_workbench.py'
        spec = importlib.util.spec_from_file_location('synthetic_workbench_example', source)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            reader = root / 'downloads/1'
            reader.mkdir(parents=True)
            (reader / 'sample.wav').write_bytes(b'synthetic fixture')
            state = reader / 'state.json'
            state.write_text(json.dumps({'reader_id': '1', 'candidates': [
                {'title': 'Example', 'download': {'status': 'done', 'quality': '128', 'file': 'sample.wav'}},
                {'title': 'Missing', 'download': {'status': 'done', 'file': 'missing.wav'}},
                {'title': 'Rejected', 'decision': 'reject', 'download': {'status': 'done', 'file': 'sample.wav'}},
                {'title': 'Escapes reader', 'download': {'status': 'done', 'file': '../../outside.wav'}},
            ]}))
            before = hashlib.sha256(state.read_bytes()).hexdigest()
            component = module.create_component({'data_dir': root / 'workbench', 'download_sources': [reader.parent]})
            self.assertFalse((root / 'workbench').exists())
            component.start()
            try:
                data = json.loads(component.app.handle('GET', '/api/status')[2])
                self.assertEqual([r['title'] for r in data['recordings']], ['Example'])
                self.assertEqual(component.app.handle('POST', '/api/work', b'{}')[0], 202)
            finally:
                component.stop()
            saved = json.loads((root / 'workbench/last_shutdown.json').read_text())
            self.assertEqual(saved, {'service': 'stopped', 'completed': [{'recordings_seen': 1}]})
            self.assertEqual(hashlib.sha256(state.read_bytes()).hexdigest(), before)


if __name__ == '__main__':
    unittest.main()
