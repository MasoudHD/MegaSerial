# AI-assisted development rules

These rules apply to every future automated or AI-assisted change in this repository.

1. Inspect the relevant existing code, configuration, and tests before proposing or making a change. State any assumption that cannot be verified from the repository.
2. Keep the requested scope: do not modify unrelated code, files, formatting, or behavior.
3. Preserve existing behavior unless the request explicitly authorizes a behavior change. Treat serial I/O, persistence, and sequence execution as high-risk behavior.
4. Avoid opportunistic or large-scale refactoring. Prefer small, reversible, independently reviewable changes.
5. Do not add a dependency, service, or network call without a clear justification, compatibility consideration, and explicit approval when it changes product scope.
6. Keep modules focused on one responsibility. Add a focused module or service when a feature would otherwise substantially enlarge an existing coordinator.
7. Follow the documented current architecture unless a proposed architectural change has been explicitly approved. Update the relevant documentation when that architecture changes.
8. Reuse the project’s data models and conversion helpers (`Step`, `NamedSequence`, `utils`) rather than duplicating parsing, serialization, or sequence logic.
9. Add or update tests for important behavior changes when practical. At minimum, cover non-UI logic and preserve the hardware-backed end-to-end test where applicable.
10. Validate changes proportionally: run focused checks first, then the available automated test suite when the environment supports it. Report checks that could not run and why.
11. Preserve project-file compatibility deliberately. Version or migrate persisted formats before making incompatible schema changes.
12. Do not commit build artifacts, local settings, captured logs, credentials, or device-specific project data.

Before handoff, summarize changed files, observable behavior, tests run, and known limitations.
