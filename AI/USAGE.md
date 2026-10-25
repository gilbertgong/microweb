# Assistant usage

Requests include prerequisites: complete missing setup, then perform the requested task and verify its result.
Use existing valid setup rather than reinstalling anything. See `STRATEGY.md` for this documentation pattern.

## Install / use in an application

Find Python 3.10+. Copy a released microweb.py into the consuming project and retain its embedded notice.
No third-party dependencies are needed. Verify `python microweb.py --version`, then use App or Shell.
Do not replace an existing modified copy without reviewing those changes.

## Smoke test

Run the offline unittest discovery command in README. To inspect the console, launch the example on an unused
loopback port; check its landing page, tool view, status link, and standalone launch. Stop only your own server.

For the combined proof, use examples/downloader_console.py with an adapted downloader checkout and a fresh
existing empty state directory, following README. Automatic collection is disabled. Check both navigation
entries, the synthetic task, and --standalone modes; do not use production libraries for smoke tests. The
synthetic component needs no ML dependencies. Shutdown should leave workbench/last_shutdown.json in the
chosen state directory, with its service stopped and submitted synthetic tasks completed.

## Check / update

Use the explicit CLI commands in README. Checking needs network access; it must not change files.
Updating is an explicit operation: expect a backup and run the consuming application's checks after replacement.
Development copies cannot self-update until released. Never silently force past local modifications.

## Prepare a release

Only when requested: inspect a clean committed main and configured Git identity, choose the actual OWNER/REPO,
set and commit a new numeric `__version__` in microweb.py, then run `bash scripts/release.sh`.
It detects the GitHub repository from origin; an optional OWNER/REPO argument overrides detection.
Without a usable origin or explicit argument it explains how to configure either, and changes nothing.
It reads the version from the source and creates a local commit and tag without pushing.
Verify the manifest SHA-256 matches tagged microweb.py bytes. Publishing is a separate user decision.
