# Assistant usage

Requests include prerequisites: complete missing setup, then perform the requested task and verify its result.
Use existing valid setup rather than reinstalling anything. See `STRATEGY.md` for this documentation pattern.

## Install / use in an application

Find Python 3.10+. Copy a released microweb.py into the consuming project and retain its embedded notice.
No third-party dependencies are needed. Verify `python microweb.py --version`, then define routes on App and run it.
Start with the minimal app in README. Introduce Shell only for an explicitly desired combined console.
Do not replace an existing modified copy without reviewing those changes.

## Smoke test

Run the offline unittest discovery command in README. To inspect the console, launch the example on an unused
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
Development copies cannot self-update until released. Never silently force past local modifications.

## Prepare a release

Only when requested: inspect a clean committed main and configured Git identity, choose the actual OWNER/REPO,
set and commit a new `__version__` such as `v0.1.0` in microweb.py, then run `bash scripts/release.sh`.
It detects the GitHub repository from origin; an optional OWNER/REPO argument overrides detection.
Without a usable origin or explicit argument it explains how to configure either, and changes nothing.
It reads the version from the source and creates a local commit and tag without pushing.
Preserve the source string exactly in the manifest and tag, including its `v` prefix.
Verify the manifest SHA-256 matches tagged microweb.py bytes. Publishing is a separate user decision.
