# Optional shell conventions

The shell is a small shared wrapper around independently usable applications. These conventions apply to
explicit registration and the optional local-discovery example; neither is required for a plain App.

## Component overview

The home page is a Components overview, with one row per registered panel or banner. It shows a linked name,
stable ID, optional short purpose, placement and mount path. Component names are ordinary links, preserving
keyboard access, link copying and opening in another tab. There is no duplicate View/Open column or scripted
row-click behavior. A panel link opens that view within the shell; a banner link opens its mounted app directly.

This is a human-facing counterpart to the launch configuration, not a live manifest editor or a health check.
The example launcher shows metadata/import failures separately; a registered component may still have
application-specific availability or status that the shell does not inspect. Empty consoles retain guidance.

```python
shell.mount('/library', app, label='Library', description='Browse and review local items.')
shell.add(component, '/jobs', description='Manage queued work and results.')
```

Descriptions are optional plain display text, escaped with labels and IDs. They belong to shell registration,
not Component's lifecycle interface. A discovery manifest entry may supply `"description": "Short purpose"`;
the launcher forwards it to Shell.add. Apps mounted directly with App.mount do not acquire a shell UI.

## Navigation and banners

Use primary navigation for the main views. It consists of page links, not an ARIA tabs widget; the current
link has `aria-current="page"`. A banner is shared above the overview and all selected panels, without its own
primary-navigation link. Its title remains available to assistive technology through the iframe title.

Banner height is declared by the host. Components own their inner layout: fixed-width cards centered as a
group can provide stable dimensions with different numbers of cards. A row may scroll horizontally when it
does not fit. Account for scrollbars and text/control height when choosing the iframe height. Neither a
particular card width nor a hardware-monitoring dashboard belongs in the generic framework.

Shell navigation reloads frames. Put sampling/history or other state behind the application API if it must
survive view changes; do not assume a banner's DOM persists. Use request-aware or relative URLs under mounts
and scope browser preference keys by application/component ID.

## Shared vocabulary and application boundaries

| Element | Term |
|---|---|
| Container, navigation and mounts | App shell |
| Top-level links | Primary navigation |
| Hosted applications | Panels / views |
| Shared strip above views | Status banner |
| Links within a panel | Section navigation / sidebar |
| Expandable sections | Disclosures / collapsible sections |
| Lists with columns | Data tables |
| Expanded table record | Detail row / row expansion |
| Previous/Next and page-size selector | Pagination controls |
| Slide-in detail or log area | Drawer |

“Component” means a hosted app and lifecycle boundary here, not every visual widget. Multiple components may
come from one repository and share an application-owned context. The tool must coordinate shared services so
several factories do not start duplicate workers or scanners.

Filtering, sorting, pagination, hardware readings, job controls and cross-view selections are application UI.
The shell does not impose their implementation or a universal data model. For paginated collections, apply
filters/sort before selecting the page, keep detail rows with their parent, and preserve usable page selection
when refreshing data. A mock should use the same frontend contract without importing the real backend or
requiring production files/models. Mock data and disabled/simulated operations should be clearly identified.
