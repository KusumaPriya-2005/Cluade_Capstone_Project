## 6. Code review (KAN-1, run 20261026-215752-task-management)

### Scope reviewed
- Inputs: `04-plan.md`, `02-architecture.md` (revision 2, main sketch, error table, D5, D12, D13), `01-requirements.md` (AC-1 to AC-17) and `05-implementation.md`.
- Source, read in full:
  - `src/taskmgr/errors.py`
  - `src/taskmgr/model.py`
  - `src/taskmgr/validation.py`
  - `src/taskmgr/interfaces.py`
  - `src/taskmgr/memory.py`
  - `src/taskmgr/system.py`
  - `src/taskmgr/service.py`
  - `src/taskmgr/json_store.py`
  - `src/taskmgr/cli.py`
  - `src/taskmgr/__init__.py`
  - `src/taskmgr/__main__.py`
- Tests, read in full:
  - `tests/taskmgr_helpers.py`
  - `tests/test_taskmgr_validation.py`
  - `tests/test_taskmgr_memory.py`
  - `tests/test_taskmgr_service.py`
  - `tests/test_taskmgr_json_store.py`
  - `tests/test_taskmgr_cli.py`
  - `tests/test_taskmgr_public_api.py`
  - `tests/test_taskmgr_imports.py`
- Git state: `git status --short` and `git diff --stat` show no tracked file under `src/pwreset`, `pyproject.toml`, `tests/conftest.py`, `README.md` or `CHANGELOG.md` changed. The only tracked modifications are `.claude/skills/sdlc-workflow/SKILL.md` and `CLAUDE.md`. They were already modified before this run (see the start-of-session status), and the implementer did not touch them. All taskmgr files are untracked and new.
- I did not run the tests, because Bash is limited to read-only Git commands. I rely on the reported "301 passed" and on reading the code and tests.

### Assessment against the plan, architecture and AC

**Matches the plan**
- `cli.main` follows the architecture sketch exactly:
  - Only `parse_args` is inside the `SystemExit` handler. `None` maps to 0, an int maps to itself, and anything else maps to 2.
  - `StorageError` is caught before `TaskManagerError`, so `CorruptStorageError` exits 3.
  - There is no catch-all.
  - Streams are resolved at call time.
- The exit constants are 0/1/2/3. `__main__` is `raise SystemExit(main())`.
- `--file` uses a `Path`-returning type that rejects `""`. The code uses `args.file is None`, and `default_store_path()` is called only when `--file` is absent.
- The loader step order matches the plan and architecture table. The order is:
  - read (directory check, then `FileNotFoundError` returns `[]`)
  - empty file
  - strict UTF-8
  - JSON (`ValueError` and `RecursionError`)
  - top-level non-object (`bad_shape`)
  - missing `version`
  - `version` that is not exactly the int 1, using `type(v) is int` so `True` and `1.0` are rejected
  - missing `tasks`
  - unknown top-level key
  - `tasks` not a list
  - per task: shape, missing key then extra key, types, status, id, title, duplicate
- Only the 15 `StorageReason` codes exist. `_fail` always uses `from None`. No message uses `str(exc)` of another exception.
- `load_all` wraps its whole body. `FileNotFoundError` is handled first inside `_read_raw`. Other `OSError` becomes `read_failed from None`.
- `save_all`:
  - It binds `tmp = None` first and wraps the whole body.
  - The temp file is closed before `os.replace`.
  - An `OSError` becomes `write_failed from None`, after a `_discard` that swallows `OSError`.
  - `os.replace`, `os.unlink` and `json.dump` are called module-qualified.
- Validation order is INVALID_TYPE, `strip`, EMPTY, TOO_LONG, then CONTROL_CHARS. CONTROL_CHARS rejects Cc and Cs. `validate_task_id` uses `fullmatch`, so a trailing `\n` is rejected.
- `TaskNotFoundError` uses `ascii(task_id[:64])`. Title and id errors never echo input.
- The service has no I/O. It validates before loading, makes up to 20 id attempts, and `IdGenerationError` is raised with zero saves. An unknown id raises before `save_all`.
- Conventions: every module has a docstring, then `from __future__ import annotations`, and `__init__` has a sorted `__all__`. There are no gratuitous comments (the single `Cc/Cs` comment explains a why). Only the standard library is used, and `taskmgr.cli` is not imported by the package. All of this matches `pwreset`.

**Security and privacy**
- No secrets or credentials were found.
- No file contents or exception text from `OSError`, `JSONDecodeError` or `UnicodeDecodeError` reaches the output. The tests assert that a marker string is absent from `str(exc)`, from stderr, and from `__cause__`. They also assert `__suppress_context__`.
- Titles and ids that reach the terminal are validated (no Cc or Cs characters), and unknown ids are escaped with `ascii()`.
- The `--file` path shown in `StorageError` messages is the user's own input and is not escaped. This is accepted in the architecture (path display note).
- The temp file is created in the target directory with a `.tasks-` prefix. Windows `NamedTemporaryFile` and POSIX 0600 permissions are fine here. The old file is untouched on every failure path.

**AC coverage**: every AC has a real, non-vacuous test. I found no test that only passes by accident.

