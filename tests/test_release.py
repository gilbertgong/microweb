"""Exercise release commits and tags only in a disposable repository."""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class ReleaseTests(unittest.TestCase):
    def test_release_manifest_tag_and_failure_paths(self):
        bash = shutil.which("bash")
        if not bash and os.name == "nt":
            candidate = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Git/bin/bash.exe"
            if candidate.exists():
                bash = str(candidate)
        if not bash or not shutil.which("git"):
            self.skipTest("release integration test requires Bash and Git")
        upstream = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "scripts").mkdir()
            (root / "tests").mkdir()
            for relative in ["microweb.py", ".gitattributes", ".gitignore", "scripts/release.sh",
                             "tests/test_microweb.py", "tests/test_updates.py"]:
                shutil.copy2(upstream / relative, root / relative)
            # This fixture must work even when the outer suite is checking a release.
            fixture_source = root / "microweb.py"
            fixture_source.write_bytes(re.sub(
                rb'^__version__ = .*$', b'__version__ = "1.0.0"',
                fixture_source.read_bytes(), count=1, flags=re.M))
            # Do not copy this test: the release script runs the copied suite.
            env = dict(os.environ, PYTHON=sys.executable.replace("\\", "/"),
                       GIT_AUTHOR_NAME="Release test", GIT_AUTHOR_EMAIL="test@example.invalid",
                       GIT_COMMITTER_NAME="Release test", GIT_COMMITTER_EMAIL="test@example.invalid")
            def run(*args, check=True):
                return subprocess.run(args, cwd=root, env=env, text=True, capture_output=True, check=check)
            run("git", "init", "-b", "main")
            run("git", "config", "core.autocrlf", "false")
            run("git", "add", ".")
            run("git", "commit", "-m", "Initial fixture")
            missing = run(bash, "scripts/release.sh", check=False)
            self.assertNotEqual(missing.returncode, 0)
            self.assertIn("manifest and download URLs", missing.stderr)
            self.assertIn("optional", missing.stderr)
            self.assertIn("bash scripts/release.sh OWNER/REPO", missing.stderr)
            self.assertEqual(run("git", "status", "--porcelain").stdout, "")
            run("git", "remote", "add", "origin", "https://example.invalid/other/repo.git")
            unsupported = run(bash, "scripts/release.sh", check=False)
            self.assertIn("Cannot detect", unsupported.stderr)
            run("git", "remote", "set-url", "origin", "git@github.com:example/microweb.git")
            result = run(bash, "scripts/release.sh", check=False)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            manifest = json.loads((root / "microweb.version").read_bytes())
            tagged = subprocess.check_output(["git", "show", "v1.0.0:microweb.py"], cwd=root, env=env)
            self.assertEqual(manifest["sha256"], hashlib.sha256(tagged).hexdigest())
            self.assertIn(b'__version__ = "1.0.0"', tagged)
            self.assertIn(b'/main/microweb.version"', tagged)
            self.assertEqual(run("git", "status", "--porcelain").stdout, "")
            self.assertEqual(run("git", "cat-file", "-t", "v1.0.0").stdout.strip(), "tag")
            self.assertNotEqual(run(bash, "scripts/release.sh", "example/microweb", check=False).returncode, 0)
            for remote in ["https://github.com/example/microweb.git", "ssh://git@github.com/example/microweb.git",
                           "git@github.com:example/microweb.git"]:
                run("git", "remote", "set-url", "origin", remote)
                duplicate = run(bash, "scripts/release.sh", check=False)
                self.assertIn("Release repository: example/microweb", duplicate.stdout)
                self.assertIn("Tag already exists: v1.0.0", duplicate.stderr)
            # An explicit argument overrides an unsupported origin.
            run("git", "remote", "set-url", "origin", "https://example.invalid/other/repo.git")
            fixture_source.write_bytes(fixture_source.read_bytes().replace(b'__version__ = "1.0.0"', b'__version__ = "1.0.1"'))
            run("git", "add", "microweb.py")
            run("git", "commit", "-m", "Set next fixture version")
            override = run(bash, "scripts/release.sh", "example/microweb", check=False)
            self.assertEqual(override.returncode, 0, override.stdout + override.stderr)
            self.assertEqual(json.loads((root / "microweb.version").read_bytes())["version"], "1.0.1")
            # Failed tests restore the pre-release source and manifest.
            fixture_source.write_bytes(fixture_source.read_bytes().replace(b'__version__ = "1.0.1"', b'__version__ = "1.1.0"'))
            source_before = fixture_source.read_bytes()
            manifest_before = (root / "microweb.version").read_bytes()
            (root / "tests/test_failure.py").write_text(
                'import unittest\nclass Failure(unittest.TestCase):\n def test_fail(self): self.fail("fixture")\n',
                encoding="utf-8")
            run("git", "add", ".")
            run("git", "commit", "-m", "Introduce fixture failure")
            self.assertNotEqual(run(bash, "scripts/release.sh", "example/microweb", check=False).returncode, 0)
            self.assertEqual((root / "microweb.py").read_bytes(), source_before)
            self.assertEqual((root / "microweb.version").read_bytes(), manifest_before)
            self.assertEqual(run("git", "tag", "--list", "v1.1.0").stdout, "")
            self.assertEqual(run("git", "status", "--porcelain").stdout, "")
            (root / "microweb.py").write_bytes(source_before + b"# local edit\n")
            self.assertNotEqual(run(bash, "scripts/release.sh", "example/microweb", check=False).returncode, 0)


if __name__ == "__main__":
    unittest.main()
