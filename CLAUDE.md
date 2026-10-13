# Agentic SDLC Workflow

Reusable workflow that turns a user story into a reviewed, verified pull request by coordinating specialized subagents. Start it with `/sdlc-workflow <user story>`.

## Stage order (fixed)

| # | Agent | Artifact in `workflow-runs/<run-id>/` | Approval gate after |
|---|---|---|---|
| 1 | requirements-analyst | `01-requirements.md` | `requirements` |
| 2 | architect | `02-architecture.md` | |
| 3 | design-reviewer | `03-design-review.md` | `design-review` |
| 4 | implementation-planner | `04-plan.md` | `plan` |
| 5 | implementer | `05-implementation.md` | |
| 6 | code-reviewer | `06-code-review.md` | |
| 7 | verifier | `07-verification.md` | `pre-pr` |
| 8 | release-preparer | `08-pr.md` | |

## Rules

- The Orchestrator is the `sdlc-workflow` skill and runs in the main session. Only it talks to the user and updates `state.json`. It saves every artifact except `08-pr.md`, which `release-preparer` writes itself.
- Subagents never launch other subagents. Only `implementer` and `release-preparer` may modify project files; the other six return their output as text.
- Stages communicate only through the artifact files. Do not skip, reorder, or merge stages.
- Hooks enforce the rules: `workflow-guard.ps1` blocks out-of-order stages, unapproved gates, and secret-like content in artifacts and `CHANGELOG.md`; `bash-guard.ps1` allows publishing only to the repository in `.claude/publish.json` (see the last rule below), blocks Git config changes and `.env*` access, and limits `code-reviewer` and `verifier` Bash use. If a hook denies a call, fix the cause; do not work around it.
- Never write secrets, credentials, tokens, keys, connection strings, or personal data into artifacts, `state.json`, `CHANGELOG.md`, or PR text. Use `<redacted>`. Do not read `.env*` files.
- The release stage makes a local branch with two commits: the change, and the `workflow-runs/<run-id>/` artifacts kept as evidence.
- After stage 8 the Orchestrator publishes: it pushes the feature branch (and `main` if the remote has none) and opens the PR with `gh pr create`, only to the repository in `.claude/publish.json`, only after `pre-pr` is approved, never with force. Subagents never publish.

## Conventions

- Run ids look like `yyyyMMdd-HHmmss-<short-slug>`.
- Artifact formats are defined in `.claude/skills/sdlc-workflow/artifact-templates.md`.
- Keep changes minimal and add no dependencies unless the approved plan requires them.
