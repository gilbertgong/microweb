"""Exercise publishing orchestration without invoking Git, gh or the network."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock


class PublishTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        source = Path(self.temp.name) / "microweb.py"
        source.write_bytes(b'__version__ = "v1.0.0"\n')
        script = (Path(__file__).resolve().parents[1] / "scripts/release.sh").read_text(encoding="utf-8")
        code = script.split("<<'PY'\n", 1)[1].split("parser = argparse.ArgumentParser", 1)[0]
        self.ns = {}
        exec(compile(code, "release.sh helpers", "exec"), self.ns)
        # Replace the subprocess binding itself so no real process can run in these tests.
        self.process = Mock()
        self.process.run.return_value = SimpleNamespace(
            returncode=0, stdout="git@github.com:example/microweb.git\n")
        self.gh = Mock(return_value=SimpleNamespace(stdout=source.read_bytes()))
        self.release = {"assets": [{"name": "microweb.py"}], "draft": False,
                        "html_url": "https://github.com/example/microweb/releases/tag/v1.0.0"}
        self.remote = Mock(return_value=self.release)
        self.ns.update(source=source, repository="example/microweb", tag="v1.0.0",
                       git=Mock(side_effect=lambda *args: "main" if args[0] == "branch" else ""),
                       subprocess=self.process, gh=self.gh, remote_release=self.remote, report=Mock())

    def publish(self):
        self.ns["publish_release"]()

    def test_create_release_attaches_only_runtime_after_atomic_push(self):
        self.remote.side_effect = [None, self.release]
        self.publish()
        self.process.run.assert_any_call(
            ["git", "push", "--atomic", "git@github.com:example/microweb.git",
             "refs/heads/main:refs/heads/main", "refs/tags/v1.0.0:refs/tags/v1.0.0"], check=True)
        self.gh.assert_any_call("release", "create", "v1.0.0", "microweb.py", "--repo", "example/microweb",
                                "--verify-tag", "--title", "v1.0.0", "--generate-notes")
        self.assertNotIn("microweb.version", str(self.gh.call_args_list))
        self.assertEqual(self.gh.call_args_list[-1].args[1], "download")

    def test_retry_with_existing_matching_attachment_only_verifies(self):
        self.publish()
        self.assertEqual(self.gh.call_count, 1)
        self.assertEqual(self.gh.call_args.args[1], "download")

    def test_retry_uploads_missing_attachment(self):
        self.release["assets"] = []
        self.publish()
        self.gh.assert_any_call("release", "upload", "v1.0.0", "microweb.py", "--repo", "example/microweb")
        self.assertNotIn("--clobber", str(self.gh.call_args_list))

    def test_mismatching_attachment_is_not_overwritten(self):
        self.gh.return_value.stdout = b"different bytes"
        with self.assertRaisesRegex(SystemExit, "refusing to replace"):
            self.publish()
        self.assertEqual(self.gh.call_count, 1)

    def test_override_or_different_origin_pushurl_uses_selected_repository(self):
        self.process.run.return_value.stdout = "git@github.com:other/repo.git\n"
        self.publish()
        push = self.process.run.call_args_list[-1].args[0]
        self.assertEqual(push[3], "https://github.com/example/microweb.git")

    def test_failed_push_does_not_create_release(self):
        self.process.run.side_effect = [SimpleNamespace(stdout="git@github.com:example/microweb.git\n"),
                                        subprocess.CalledProcessError(1, ["git", "push"])]
        with self.assertRaises(subprocess.CalledProcessError):
            self.publish()
        self.remote.assert_not_called()
        self.gh.assert_not_called()

    def test_pending_changes_or_wrong_branch_do_not_push(self):
        for branch, status in [("main", "M file"), ("feature", "")]:
            self.ns["git"].side_effect = lambda *args: branch if args[0] == "branch" else status
            with self.assertRaisesRegex(SystemExit, "clean main"):
                self.publish()
        self.process.run.assert_not_called()

    def test_existing_draft_is_not_silently_published(self):
        self.release["draft"] = True
        with self.assertRaisesRegex(SystemExit, "draft"):
            self.publish()
        self.gh.assert_not_called()

    def test_query_only_treats_http_404_as_missing_release(self):
        # Use the real helper, with only its subprocess dependency mocked.
        script = (Path(__file__).resolve().parents[1] / "scripts/release.sh").read_text(encoding="utf-8")
        code = script.split("<<'PY'\n", 1)[1].split("parser = argparse.ArgumentParser", 1)[0]
        helper = {}
        exec(compile(code, "release.sh helpers", "exec"), helper)
        helper.update(subprocess=self.process, repository="example/microweb", tag="v1.0.0")
        self.process.run.return_value = SimpleNamespace(returncode=1, stderr=b"gh: Not Found (HTTP 404)")
        self.assertIsNone(helper["remote_release"]())
        self.process.run.return_value.stderr = b"network unavailable"
        with self.assertRaisesRegex(SystemExit, "Cannot inspect GitHub release"):
            helper["remote_release"]()


if __name__ == "__main__":
    unittest.main()
