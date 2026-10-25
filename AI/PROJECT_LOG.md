# Project log

## 2026-10-21 — Standalone foundation

Started from an existing small BSD-licensed standard-library HTTP framework, retaining its license.
Extended it for mounted applications, an optional console shell, streamed media, and explicit vendored-file
updates. The runtime stays one file, while tests, examples and release tooling live in the repository.
The shell uses an iframe to retain tool independence without rewriting their HTML. Mount-aware links remain
the application's responsibility. Release metadata is split: version/announcement URL inside Python, final
SHA-256 in a separate manifest, avoiding a self-referential checksum. Main hosts the release announcement;
the manifest downloads the exact tagged Python file. No existing application was migrated or modified.

Validation: 26 tests passed on Python 3.12 and 3.14, including live loopback range/HEAD/JSON responses,
mounting, update modification/checksum/syntax/backup failures, and disposable Git release commits/tags.
Browser verified the landing page, tool view and API link preserving the mount prefix. Release tests
verify tagged bytes against the manifest, duplicate-version refusal, dirty-tree refusal and restoration
after failed tests. Real repository initialized on main, with no commits, remote or release yet.
User raised iframe integration concerns: confirmed presentation can later use a shared layout instead;
the framework and mounting contract remain independent of that choice.

## 2026-10-21 — Release version from source

At the user's request, release.sh now reads the literal __version__ from microweb.py rather than
accepting a version argument. Set and commit the version first, then pass only OWNER/REPO. The script
compares it to the previous release manifest and refuses existing tags and development versions.
It parses metadata without importing/executing the module. Disposable release tests use the same flow.

## 2026-10-21 — Optional release repository argument

Release setup now detects GitHub OWNER/REPO from origin, supporting HTTPS and SSH forms. An explicit
argument overrides detection. Without a usable remote, a no-argument launch explains why the location
is needed and shows both remote setup and explicit invocation; no files or configuration are changed.
Offline disposable-repository tests cover those messages, URL forms, an inferred release and an
explicit override release. No GitHub requests are made by detection or release preparation.

## 2026-10-25 — Component integration contract

The user agreed on a small component/configuration/lifecycle boundary and requested a specification.
Added docs/component-contract.md: quiet factories, optional Component wrapper, tool-owned settings,
mount-aware apps, shared standalone/combined lifecycle, partial-start cleanup and safe shutdown ownership.
The shell supplies navigation and hosting; tools retain state and independent workers retain their jobs.
Initial interoperation can use a documented read-only library adapter. Component and Shell.add signatures
are proposed and unimplemented; no runtime or downstream application code was changed. Synthetic component
checks precede application adaptation. The specification records requirements for in-flight request draining
and mock mutation isolation, rather than assuming routing alone establishes either property.
