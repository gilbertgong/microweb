# Start here

Read `PLAN.md`, `LOCAL.md` if present, `PROJECT_LOG.md` when history matters, and `STRATEGY.md`
when changing documentation structure. For operational requests read `USAGE.md` and the README.
For component or shell integration work, read `../docs/component-contract.md`; distinguish its planned
Component/lifecycle API from the currently implemented App/Shell methods.

## Working preferences

- Remember in the repo: preferences here, present state in PLAN, dated history in PROJECT_LOG.
  Local machine details belong only in ignored LOCAL.md. Shared docs must stand alone.
  *Why:* assistants and computers change; the repository carries the context.
- Update affected documentation with code changes. README is for people; AI docs are for assistants.
  *Why:* a stale description misleads the next reader.
- Keep the runtime in one standard-library Python file, with clearly separated optional shell code.
  *Why:* consumers should be able to vendor one file without installing dependencies.
- Keep application-specific behavior outside microweb. Discuss new directions before implementing them.
  *Why:* this is a reusable foundation, with downstream applications maintained independently.
- Check versions and update only on explicit CLI actions. Never automatically update on import or startup.
  *Why:* consumers control when tested framework copies change.
- Read release versions from `microweb.py`'s `__version__`, not a separate command-line argument.
  *Why:* the source file is the single place to set the intended version.
- Use UTF-8 and LF for text. Run meaningful offline tests for routing, files, updates and release behavior.
  *Why:* published hashes must match vendored bytes across operating systems.
- Do not publish, push, or create a real release without a user request. Test releases in disposable repos.
  *Why:* a version announcement is a deliberate publishing decision.
