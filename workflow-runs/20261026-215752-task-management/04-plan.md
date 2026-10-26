## 4. Implementation plan (KAN-1, run 20261026-215752-task-management)

Inputs: `01-requirements.md`, `02-architecture.md` (revision 2, approved) and `03-design-review.md` (round 2: approve, advisory N1-N7). The user approved the design at checkpoint 2, including rejecting control characters inside titles. The review changes N1-N7 are absorbed below. Each is tagged where it is applied.

Constraints for the implementer:
- Create only the files listed. Change no existing file, and in particular not `src/pwreset/*`, `pyproject.toml` or `tests/conftest.py`.
- Add no dependencies and install nothing.
- Run tests with `python -m pytest` only. Make no git commits.
- Every new `src/taskmgr/*.py` module starts with a docstring, then `from __future__ import annotations`, as `pwreset` does.
- Write no secrets. Use `<redacted>` in any text where a secret would appear.

Conventions confirmed in the repo (read-only):
- `pwreset` uses a `src/` layout and one module per concern. It has an in-memory repository with `__repr__` and `snapshot()`, and `__init__.py` re-exports an explicit `__all__`.
- Tests are flat files `tests/test_*.py`. Shared fakes for `pwreset` live in `tests/conftest.py`, which imports `pwreset` modules. The new tests must not rely on it.
- `tests/` has no `__init__.py`, so pytest puts `tests/` on `sys.path`. A plain helper module there can be imported by bare name.
- `pyproject.toml` has `pythonpath=["src"]` and `testpaths=["tests"]`. Package discovery (`packages.find where=["src"]`) already picks up `taskmgr`, so no packaging change is needed.

### Tasks

Order: errors/model/validation, then interfaces and the in-memory repository, service, JSON store, CLI, public API, packaging checks, and a final full run. Each task has its own tests, so it can be verified on its own with the command shown.

**T1. Errors, model and validation**
- Create:
  - `src/taskmgr/__init__.py`: docstring only for now. It is completed in T6. It is needed now so that `taskmgr` imports.
  - `src/taskmgr/errors.py`
  - `src/taskmgr/model.py`
  - `src/taskmgr/validation.py`
  - `tests/test_taskmgr_validation.py`
- `errors.py`:
  - Enums `TitleProblem` (`EMPTY`, `TOO_LONG`, `INVALID_TYPE`, `CONTROL_CHARS`) and `StorageReason` (exactly the 15 codes in the architecture: `read_failed`, `write_failed`, `not_a_file`, `invalid_encoding`, `invalid_json`, `empty_file`, `bad_shape`, `bad_version`, `unknown_key`, `missing_key`, `bad_type`, `bad_status`, `bad_id`, `bad_title`, `duplicate_id`). Add no other codes (N7).
  - Classes `TaskManagerError`, `InvalidTitleError(.problem)`, `TaskNotFoundError(.task_id)`, `IdGenerationError`, `StorageError(.path, .reason)` and `CorruptStorageError(StorageError)`.
  - Messages are fixed text, as in the architecture. `TaskNotFoundError` uses `ascii(task_id[:64])`. No message uses `str(exc)` of another exception.
- `model.py`: `TaskStatus`, `StatusFilter.matches(task)` and the frozen `Task(id, title, status=PENDING)`.
- `validation.py`:
  - `MAX_TITLE_LENGTH=200` and `MAX_ID_LENGTH=64`.
  - `normalize_title` applies these steps in order: INVALID_TYPE; `strip()`; EMPTY; TOO_LONG; CONTROL_CHARS; return the stripped title.
  - The CONTROL_CHARS step rejects `unicodedata.category(ch)` of `Cc` and also of `Cs` (lone surrogates). Both are reported as `CONTROL_CHARS` (N2).
  - `validate_task_id` uses `re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value)` and raises `ValueError` for a non-`str` or a mismatch.
