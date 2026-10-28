# Component, configuration and lifecycle contract

**Status:** implemented foundation, 2026-10-25. Component, Component.run, Shell.add and shared lifecycle
orchestration are implemented, with unit and loopback checks. An adapted downloader and a synthetic
workbench demonstrate combined and standalone hosting. Integration of an actual voice workbench remains
separate; this does not establish that an application's mock mode or private state is isolated.

## Purpose

Let a tool run independently or join a shared local console using the same application code. Keep the
framework standard-library-only and vendorable as one Python file. The optional shell supplies navigation;
tools retain their own behavior, settings, state and dependencies.

The first intended applications are a downloader and a voice workbench. A repository may provide multiple
components: for example, two workbench panels and a Machine banner. Sections can also remain inside one
component. Component boundaries describe hosted views and lifecycle ownership, not repository boundaries.

## Responsibilities

| Owner | Responsibility |
|---|---|
| Launcher | Load startup settings, resolve paths, construct the selected components, choose bind address and mounts |
| Microweb host | Bind and serve HTTP; start and stop registered components in a defined order |
| Optional Shell | Landing page, labels and shared navigation around mounted apps |
| Component | Routes, frontend, private state, configuration interpretation and its owned background services |
| Independent worker | Scheduling and executing jobs that may outlive the console |

No shared database, unified job model or general configuration engine is required. Registration may be explicit
Python or the [optional local discovery example](discovery-example.md); discovery is not part of the runtime.
Installing one tool must not require another tool's ML stack.

## Component interface

A tool exposes `create_component(settings)`. It returns a small microweb Component with:

```python
Component(
    id="downloads",          # stable identifier within the host
    label="Downloads",       # human-readable navigation label
    app=app,                 # microweb.App, with routes relative to its own root
    start=start_services,    # optional zero-argument callable
    stop=stop_services,      # optional zero-argument callable
)
```

The wrapper provides callable `start()` and `stop()` methods; absent callbacks behave as no-ops.
It also provides `run(host, port, on_ready=None)` for standalone hosting through the same lifecycle
implementation used by the combined host. Tool-specific objects can be captured by the callbacks and
route closures. The shell does not inspect those objects.

Importing the tool and calling its factory must not start services, launch jobs, bind ports or modify user
files. Factories may read startup settings and register routes. Filesystem creation, registry scans and
other startup writes belong in `start()` or explicit user operations.

The initial contract assumes one host run per component instance. Repeated start/stop cycles on the same
instance are not required. `stop()` must tolerate partial startup and repeated cleanup without damaging state.
The host rejects duplicate component IDs and conflicting mounts before starting services.

## Configuration

The launcher reads settings once at startup and passes each component its own settings object. A plain
dictionary or simple Python settings class is sufficient. Components interpret their own settings; microweb
does not prescribe a file format or validate application-specific choices.

```python
downloads = create_downloader({
    "session_file": settings_dir / "downloads.json",
})
voices = create_workbench({
    "data_dir": data_dir / "voices",
    "download_sources": [data_dir / "downloads"],
    "worker_python": worker_python,
})
```

These keys illustrate tool settings; their exact schemas remain owned by the applications.

- Relative filesystem paths resolve against the settings file's directory, not the process's current directory.
  A Python launcher supplying paths directly resolves them before construction.
- The host owns its bind address, port, console title and mount prefixes.
- Each tool owns its data directories, interpreters, binaries, models and source-library settings.
- Settings are fixed for the host run. User changes to recipes or download targets remain normal application
  operations; they do not require a general hot-reload mechanism.
- Tools must avoid capturing obsolete path settings at import time. An instance context or equivalent
  application-owned state must consistently reflect the settings passed to its factory.
- Keep mutable user data separate from the vendored framework and application source. Tools explicitly
  serve generated media; the shell does not expose their entire data directories as static files.

The first integration may support one configured instance of each tool per process. Supporting simultaneous
live and mock workbenches, or multiple differently configured workbenches, requires instance-isolated state
and is not assumed merely because prefix mounting works.

## Hosting and mounting

Standalone, using the Component helper:

```python
component = create_component(settings)
component.run("127.0.0.1", 8765)
```

Combined, using Shell.add:

```python
shell = Shell(title="Voice tools")
shell.add(downloads, prefix="/downloads")
shell.add(voices, prefix="/voices")
shell.run("127.0.0.1", 8765)
```

`Shell.add` mounts `component.app`, uses its label in navigation, and registers its lifecycle callbacks.
It also accepts `description="Short purpose"`, plain presentation text for the Components overview. The same
optional keyword is available on Shell.mount for ordinary Apps. Component's interface remains unchanged.
The overview lists every registered view, including banners, with linked name/ID, purpose, placement and
mount. Panel links select the shell view; banner links open the app directly. It reports registration,
not live health. See [shell conventions](shell-conventions.md) for layout and terminology.
Its default placement is `"panel"`. Use `shell.add(machine, prefix="/machine", placement="banner", height=80)`
for a compact shared frame below navigation and above every panel, including the landing page. Banners
have no navigation tab. Both placements share the same Component contract and lifecycle; placement belongs
to the shell. Registration order determines tab order and banner stacking. Banner height is fixed in pixels,
default 96; a component owns its compact layout. Shell navigation reloads frames, while services remain alive.
Multiple components sharing one service must coordinate ownership in their application; the host calls each
registered component's callbacks and does not deduplicate private resources.
The existing `App.mount(prefix, app)` remains usable without Component or Shell; mounting an ordinary App
does not discover or start background services. Existing plain `App.run()` remains supported.

