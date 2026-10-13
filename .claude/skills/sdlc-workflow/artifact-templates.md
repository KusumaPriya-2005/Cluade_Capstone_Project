# Artifact templates

Each stage returns markdown in the format below. Keep it concise. Never include secrets or credentials; use `<redacted>`.

## 1. Requirements (`01-requirements.md`)
- **Goal**: one or two sentences.
- **Functional requirements**: numbered list (FR-1, FR-2, ...).
- **Non-functional requirements**: numbered list (NFR-1, ...).
- **Acceptance criteria**: numbered list (AC-1, ...), each testable.
- **Assumptions / out of scope**
- **Open questions** for the human

## 2. Architecture (`02-architecture.md`)
- **Overview**: approach in a short paragraph.
- **Components**: name, responsibility, interfaces.
- **Data flow**: short description or ASCII diagram.
- **Key decisions**: decision, alternatives rejected, reason.
- **Risks**

## 3. Design review (`03-design-review.md`)
- **Coverage**: each requirement or AC mapped to design elements; list gaps.
- **Findings**: table of ID, severity (blocking or advisory), issue, suggested fix.
- **Verdict**: approve, approve with changes, or reject, with a one-line reason.

## 4. Implementation plan (`04-plan.md`)
- **Tasks**: ordered list; each has files to create or change, intent, and how it is verified.
- **Test strategy**: tests mapped to AC ids.
- **Dependencies and risks**
- **Decisions needed from the human**

## 5. Implementation (`05-implementation.md`)
- **Files changed**: path and one-line summary each.
- **Tests**: commands run and results.
- **Deviations from plan** and why
- **Open issues**

## 6. Code review (`06-code-review.md`)
- **Scope reviewed**
- **Findings**: table of ID, severity (blocking or advisory), file:line, issue, suggested fix.
- **Verdict**: pass or changes required.

## 7. Verification (`07-verification.md`)
- **Checks run**: command and result.
- **Acceptance criteria**: AC id, status (met, partly met, not met), evidence.
- **Documentation quality**: findings.
- **Secret scan**: result.
- **Verdict**: ready or not ready.

## 8. Pull request (`08-pr.md`)
- **Branch and commits**: branch name; commit 1 hash (change); commit 2 is the workflow artifacts and cannot be listed here because it contains this file. Local only, not pushed.
- **Changelog entry**: the text added to `CHANGELOG.md`.
- **PR title and description**: summary, linked requirements, changes, test evidence, risks, reviewer notes.