- Verified by `python -m pytest tests/test_taskmgr_validation.py -q`. Tests:
  - Titles `""`, `"   "` and `"\t\n"` give EMPTY. `"\x85"` and `"\x1f"` alone also give EMPTY.
  - A 200-character title passes and a 201-character title gives TOO_LONG. A non-`str` (`None`, `5`, `b"x"`) gives INVALID_TYPE. `" Buy milk "` returns `"Buy milk"`.
  - CONTROL_CHARS cases: `"a\x00b"`, `"a\x1bb"`, `"a\x9bb"`, `"a\nb"`, `"a\tb"`, `"a\x7fb"`, and `"a\ud800b"` (N2).
  - N5 note, written in a comment in the test: `str.strip()` also strips `\x1c`-`\x1f`, `\x0b`, `\x0c` and `\x85` at the edges. So CONTROL_CHARS cases use characters that are not stripped (`\x00`, `\x1b`, `\x9b`) or put the control character in the interior.
  - Emoji and non-ASCII titles pass.
  - `InvalidTitleError` messages are fixed and never contain the title.
  - `TaskNotFoundError` with `"x\x1b[31m"` gives text containing `\x1b` and no raw ESC byte. A long id is cut at 64 characters.
  - `validate_task_id` accepts 8 hex characters and 64 characters. It rejects `""`, 65 characters, `"a b"`, `"é"`, `"../x"`, an id with `\x1b`, an id with a trailing `\n`, and `None`.
  - Hierarchy lock: `issubclass(CorruptStorageError, StorageError)` and `issubclass(StorageError, TaskManagerError)`.
  - `StatusFilter.matches` for the three filters. `Task` is frozen (assigning to a field raises).

**T2. Interfaces, in-memory repository and test helpers**
- Create:
  - `src/taskmgr/interfaces.py`: `TaskRepository` (`load_all`, `save_all`) and `IdGenerator` (`new_id`) as `Protocol`s.
  - `src/taskmgr/memory.py`: `InMemoryTaskRepository`. It keeps a private list. `load_all` returns a copy and `save_all` stores a copy. `__repr__` returns `InMemoryTaskRepository()`. `snapshot()` is test-only.
  - `tests/taskmgr_helpers.py`: fakes that are not collected by pytest and do not touch `conftest.py`. They are `SequenceIdGenerator` (ids `id000001`, ...), `AlwaysSameIdGenerator(id)` with a call counter, and `SpyTaskRepository` (wraps a repository and counts `load_all` and `save_all` calls).
  - `tests/test_taskmgr_memory.py`
- Verified by `python -m pytest tests/test_taskmgr_memory.py -q`. Tests:
  - A new repository returns `[]`.
  - A save/load round trip returns equal tasks, and the repository stores copies. Mutating the returned list does not change the stored state.
  - `repr` is the class name only.
  - The helper import works (`from taskmgr_helpers import ...`). If it does not, move the fakes into the test modules rather than touching `conftest.py`, and record that as a deviation.

**T3. Id generator and service**
- Create:
  - `src/taskmgr/system.py`: `RandomIdGenerator.new_id()` returns `secrets.token_hex(4)`.
  - `src/taskmgr/service.py`: `TaskService(repository, id_generator)`.
  - `tests/test_taskmgr_service.py`
- `service.py`:
  - There is no cache, no I/O and no printing.
  - Mutations validate first, then load, change the list, and call `save_all` once. `add` also generates the id (up to 20 attempts).
  - Private helpers: `_find_index(tasks, task_id)` raises `TaskNotFoundError` before any save. `_set_status` is shared by `complete` and `reopen`, which are idempotent. Use `dataclasses.replace` on the frozen `Task`.
  - `add`: call `normalize_title` first, then `load_all`. Make up to 20 attempts to get an id. An attempt is rejected if `validate_task_id` raises `ValueError` or the id collides with an existing id. After 20 rejected attempts, raise `IdGenerationError` with no `save_all`.
  - `list_tasks(status_filter=StatusFilter.ALL)`, `complete`, `reopen`, `edit` and `delete` are as in the architecture. Lookup ids are matched by exact equality and are not format-validated.
