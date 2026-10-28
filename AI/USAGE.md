# Assistant usage

Requests include prerequisites: complete missing setup, then perform the requested task and verify its result.
Use existing valid setup rather than reinstalling anything. See `STRATEGY.md` for this documentation pattern.

## Install / use in an application

Find Python 3.10+. Copy a released microweb.py into the consuming project and retain its embedded notice.
No third-party dependencies are needed. Verify `python microweb.py --version`, then define routes on App and run it.
Start with the minimal app in README. Introduce Shell only for an explicitly desired combined console.
Do not replace an existing modified copy without reviewing those changes.

## Smoke test

Run `python -B -m unittest discover -s tests -q` from the repository root. To inspect the console, launch the example on an unused
loopback port; check its landing page, tool view, status link, and standalone launch. Stop only your own server.
The optional console demo is `python examples/console.py`: all views are bundled. No cloning, package installation,
configuration or data directories are prerequisites. Check Library, Workbench's demo task button, and the
synthetic CPU/memory banner (no GPU features). Use `--standalone library|workbench|machine` for individual views.

For the separate advanced combined proof, use examples/downloader_console.py with an adapted downloader checkout.
Normal use defaults to ignored data/downloader-console/, created after binding and reused. For smoke verification,
supply --state-dir pointing to fresh scratch storage so existing example/user data stays untouched. Automatic
collection is disabled. Check both navigation
entries and the synthetic task; this integration launcher always hosts both components. Do not use production libraries for smoke tests. The
synthetic component needs no ML dependencies. Shutdown should leave workbench/last_shutdown.json in the
chosen state directory, with its service stopped and submitted synthetic tasks completed.

## Discover local components

The home page should show one row per loaded panel/banner, with linked names and optional purpose text.
Check banner links independently, selected-panel navigation and nested mount URLs. It reports registrations,
not health. Presentation guidance and vocabulary are in docs/shell-conventions.md.

For optional discovery, follow docs/discovery-example.md. Users install checkouts into components/; the launcher
only detects local manifests. For smoke checks use temporary component/data roots and fabricated apps or a local
copy of the intended tool. Verify empty-state guidance, load diagnostics, mounted routes and shutdown; keep data
outside checkouts. Do not install dependencies or fetch repositories unless the user separately requests it.
Use examples/demo_components as the no-dependency fixture for multiple panels from one checkout and a shared
banner. Check tab order and the banner on landing and both panel pages; its displayed Machine values are synthetic.

## Check / update

Use the explicit CLI commands in README. Checking needs network access; it must not change files.
Updating is an explicit operation: expect a backup and run the consuming application's checks after replacement.
Copies need a configured manifest URL and a valid vMAJOR.MINOR.PATCH version. Explicit --update replaces
local edits after preserving the current bytes in microweb.py.bak; no installed-file checksum gate or
old-manifest lookup is required. Downloaded checksum/version/syntax are still validated. An existing
backup is never overwritten. Same-version modified files can be restored; matching files are left alone,
and newer installed versions are not downgraded. --check-update stays read-only.

## Prepare a release

Only when requested: inspect main and configured Git identity, choose the actual OWNER/REPO,
set a new `__version__` such as `v0.1.0` in microweb.py, then stage all intended release files.
Requirements: Bash, Git, Python, an existing commit, branch main and configured Git author/committer.
Set PYTHON to select the interpreter. Windows supports Git Bash and MSYS2. Use canonical
vMAJOR.MINOR.PATCH with no development suffix, newer than the previous manifest for a new release.
Run `bash scripts/release.sh` without a preparatory commit. It rejects unstaged tracked changes and
non-ignored untracked files. Its one release commit includes all staged work and generated updates.
Failed tests restore source/manifest bytes and preserve the user's staged work.
It detects the GitHub repository from origin; `--repo OWNER/REPO` overrides detection.
Supported origin forms are GitHub HTTPS, git@github.com:OWNER/REPO.git and ssh://git@github.com/OWNER/REPO.git.
Without a usable origin or explicit argument it explains how to configure either, and changes nothing.
It reads the version from the source and creates a local commit and tag; default runs never push.
Preserve the source string exactly in the manifest and tag, including its `v` prefix.
The script sets the embedded manifest URL, hashes final UTF-8/LF source, and writes microweb.version
automatically; do not manually synchronize the manifest. A Git failure after preparation leaves files
or a local release commit available for inspection; inspect status and tags before retrying.
Verify the manifest SHA-256 matches tagged microweb.py bytes. Publishing is a separate user decision.
Rerunning the script for an existing tag performs local validation without changing release artifacts. Read its
step-by-step report; a mismatch is a failure to investigate, not permission to replace the tag. It allows
later tooling/docs commits but requires source and manifest to match the tagged release exactly.
Validation checks tag annotation/ancestry, working/tagged source and manifest bytes, LF, embedded update
URL, manifest version/download URL and SHA-256. Local validation does not confirm remote publication.
An existing tag also prints guidance to bump __version__ in microweb.py and stage it for a new release;
never replace an existing tag to publish changed source under the same version.
Successful test runs are cached in ignored tests/.release-cache/ against the source SHA-256, release
commit, test/script/example inputs and interpreter. Matching passes skip tests; integrity validation
always runs. Missing/invalid/mismatched cache entries run tests normally. Failures are not cached.
Remove that directory for a fresh run. New releases always run tests before committing.

## Publish a release

Only when the user explicitly requests publishing/pushing: use `bash scripts/release.sh --push`, optionally
with `--repo OWNER/REPO`. Installing/configuring gh is separate setup; verify Git authentication and
`gh auth login` before publishing. The script checks gh authentication before preparing a new release.
It completes the same staged local release workflow (or validates an existing one), then requires clean
main, pushes main and the selected tag atomically without force, and creates a GitHub release with
generated notes. The only uploaded asset is microweb.py; microweb.version stays in Git only.
It downloads that asset to verify its checksum. Origin's push URL is used only if it matches the selected
GitHub repo; an override otherwise uses that repo's HTTPS URL. Do not silently publish to another repo.

Retry --push after a partial failure: local release history is retained, existing published releases
are reused, missing microweb.py is uploaded, and matching assets are only verified. Different existing
asset bytes fail without replacement. An existing draft must be explicitly published before retrying.
Do not bump again just to recover a publishing failure. No --push means no gh/network/publishing calls.
Verify publishing code with mocked commands and disposable repositories; never test against a real
remote without the user's explicit authorization to publish that release.
