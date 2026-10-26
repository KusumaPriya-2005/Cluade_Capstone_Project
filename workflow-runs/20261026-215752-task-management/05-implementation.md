## 5. Implementation (KAN-1, run 20261026-215752-task-management)

All of T1 to T8 are done in the current working tree on `feature/profile-update`. I made no commits, branches or Git config changes, and ran no push or `gh`. Everything uses the standard library only, and nothing was installed.

### Files changed

All files are new. No existing file was modified.

Source, in `src/taskmgr/`:
- `__init__.py`: public API with a sorted `__all__`. It does not import `cli`.
- `errors.py`: `TitleProblem` and `StorageReason` (the 15 codes), plus the error classes with fixed messages. `TaskNotFoundError` uses `ascii(task_id[:64])`.
- `model.py`: `TaskStatus`, `StatusFilter.matches` and the frozen `Task`.
- `validation.py`: `normalize_title` (rejects category Cc and Cs characters), `validate_task_id`, `MAX_TITLE_LENGTH` and `MAX_ID_LENGTH`.
- `interfaces.py`: `TaskRepository` and `IdGenerator` Protocols.
- `memory.py`: `InMemoryTaskRepository`.
- `system.py`: `RandomIdGenerator`, which returns `secrets.token_hex(4)`.
- `service.py`: `TaskService` with `add`, `list_tasks`, `complete`, `reopen`, `edit` and `delete`. It has no I/O and no cache.
- `json_store.py`: `JsonFileTaskRepository`. The loader is table-driven, with `_fail` and one method per step group. `save_all` is wrapped as a whole with `tmp = None` bound first, and it calls `os.replace`, `os.unlink` and `json.dump` module-qualified.
- `cli.py`: the exit-code constants, `build_parser`, `default_store_path`, `render_tasks`, `_emit` and `main`. `--file` uses a `Path`-returning type that rejects `""`. The code checks `args.file is None`.
- `__main__.py`: `raise SystemExit(main())`.

Tests, in `tests/`:
- `taskmgr_helpers.py`: `SequenceIdGenerator`, `AlwaysSameIdGenerator` and `SpyTaskRepository`, plus the selective N4 fakes `patch_replace_fails`, `patch_unlink_fails` and `patch_dump_fails`. The fakes swap `json_store.os` or `json_store.json` for a delegating proxy, so the global modules are not touched.
- `test_taskmgr_validation.py`: 42 tests.
- `test_taskmgr_memory.py`: 5 tests.
- `test_taskmgr_service.py`: 32 tests.
- `test_taskmgr_json_store.py`: 57 tests. It covers the corrupt-file table, including the CLI exit-3 assertion, plus no-leak, atomic-write, round-trip, restart (AC-13 and AC-14) and parent-is-a-file cases.
- `test_taskmgr_cli.py`: 32 tests. It has the autouse fake-home fixture, the cp1252 stdout test and the `python -m taskmgr` subprocess exit-status test.
- `test_taskmgr_public_api.py`: 4 tests.
- `test_taskmgr_imports.py`: 4 tests.

### Tests

Commands and results:
- `python -m pytest tests/test_taskmgr_validation.py -q`: 42 passed.
- `python -m pytest tests/test_taskmgr_memory.py -q`: 5 passed. The `from taskmgr_helpers import ...` import works, so the fallback was not needed.
- `python -m pytest tests/test_taskmgr_service.py -q`: 32 passed.
- `python -m pytest tests/test_taskmgr_json_store.py -q`: 57 passed.
- `python -m pytest tests/test_taskmgr_cli.py tests/test_taskmgr_json_store.py -q`: 89 passed.
- `python -m pytest tests/test_taskmgr_public_api.py -q`: 4 passed.
- `python -m pytest tests/test_taskmgr_imports.py -q`: 4 passed.
- Final full run, `python -m pytest -q`: **301 passed, 0 failed** in 2.47s. This includes the existing `pwreset` tests.

`git status` check (read-only):
- Only `src/taskmgr/`, `tests/taskmgr_helpers.py` and the seven `tests/test_taskmgr_*.py` files are new in the code tree.
- `git diff --stat` for `src/pwreset`, `pyproject.toml`, `tests/conftest.py`, `README.md` and `CHANGELOG.md` is empty.
- The other `M` and `??` entries (`.claude/`, `CLAUDE.md`, `.mcp.json`, `Inputs/`, `docs/`, `workflow-runs/`) were already there at the start of the session.
- No stray `.tasks-*.tmp` or `tasks.json` file is in the repo.
- `~/.taskmgr` does not exist, so nothing was written to the real home directory.

### Deviations from plan

1. **Cleanup-failure test (T4, F1).** The plan says that in the case where `os.unlink` also raises, no `.tasks-*.tmp` is left. That cannot hold when the fake blocks every cleanup unlink. The test therefore asserts the following:
   - the error is still `StorageError(write_failed)`;
   - the old bytes are intact;
   - the unlink error is not leaked.
   The test then removes the stale temp file itself, because stale temp files are ignored on load by design. The other two atomic-write cases (failing `json.dump` and failing `os.replace`) do assert that no temp file is left.
2. **Duplicate-id check (T4).** `_check_duplicate` is the 7th entry in the per-task check tuple. To fit that, all per-task checks take `(item, seen)`. This matches "a to g" in the plan.
3. **`_discard` and the second handler (T4).** `save_all` has a final `except Exception` that calls `_discard` and re-raises. `KeyboardInterrupt` and other `BaseException`s are not cleaned up. This follows the plan's wording and is harmless, because stale temp files are ignored.
4. **N4 fakes (T4).** The fakes are in `tests/taskmgr_helpers.py`, so T4 and T5 share them. The helpers file is one of the plan's named files, and `conftest.py` is untouched.

### Open issues

- `parent-is-a-file` behaviour differs by platform (N1). The test accepts either `[]` or `StorageError(read_failed)` from `load_all`, as planned. On this Windows host it passes.
- For the PR description (F11): the distribution is still named `pwreset` and now ships two packages. There is no `[project.scripts]` entry, so the CLI runs as `python -m taskmgr` with `src` on `PYTHONPATH`, or after `pip install -e .`.
- Concurrent processes can lose an update (F13). This is documented only, with no test.
- `README.md` and `CHANGELOG.md` were deliberately not edited. The release preparer handles the changelog, and the task-manager usage is not yet documented in the README.
