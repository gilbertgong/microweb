#!/usr/bin/env bash
# Usage: bash scripts/release.sh [OWNER/REPO]
# Creates a LOCAL release commit and annotated tag. Never pushes.
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ $# -gt 1 ]]; then
    echo 'Usage: bash scripts/release.sh [OWNER/REPO] (defaults to GitHub origin; version comes from microweb.py)' >&2
    exit 2
fi
export PYTHONDONTWRITEBYTECODE=1
"${PYTHON:-python}" - "$@" <<'PY'
import ast
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

def git(*args):
    return subprocess.check_output(["git", *args], text=True).strip()

repository = sys.argv[1] if len(sys.argv) > 1 else None
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
            "Or supply it explicitly: bash scripts/release.sh OWNER/REPO\n"
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
if git("status", "--porcelain"):
    sys.exit("Commit or stash working-tree changes before creating a release")
git("rev-parse", "--verify", "HEAD")
if git("branch", "--show-current") != "main":
    sys.exit("Create releases on main; its manifest announces the latest release")
git("var", "GIT_AUTHOR_IDENT")
git("var", "GIT_COMMITTER_IDENT")
tag = version
if git("tag", "--list", tag):
    sys.exit(f"Tag already exists: {tag}")
manifest_path = Path("microweb.version")
old_manifest = manifest_path.read_bytes() if manifest_path.exists() else None
if old_manifest is not None:
    previous = json.loads(old_manifest)["version"]
    if tuple(map(int, version[1:].split("."))) <= tuple(map(int, previous[1:].split("."))):
        sys.exit("__version__ must be newer than the previous release manifest")
raw = f"https://raw.githubusercontent.com/{repository}"
text, count = re.subn(r'^UPDATE_URL = .*$', f'UPDATE_URL = "{raw}/main/microweb.version"', text, count=1, flags=re.M)
assert count == 1
data = text.replace("\r\n", "\n").encode("utf-8")
manifest = {
    "version": version,
    "url": f"{raw}/refs/tags/{tag}/microweb.py",
    "sha256": hashlib.sha256(data).hexdigest(),
}
try:
    source.write_bytes(data)
    manifest_path.write_bytes((json.dumps(manifest, indent=2) + "\n").encode("utf-8"))
    subprocess.run([sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-q"], check=True)
except BaseException:
    source.write_bytes(original)
    if old_manifest is None:
        manifest_path.unlink(missing_ok=True)
    else:
        manifest_path.write_bytes(old_manifest)
    raise
# Failures from here leave the prepared files/commit available for inspection.
git("add", "--", "microweb.py", "microweb.version")
subprocess.run(["git", "commit", "-m", f"Release {tag}"], check=True)
subprocess.run(["git", "tag", "-a", tag, "-m", f"microweb {version}"], check=True)
print(f"Created {tag} locally. SHA-256: {manifest['sha256']}")
print(f"Review, then publish together: git push --atomic origin main refs/tags/{tag}")
PY