- Verified by `python -m pytest tests/test_taskmgr_service.py -q`. The service tests run on `InMemoryTaskRepository` and the spy. Tests:
  - AC-1 (add to an empty list gives a pending task with the generated id).
  - AC-3 (existing tasks are unchanged, order is creation order).
  - AC-2 (blank, tab and newline titles raise `InvalidTitleError`, the spy sees 0 `save_all` calls, and the list is unchanged).
  - AC-4 and AC-11 (`list_tasks` with the three filters).
  - AC-6 and AC-7 (`complete` and `reopen`, plus idempotency).
  - AC-8 (`edit` keeps the id, status and position).
  - AC-9 (a blank edit raises, there is no save, and the old title is retained).
  - AC-10 (delete B from A, B, C leaves A, C in order).
  - AC-16 (unknown id for `complete`, `reopen`, `edit` and `delete` raises `TaskNotFoundError`, the spy sees 0 saves, and the list is unchanged).
  - An id with `\x1b` is escaped in the message.
  - Id exhaustion: `AlwaysSameIdGenerator` with a store that already holds that id raises `IdGenerationError` after exactly 20 `new_id` calls and 0 `save_all` calls. A generator returning an id with a control character, or one longer than 64 characters, also raises `IdGenerationError`.
  - `RandomIdGenerator` returns 8 lowercase hex characters that pass `validate_task_id`.
  - NFR-6: the id generator is injectable.

**T4. JSON file repository**
- Create:
  - `src/taskmgr/json_store.py`
  - `tests/test_taskmgr_json_store.py`
- `JsonFileTaskRepository(path: Path)` does no I/O in its constructor. It must call `os.replace`, `os.unlink` and `json.dump` module-qualified, so the tests can patch them.
- Loader, table-driven (N7). Keep the structure below and do not use one long if-chain:
  - A tiny private helper `_fail(reason)` raises `CorruptStorageError(self._path, reason) from None`. It never uses `str(exc)` of another exception. Use only the 15 existing `StorageReason` codes.
  - Small functions or methods, one per step group:
    - `_read_raw`: `is_dir` gives `StorageError(not_a_file)`. `read_bytes` returns `[]` on `FileNotFoundError`. Any other failure gives `read_failed`.
    - `_decode_json`: 0 bytes gives `empty_file`. A strict UTF-8 failure gives `invalid_encoding`. `json.loads` raising `ValueError` or `RecursionError` gives `invalid_json`.
    - `_check_document`: the top-level steps 6-10, in order. A non-object gives `bad_shape`; no `version` gives `missing_key`; `version` not exactly the int 1 (`type(v) is int and v == 1`) gives `bad_version`; no `tasks` gives `missing_key`; an extra top-level key gives `unknown_key`; `tasks` not a list gives `bad_shape`.
    - `_parse_task` runs an ordered tuple of per-task check functions (a to g). Each one calls `_fail` on the first violation. The order is: shape; missing key then extra key; types; status; id; title (`normalize_title` raises or returns a different value gives `bad_title`); duplicate id.
  - The first failure decides the code. The check order is exactly the architecture's table.
- N1, load: wrap `is_dir`, `read_bytes` and the rest of the body of `load_all` after the corrupt-file checks, so any `OSError` becomes `StorageError(read_failed) from None`. `FileNotFoundError` is still handled first and returns `[]`. `StorageError` and `CorruptStorageError` are not `OSError`, so they pass through the handler unchanged.
- N1, save: wrap the whole of `save_all`, not just the replace. The steps are:
  1. `tmp = None` is bound first.
  2. `is_dir` gives `not_a_file`.
  3. Create the parent directories.
  4. Open `NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=parent, prefix=".tasks-", suffix=".tmp", delete=False)` and set `tmp` to its name.
  5. Inside the `with` block: `json.dump(indent=2, ensure_ascii=False)`, write `\n`, `flush`, `os.fsync`.
  6. Leave the `with` block (the file is closed), and only then call `os.replace(tmp, path)`.
  - Any `OSError` calls `_discard(tmp)` only if `tmp is not None`, then raises `StorageError(write_failed) from None`. Any other exception calls `_discard` the same way and re-raises. `_discard` swallows `OSError`.
