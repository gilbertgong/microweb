# Current state

## Goal and approach

A Flask-style web server distributed as one standard-library Python file. The primary workflow is to copy
microweb.py beside an application, register routes and run App. Shared-console composition is secondary and optional.
Vendored distribution, with a dedicated upstream repository, versioned releases and explicit updates.
The optional Shell supplies navigation and embeds mounted apps; it does not manage application state or ML jobs.

## Implemented

- Flask-style request routing, JSON, static files, streams and custom responses.
- Prefix mounts, mount-aware URLs, optional shell with landing page and persistent navigation.
- Components overview with linked names, IDs, optional descriptions, placement and mounts; banners included.
  Primary navigation exposes its current page. Discovery entries accept optional description strings.
- Shell.add supports panel tabs and shared banners with fixed frame heights, using the same lifecycle contract.
- Component wrapper, Shell.add, shared standalone/combined lifecycle, partial-start cleanup and active-request
  draining before reverse shutdown. Component factories and registration do not start background services.
- Real-downloader/synthetic-workbench example explicitly mounts both components, with parsing separate from composition.
  Its state directory defaults to ignored data/downloader-console/, prepared after binding; --state-dir is optional.
- Optional one-command console demo examples/console.py bundles synthetic Library/Workbench and CPU/memory banner.
  No packages, external tools, other checkouts or data setup; no GPU UI/probes or generated files.
  Individual views also run standalone. Advanced downloader integration remains a separate optional proof.
- Optional examples/component_console.py discovers local checkout manifests under ignored components/,
  mounts compatible apps and shows load problems. Data lives separately under ignored data/; no installation
  or downloads. Explicit launchers and the single-file runtime remain independent of discovery.
  A manifest's components array supports multiple views per checkout; order sorts panels left to right and
  banners top to bottom across repos. examples/demo_components supplies two synthetic panels and one banner.
- Streaming file responses with HEAD and byte ranges; loopback-oriented threaded HTTP server.
- Embedded partial metadata; separate release manifest on main with tagged download and checksum.
- Explicit update checks and replacement with modification detection and backup.
- Bash release workflow that tests, commits and tags locally; runnable standalone/combined example.
  The version comes directly from committed `__version__`; GitHub OWNER/REPO is detected from origin
  or supplied as an optional argument. Missing remote setup gets an explanatory message without changes.

## Status and next steps

The [component contract](../docs/component-contract.md) agreed on 2026-10-25 is implemented for the framework.
The downloader adapter and a synthetic workbench prove both combined and standalone hosting, data reading,
media ranges and shutdown without terminating an independent process. The actual voice workbench remains
outside integration until its own handoff. No research application or live queue was changed.

The extended 55-test suite passes on Python 3.12 and 3.14 with site packages disabled, covering a portable
copied demo, discovery, descriptions/overview, placement/order, lifecycle, active-request drain,
synthetic-workbench and disposable release checks. Browser checked shell navigation, mounted downloader pages and
audio playback, and a completed synthetic task. A further isolated discovery browser check verified two panels
from one checkout plus a shared banner, also above the downloader and its Review page. Configure/check the GitHub origin before making
the first release; release tooling detects OWNER/REPO or accepts it explicitly. The downloader adapter uses
the same controller and retains standalone operation. The current source remains a development version.
Artifact handoffs between tools remain an application-level design task.
The initial optional shell uses an iframe. A shared page layout is a possible alternative for tighter
navigation integration; mounting and routing do not depend on frames.

## Orientation

`microweb.py` is the entire vendored runtime; `examples/console.py` demonstrates both launch modes.
`tests/` contains offline tests; `scripts/release.sh` performs local release preparation.
`docs/component-contract.md` specifies the module/configuration/lifecycle boundary.
`docs/shell-conventions.md` records overview, navigation, banner-layout and UI vocabulary conventions.
