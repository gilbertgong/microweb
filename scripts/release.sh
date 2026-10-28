#!/usr/bin/env bash
# Usage: bash scripts/release.sh [--repo OWNER/REPO]
# Creates or validates a LOCAL release commit and annotated tag. Never pushes.
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONDONTWRITEBYTECODE=1
"${PYTHON:-python}" - "$@" <<'PY'
import ast
import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

def git(*args):
    return subprocess.check_output(["git", *args], text=True).strip()

def report(message):
    print(message, flush=True)

def release_commit():
    # Avoid ^{}: MSYS2 Git can glob its braces when invoked from native Python.
    return git("rev-list", "-n", "1", f"refs/tags/{tag}")

def run_tests():
    report(f"Running offline tests with {sys.executable} ...")
    subprocess.run([sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-q"], check=True)
    report("PASS: offline tests")

def test_cache():
    # Include the current test/tool/example inputs and interpreter: a source checksum alone
    # would otherwise hide failures introduced after the release was tagged.
    inputs = hashlib.sha256()
    paths = subprocess.check_output(["git", "ls-files", "-co", "--exclude-standard", "-z"])
    for name in sorted(set(paths.decode("utf-8").split("\0"))):
        if name.startswith(("tests/", "scripts/", "examples/")) and Path(name).is_file():
            inputs.update(name.encode("utf-8") + b"\0")
            content = Path(name).read_bytes()
            inputs.update(len(content).to_bytes(8, "big") + content)
    state = {"schema": 1, "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
             "release_commit": release_commit(),
             "test_inputs_sha256": inputs.hexdigest(),
             "python": sys.version, "executable": sys.executable}
    key = hashlib.sha256(json.dumps(state, sort_keys=True).encode("utf-8")).hexdigest()
    return Path("tests/.release-cache") / f"{key}.json", state

def save_test_pass(path, state):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path.parent, mode="w", encoding="utf-8",
                                         newline="\n", delete=False) as cache_file:
            temporary = Path(cache_file.name)
            json.dump({"passed": True, **state}, cache_file, indent=2)
            cache_file.write("\n")
        temporary.replace(path)
        report(f"Saved test pass: {path}")
    except OSError as error:
        report(f"Warning: could not save test pass: {error}")
    finally:
        if "temporary" in locals():
            temporary.unlink(missing_ok=True)

def cached_tests():
    path, state = test_cache()
    try:
        cached = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cached = None
    if cached == {"passed": True, **state}:
        report(f"PASS: cached offline tests ({path})")
        return
    report("No matching test pass cached; running tests normally.")
    run_tests()
    save_test_pass(path, state)

def validate_release():
    report(f"Validating local release {tag} ...")
    def require(condition, message):
        if not condition:
            sys.exit(f"Release validation failed: {message}")
        report(f"PASS: {message}")
    require(git("cat-file", "-t", f"refs/tags/{tag}") == "tag", "annotated release tag")
    require(subprocess.run(["git", "merge-base", "--is-ancestor", release_commit(), "HEAD"]).returncode == 0,
            "release commit belongs to current history")
    tagged_source = subprocess.check_output(["git", "show", f"refs/tags/{tag}:microweb.py"])
    tagged_manifest = subprocess.check_output(["git", "show", f"refs/tags/{tag}:microweb.version"])
    require(source.read_bytes() == tagged_source, "working source matches tagged bytes")
    require(manifest_path.exists() and manifest_path.read_bytes() == tagged_manifest,
            "working manifest matches tagged bytes")
    require(b"\r" not in tagged_source, "tagged source uses LF")
    expected_source, count = re.subn(r'^UPDATE_URL = .*$', f'UPDATE_URL = "{raw}/main/microweb.version"',
                                    tagged_source.decode("utf-8"), count=1, flags=re.M)
    require(count == 1 and expected_source.encode("utf-8") == tagged_source, "embedded update URL")
    expected = {"version": version, "url": f"{raw}/refs/tags/{tag}/microweb.py",
                "sha256": hashlib.sha256(tagged_source).hexdigest()}
    require(json.loads(tagged_manifest) == expected, "manifest version, download URL and SHA-256")
    report(f"Release commit: {release_commit()}")
    report(f"SHA-256: {expected['sha256']}")

parser = argparse.ArgumentParser(description="Create or validate a local microweb release. Never pushes.")
parser.add_argument("--repo", metavar="OWNER/REPO", help="GitHub repository (defaults to origin)")
repository = parser.parse_args().repo
if repository is None:
    origin = subprocess.run(["git", "remote", "get-url", "origin"], text=True, capture_output=True)
    remote = origin.stdout.strip().rstrip("/") if origin.returncode == 0 else ""
    match = re.fullmatch(r"(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)", remote)
    if not match:
        sys.exit(
            "Cannot detect a GitHub OWNER/REPO from origin (missing or unsupported remote).\n"
            "This identifies the GitHub repository used for the release manifest and download URLs.\n"
            "OWNER/REPO is optional when origin is a GitHub HTTPS or SSH URL.\n"
            "Either configure it: git remote add origin https://github.com/OWNER/REPO.git\n"
            "Or supply it explicitly: bash scripts/release.sh --repo OWNER/REPO\n"
            "No remote or files have been changed."
        )
    repository = match.group(1).removesuffix(".git")
if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
    sys.exit("Repository must be OWNER/REPO")
print(f"Release repository: {repository}", flush=True)
source = Path("microweb.py")
original = source.read_bytes()
text = original.decode("utf-8")
versions = [node.value.value for node in ast.parse(text).body
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)
            and any(isinstance(name, ast.Name) and name.id == "__version__" for name in node.targets)]