- Verified by `python -m pytest tests/test_taskmgr_json_store.py -q`. Tests:
  - AC-15, missing file: `load_all` returns `[]` and creates nothing. A stale `.tasks-x.tmp` beside it is ignored.
  - AC-15, corrupt file: the parametrized table from the architecture (content, reason), one test function with 5 assertions per case. They are the exact `CorruptStorageError` reason, identical bytes after, `TaskService.add` on that file also raises `CorruptStorageError` with identical bytes, the directory holds only the original file, and the CLI `list` returns 3 (the CLI assertion is added in T5, when `cli.py` exists).
  - Loader cases (write bytes with literal escapes): `bad_title` includes `"a\ud800b"` (written as the JSON escape, so `json.loads` yields a lone surrogate) (N2), `"a\x1b[31mb"`, `"a\nb"`, `"a\x9bb"`, `""`, `"   "`, `" padded "`, and a 201-character title. `bad_id` includes `""`, `"a b"`, 65 characters, `"é"`, `"../x"`, an id with `\x1b`, and an id with a trailing `\n`.
  - Boundary cases that load: a 200-character title, a 64-character id, and a non-ASCII or emoji title.
  - A directory as the path gives `StorageError(not_a_file)` and the object is not a `CorruptStorageError`.
  - Round trip: `save_all` then `load_all` returns equal tasks. The text ends with `\n`, and a non-ASCII title appears literally as UTF-8 in the bytes.
  - AC-13 and AC-14 at storage and service level: a second `JsonFileTaskRepository` and `TaskService` on the same `tmp_path` file shows the tasks after add, edit, complete and reopen, and a deleted task is absent. These two end-to-end tests may live in `tests/test_taskmgr_service.py` or in this file. Pick one place.
  - F5, no leakage: marker `ZZ-MARKER-ZZ` in truncated JSON, in invalid UTF-8 bytes plus the marker, and in valid JSON with a bad title that contains the marker and a control character. In each, `str(exc)` does not contain the marker, `exc.__cause__ is None`, and `exc.__suppress_context__` is true. The CLI stderr check is in T5.
  - F1, atomic write: for each case below, the old bytes are intact and no `.tasks-*.tmp` is left. The cases are a failing `json.dump`, a failing `os.replace`, and the case where `os.unlink` also raises `OSError`. In that last case the raised error is still `StorageError(write_failed)`, not the cleanup error.
  - N4, how to patch: use `monkeypatch.setattr` on the module attribute (`taskmgr.json_store.os`, `.json`). The fake functions raise only for the expected target and delegate to the real function otherwise. These are the fakes:
    - `os.replace` raises `PermissionError` only when the destination equals the repository path.
    - `os.unlink` raises `OSError` only when the basename starts with `.tasks-` and ends with `.tmp`.
    - `json.dump` raises `OSError` only when the file object's `name` is such a temp file.
    - Everything else calls the saved real function, so pytest and other code are unaffected.
  - N1 test: the parent of the store path is an existing file (for example `<tmp>/afile/tasks.json`, where `afile` is a file). `save_all` raises `StorageError` with `write_failed` and not a raw `OSError`, with `__cause__ is None`. For `load_all` and `TaskService.add` on that path, assert a `StorageError` that is not a `CorruptStorageError`, with a reason of `read_failed` or `write_failed`. Reason: on Windows opening `file/x` can raise `FileNotFoundError`, so `load_all` may return `[]` there. Accept either outcome, and never accept a raw `OSError`.

**T5. CLI**
- Create:
  - `src/taskmgr/cli.py`
  - `src/taskmgr/__main__.py`: `from .cli import main`, then `raise SystemExit(main())`.
  - `tests/test_taskmgr_cli.py`