| AC | Tests |
|---|---|
| AC-1, AC-3 | `test_taskmgr_service.py`: add to an empty list; existing tasks and order kept |
| AC-2 | service (`test_add_rejects_bad_titles_without_saving`), validation, and CLI `test_add_invalid_title` |
| AC-4, AC-11 | `test_list_tasks_filters` and `test_rows_show_title_and_status_label` |
| AC-5 | `test_empty_store_list` |
| AC-6, AC-7 | `test_complete_and_reopen_with_idempotency` and `test_done_and_undo` |
| AC-8, AC-9, AC-10 | service tests, plus the CLI blank-edit check |
| AC-12 | `test_empty_filter_messages` (covers the empty store with `--filter pending`) |
| AC-13, AC-14 | `test_restart_state_changes` and `test_end_to_end_across_restarts` |
| AC-15 | 43-case `test_corrupt_file` table (exact reason, bytes identical before and after, `add` also fails, CLI exit 3, no stray files); missing file; directory path; parent-is-a-file; atomic-write cases |
| AC-16 | the four-operation parametrized test in both service and CLI, plus the `\x1b` escape test |
| AC-17 | `ast` scan with a negative control, runtime `sys.modules` check, and the `pyproject.toml` guard |

**Test isolation**
- The CLI autouse fixture redirects `Path.home`, `HOME` and `USERPROFILE`. Every test passes `--file` except the single default-path test, which runs against the fake home.
- The subprocess tests use a minimal environment and pass `--file`.
- `monkeypatch.chdir` is used in one test only.
- The selective fakes delegate to the real function (`_Proxy`) and affect only `taskmgr.json_store`'s module reference, so global `os` and `json` are not touched.

**Deviations reported by the implementer**
1. Cleanup-failure test. Accepted (see A1 for one small hardening).
2. `(item, seen)` signature for all per-task checks. Accepted (see A3).
3. `except Exception` only. Accepted (see A4).
4. N4 fakes placed in `tests/taskmgr_helpers.py`. Accepted. `conftest.py` is untouched, as required.

### Findings

| ID | Severity | File:line | Issue | Suggested fix |
|---|---|---|---|---|
| A1 | advisory | `tests/test_taskmgr_json_store.py:230-242` | `test_failing_cleanup_does_not_mask_the_write_error` never proves that the `os.unlink` fake actually fired (that a temp file was left because cleanup was blocked). Because `pytest.raises(StorageError)` already catches a leaked `OSError`, the test is meaningful but weaker than intended. The `"unlink" not in str(...)` assertion is trivially true. | Before the cleanup loop, add `assert temp_files(tmp_path) != []`. Drop the `"unlink"` assertion. |
| A2 | advisory | `tests/test_taskmgr_json_store.py:45-89` | The table checks one violation per case. It does not lock the cross-step ordering that the plan says decides the code ("first failure decides"). Examples of untested ties: an extra top-level key with `tasks` not a list gives `unknown_key`; `version` 2 with no `tasks` gives `bad_version`; a task with both a missing and an extra key gives `missing_key`; a task with a bad type and a bad status gives `bad_type`; a task with a bad id and a bad title gives `bad_id`. A reordering of the `_parse_tasks` tuple would pass today. | Add three or four ordering cases to `CORRUPT_CASES`. They are cheap and need no code change. |
| A3 | advisory | `src/taskmgr/json_store.py:143-177` | Six of the seven per-task checks take a `seen` argument they do not use (only `_check_duplicate` uses it). This is unnecessary coupling that the implementer reported. It works and is small. | Optional: make the checks `(item)` only and handle `seen` in `_parse_tasks` for the final step, or keep it as is. Not worth a rework cycle. |
| A4 | advisory | `src/taskmgr/json_store.py:70-75` | `save_all` cleans up the temp file only for `Exception`. A `KeyboardInterrupt` during `json.dump` or `fsync` leaves a `.tasks-*.tmp` file. This is harmless (stale temps are ignored on load, and the old file is intact), and it follows the plan's wording. Separately, a `Task` with a lone surrogate passed directly to `save_all` would escape as a raw `UnicodeEncodeError` (a `ValueError`) after cleanup. This is unreachable through the service or the CLI, because titles are validated. | Optional: use `except BaseException` for the second handler, or a `finally`-style cleanup guarded by a success flag. Leave the repository unvalidated, as designed. |
| A5 | advisory | `src/taskmgr/errors.py:70-77` | `CorruptStorageError.__init__` skips its parent's initializer by calling `TaskManagerError.__init__` directly, and then assigns `path` and `reason` again. It works and is tested. It is fragile if `StorageError.__init__` gains logic later. | Optional: build the message in a small `_message()` hook or a shared helper. Or pass the message through `super().__init__` by splitting out the field assignment. |
| A6 | advisory | `src/taskmgr/cli.py:125` | `Path.home()` can raise `RuntimeError` (no resolvable home) when `--file` is absent. That is not a `TaskManagerError`, so the user gets a traceback. This is consistent with the "no catch-all" decision and is a rare edge case. | Optional: document it, or have `default_store_path()` raise a `StorageError(read_failed)`-style error. No change needed for this change. |
| A7 | advisory | `tests/test_taskmgr_cli.py:189-193` | `test_help_returns_0` asserts `"--" in captured.out`, which is true of almost any help text. | Optional: assert `"--file"` and the `--` note instead. |

No blocking findings.

### Verdict
**pass.** Behaviour matches the approved plan and architecture revision 2: catch order and exit codes, `SystemExit` handling, loader order and reason codes, Cc/Cs rejection, atomic write with `tmp = None` and `OSError` wrapping, and `from None` with no `str(exc)` leakage. AC-1 to AC-17 each have real tests, and the tests are isolated from the real home directory. No existing file was modified by the implementation. The advisory items can be left for a later change or taken at the Orchestrator's discretion. A1 and A2 are the most valuable hardenings.