if len(versions) != 1 or not isinstance(versions[0], str):
    sys.exit("microweb.py must define one literal __version__ string")
version = versions[0]
if not re.fullmatch(r"v(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)", version):
    sys.exit("Set __version__ in microweb.py to vMAJOR.MINOR.PATCH, without a development suffix")
report(f"Source version / tag: {version} (used unchanged)")
tag = version
raw = f"https://raw.githubusercontent.com/{repository}"
manifest_path = Path("microweb.version")
if git("tag", "--list", tag):
    report(f"Release {tag} already exists; validation only. Release files, commits and tags stay unchanged.")
    report("To generate a new release, bump __version__ in microweb.py and stage your changes first.")
    validate_release()
    cached_tests()
    report(f"Validated {tag} locally. No network requests or pushes performed.")
    sys.exit(0)
report("Checking prerequisites for a new release ...")
if subprocess.run(["git", "diff", "--quiet", "--"]).returncode != 0:
    sys.exit("Stage all intended changes before releasing; unstaged tracked changes remain (git diff).")
if git("ls-files", "--others", "--exclude-standard"):
    sys.exit("Stage intended new files or ignore unrelated files before releasing; untracked files remain.")
git("rev-parse", "--verify", "HEAD")
if git("branch", "--show-current") != "main":
    sys.exit("Create releases on main; its manifest announces the latest release")
git("var", "GIT_AUTHOR_IDENT")
git("var", "GIT_COMMITTER_IDENT")
old_manifest = manifest_path.read_bytes() if manifest_path.exists() else None
if old_manifest is not None:
    previous = json.loads(old_manifest)["version"]
    if tuple(map(int, version[1:].split("."))) <= tuple(map(int, previous[1:].split("."))):
        sys.exit("To generate a new release, bump __version__ in microweb.py above "
                 f"{previous}, then stage the change.")
report("PASS: staged working changes, main, Git identity, unused tag and increasing version")
report("The release commit will include all staged changes plus the generated source/manifest updates.")
text, count = re.subn(r'^UPDATE_URL = .*$', f'UPDATE_URL = "{raw}/main/microweb.version"', text, count=1, flags=re.M)
assert count == 1
data = text.replace("\r\n", "\n").encode("utf-8")
manifest = {
    "version": version,
    "url": f"{raw}/refs/tags/{tag}/microweb.py",
    "sha256": hashlib.sha256(data).hexdigest(),
}
try:
    report(f"Preparing embedded update URL and {manifest_path} ...")
    source.write_bytes(data)
    manifest_path.write_bytes((json.dumps(manifest, indent=2) + "\n").encode("utf-8"))
    report(f"Prepared SHA-256: {manifest['sha256']}")
    run_tests()
except BaseException:
    report("Preparation failed; restoring the previous source and manifest.")
    source.write_bytes(original)
    if old_manifest is None:
        manifest_path.unlink(missing_ok=True)
    else:
        manifest_path.write_bytes(old_manifest)
    raise
# Failures from here leave the prepared files/commit available for inspection.
git("add", "--", "microweb.py", "microweb.version")
report(f"Creating local release commit and annotated tag {tag} ...")
subprocess.run(["git", "commit", "-m", f"Release {tag}"], check=True)
subprocess.run(["git", "tag", "-a", tag, "-m", f"microweb {version}"], check=True)
validate_release()
save_test_pass(*test_cache())
print(f"Created {tag} locally. SHA-256: {manifest['sha256']}")
print(f"Review, then publish together: git push --atomic origin main refs/tags/{tag}")
PY