- `cli.py`:
  - Constants `EXIT_OK=0`, `EXIT_DOMAIN=1`, `EXIT_USAGE=2`, `EXIT_STORAGE=3`.
  - `build_parser()` uses `argparse.ArgumentParser(prog="taskmgr")` (N6).
  - `--file` is the global option placed before the subcommand. Its `type` produces a `Path` (N6). Note that `Path("")` silently becomes `.`, so use a tiny `type` function. It returns `Path(value)` and raises `argparse.ArgumentTypeError` when `value == ""`, so `--file ""` is a usage error with exit 2. The default is `None`.
  - Compare with `args.file is None` to choose `default_store_path()`, never `args.file or ...` (N6). `default_store_path()` is `Path.home() / ".taskmgr" / "tasks.json"`, called only when `--file` is absent.
  - Subcommands via `add_subparsers(dest="command", required=True)`: `add TITLE`, `list [--filter all|pending|completed]` (default `all`), `done ID`, `undo ID`, `edit ID TITLE`, `delete ID`. The help text notes that a leading `-` needs `--`.
  - Pure `render_tasks(tasks, status_filter)`. Row format is `[ ] <id>  <title>  (pending)` or `[x] <id>  <title>  (completed)`. Empty under all gives `No tasks yet.`. Empty under a filter gives `No pending tasks.` or `No completed tasks.`. There is no escaping.
  - Confirmation lines are printed only after the service call returns: `Added: <row>`, `Completed: <row>`, `Reopened: <row>`, `Updated: <row>`, `Deleted: <id>`.
  - `_emit(stream, text)` writes `text + "\n"`. On `UnicodeEncodeError` it re-encodes with `stream.encoding or "ascii"` and `errors="replace"`, then writes the degraded text.
  - `main(argv=None, *, id_generator=None, stdout=None, stderr=None) -> int` follows the architecture's sketch exactly. Only `parse_args` is inside the `SystemExit` handler (an int maps to itself, `None` to 0, anything else to 2). `StorageError` is caught before `TaskManagerError`. There is no catch-all. Streams are resolved at call time.
- Verified by `python -m pytest tests/test_taskmgr_cli.py -q`. Tests:
  - Autouse fixture: monkeypatch `Path.home`, `HOME` and `USERPROFILE` to a `tmp_path` subdirectory. Every test passes `--file` except the single default-path test, which asserts `default_store_path() == <fake home>/.taskmgr/tasks.json` (F3).
  - AC-5: an empty store `list` prints `No tasks yet.`.
  - AC-12: `list --filter completed` with no completed tasks prints `No completed tasks.`. A completely empty store with `--filter pending` prints `No pending tasks.` (F7).
  - AC-4: the rows show title and the status text label.
  - AC-2: `add ""`, `add "   "` and an embedded-newline title each return 1, stderr starts with `error:`, stdout is empty, and the file is unchanged (or not created).
  - AC-6 and AC-7 through `done` and `undo`.
  - AC-16: an unknown id for `done`, `undo`, `edit` and `delete` each returns 1. An id with `\x1b` gives a stderr line with the text `\x1b` and no raw ESC byte (F8).
  - AC-13 and AC-14 end to end (F12): `main` called many times against the same `--file` (`add`, `list`, `done`, `list`, `edit`, `list`, `delete`, `list`), asserting the printed state after each step.
  - AC-15 CLI part: a corrupt file returns 3 (not 1) for both `list` and `add`, with the bytes unchanged. Add the CLI `list` assertion to the T4 corrupt-file table test. The no-leak CLI check: stderr does not contain `ZZ-MARKER-ZZ`.
  - Exit 3 for a directory given as `--file`, with `not_a_file` in stderr. Exit 3 when `os.replace` is patched (with the N4-style fake) so that `add` fails: the old file is intact and no `.tasks-*.tmp` is left.
  - Exit 0 returns 0 with empty stderr.
  - Exit 1 for id exhaustion: the first `add` with `AlwaysSameIdGenerator("aaaa")` returns 0. The second returns 1 with stderr `error: Could not generate a unique task id.` and the file unchanged.
  - Exit 2 and 0 for argparse: `main([])`, an unknown subcommand, `list --filter bogus`, and `--file ""` each return 2 without raising `SystemExit`. `capsys` shows usage text on stderr beginning with `usage: taskmgr` (N6 `prog`), and the `--file` target is not created. `main(["--help"])` returns 0 and the help text is on stdout.
  - The `--file` value is a `Path` (assert by running `add` with a relative-path string and checking the file at that location under `tmp_path` via `monkeypatch.chdir`, or by inspecting `build_parser().parse_args([...]).file`).
  - Console encoding (F2): a fake stdout built from `io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict")` receives `add` and `list` of an emoji title. Both return 0 and do not raise. The test calls `flush()` before reading the buffer. A second repository reload shows the emoji intact.
  - Subprocess smoke test: `sys.executable -m taskmgr --file <tmp> list` with `PYTHONPATH` set to the `src` directory (use a minimal env of `PYTHONPATH` and `SYSTEMROOT`). Expect exit 0 and `No tasks yet.`. Then with a corrupt file expect exit code 3.
  - Complete the `render_tasks` unit checks (pure function, no files).

