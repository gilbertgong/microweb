# Optional component-discovery console

This is an example under `examples/`, not the framework's primary launch mode. It adds a directory
convention around Component and Shell.add. Neither microweb.py nor explicit registration depends on it.
The launcher never downloads, clones, updates or installs component code or dependencies.

## Run

From the microweb repository root:

```sh
git clone <tool-repository-url> components/librivox-download
python examples/component_console.py
```

The tool must ship the manifest described below. An older clone without it is simply not listed. Restart
the launcher after adding or updating components. With none installed, the console displays setup guidance.
The default address is `http://127.0.0.1:8765/`; choose another port with `--port` if needed.

Only `components/.gitkeep` is tracked. Cloned checkouts and their own Git metadata are ignored by this
repository. User data lives separately under ignored `data/<component id>/`, created after socket binding,
so replacing a tool checkout does not replace its session or recordings. No data folder is created for an
empty console or a component that could not be loaded. Bind failure also creates no component data folders.

You can override the locations:

```sh
python examples/component_console.py --components-dir /path/to/tools --data-dir /path/to/data --port 8766
```

Those explicit relative command-line locations resolve against the current working directory. Without
arguments, components and data are relative to the microweb repository, independent of the working directory.

## Manifest supplied by each tool

At the root of the tool checkout, place `microweb-component.json`:

```json
{
  "component_api": 1,
  "components": [
    {
      "id": "downloads",
      "label": "Downloads",
      "description": "Collect and review a local recording library.",
      "factory": "librivox_web:create_component",
      "placement": "panel",
      "order": 10,
      "defaults": {"session_file": "session.json", "collect": false}
    }
  ]
}
```

The root `component_api` is integer `1`, identifying this interface rather than a software release.
`components` is an array, including for a repository providing only one component. Each entry has:

- `id`: stable lowercase name, starting with a letter, using letters, digits, hyphens or underscores.
  It determines both `/downloads/` and `data/downloads/`. Folder names need not match IDs.
- `label`: the panel navigation label or banner frame title.
- `description`: optional plain string describing the component's purpose on the overview. It is display
  metadata, not a factory setting; omitted descriptions display a dash. HTML is escaped.
- `factory`: importable `module:function`, or `package.module:function`, located in that checkout.
  It accepts a settings dictionary and returns a compatible Component with the same ID.
- `defaults`: optional object of tool-owned startup settings. Values are not interpreted as generic paths
  by the launcher. The tool's factory owns their meaning.
- `placement`: optional `"panel"` (default) or `"banner"`. Panels appear in primary navigation and the
  Components overview. Banners appear below navigation and above the content on the landing page and every panel page;
  they do not get tabs. Both use the same Component and lifecycle contract.

- `order`: optional integer, default `100`. Lower numbers come first across all repositories: panels
  left to right, banners top to bottom. Equal values sort by component ID. This also determines startup
  registration order; dependencies and shared-service ownership remain the application's responsibility.
- `height`: optional positive integer in pixels, default `96`, used only for banner frames. Banners own
  their compact layout; there is no automatic sizing or cross-frame messaging protocol.

The landing page lists one row per loaded view, including banners. Names are links; panel names select
the shell view and banner names open the standalone mounted page. IDs, descriptions, placement and mount
paths make the installed composition inspectable without an additional action column. Load problems and
setup guidance remain visible alongside the overview. This is not a health-check dashboard.

For example, one workbench checkout can export three factories:

```json
{
  "component_api": 1,
  "components": [
    {"id": "machine", "label": "Machine", "factory": "workbench.web:machine", "placement": "banner", "height": 80, "order": 10},
    {"id": "library", "label": "Library", "factory": "workbench.web:library", "order": 20},
    {"id": "voices", "label": "Voices", "factory": "workbench.web:voices", "order": 30}
  ]
}
```

Each component has its own mount and data directory even when factories share a repository or module.
If factories share a controller or background service, the tool must arrange one owner or coordinated
start/stop; the launcher does not infer shared resources. Navigation reloads the shell and its frames,
so a banner is present everywhere but its DOM is not retained across panel switches. Services remain
running for the whole host lifetime.

To try a synthetic two-panel/one-banner checkout without installing another project, copy
`examples/demo_components/` to `components/demo/`, then launch this example. On MSYS2:

```sh
cp -r examples/demo_components components/demo
python examples/component_console.py
```

Its Machine values are explicitly synthetic. This fixture starts no workers and probes no hardware.
Its banner shows CPU and memory only; no GPU tooling is required. For the same bundled views without
copying anything or using discovery, simply run `python examples/console.py`.

The launcher scans only immediate subdirectories and reads all metadata before importing tool code.
Duplicate IDs are excluded together, including duplicates within one repo. Invalid entries do not prevent
valid companions from loading. Invalid manifests, unavailable dependencies and factory failures
appear on the landing page and in the terminal; other loadable tools still appear. A service-start failure
after binding stops the host with normal component cleanup rather than leaving a partly started console.

Installed components use the common microweb runtime already imported by the launcher, and must use
distinct application module/package names. The example supports ordinary source checkouts; it does not
set up virtual environments or isolated import namespaces. Components requiring another environment need
a different adapter/hosting arrangement. Cloning a repository does not install its dependencies.

## Local settings

An optional JSON file maps component IDs to overrides. For example, `console.local.json`:

```json
{
  "downloads": {
    "session_file": "listening.json",
    "collect": false
  }
}
```

```sh
python examples/component_console.py --settings console.local.json
```

The root `console.local.json` is ignored. Other explicitly named settings files follow their normal Git rules.
The launcher merges overrides over manifest defaults and supplies an absolute `settings_dir` of
`data/<component id>/`. That launcher-owned field cannot be overridden per component; use `--data-dir`
to change its root. Relative tool paths resolve against settings_dir according to the tool's factory,
not against the cloned source directory or the overrides file's directory. Absolute tool paths remain usable.

For the downloader defaults, the session is `data/downloads/session.json`; its normal default output root
is `data/downloads/downloads/`. Startup collection is disabled by the manifest, although the real Download
controls work normally when requested. The original downloader CLI keeps its own launch behavior.

## Lifecycle

Discovery and app construction create no data directories or background services. For each selected component,
the example registers a small wrapper that creates its data directory at startup and then calls its start.
Stopping delegates to the tool's stop. The common host binds first, handles partial-start failures, drains
accepted requests and stops in reverse order. This example adds no downloads, process manager or shared database.

The explicit `examples/downloader_console.py` and `examples/console.py` remain available. The former still
demonstrates the synthetic workbench; discovery does not implicitly add that test tool to your installed components.
