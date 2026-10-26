## 7. Verification (KAN-1, run 20261026-215752-task-management)

### Checks run

Commands were run from the repository root (Git Bash). No lint or build tool is configured in `pyproject.toml` (only setuptools and pytest settings), so there is no linter or build command to run. I did not run a build, to avoid creating files.

| # | Command | Result |
|---|---|---|
| 1 | `python -m pytest -q` | 301 passed in 2.02s, 0 failed. This includes the existing pwreset tests. It matches the implementer's "301 passed". |
| 2 | `python -m pytest tests/test_taskmgr_*.py -q` | 176 passed in 1.92s. |
| 3 | `git status --short` | Modified: `.claude/skills/sdlc-workflow/SKILL.md` and `CLAUDE.md`. Both were already modified in the start-of-run snapshot. Untracked: `.claude/agents/sdlc-orchestrator.md`, `.mcp.json`, `Inputs/`, `docs/`, `src/taskmgr/`, `tests/taskmgr_helpers.py`, the seven `tests/test_taskmgr_*.py` files, and the two `workflow-runs/` directories. This is the same set as at the start of the run. |
| 4 | `git diff --stat` | Only the two modified files above: SKILL.md (7 insertions, 72 deletions) and CLAUDE.md (1 insertion, 1 deletion). Both pre-date this run. Git printed LF/CRLF warnings only. |
| 5 | `git diff --stat -- src/pwreset pyproject.toml tests/conftest.py README.md CHANGELOG.md` | Empty. None of these files changed. |
| 6 | Glob `**/{tasks.json,.tasks-*.tmp,*.tmp}` over the repo | No files found. There is no stray `tasks.json` or `.tasks-*.tmp` in the repo. |
| 7 | CLI end to end, batch 1 (`PYTHONPATH=src`, `--file "$TEMP/vfy-taskmgr-20261026/tasks.json"`, which is outside the repo and outside the real home) | `list` printed `No tasks yet.` with exit 0. `add "Buy milk"` printed `Added: [ ] 685ad4f0  Buy milk  (pending)` with exit 0. `add "Walk dog"` was added. `add "   "` printed `error: Title must not be empty.` with exit 1. A final `list` showed both tasks in creation order, as pending. |
| 8 | CLI end to end, batch 2 (done, undo, edit, delete, filters, `-h`, and a dump of the temp file) | Not run. The permission classifier denied the command, which included reading the temp file and piping `-h` output. I did not retry it in pieces. Those behaviours rely on the automated tests (see the AC table). |

Notes: the temp file `$TEMP\vfy-taskmgr-20261026\tasks.json` was created by the program under test, outside the repo, and I did not delete it (deleting files is blocked). `Path.home()` was not used because `--file` was always given. The repo was not touched.

### Acceptance criteria

The test file names below are in `tests/`. Test names are taken from the code review in `06-code-review.md` and match the passing suite. I confirmed that the suite passes, and I spot-checked the CLI behaviour above.

| AC | Status | Evidence |
|---|---|---|
| AC-1 | met | `test_taskmgr_service.py`, add to an empty list (one pending task titled "Buy milk"). CLI run #7: `add "Buy milk"` gave a pending task. |
| AC-2 | met | `test_add_rejects_bad_titles_without_saving` (service, uses a spy repository to prove no save). `test_taskmgr_validation.py` (42 tests). CLI `test_add_invalid_title`. CLI run #7: blank add gave exit 1 and left the list unchanged. |
| AC-3 | met | Service test: existing tasks and order kept after an add. CLI run #7: both tasks listed. |
| AC-4 | met | `test_list_tasks_filters` and `test_rows_show_title_and_status_label`. CLI run #7: rows show `[ ] id  title  (pending)`. |
| AC-5 | met | `test_empty_store_list`. CLI run #7: `No tasks yet.`, not blank. |
| AC-6 | met | `test_complete_and_reopen_with_idempotency` (service) and `test_done_and_undo` (CLI). |
| AC-7 | met | The same two tests (reopen / undo). |
| AC-8 | met | Service edit tests (id and status unchanged, new title listed) and the CLI edit test. |
| AC-9 | met | Service tests (blank edit rejected, old title kept) and the CLI blank-edit check. |
| AC-10 | met | Service delete test (A, B, C: B removed, others unchanged, order preserved). |
| AC-11 | met | `test_list_tasks_filters` covers the pending, completed and all filters. The CLI `--filter` choices come from `StatusFilter` (`cli.py:49-51`). |
| AC-12 | met | `test_empty_filter_messages`. `render_tasks` (`cli.py:67-72`) returns `No <filter> tasks.`, for example "No completed tasks." |
| AC-13 | met | `test_restart_state_changes` and `test_end_to_end_across_restarts` (a new repository instance on the same file). CLI run #7 also persisted tasks across separate processes. |
| AC-14 | met | The same restart tests cover delete, edit and status change. The CLI run did not exercise these, so the evidence is the tests. |
| AC-15 | met | The 43-case `test_corrupt_file` table in `test_taskmgr_json_store.py`. It checks the exact reason, that the bytes are identical before and after, that `add` also fails, that the CLI exits 3, and that no stray files remain. It also covers a missing file returning `[]`, a directory path, a parent-is-a-file path, and the atomic-write failure cases. CLI run #7: a missing file gave `No tasks yet.` |
| AC-16 | met | Parametrized four-operation unknown-id tests in both the service and CLI test files (complete, un-complete, edit, delete), plus the `\x1b` escape test. |
| AC-17 | met | `test_taskmgr_imports.py` (4 tests): an `ast` import scan with a negative control, a runtime `sys.modules` check, and the `pyproject.toml` guard. The suite runs with the existing `pyproject.toml` pytest settings (`pythonpath = ["src"]`, `testpaths = ["tests"]`). `pyproject.toml` is unchanged. |