**T6. Public API**
- Change `src/taskmgr/__init__.py`. Create `tests/test_taskmgr_public_api.py`.
- `__init__.py`:
  - Re-export the model (`Task`, `TaskStatus`, `StatusFilter`), the errors (including `TitleProblem` and `StorageReason`), the Protocols, `InMemoryTaskRepository`, `JsonFileTaskRepository`, `TaskService`, `RandomIdGenerator`, and the validation helpers (`normalize_title`, `validate_task_id`, `MAX_TITLE_LENGTH`, `MAX_ID_LENGTH`).
  - Define an explicit sorted `__all__` as `pwreset` does. Do not import `cli` at package import time, so importing `taskmgr` stays light.
- Verified by `python -m pytest tests/test_taskmgr_public_api.py -q`. A test mirrors `test_root_exports`: every name in `__all__` exists, and a sample `from taskmgr import TaskService, TaskNotFoundError` works. A test checks that `taskmgr.cli` is importable separately.

**T7. Packaging and standard-library-only checks (AC-17)**
- Create `tests/test_taskmgr_imports.py`. Change no other file.
- Verified by `python -m pytest tests/test_taskmgr_imports.py -q`. Tests:
  - `ast` scan of every `src/taskmgr/*.py` (N3): for `import a.b`, compare `a` (`name.split('.')[0]`). For `from m import x`, treat `node.level > 0` as allowed (relative, where `node.module` may be `None`), and otherwise compare `node.module.split('.')[0]`. The allowed classes are: in `sys.stdlib_module_names` (this includes `__future__`), or the own package `taskmgr`. A negative control checks the scanner flags a fake third-party name (for example run the scan function over a small source string `import requests`).
  - Subprocess check (N3): copy the `test_no_third_party_import` filter exactly: `'.' not in m`, `not m.startswith('_')`, `m not in sys.stdlib_module_names`, `m != 'taskmgr'`. Import `taskmgr` and `taskmgr.cli`, and print the offenders. Expect an empty output. Use `capture_output=True, text=True, check=True` and `env={"PYTHONPATH": <repo>/src, "SYSTEMROOT": os.environ.get("SYSTEMROOT", "")}`, like the existing test.
  - A `pyproject.toml` guard (reads the file with `tomllib`, which is stdlib in 3.11): `dependencies == []` and the pytest `pythonpath` and `testpaths` are unchanged. This shows that AC-17 holds under the existing settings, and that the plan did not change the file.