Each child App owns its routes and static directory. Register `/api/status` on the child, then mount it;
do not also prepend `/voices` while registering those routes. Mounting owns the prefix once.

Applications use relative frontend URLs or `req.url()` for links, API calls and generated media references.
The existing redirect from `/voices` to `/voices/` preserves relative URL resolution. Browser storage keys
should include the component ID because mounted applications share an origin.

In-process components must use a common microweb runtime and ordinary package namespaces. Avoid competing
imports of incompatible vendored copies or generic top-level modules made visible by changing sys.path.
The factory's import path belongs to each tool's packaging; microweb does not become a tool dependency manager.

The initial shell can embed complete tool pages in same-origin iframes. A later shared page layout can use
the same component and lifecycle contract. Neither approach shares internal state automatically. Separate
process/environment hosting remains possible future work; this initial contract specifies in-process apps.

## Lifecycle

The host follows this order for standalone and combined operation:

1. Construct the selected components and register routes and mounts.
2. Bind the listening socket. If binding fails, close it and start no component services.
3. Call component `start()` methods in registration order, once each.
4. Invoke `on_ready`, then serve requests. A startup failure must not announce readiness.
5. When serving ends, stop accepting new requests and shut down components in reverse startup order.
6. Close the server's resources even if startup, serving or cleanup raises an exception.

Registering routes must not itself start a registry scanner, fake worker, model renderer or other service.
`start()` should return when its owned services are ready to operate, rather than waiting for long jobs.

If `start()` fails partway through, the host calls `stop()` for that attempted component as well as the
components already started, in reverse order. A component therefore tracks partially acquired resources.
If one stop fails, the host still attempts the remaining stops and server closure, then reports the failure.
Cleanup must preserve the original startup/serving error when one exists.

`stop()` prevents new component operations, signals its owned background services and lets relevant in-flight
requests or work reach a safe stopping point before releasing the resources they use. HTTP handlers already
running at shutdown must not race against closed component resources. The host and implementation must
coordinate that drain; ending the accept loop alone does not mean request threads have finished.

Specific application responsibilities include:

- Downloader: request pause, finish or checkpoint the current transfer according to its existing behavior,
  and join the collection services this instance owns. Do not lose queued intent or delete downloaded files.
- Workbench: stop the registry scanner, settle its local listening/render work and release owned resources.
  Independent queue workers and detached training/search jobs continue running unless the user separately
  requests otherwise.
- Mock workbench: stop only its fake worker and sandbox services. Every mutating action, including newly
  added actions, must stay inside the sandbox or be explicitly disabled there.

There is no host-wide process-killing policy. An application's explicit Cancel operation remains distinct
from closing the console. If cleanup cannot finish, report the condition rather than silently claiming a
clean shutdown or forcibly terminating independent jobs.

## Interoperation between tools

The shell connects navigation and configuration. Applications own data exchange through documented interfaces.

For the first downloader/workbench join, a read-only adapter over the existing download library is sufficient.
Document the fields the workbench consumes, reader/source identity, relative recording paths, source-text
locations, review decisions and how actual file availability is checked. The downloader remains the writer
of its library state and review annotations; the workbench writes its own projects and results.

Record a compatibility/version policy for that read interface when integrating it. A general artifact manifest
or new exchange service is not required by this component spec. The shell must not gain knowledge of private
state.json fields, recipes, pack geometry or model settings.

## Implementation and acceptance

Integration sequence (the foundation and synthetic/downloader proof are now implemented):

1. Add Component and shared host lifecycle orchestration, preserving plain App/Shell use and single-file distribution.
2. Prove standalone and combined operation with small synthetic components and isolated temporary state.
3. Adapt the downloader's HTTP layer and frontend URLs while retaining its existing collection/media behavior.
4. Adapt the workbench after its own integration handoff; changing research features need not block the framework.

Meaningful framework checks must cover:

- Same component routes, static assets and audio ranges work standalone and under a prefix, without double prefixes.
- Factories and route registration have no startup side effects; an empty shell and plain App still work.
- Bind failure starts no services; startup order and reverse cleanup order are correct.
- Partial-start failure cleans up the attempted component and earlier components; later components never start.
- Readiness is announced only after successful startup; exceptions and interrupts still release resources.
- One failing stop does not prevent other cleanup; active handlers cannot use torn-down resources.
- Closing the host leaves independently owned jobs alone; tool adapters preserve their own shutdown semantics.
- Settings-relative paths work from an unrelated current directory; selected tools alone determine dependencies.

Workbench isolation checks belong with that adapter. Mock labels or past mock tests are not proof that every
subsequently added write action is isolated. Use disposable files and fake jobs to test destructive or process
control actions; never use the live queue or live search artifacts to validate the shell.