All 17 AC are met. The CLI behaviour for done, undo, edit, delete, filters and help was verified through tests only, because the second manual batch was denied (check 8).

### Documentation quality

- **Docstrings:** Each of the 11 modules in `src/taskmgr/` starts with a module docstring, followed by `from __future__ import annotations`. This matches `pwreset`. Classes and methods mostly have no docstrings. For example, `TaskService` methods have none. This is consistent with the existing library's minimal style and is not a defect.
- **CLI help:** `build_parser` gives each subcommand a one-line help (add, list, done, undo, delete, edit). The `--file` help states the default (`~/.taskmgr/tasks.json`) and says to give it before the command. The parser description notes that a title or id starting with `-` needs `--`. The text is accurate. The help output itself was not run (see check 8). The implementation matches the argparse definitions I read in `cli.py`.
- **README:** `README.md` has no mention of `taskmgr` or tasks. The implementer left it untouched on purpose, and it is unchanged. A short README section is advisable (not blocking). It should cover: the package exists, the commands (`add`, `list [--filter]`, `done`, `undo`, `edit`, `delete`), the `--file` option and the default path, exit codes 0/1/2/3, and how to run it (`python -m taskmgr` with `src` on `PYTHONPATH`, or after `pip install -e .`, since there is no console script). The note should also say that concurrent processes can lose an update (F13). The README could also be updated in a follow-up PR if the team wants a minimal change.
- **CHANGELOG:** `CHANGELOG.md` is unchanged. The release preparer should add the entry.
- **Advisory items from the code review** (A1 to A7) remain open and none is blocking. Of these, A1 (assert that a temp file was left in the cleanup test) and A2 (cross-step ordering cases in the corrupt-file table) would add the most test value. A7 (the weak `--` assertion in `test_help_returns_0`) is also open.
- **Stale content:** The `pyproject.toml` description still reads "Password reset service layer (stdlib only)." That is now incomplete, because the distribution ships two packages. The PR text should say so.

### Open items for the PR (check 6)

- The distribution name in `pyproject.toml` is still `pwreset` (with the description "Password reset service layer"), and `[tool.setuptools.packages.find] where = ["src"]` now picks up both `pwreset` and `taskmgr`. Confirmed.
- There is no `[project.scripts]` entry. Confirmed. The CLI runs as `python -m taskmgr`.
- The PR description should state both points, per F11 in the plan. It should also mention the known concurrent-update limitation (F13) and the open README gap.

### Secret scan

- Scope: `src/taskmgr/`, `tests/test_taskmgr_*.py`, `tests/taskmgr_helpers.py`, and `workflow-runs/20261026-215752-task-management/`.
- Method: Grep with a case-insensitive pattern for password, secret, token, API key, bearer, authorization, private key and key headers, AWS key ids, GitHub and Slack tokens, `sk-` keys, credentials in URLs, connection strings, email addresses, SSN-like numbers, and long base64-like strings. A separate Grep for hard-coded user-home paths (`C:\Users\`, `/Users/`, `/home/`) in `src/taskmgr`.
- Result: no credentials, tokens, keys, connection strings, email addresses or personal data. The hits were all benign:
  - `import secrets` and `secrets.token_hex(4)` in `src/taskmgr/system.py` (a random id generator, not a secret).
  - Test marker strings used to prove that file content never leaks into error messages. These are dummy values.
  - Mentions of "secrets" and `secrets.token_hex` in the workflow artifacts as prose.
- No hard-coded home paths in `src/taskmgr`. I did not read any `.env*` file. Tasks hold only an id, title and status (NFR-5), and the tests assert that no file content leaks into errors.

### Verdict

**Ready.** The full suite passes (301 passed, including the 176 new taskmgr tests). All 17 acceptance criteria are met, with an automated test for each, and the CLI add/list/blank-title paths were checked live against a temp file outside the repo. No existing file was modified by the implementation. The only modified tracked files are `.claude/skills/sdlc-workflow/SKILL.md` and `CLAUDE.md`, which were already modified before this run. There are no stray `tasks.json` or `.tasks-*.tmp` files and no secrets. Open items for the PR text and the release preparer, none blocking: add the changelog entry, state that the distribution is still named `pwreset` and has no `[project.scripts]`, and consider a short README section for the new package. The second manual CLI batch was not run (denied), so those commands rely on the tests.