**T8. Final full run**
- Change nothing, unless a failure requires a fix in the files above.
- Run `python -m pytest -q` (the whole suite: the existing `pwreset` tests and the new `taskmgr` tests). Expect all green. Record the command and result in `05-implementation.md`.
- Run `git status` (read-only) to confirm that only `src/taskmgr/` and `tests/test_taskmgr_*.py` plus `tests/taskmgr_helpers.py` are new, that `src/pwreset/`, `pyproject.toml` and `tests/conftest.py` are unchanged, and that no stray `.tasks-*.tmp` or `tasks.json` file is in the repo. Check that no real home directory file was created.
- Make no commits.

### Test strategy

Test files, all new:
- `tests/test_taskmgr_validation.py`
- `tests/test_taskmgr_memory.py`
- `tests/test_taskmgr_service.py`
- `tests/test_taskmgr_json_store.py`
- `tests/test_taskmgr_cli.py`
- `tests/test_taskmgr_public_api.py`
- `tests/test_taskmgr_imports.py`
- the helper `tests/taskmgr_helpers.py`

They use `tmp_path`, never touch `conftest.py`, and use no network or real home directory.

| AC | Tests | File |
|---|---|---|
| AC-1 | `add` to an empty list gives one pending task | service |
| AC-2 | blank, tab and newline titles rejected; zero `save_all` calls; CLI exit 1, stdout empty; embedded control characters and over-length titles also rejected | validation, service, cli |
| AC-3 | existing tasks unchanged after `add` | service |
| AC-4 | `list_tasks(ALL)` returns all; rows show title and text status | service, cli |
| AC-5 | `No tasks yet.` | cli |
| AC-6, AC-7 | `complete` and `reopen`, idempotency, CLI `done` and `undo` | service, cli |
| AC-8 | `edit` keeps id, status and position | service |
| AC-9 | blank edit rejected, old title retained, no save | service, cli |
| AC-10 | delete B leaves A and C in order | service |
| AC-11 | three filters | service, cli |
| AC-12 | `No completed tasks.`; empty store with `--filter pending` gives `No pending tasks.` | cli |
| AC-13, AC-14 | second repository and service on the same file; CLI end-to-end sequence | json_store/service, cli |
| AC-15 | missing file gives `[]`; the full corrupt-file table (exact reason, bytes unchanged, `add` also fails, no temp file, CLI exit 3); directory path; parent-is-a-file | json_store, cli |
| AC-16 | unknown id for four operations, zero saves; `\x1b` escaped | service, cli |
| AC-17 | `ast` scan; subprocess `sys.modules` check; `pyproject.toml` guard; pytest runs under the existing settings | imports |

Mapping of the design-review changes:

| Finding | Where it is verified |
|---|---|
| B1 (catch order, `main` returns int) | hierarchy-lock test (T1); exit 0/1/2/3 branch tests and the subprocess exit-status smoke test (T5) |
| B2 (strict loader, version, keys, title rule) | AC-15 corrupt-file table (T4) |
| F1 (atomic write) | failing `json.dump`, `os.replace` and `os.unlink` tests (T4); exit 3 write failure (T5) |
| F2 (console encoding) | cp1252 stdout test (T5) |
| F3 (no real home) | autouse `Path.home` fixture and default-path test (T5) |
| F4, F5 (fixed messages, no leakage) | `not_a_file` test and marker tests (T4, T5) |
| F6 (`list_tasks`) | service tests (T3) |
| F7 (empty store under a filter) | CLI test (T5) |
| F8 (escaped id) | validation, service and CLI tests |
| F9 (imports) | T7 |
| F10, F11 (no `[project.scripts]`, name unchanged) | `pyproject.toml` guard (T7); PR note |
| F12 (end-to-end restart) | CLI sequence test (T5) |
| F13 (concurrency) | documented only; no test |
| N1 | `load_all` and `save_all` wrapped, `tmp = None`; parent-is-a-file test (T4) |
| N2 | `Cs` rejected in `normalize_title`; `"a\ud800b"` in validation tests and `bad_title` loader cases (T1, T4) |
| N3 | filter and minimal env copied from `test_public_api`; `ast` scan uses `split('.')[0]` and `level > 0` (T7) |
| N4 | selective fakes that delegate to the real functions (T4, T5) |
| N5 | test comment on `strip()` edge characters (T1); item under Decisions below |
| N6 | `prog="taskmgr"`, `Path`-returning `--file` type, `is None` check, empty value rejected (T5) |
| N7 | table-driven loader with `_fail(reason)` and one function per step group; no extra codes (T4) |

