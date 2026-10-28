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

## 2026-10-25 — Component implementation and downloader proof

Implemented Component, Shell.add and shared host orchestration. Binding precedes startup; readiness follows
startup; failure cleanup includes a partially started component, with reverse stops and original exceptions
preserved. Accepted request threads drain before teardown. Plain App/Shell use remains supported.
Added lifecycle tests and a synthetic component that reads a download library without modifying it, drains
its tiny work queue and writes a shutdown receipt. A launcher combines it with a real adapted downloader
checkout or runs either component independently, using explicit isolated state and no automatic collection.
The actual research console and live queues were not touched. Browser proof exercised mounted navigation,
local audio playback and a synthetic task. The HTTP proof also verified that an independent test process
survived host shutdown. Detailed local test paths are recorded only outside the shared repository.

Final validation: 37 microweb tests and 114 downloader tests pass on both Python 3.12 and 3.14. JavaScript
syntax, Python syntax, documentation links, LF text and diff whitespace checks passed. The two runtime
copies match byte-for-byte. The isolated HTTP proof covered combined and both standalone modes, range
responses, saved decisions, synthetic task completion and preservation of an unrelated test process.

## 2026-10-25 — Local manifest discovery example

After checkpointing lifecycle/integration work, added the user-approved optional discovery launcher under examples/.
Users clone component repositories into ignored components/ (only .gitkeep tracked); each tool supplies its own
microweb-component.json. Metadata is read before import, compatible factories are constructed quietly and apps
mount by ID. Load errors appear in the console without hiding healthy tools. Defaults plus explicit JSON overrides
are passed to factories with a separate per-tool data directory, created after binding. Nothing downloads or installs
code/dependencies. Existing explicit registration remains supported. The downloader ships a manifest
with startup collection disabled. The synthetic workbench stays in the explicit example, not automatic discovery.

The user extended the design to multiple components from one checkout, ordered panel tabs and shared banners.
The manifest uses a components array with per-entry placement/order and optional banner height. Lower orders
come first across repos, with ID as tie-breaker. Shell.add implements placement without changing Component's
lifecycle interface. Banners appear on landing and every panel page; frames reload on shell navigation.
The application owns coordination of services shared by its factories. Added a no-dependency synthetic checkout
with two panels and one banner; it is installed only when copied explicitly. 48 tests pass on Python 3.12/3.14.
Browser verification covered both demo panels, the real downloader's mounted pages and the banner above them.

## 2026-10-27 — Promote reusable shell UI conventions

At the user's request, brought the reviewed component-overview convention into the optional core Shell.
Home now lists all registered panels and banners, with linked names/IDs, optional descriptions, placement
and mount paths. Panel links select the shell view; banners open directly. Removed duplicate launch cards
and action columns, added semantic table headers and current-page primary navigation. This reports registration,
not component health. Plain App.mount, standalone apps, existing Shell signatures and lifecycle stay supported.
Shell.add and Shell.mount gain optional description text; discovery validates/forwards the corresponding
manifest field. Examples demonstrate descriptions. Shared layout/vocabulary guidance records the prototype
lessons without moving its pagination, hardware metrics, fixed card dimensions or mock backend into the runtime.
Runtime stays one stdlib Python file; discovery stays in examples. Existing downstream vendored copies are
independent snapshots and are not automatically replaced by this change.
Validation: all 51 tests pass on Python 3.12 and 3.14, including disposable release preparation. Browser
checked the actual discovery example's three-row overview, description display, panel name navigation,
active-page metadata, shared banner and direct banner link. Syntax/LF/local-link/whitespace checks passed.

## 2026-10-27 — One-command self-contained demo

The user wanted a useful example without depending on another project or package. examples/console.py now
explicitly registers bundled Library and Workbench panels plus a synthetic Machine banner. It starts with
one command from the repository root, no configuration/data setup or installs. The banner reuses the compact
card/chart layout with CPU and memory only; the user explicitly excluded GPU from this example. All readings
are fabricated, with no nvidia-smi, hardware-monitoring package, model, process or worker dependency.
Library has sample records/status JSON and Workbench records a demo result in memory. Nothing writes data.
The bundled manifest is also usable by the optional discovery example; explicit standalone modes use the same
factories. The real-downloader integration proof remains separate and is labelled advanced in README.
53 tests pass on Python 3.12/3.14 with site packages disabled, including a subprocess using only a copied
runtime and bundled example outside the workspace. Browser verified both panels, CPU/memory chart and task
button. The runtime itself did not change in this step; consuming projects' copies remain untouched.

