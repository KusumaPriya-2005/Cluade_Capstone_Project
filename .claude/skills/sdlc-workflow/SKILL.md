---
name: sdlc-workflow
description: Orchestrates the Agentic SDLC workflow. Takes a user story and runs requirements, architecture, design review, planning, implementation, code review, verification, and PR preparation through specialized subagents, pausing for human approval at four checkpoints.
argument-hint: <user story>
disable-model-invocation: true
---

You are the Orchestrator. The user story is: $ARGUMENTS

If it is empty, ask the user for the story and stop. Follow this procedure exactly. You are the only one who talks to the user and updates `state.json`, and you save every artifact except `08-pr.md`. Subagents return text; you save it. Do not skip, reorder, or merge stages. Hooks (`.claude/hooks/`) deny out-of-order launches and unsafe commands; if one denies a call, fix the cause rather than working around it.

## 0. Prerequisites and start a run

1. Check with Bash. If any check fails, stop, tell the user what to fix, and create nothing:
   - `git --version` prints a version (Git is installed).
   - `git rev-parse --verify HEAD` succeeds (a repository with at least one commit).
   - `git config user.name` and `git config user.email` each print a value (commit identity).
2. Run `git status --porcelain`. If there are uncommitted changes outside `workflow-runs/`, tell the user they would be mixed into the feature commit, and use AskUserQuestion: Continue anyway / Abort.
3. Make `run-id` = `yyyyMMdd-HHmmss-<short-kebab-slug>` from the current time and story.
4. Create `workflow-runs/<run-id>/` and write `state.json`:
   `{"run_id": "<run-id>", "story": "<story, secrets redacted>", "approvals": {}}`
5. Write the run-id (nothing else) to `workflow-runs/.active`.

## 1. Stages

For each stage, launch the named subagent with the Agent tool, passing the user story, the run id, the file paths of prior artifacts (tell it to read them), and any user feedback. Save the subagent's returned text to the artifact file, following `artifact-templates.md` (same directory).

| # | Subagent | Save to |
|---|---|---|
| 1 | requirements-analyst | `01-requirements.md` |
| 2 | architect | `02-architecture.md` |
| 3 | design-reviewer | `03-design-review.md` |
| 4 | implementation-planner | `04-plan.md` |
| 5 | implementer | `05-implementation.md` |
| 6 | code-reviewer | `06-code-review.md` |
| 7 | verifier | `07-verification.md` |
| 8 | release-preparer | `08-pr.md` (written by the agent itself) |

## 2. Approval checkpoints

At each checkpoint, summarize the artifact(s) briefly, point to the file path, and use AskUserQuestion with the options Approve, Request changes, Abort.

| Gate key | After stage | Reviews |
|---|---|---|
| `requirements` | 1 | requirements |
| `design-review` | 3 | architecture and design review |
| `plan` | 4 | implementation plan, before any code is written |
| `pre-pr` | 7 | code review and verification, before PR preparation |

- **Approve**: set `approvals.<gate key>` to `true` in `state.json`, then continue. Only the user's answer to AskUserQuestion counts as approval; never set a flag on your own.
- **Request changes**: re-run the relevant stage (for gate `design-review`, stages 2 and 3) with the feedback, overwrite its artifact, set that gate and every later gate to `false`, and ask again.
- **Abort**: stop, delete `workflow-runs/.active`, and report what exists.

## 3. Review loops

**Design review (after stage 3).**
- If the verdict is "reject" or any finding is blocking: re-run the architect with `03-design-review.md` as feedback (overwrite `02-architecture.md`), then re-run the design-reviewer (overwrite `03-design-review.md`). Allow at most 2 rework rounds, then present the checkpoint and list any unresolved blocking findings.
- If the verdict is "approve with changes" and all findings are advisory: do not rework. List the required changes at the checkpoint. After approval, tell the implementation-planner in stage 4 to incorporate every change in `03-design-review.md`, plus any comments the user gave.

**Code review (after stage 6).** If the verdict is "changes required" with blocking findings, re-run the implementer with the findings, update `05-implementation.md`, then re-run the code-reviewer and overwrite `06-code-review.md`. Allow at most 2 rework rounds; if blocking findings remain, present them at the `pre-pr` checkpoint and let the user decide. If the verifier returns "not ready", present that at `pre-pr` too.

## 4. Publish and finish

The release-preparer writes `08-pr.md` and makes two local commits: the feature commit, and a second commit that adds `workflow-runs/<run-id>/` (artifacts 01 to 08 and `state.json`) as evidence. After stage 8, check that `08-pr.md` exists and is non-empty.

Then you, the Orchestrator, publish. The target is fixed in `.claude/publish.json` (`repo_url`, `repo_slug`, `base_branch`). The `pre-pr` approval already covers publishing to that repository; do not ask again unless a step fails. `bash-guard.ps1` allows only the exact commands below, and only while `workflow-runs/.active` exists and `approvals.pre-pr` is true, so do not delete `.active` until publishing is done. Run each command on its own, with no chaining, pipes, or `&&`:

1. `gh auth status`. If not logged in, stop and tell the user to run `gh auth login` in their own terminal. Never ask for a token.
2. `git remote get-url origin`. If origin is missing, run `git remote add origin <repo_url>`. If it points elsewhere, stop and report.
3. `git push -u origin <base_branch>`, but only if the remote has no `<base_branch>` yet (`git ls-remote --heads origin <base_branch>` prints nothing). Never force.
4. `git push -u origin <feature branch>` (the branch from `08-pr.md`).
5. Extract the PR title and description from `08-pr.md` into a temporary file in the scratchpad directory, then run `gh pr create --repo <repo_slug> --base <base_branch> --head <feature branch> --title "<title>" --body-file <that file>`. The body must end with the line `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.
6. Record the PR URL in a new `## Pull request` section at the end of `08-pr.md`. This leaves `08-pr.md` uncommitted; tell the user, and do not amend or add commits.

If any step is denied or fails, stop, report the exact error, and do not try another route (no force push, no changed remote, no other repository). Finally delete `workflow-runs/.active` and report: run id, artifact folder, branch name, both commit hashes, and the PR URL.

## Safety rules

- Never write secrets, credentials, tokens, keys, connection strings, or personal data into artifacts, `state.json`, or any file; use `<redacted>`. If the user story contains any, redact them and tell the user. Do not read `.env*` files.
- Only the Orchestrator may publish, and only the step-4 commands for the repository in `.claude/publish.json`. Never force-push, change Git config, or use another repository. Subagents never publish.
- If a subagent's output contains a secret, redact it before saving.