### Dependencies and risks

Dependencies:
- None added. Standard library only (`argparse`, `json`, `os`, `tempfile`, `secrets`, `unicodedata`, `re`, `dataclasses`, `enum`, `pathlib`, `typing`, `ast`, `tomllib`, `subprocess`). `tomllib` needs Python 3.11, which `pyproject.toml` already requires.
- The tasks are ordered so that each one only imports modules from earlier tasks. T4 and T5 need T1-T3. T6 needs T1-T5.
- `pytest` is already the dev dependency.

Risks and mitigations:
- Windows `os.replace` and file-lock behaviour: tests patch with selective fakes (N4), so they do not depend on real locks. Close the temp file before `os.replace`.
- `load_all` when the parent path is a file differs by platform. POSIX raises `NotADirectoryError` (reason `read_failed`). Windows may raise `FileNotFoundError` (result `[]`). The N1 test accepts either outcome for `load_all` and always requires `write_failed` from `save_all`.
- `--file ""`: `type=Path` alone would turn it into `.`. The plan uses a small `Path`-returning type function that rejects empty, which is the reject-empty option of N6. If the implementer prefers a plain `type=Path`, the empty check must go in after parsing, with the same exit code 2 and the same test.
- Test helper import (`taskmgr_helpers`) relies on the default pytest `rootdir`/prepend import mode with no `tests/__init__.py`. T2 verifies this early. The fallback is to inline the fakes in the test modules.
- Subprocess tests need `sys.executable` and a minimal env (`PYTHONPATH`, `SYSTEMROOT`). Where the test also needs `HOME`/`USERPROFILE` redirected, keep them out of the subprocess, as the CLI test passes `--file`.
- The strict loader treats hand-edited files as corrupt. This is intended (D14).
- Concurrent processes can lose an update (A7, F13). Documented only.
- Test count: about 60 loader and CLI cases. Use `pytest.mark.parametrize` and the shared helper to keep the files short, and do not add features beyond the design.
- Scope creep: no README or CHANGELOG edits by the implementer. The release preparer handles the changelog.

Open items (not blocking):
- The distribution name in `pyproject.toml` stays `pwreset` (description "Password reset service layer"), and it now ships two packages (`pwreset` and `taskmgr`). This is deliberate (F11). It must be mentioned in the PR description.
- No `[project.scripts]` entry is added. The CLI runs as `python -m taskmgr` with `src` on `PYTHONPATH` or after `pip install -e .`.

### Decisions needed from the human

None blocks the start of implementation. These are already-approved defaults and open items for the record:

1. Reject embedded tabs, newlines and other control characters in titles. Default: reject. Already approved at checkpoint 2 (design review N5). Leading and trailing whitespace is still stripped. If the human reverses this, the change touches `normalize_title`, the loader's `bad_title` rule and their tests.
2. Distribution name stays `pwreset` (F11). Default: leave unchanged and mention it in the PR. Confirm if a rename or a description change is wanted. That would be a separate change and would touch `pyproject.toml`.
3. Ids that start with `-` (N6c): a hand-edited id such as `-x` is valid, but `done -x` then needs `--`. Default: leave the id rule as is and rely on the documented `--`. Generated ids are hex, so this applies only to hand-edited files. Say so if you want the first id character restricted to alphanumeric.
4. Defaults carried from the approved requirements and design, with no new decision: Python standard library only, a library plus a small `argparse` CLI, one JSON file at `~/.taskmgr/tasks.json` (override with `--file`), duplicates allowed, a 200-character title cap, an error on unknown ids, and abort on a corrupt file.