## 2026-10-27 — Restore web-server-first positioning

The user clarified that console composition is a secondary optional feature. README now leads with the
single-file Flask-style server, copying microweb.py beside app.py, a minimal App with page/JSON routes,
and the python app.py command. Routing/request/response guidance precedes the optional console section.
The bundled demo remains available there; lifecycle, discovery and advanced integration are nested under
that optional section. Recorded the positioning preference in AI memory and aligned the plan/usage guide.
Documentation only; no application behavior changed.

## 2026-10-27 — Advanced example storage default

The user found a required state-directory argument distracting in the integration example. It now defaults
to ignored data/downloader-console/ relative to the repository, creates it after socket binding and reuses
existing state. --state-dir remains an optional override; the resolved location is printed at readiness.
A small launcher-owned Component wrapper prepares the directory before each tool's normal start and delegates
cleanup. No framework storage requirement was introduced. The self-contained demo remains memory-only.
All 55 tests pass on Python 3.12 and 3.14 with site packages disabled. Tests confirm the default needs no
state argument, bind failure creates no directory, and successful startup/cleanup delegates normally.

## 2026-10-27 — Simplify the integration launcher

At the user's request, removed standalone branching from downloader_console.py and extracted parse_args.
main now constructs the two apps and explicitly mounts /downloads and /voices before running the shell.
The optional state override/default and deferred storage preparation remain. Standalone support in the
framework and the separate self-contained console demo is unchanged.

## 2026-10-27 — Prepare first release, 0.1.0

User requested a release through scripts/release.sh. Normalized the source version from v0.1.0 to 0.1.0;
the release script adds the v prefix to the annotated tag. Origin identifies gilbertgong/microweb. The script
generates the update URL and SHA-256 manifest, runs the tests, and commits/tags locally. No push is authorized.


## 2026-10-27 — Preserve the literal prefixed release version

The user chose v0.1.0 as the actual source version. Source, manifest and annotated tag now share the
same literal string; release.sh neither adds nor removes a prefix. The updater uses that exact string
for tagged manifest lookup and parses its numeric portion only for comparisons. Tests cover exact release
metadata and canonical version validation. All 56 tests pass on Python 3.12 and 3.14.
The prior first-release tag was local only (checked against origin) and is regenerated through the script;
the earlier release commits remain in history. Nothing is pushed.


## 2026-10-27 — Verbose release progress and repeatable validation

At the user's request, release.sh now reports prerequisites, preparation, tests, commit/tag creation
and integrity checks. New releases receive final validation. An existing version tag selects read-only
validation plus tests instead of an error. Validation checks annotation, ancestry, working/tagged source
and manifest bytes, LF, update/download URLs, version and SHA-256. It allows later tooling/docs changes;
new releases still require clean main and Git identity. No network access or pushes are performed.
All 56 tests pass on Python 3.12/3.14, including repeat runs without ref/file changes, later documentation
commits, and rejection of changed release artifacts or a mismatched repository. Ran the updated script
against the actual local v0.1.0 release: all checks and tests passed; release artifacts and tag unchanged.


## 2026-10-27 — Explicit repository option and cached test passes

Repository override is now --repo OWNER/REPO; positional input is rejected and origin detection remains
the default. Successful release tests are saved atomically under ignored tests/.release-cache/. Records
include source SHA-256, release commit, Python interpreter and a hash of current test/script/example inputs.
Existing releases always undergo integrity validation, then reuse only a matching successful record.
Absent, malformed or mismatched records run tests normally; failed tests do not write a pass. New releases
always test before committing and save the pass after final validation. Cache write failures are warnings.
All 56 tests pass on Python 3.12/3.14. Disposable-repo checks cover argument errors, cache hits, missing/
corrupt records, invalidation by new tests and uncached failures. Two actual v0.1.0 validations confirmed
first-run cache population and second-run reuse. Release artifacts/tag remain unchanged; nothing pushed.
