# Start here

Read `PLAN.md`, `LOCAL.md` if present, `PROJECT_LOG.md` when history matters, and `STRATEGY.md`
when changing documentation structure. For operational requests read `USAGE.md` and the README.
For component or shell integration work, read `../docs/component-contract.md`. Component and its lifecycle
helpers are implemented; the real voice workbench remains a separate integration task.
For console presentation, read `../docs/shell-conventions.md`: the home page is a component overview with
linked names, including banners. Descriptions are optional display metadata. Application UI remains separate.

## Working preferences

- Keep README aimed at users of the framework: usage, API, examples and updates. Put repository
  maintenance, testing and release/publishing workflows in AI/ rather than README.
  *Why:* the user explicitly wants the README to explain consuming the project, not maintaining it.
- Lead with the Flask-style, single-file web server: copy microweb.py, write an App, run it.
  Keep console/shell composition a secondary optional feature in introductions, examples and documentation.
  *Why:* the console is useful but should not obscure the framework's primary purpose or suggest extra setup.
- Remember in the repo: preferences here, present state in PLAN, dated history in PROJECT_LOG.
  Local machine details belong only in ignored LOCAL.md. Shared docs must stand alone.
  *Why:* assistants and computers change; the repository carries the context.
- Update affected documentation with code changes. README is for people; AI docs are for assistants.
  *Why:* a stale description misleads the next reader.
- Keep the runtime in one standard-library Python file, with clearly separated optional shell code.
  *Why:* consumers should be able to vendor one file without installing dependencies.
- Keep manifest discovery in the optional examples launcher. Users clone component repos themselves;
  never automatically download, update or install discovered tools or their dependencies.
  *Why:* discovery is a convenience example, separate from the framework's primary use and explicit registration.
- Keep application-specific behavior outside microweb. Discuss new directions before implementing them.
  *Why:* this is a reusable foundation, with downstream applications maintained independently.
- Check versions and update only on explicit CLI actions. Never automatically update on import or startup.
  *Why:* consumers control when tested framework copies change.
- Read release versions from `microweb.py`'s `__version__`, not a separate command-line argument.
  *Why:* the source file is the single place to set the intended version.
- Release directly from staged changes, including manual version bumps, in one commit with generated metadata.
  Do not require a preparatory commit. Reject unstaged tracked changes and non-ignored untracked files.
  *Why:* the user wants one release commit covering the tested staged work and generated manifest.
- Use the literal prefixed release version everywhere, for example v0.1.0 in source, manifest and tag.
  The release script must not add or remove the prefix; numerical comparison is internal only.
  *Why:* the user prefers one consistent version string rather than different source and tag forms.
- Use UTF-8 and LF for text. Run meaningful offline tests for routing, files, updates and release behavior.
  *Why:* published hashes must match vendored bytes across operating systems.
- Do not publish, push, or create a real release without a user request. Test releases in disposable repos.
  *Why:* a version announcement is a deliberate publishing decision.
- Keep release.sh local by default. Explicit --push publishes main and the selected tag plus a GitHub
  release with only microweb.py attached; the manifest belongs in Git, not the release assets.
  *Why:* the user wants optional end-to-end publishing without changing the default local workflow.
