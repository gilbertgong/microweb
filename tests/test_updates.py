import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import microweb


class UpdateTests(unittest.TestCase):
    def test_release_version_format(self):
        self.assertEqual(microweb._version_parts("v0.1.0"), (0, 1, 0))
        for version in ["0.1.0", "vv0.1.0", "v01.1.0", "v0.1.0.dev1"]:
            with self.subTest(version=version), self.assertRaises(ValueError):
                microweb._version_parts(version)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.target = Path(self.temp.name) / "microweb.py"
        self.original = b'__version__ = "v1.0.0"\n'
        self.incoming = b'__version__ = "v1.1.0"\n'
        self.target.write_bytes(self.original)
        self.old = {"version": "v1.0.0", "sha256": hashlib.sha256(self.original).hexdigest()}
        self.latest = {"version": "v1.1.0", "url": "https://example.test/v1.1.0/microweb.py",
                       "sha256": hashlib.sha256(self.incoming).hexdigest()}
        self.version_patch = patch.object(microweb, "__version__", "v1.0.0")
        self.url_patch = patch.object(microweb, "UPDATE_URL", "https://raw.githubusercontent.com/example/microweb/main/microweb.version")
        self.version_patch.start()
        self.url_patch.start()

    def tearDown(self):
        self.version_patch.stop()
        self.url_patch.stop()
        self.temp.cleanup()

    def install(self, incoming=None):
        responses = [json.dumps(self.old).encode(), self.incoming if incoming is None else incoming]
        with patch.object(microweb, "_download", side_effect=responses) as download:
            result = microweb.install_update(self.latest, self.target)
        return result, download

    def test_check_does_not_write(self):
        with patch.object(microweb, "_download", return_value=json.dumps(self.latest).encode()):
            self.assertEqual(microweb.check_update(), self.latest)
        self.assertEqual(self.target.read_bytes(), self.original)

    def test_update_backup_and_old_tag(self):
        result, download = self.install()
        self.assertTrue(result)
        self.assertEqual(self.target.read_bytes(), self.incoming)
        self.assertEqual(self.target.with_suffix(".py.bak").read_bytes(), self.original)
        self.assertIn("/refs/tags/v1.0.0/", download.call_args_list[0].args[0])

    def test_modified_copy_refused(self):
        self.target.write_bytes(self.original + b"# local changes\n")
        with self.assertRaisesRegex(ValueError, "modifications"):
            self.install()
        self.assertFalse(self.target.with_suffix(".py.bak").exists())

    def test_bad_checksum_refused(self):
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            self.install(b"bad bytes")
        self.assertEqual(self.target.read_bytes(), self.original)

    def test_version_mismatch_and_syntax(self):
        for data in [b'__version__ = "v9.0.0"\n', b"invalid python !!!"]:
            self.latest["sha256"] = hashlib.sha256(data).hexdigest()
            with self.assertRaises((ValueError, SyntaxError)):
                self.install(data)
            self.assertEqual(self.target.read_bytes(), self.original)

    def test_existing_backup_preserved(self):
        backup = self.target.with_suffix(".py.bak")
        backup.write_bytes(b"previous backup")
        with self.assertRaisesRegex(ValueError, "backup already exists"):
            self.install()
        self.assertEqual(backup.read_bytes(), b"previous backup")

    def test_same_or_older_no_download(self):
        for version in ["v1.0.0", "v0.9.0"]:
            with patch.object(microweb, "_download") as download:
                self.assertFalse(microweb.install_update({"version": version}, self.target))
                download.assert_not_called()

    def test_replace_failure_leaves_backup_and_original(self):
        with patch.object(Path, "replace", side_effect=OSError("test replacement failure")):
            with self.assertRaises(OSError):
                self.install()
        self.assertEqual(self.target.read_bytes(), self.original)
        self.assertEqual(self.target.with_suffix(".py.bak").read_bytes(), self.original)
        self.assertFalse(list(self.target.parent.glob(".microweb-*")))

    def test_development_no_network(self):
        with patch.object(microweb, "UPDATE_URL", ""), patch.object(microweb, "_download") as download:
            with self.assertRaisesRegex(ValueError, "development copy"):
                microweb.check_update()
            download.assert_not_called()


if __name__ == "__main__":
    unittest.main()
