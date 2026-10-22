# Current state

## Goal and approach

A single-file standard-library foundation for independent local web apps that can also join a shared console.
Vendored distribution, with a dedicated upstream repository, versioned releases and explicit updates.
The optional Shell supplies navigation and embeds mounted apps; it does not manage application state or ML jobs.

## Implemented

- Flask-style request routing, JSON, static files, streams and custom responses.
- Prefix mounts, mount-aware URLs, optional shell with landing page and persistent navigation.
- Streaming file responses with HEAD and byte ranges; loopback-oriented threaded HTTP server.
- Embedded partial metadata; separate release manifest on main with tagged download and checksum.
- Explicit update checks and replacement with modification detection and backup.
- Bash release workflow that tests, commits and tags locally; runnable standalone/combined example.
  The version comes directly from committed `__version__`; GitHub OWNER/REPO is detected from origin
  or supplied as an optional argument. Missing remote setup gets an explanatory message without changes.

## Status and next steps

Initial implementation validated with 26 offline tests on Python 3.12 and 3.14, including loopback HTTP and
disposable-repository release tests. Browser checked landing page, framed tool and mount-aware API link.
No downstream migration, remote, public release or integration approved
as part of this repository setup. Choose the GitHub repository before making the first release; release tooling
accepts OWNER/REPO explicitly. Future downloader integration should preserve existing operation and media behavior.
Artifact handoffs between tools remain an application-level design task.
The initial optional shell uses an iframe. A shared page layout is a possible alternative for tighter
navigation integration; mounting and routing do not depend on frames.

## Orientation

`microweb.py` is the entire vendored runtime; `examples/console.py` demonstrates both launch modes.
`tests/` contains offline tests; `scripts/release.sh` performs local release preparation.
