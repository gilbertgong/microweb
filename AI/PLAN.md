# Current state

## Goal and approach

A single-file standard-library foundation for independent local web apps that can also join a shared console.
Vendored distribution, with a dedicated upstream repository, versioned releases and explicit updates.
The optional Shell supplies navigation and embeds mounted apps; it does not manage application state or ML jobs.

## Implemented

- Flask-style request routing, JSON, static files, streams and custom responses.
- Prefix mounts, mount-aware URLs, optional shell with landing page and persistent navigation.
- Component wrapper, Shell.add, shared standalone/combined lifecycle, partial-start cleanup and active-request
  draining before reverse shutdown. Component factories and registration do not start background services.
- Real-downloader/synthetic-workbench example with explicit checkout/state paths and standalone modes.
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

The extended 37-test suite passes on Python 3.12 and 3.14, including component lifecycle, active-request drain,
synthetic-workbench and disposable release checks. Browser checked shell navigation, mounted downloader pages and
audio playback, and a completed synthetic task. Configure/check the GitHub origin before making
the first release; release tooling detects OWNER/REPO or accepts it explicitly. The downloader adapter uses
the same controller and retains standalone operation. The current source remains a development version.
Artifact handoffs between tools remain an application-level design task.
The initial optional shell uses an iframe. A shared page layout is a possible alternative for tighter
navigation integration; mounting and routing do not depend on frames.

## Orientation

`microweb.py` is the entire vendored runtime; `examples/console.py` demonstrates both launch modes.
`tests/` contains offline tests; `scripts/release.sh` performs local release preparation.
`docs/component-contract.md` specifies the module/configuration/lifecycle boundary.
