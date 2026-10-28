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
                             "tests/test_microweb.py", "tests/test_updates.py", "tests/test_components.py"]:
                shutil.copy2(upstream / relative, root / relative)
            # This fixture must work even when the outer suite is checking a release.
            fixture_source = root / "microweb.py"
            fixture_source.write_bytes(re.sub(
                rb'^__version__ = .*$', b'__version__ = "v1.0.0"',
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
            for args in [("example/microweb",), ("--repo",), ("--unknown",)]:
                invalid_args = run(bash, "scripts/release.sh", *args, check=False)
                self.assertEqual(invalid_args.returncode, 2)
            missing = run(bash, "scripts/release.sh", check=False)
            self.assertNotEqual(missing.returncode, 0)
            self.assertIn("manifest and download URLs", missing.stderr)
            self.assertIn("optional", missing.stderr)
            self.assertIn("bash scripts/release.sh --repo OWNER/REPO", missing.stderr)
            self.assertEqual(run("git", "status", "--porcelain").stdout, "")
            run("git", "remote", "add", "origin", "https://example.invalid/other/repo.git")
            unsupported = run(bash, "scripts/release.sh", check=False)
            self.assertIn("Cannot detect", unsupported.stderr)
            run("git", "remote", "set-url", "origin", "git@github.com:example/microweb.git")
            result = run(bash, "scripts/release.sh", check=False)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            manifest = json.loads((root / "microweb.version").read_bytes())
            self.assertEqual(manifest["version"], "v1.0.0")
            self.assertEqual(manifest["url"], "https://raw.githubusercontent.com/example/microweb/refs/tags/v1.0.0/microweb.py")
            self.assertEqual(run("git", "tag", "--list").stdout.strip(), "v1.0.0")
            tagged = subprocess.check_output(["git", "show", "v1.0.0:microweb.py"], cwd=root, env=env)
            self.assertEqual(manifest["sha256"], hashlib.sha256(tagged).hexdigest())
            self.assertIn(b'__version__ = "v1.0.0"', tagged)
            self.assertIn(b'/main/microweb.version"', tagged)
            self.assertEqual(run("git", "status", "--porcelain").stdout, "")
            self.assertEqual(run("git", "cat-file", "-t", "v1.0.0").stdout.strip(), "tag")
            cache_dir = root / "tests/.release-cache"
            cache_path, = cache_dir.glob("*.json")
            cached = json.loads(cache_path.read_bytes())
            self.assertTrue(cached["passed"])
            self.assertEqual(cached["sha256"], manifest["sha256"])
            self.assertEqual(cached["release_commit"], run("git", "rev-parse", "HEAD").stdout.strip(),
                             result.stdout + result.stderr + run("git", "show-ref", "--head", "-d").stdout)
            self.assertEqual(run("git", "check-ignore", "tests/.release-cache/probe").returncode, 0)
            head_before = run("git", "rev-parse", "HEAD").stdout
            tag_before = run("git", "rev-parse", "refs/tags/v1.0.0").stdout
            source_before = fixture_source.read_bytes()
            manifest_before = (root / "microweb.version").read_bytes()
            for remote in ["https://github.com/example/microweb.git", "ssh://git@github.com/example/microweb.git",
                           "git@github.com:example/microweb.git"]:
                run("git", "remote", "set-url", "origin", remote)
                duplicate = run(bash, "scripts/release.sh", check=False)
                self.assertIn("Release repository: example/microweb", duplicate.stdout)
                self.assertEqual(duplicate.returncode, 0, duplicate.stdout + duplicate.stderr)
                self.assertIn("already exists; validation only", duplicate.stdout)
                self.assertIn("bump __version__ in microweb.py", duplicate.stdout)
                self.assertIn("PASS: manifest version, download URL and SHA-256", duplicate.stdout)
                self.assertIn("PASS: cached offline tests", duplicate.stdout)
                self.assertNotIn("Running offline tests", duplicate.stdout)
                self.assertEqual(run("git", "rev-parse", "HEAD").stdout, head_before)
                self.assertEqual(run("git", "rev-parse", "refs/tags/v1.0.0").stdout, tag_before)
                self.assertEqual(fixture_source.read_bytes(), source_before)
                self.assertEqual((root / "microweb.version").read_bytes(), manifest_before)
                self.assertEqual(run("git", "status", "--porcelain").stdout, "")
            # Missing, malformed or failed cache entries run tests and get replaced only on success.
            for content in [None, b"invalid json", b'{"passed": false}']:
                if content is None:
                    cache_path.unlink()
                else:
                    cache_path.write_bytes(content)
                uncached = run(bash, "scripts/release.sh", check=False)
                self.assertEqual(uncached.returncode, 0, uncached.stdout + uncached.stderr)
                self.assertIn("Running offline tests", uncached.stdout)
                self.assertTrue(json.loads(cache_path.read_bytes())["passed"])
            # New tests invalidate a prior pass, and failures never write another pass record.
            failure = root / "tests/test_cache_failure.py"
            failure.write_text('import unittest\nclass Failure(unittest.TestCase):\n def test_fail(self): self.fail("cache fixture")\n',
                               encoding="utf-8")
            cache_before = {p.name: p.read_bytes() for p in cache_dir.glob("*.json")}
            failed = run(bash, "scripts/release.sh", check=False)
            self.assertNotEqual(failed.returncode, 0)
            self.assertIn("Running offline tests", failed.stdout)
            self.assertEqual({p.name: p.read_bytes() for p in cache_dir.glob("*.json")}, cache_before)
            failure.unlink()
            # Validation permits later tooling/docs commits but rejects changed release artifacts.
            (root / "notes.txt").write_text("Later documentation\n", encoding="utf-8")
            run("git", "add", "notes.txt")
            run("git", "commit", "-m", "Later documentation")
            self.assertEqual(run(bash, "scripts/release.sh", check=False).returncode, 0)
            for path, original, message in [
                (fixture_source, source_before, "working source matches tagged bytes"),
                (root / "microweb.version", manifest_before, "working manifest matches tagged bytes"),
            ]:
                path.write_bytes(original + b"\n")
                invalid = run(bash, "scripts/release.sh", check=False)
                self.assertNotEqual(invalid.returncode, 0)
                self.assertIn("Release validation failed: " + message, invalid.stderr)
                self.assertEqual(path.read_bytes(), original + b"\n")
                path.write_bytes(original)
            wrong_repo = run(bash, "scripts/release.sh", "--repo", "other/microweb", check=False)
            self.assertNotEqual(wrong_repo.returncode, 0)
            self.assertIn("embedded update URL", wrong_repo.stderr)
            # An explicit argument overrides an unsupported origin.
            run("git", "remote", "set-url", "origin", "https://example.invalid/other/repo.git")
            fixture_source.write_bytes(fixture_source.read_bytes().replace(b'__version__ = "v1.0.0"', b'__version__ = "v1.0.1"'))
            unstaged = run(bash, "scripts/release.sh", "--repo", "example/microweb", check=False)
            self.assertNotEqual(unstaged.returncode, 0)
            self.assertIn("unstaged tracked changes", unstaged.stderr)
            run("git", "add", "microweb.py")
            notes = root / "release-notes.txt"
            notes.write_text("Included in the release commit\n", encoding="utf-8")
            untracked = run(bash, "scripts/release.sh", "--repo", "example/microweb", check=False)
            self.assertNotEqual(untracked.returncode, 0)
            self.assertIn("untracked files remain", untracked.stderr)
            run("git", "add", "release-notes.txt")
            notes.write_text("An unstaged addition\n", encoding="utf-8")
            partial = run(bash, "scripts/release.sh", "--repo", "example/microweb", check=False)
            self.assertNotEqual(partial.returncode, 0)
            self.assertIn("unstaged tracked changes", partial.stderr)
            run("git", "add", "release-notes.txt")
            commit_count = int(run("git", "rev-list", "--count", "HEAD").stdout)
            override = run(bash, "scripts/release.sh", "--repo", "example/microweb", check=False)
            self.assertEqual(override.returncode, 0, override.stdout + override.stderr)
            self.assertEqual(json.loads((root / "microweb.version").read_bytes())["version"], "v1.0.1")
            self.assertEqual(int(run("git", "rev-list", "--count", "HEAD").stdout), commit_count + 1)
            self.assertEqual(run("git", "show", "v1.0.1:release-notes.txt").stdout, "An unstaged addition\n")
            self.assertEqual(run("git", "status", "--porcelain").stdout, "")
            # Failed tests restore the pre-release source and manifest.
            saved_tag = run("git", "rev-parse", "refs/tags/v1.0.1").stdout.strip()
            run("git", "tag", "-d", "v1.0.1")
            no_bump = run(bash, "scripts/release.sh", "--repo", "example/microweb", check=False)
            self.assertNotEqual(no_bump.returncode, 0)
            self.assertIn("bump __version__ in microweb.py above v1.0.1", no_bump.stderr)
            run("git", "update-ref", "refs/tags/v1.0.1", saved_tag)
            fixture_source.write_bytes(fixture_source.read_bytes().replace(b'__version__ = "v1.0.1"', b'__version__ = "v1.1.0"'))
            source_before = fixture_source.read_bytes()
            manifest_before = (root / "microweb.version").read_bytes()
            (root / "tests/test_failure.py").write_text(
                'import unittest\nclass Failure(unittest.TestCase):\n def test_fail(self): self.fail("fixture")\n',
                encoding="utf-8")
            run("git", "add", ".")
            staged_before = run("git", "ls-files", "--stage").stdout
            status_before = run("git", "status", "--porcelain").stdout
            head_before = run("git", "rev-parse", "HEAD").stdout
            self.assertNotEqual(run(bash, "scripts/release.sh", "--repo", "example/microweb", check=False).returncode, 0)
            self.assertEqual((root / "microweb.py").read_bytes(), source_before)
            self.assertEqual((root / "microweb.version").read_bytes(), manifest_before)
            self.assertEqual(run("git", "tag", "--list", "v1.1.0").stdout, "")
            self.assertEqual(run("git", "ls-files", "--stage").stdout, staged_before)
            self.assertEqual(run("git", "status", "--porcelain").stdout, status_before)
            self.assertEqual(run("git", "rev-parse", "HEAD").stdout, head_before)
            (root / "microweb.py").write_bytes(source_before + b"# local edit\n")
            self.assertNotEqual(run(bash, "scripts/release.sh", "--repo", "example/microweb", check=False).returncode, 0)


if __name__ == "__main__":
    unittest.main()
