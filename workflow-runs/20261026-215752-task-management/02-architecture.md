## 2. Architecture (KAN-1, run 20261026-215752-task-management) - revision 2 (rework round 1)

### Overview
Add a new, self-contained package `src/taskmgr` next to `src/pwreset`, which stays untouched. It follows the pwreset layout and conventions:
- `errors.py` holds the domain errors.
- `interfaces.py` holds `Protocol`s for injected collaborators.
- `memory.py` holds an in-memory repository.
- `system.py` holds production defaults.
- Every module starts with `from __future__ import annotations`, as pwreset does.

The design has three layers:
1. A pure domain layer: frozen `Task` dataclass, status and filter enums, and the title and id rules in `validation.py`.
2. `TaskService`. It depends only on two Protocols, `TaskRepository` and `IdGenerator`. It has no I/O, no printing and no knowledge of JSON.
3. Adapters: `InMemoryTaskRepository` (tests), `JsonFileTaskRepository` (stdlib `json`, atomic write, strict loader) and a thin `argparse` CLI. The CLI only parses arguments, calls the service, renders text and maps errors to exit codes.

Persistence is whole-list: `load_all()` and `save_all(tasks)`. Every mutating call does validate, load, change in memory, then one `save_all`. A rejected operation never reaches `save_all`, so nothing changes (FR-2, FR-11). A corrupt file fails at the load step, so it is never overwritten (NFR-4). The service has no cache, so a new service on the same storage always sees the saved state (AC-13, AC-14).

One invariant carries the output-safety design. **A `Task` that reaches storage or the screen always has a valid id and a valid title.** The service enforces this on write. The loader enforces it on read. That is why `render_tasks` needs no escaping (B2).

### Components

Files under `src\taskmgr\`. Tests go in `tests\`.

| Module | Responsibility | Interface |
|---|---|---|
| `model.py` | Plain data and enums. | `TaskStatus(Enum)`: `PENDING="pending"`, `COMPLETED="completed"`. `StatusFilter(Enum)`: `ALL`, `PENDING`, `COMPLETED` (values `"all"`, `"pending"`, `"completed"`), with `matches(task) -> bool`. `@dataclass(frozen=True) Task(id: str, title: str, status: TaskStatus = PENDING)`. |
| `errors.py` | Domain errors, mirroring `pwreset.errors`. | See the error table below. |
| `validation.py` | The single title rule and the id rule. Used by the service on write and by the loader on read. | See "Validation rules" below. |
| `interfaces.py` | Protocols for injected collaborators. | `TaskRepository`: `load_all() -> list[Task]` (creation order; a missing store gives `[]`; may raise `StorageError` or `CorruptStorageError`) and `save_all(tasks: Sequence[Task]) -> None` (replaces the whole stored list). `IdGenerator`: `new_id() -> str`. |
| `memory.py` | `InMemoryTaskRepository`, for tests. | Holds a private list. `load_all` returns a copy. `save_all` stores a copy. `__repr__` returns the class name only. `snapshot()` is test-only. |
| `json_store.py` | `JsonFileTaskRepository(path: Path)`. Constructing it does no I/O. | Strict loader and atomic writer. See "Storage rules" below. |
| `system.py` | Production default, mirroring `pwreset.system`. | `RandomIdGenerator.new_id()` returns `secrets.token_hex(4)` (8 lowercase hex chars). It satisfies the id rule. |
| `service.py` | All task logic. | `TaskService(repository, id_generator)`. See below. |
| `cli.py` | Thin `argparse` front end. | `build_parser()`, `default_store_path()`, `main(argv=None, *, id_generator=None, stdout=None, stderr=None) -> int`, and the pure `render_tasks(tasks, status_filter) -> str`. |
| `__main__.py` | `python -m taskmgr`. | `from .cli import main` then `raise SystemExit(main())` |
| `__init__.py` | Public API with `__all__`, as pwreset does. | Re-exports the model, errors, Protocols, repositories, service and generators. |

**Errors (`errors.py`)**

| Class | Parent | Notes |
|---|---|---|
| `TaskManagerError` | `Exception` | Base class. |
| `InvalidTitleError` | `TaskManagerError` | Carries `.problem: TitleProblem`. `TitleProblem` is an Enum with `EMPTY`, `TOO_LONG`, `INVALID_TYPE`, `CONTROL_CHARS`. The message is fixed per problem (for example `Title must not be empty.`) and never echoes the title. |
| `TaskNotFoundError` | `TaskManagerError` | Carries `.task_id`. The message is `Task not found: ` followed by `ascii(task_id[:64])`, so control characters and ANSI escapes print as `\x1b`, never raw (F8). |
| `IdGenerationError` | `TaskManagerError` | Raised by `add` when no valid unique id is produced. The message is fixed: `Could not generate a unique task id.` |
| `StorageError` | `TaskManagerError` | Carries `.path` and `.reason: StorageReason`. The message is fixed text: `Storage problem (<reason.value>): <path>`. It never uses `str(exc)` of an `OSError`, `UnicodeDecodeError` or `JSONDecodeError`, and it is always raised with `from None` (F4, F5). |
| `CorruptStorageError` | `StorageError` | Same fields. The message is `Storage file is corrupt (<reason.value>): <path>. The file was not modified.` |

`StorageReason` is an Enum of fixed reason codes. All values are lowercase codes:
- I/O codes: `read_failed`, `write_failed`, `not_a_file`.
- Corrupt-file codes: `invalid_encoding`, `invalid_json`, `empty_file`, `bad_shape`, `bad_version`, `unknown_key`, `missing_key`, `bad_type`, `bad_status`, `bad_id`, `bad_title`, `duplicate_id`.

`StorageError` is raised only with the I/O codes. `CorruptStorageError` is raised only with the corrupt-file codes.

**Validation rules (`validation.py`)**

Constants: `MAX_TITLE_LENGTH = 200`, `MAX_ID_LENGTH = 64`.

`normalize_title(title: object) -> str` applies these steps in order:
1. A non-`str` raises `INVALID_TYPE`.
2. Strip with `str.strip()` (A6).
3. An empty result (empty, spaces, tabs, newlines) raises `EMPTY`. This is AC-2.
4. A length over 200 raises `TOO_LONG`.
5. Any character with `unicodedata.category(ch) == "Cc"` raises `CONTROL_CHARS`. This covers C0 (`\x00`-`\x1f`, including ESC `\x1b`), DEL `\x7f` and C1 (`\x80`-`\x9f`, including CSI `\x9b`). A newline or tab inside a title is therefore rejected. Only leading and trailing whitespace is stripped.
6. It returns the stripped title.

`validate_task_id(value: object) -> str` returns the value only if it is a `str` and `re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value)` matches. It uses `fullmatch`, not `$`, so a trailing newline is not accepted. Otherwise it raises `ValueError` (internal; callers map it to `IdGenerationError` or to `bad_id`). Ids are therefore non-empty, at most 64 characters, ASCII, and free of control characters and path separators.

**Storage rules (`json_store.py`)**

*Stored format, version 1:*
```
{"version": 1, "tasks": [{"id": "a1b2c3d4", "title": "Buy milk", "status": "pending"}]}
```
It holds only id, title and status (NFR-5). The file is written as UTF-8 with `indent=2`, `ensure_ascii=False` and a trailing `\n`.

*`load_all`* applies these steps in order. The first failure decides the reason code, so the code is deterministic:

| Step | Check | Result |
|---|---|---|
| 1 | `path.is_dir()` | `StorageError(not_a_file)`. This is not a corrupt-file case (F4). |
| 2 | `path.read_bytes()` | `FileNotFoundError` returns `[]` (AC-15; nothing is created). Any other `OSError` gives `StorageError(read_failed)`. |
| 3 | 0 bytes | `empty_file` |
| 4 | Strict UTF-8 decode | `invalid_encoding` |
| 5 | `json.loads` (a `ValueError`, which includes `JSONDecodeError`, or a `RecursionError`). A BOM or whitespace-only content fails here. | `invalid_json` |
| 6 | Top level is not an object | `bad_shape` |
| 7 | No `version` key | `missing_key` |
| 8 | `version` is not exactly the int 1 (`type(v) is int and v == 1`, so `True`, `1.0`, `"1"`, `null` and `2` all fail) | `bad_version` |
| 9 | No `tasks` key, then any key other than `version` and `tasks` | `missing_key`, then `unknown_key` |
| 10 | `tasks` is not a list | `bad_shape` |

Then, for each task item, in this order:

| Step | Check | Result |
|---|---|---|
| a | Item is not an object | `bad_shape` |
| b | A key of `id`, `title`, `status` is missing, then any extra key | `missing_key`, then `unknown_key` |
| c | `id`, `title` or `status` is not a `str` | `bad_type` |
| d | `status` is not one of `"pending"`, `"completed"` (case-sensitive) | `bad_status` |
| e | `validate_task_id(id)` fails | `bad_id` |
| f | `normalize_title(title)` raises, or returns a value different from the stored title | `bad_title` |
| g | `id` already seen | `duplicate_id` |

Step f means a stored title must already be stripped, non-empty, at most 200 characters and free of control characters. This is the same rule as on write. A hand-edited ANSI escape in a title or id is therefore rejected at load, never rendered.

Stale `.tasks-*.tmp` files in the directory are ignored, because `load_all` reads only `path`.

*`save_all`:* these steps apply on Windows and POSIX (F1).
1. If `path.is_dir()`, raise `StorageError(not_a_file)`.
2. Create the parent directories.
3. Open `tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=parent, prefix=".tasks-", suffix=".tmp", delete=False)`. The explicit UTF-8 encoding is needed because the Windows default codec is not UTF-8.
4. Inside a `with` block: `json.dump`, write `\n`, `flush`, `os.fsync(f.fileno())`.
5. Leave the `with` block, so the file is closed. Only then call `os.replace(tmp, path)`. A replace inside the open handle would fail on Windows.
6. On `OSError`, call `_discard(tmp)` and raise `StorageError(write_failed) from None`. On any other exception, call `_discard(tmp)` and re-raise.
7. `_discard` is `try: os.unlink(tmp)` with `except OSError: pass`. A failed cleanup, such as a Windows lock, never masks the original error. The old file is intact.
8. Durability is best effort. A directory `fsync` is not possible on Windows, and a hard crash can leave a stale temp file. That is harmless (see `load_all`).

Tests monkeypatch `taskmgr.json_store.os.replace`, `taskmgr.json_store.os.unlink` and `taskmgr.json_store.json.dump`. So `json_store.py` must use the module-qualified calls `os.replace`, `os.unlink` and `json.dump`.

**`TaskService` operations** (`service.py`)

All of these raise `InvalidTitleError`, `TaskNotFoundError`, `IdGenerationError` or `StorageError`/`CorruptStorageError` as noted.
- `add(title) -> Task`: validate the title first, then load. Then generate an id, up to 20 attempts. An attempt is rejected if `validate_task_id` fails or the id collides with an existing id. After 20 rejected attempts it raises `IdGenerationError`, with no `save_all`. Otherwise it appends and saves once.
- `list_tasks(status_filter=StatusFilter.ALL) -> list[Task]`: load, then filter. Order is preserved. The method is named `list_tasks`, so it does not shadow the builtin `list` (F6).
- `complete(task_id) -> Task` and `reopen(task_id) -> Task`: set the status to `COMPLETED` or `PENDING`. These are idempotent (D7). They save once.
- `edit(task_id, title) -> Task`: validate the title, then replace it in place. The id, status and position are kept.
- `delete(task_id) -> None`: remove the task. Other tasks keep their relative order.

For `complete`, `reopen`, `edit` and `delete`, an unknown id raises `TaskNotFoundError` before any `save_all`. Lookup ids are matched by exact string equality. They are not format-validated, and the error message escapes them.

**CLI** (`cli.py`)

Global option `--file PATH`, placed before the subcommand: `python -m taskmgr --file F add "Buy milk"`. The default is `default_store_path()`, which returns `Path.home() / ".taskmgr" / "tasks.json"`. It is called only when `--file` is absent, so `Path.home()` is resolved lazily (F3). Subcommands (`add_subparsers(dest="command", required=True)`):
- `add TITLE`
- `list [--filter all|pending|completed]` (default `all`, A8)
- `done ID`
- `undo ID`
- `edit ID TITLE`
- `delete ID`

A title that starts with `-` needs `--`. This is documented in the CLI help.

Rendering and messages:
- Each row is `[ ] <id>  <title>  (pending)` or `[x] <id>  <title>  (completed)`. The text label is always printed, so status is not conveyed by symbol alone. `render_tasks` does no escaping, because of the invariant in the Overview.
- An empty result under `all` prints `No tasks yet.`.
- An empty result under `pending` or `completed` prints `No pending tasks.` or `No completed tasks.`. This also applies when the whole store is empty (F7). The wording is deliberate. It names the filter (AC-12), is true in both situations, and needs no second load. It is covered by a test.
- Mutating commands print one confirmation line, such as `Added: [ ] <id>  <title>  (pending)` or `Deleted: <id>`. The line is printed only after the service call, and so after the save, succeeded.

**Exit codes and the shape of `main` (B1)**

`main` returns an `int` in every case. It never raises `SystemExit`. Constants: `EXIT_OK=0`, `EXIT_DOMAIN=1`, `EXIT_USAGE=2`, `EXIT_STORAGE=3`.

```
def main(argv=None, *, id_generator=None, stdout=None, stderr=None) -> int:
    out = sys.stdout if stdout is None else stdout      # resolved at call time
    err = sys.stderr if stderr is None else stderr
    try:
        args = build_parser().parse_args(argv)           # ONLY parse_args is inside this try
    except SystemExit as exc:                            # argparse: errors raise SystemExit(2), --help raises SystemExit(0)
        return _exit_code(exc)                           # int -> itself, None -> 0, anything else -> 2
    try:
        repo = JsonFileTaskRepository(args.file or default_store_path())
        service = TaskService(repo, id_generator or RandomIdGenerator())
        _dispatch(args, service, out)                    # prints results via _emit
        return EXIT_OK
    except StorageError as exc:                          # FIRST: also catches CorruptStorageError
        _emit(err, f"error: {exc}"); return EXIT_STORAGE
    except TaskManagerError as exc:                      # SECOND: InvalidTitle, TaskNotFound, IdGeneration
        _emit(err, f"error: {exc}"); return EXIT_DOMAIN
```

Rules:
- **Catch order.** `StorageError` is caught before `TaskManagerError`, because `CorruptStorageError` is a `StorageError`, which is a `TaskManagerError`. The reverse order would send storage failures to exit 1.
- **argparse.** `parse_args` is the only call inside the `SystemExit` handler. Usage errors (no subcommand, unknown subcommand, bad `--filter` value, missing argument) return 2. The usage text goes to the real `sys.stderr`, not the injected `err` stream, so tests read it with `capsys`. `--help` returns 0 and prints to the real `sys.stdout`. Nothing is read or written on this path, so the store file is not created.
- **Exit codes.** 0 is success. 1 is a domain error: invalid title, task not found, or id exhaustion (`IdGenerationError`, stderr `error: Could not generate a unique task id.`). 2 is a usage error. 3 is any storage error: a corrupt file, a directory given as `--file`, or an `OSError` on read or write.
- **No catch-all.** An unexpected exception propagates as a traceback, so bugs are not hidden behind a domain exit code. This is deliberate.
- **Console encoding (F2).** All output goes through `_emit(stream, text)`. It writes `text + "\n"`. On `UnicodeEncodeError` it re-encodes with `stream.encoding or "ascii"` and `errors="replace"`, then writes the degraded text. A title such as an emoji on a cp1252 console therefore prints `?` instead of crashing. Storage is unaffected, because the file is always written as explicit UTF-8.
- **No `str(exc)` leakage (F5).** Messages come only from the fixed-text exception classes above. `main` prints `error: {exc}` only for `TaskManagerError` subclasses.

### Data flow
```
argv -> cli.main -> parse_args  --SystemExit--> return 0 (help) / 2 (usage)
                 -> JsonFileTaskRepository(path) + TaskService(repo, RandomIdGenerator)
   add/edit:        normalize_title -> repo.load_all -> (add: new_id + validate_task_id + collision check)
                    -> change list -> repo.save_all
   done/undo/delete: repo.load_all -> find id (else TaskNotFoundError) -> change list -> repo.save_all
   list:            repo.load_all -> StatusFilter.matches -> render_tasks -> _emit(stdout)

load_all: is_dir? -> read_bytes (missing => []) -> empty? -> utf-8 -> json -> version -> keys -> per-task rules
save_all: tmp file (same dir, UTF-8) -> flush+fsync -> close -> os.replace(tmp, tasks.json)

Errors, caught in this order:
   StorageError / CorruptStorageError -> stderr "error: ...", exit 3
   TaskManagerError (InvalidTitle, TaskNotFound, IdGeneration) -> stderr "error: ...", exit 1
   (a mutation always loads first, so a corrupt file is never overwritten)
```

### Requirement and AC coverage
Test files are named `tests\test_taskmgr_*.py`. Shared fakes live in the test modules or in a helper module with a distinct name. They do not change the existing `conftest.py`. The fakes are:
- a sequence `IdGenerator`;
- an `AlwaysSameIdGenerator` that always returns one id;
- a spy repository that counts `save_all` calls.

**CLI test rules (F3).** Every CLI test passes `--file <tmp_path>/...`. The CLI test module also has an autouse fixture. It monkeypatches `Path.home` (and the `HOME` and `USERPROFILE` environment variables) to a `tmp_path` subdirectory. A test that forgets `--file` therefore can never touch the real home. One test checks that `default_store_path()` is `<fake home>/.taskmgr/tasks.json`.

| AC | How it is satisfied | Test |
|---|---|---|
| AC-1 | `add` on an empty repo gives one `Task` with status pending and a generated id. | service |
| AC-2 | `normalize_title` rejects `""`, `"   "` and `"\t\n"` with `InvalidTitleError(EMPTY)`. It also rejects embedded control characters (`CONTROL_CHARS`), over-length titles (`TOO_LONG`) and non-str values (`INVALID_TYPE`). The service validates before load and save, so the spy sees zero `save_all` calls and the list is unchanged. The CLI exits 1 and stdout is empty. | validation, service, cli |
| AC-3 | `add` appends. Existing tasks are unchanged and `list_tasks(ALL)` returns them all. | service |
| AC-4 | `list_tasks(ALL)` returns every `Task` with title and status. `render_tasks` prints both. | service and cli |
| AC-5 | `render_tasks([], ALL)` prints `No tasks yet.`. | cli |
| AC-6, AC-7 | `complete` and `reopen` set the status. A following `list_tasks` and the render show it. | service and cli |
| AC-8 | `edit` replaces the title in place. The id and status are unchanged. | service |
| AC-9 | `edit` with a blank title raises `InvalidTitleError`. There is no save and the old title is retained. | service |
| AC-10 | `delete` of B leaves A and C in their original relative order. | service |
| AC-11 | `StatusFilter.matches` drives `list_tasks(PENDING)`, `list_tasks(COMPLETED)` and `list_tasks(ALL)`. | service |
| AC-12 | An empty result under a non-`all` filter renders `No <filter> tasks.`. A test with a completely empty store and `--filter pending` expects `No pending tasks.` (F7). | cli |
| AC-13, AC-14 | Service level: each test builds a second `JsonFileTaskRepository` and `TaskService` on the same `tmp_path` file. It checks that the tasks come back after add, edit, complete and reopen, and that a delete is absent. CLI end to end (F12): one test calls `main` several times against the same `--file` and reads each result from a fresh call. The sequence is `add`, `list`, `done`, `list`, `edit`, `list`, `delete`, `list`. The test asserts the printed state after each step. | json repo, service, cli |
| AC-15 | See "AC-15 test cases" below. | json repo and cli |
| AC-16 | For `complete`, `reopen`, `edit` and `delete` with an unknown id, `TaskNotFoundError` is raised and the stored list is unchanged (no `save_all`). The CLI exits 1. An id containing `\x1b` produces a stderr line with the escaped form `\x1b` and no raw ESC byte (F8). | service and cli |
| AC-17 | An `ast` scan of `src\taskmgr\*.py` asserts that every import is one of: (a) a name in `sys.stdlib_module_names` (this includes `__future__`); (b) a relative import (`level > 0`); (c) the package's own name `taskmgr` or `taskmgr.*` (F9). A second test runs a subprocess with `sys.executable` and `PYTHONPATH` set to `src`. It imports `taskmgr` and `taskmgr.cli` and asserts that every top-level name in `sys.modules` is in `sys.stdlib_module_names` or is `taskmgr`. This mirrors `test_public_api.py`. The suite runs under the existing `[tool.pytest.ini_options]`, with `pythonpath=["src"]` and `testpaths=["tests"]`. | imports test |

**Exit-code and `main` tests (B1)**

These tests cover each branch of `main`:
- **Hierarchy lock.** `issubclass(CorruptStorageError, StorageError)` and `issubclass(StorageError, TaskManagerError)`. This documents why the catch order matters.
- **Exit 0.** Success returns 0 and writes nothing to stderr.
- **Exit 1 (invalid title).** Returns 1, stderr starts with `error:`, stdout is empty, and the file is unchanged.
- **Exit 1 (unknown id).** `done`, `undo`, `edit` and `delete` with an unknown id each return 1.
- **Exit 3 (corrupt file).** A corrupt file returns 3 and not 1 (this proves the catch order), for both `list` and `add`. The file bytes are unchanged.
- **Exit 3 (directory path).** `--file` pointing at a directory returns 3, and stderr contains `not_a_file`.
- **Exit 3 (write failure).** With `taskmgr.json_store.os.replace` monkeypatched to raise `PermissionError`, `add` returns 3, the old file is intact and no `.tasks-*.tmp` file is left.
- **Exit 1 (id exhaustion).**
  - Service level: an `AlwaysSameIdGenerator` and a store that already holds that id make `add` raise `IdGenerationError` after exactly 20 `new_id` calls and zero `save_all` calls.
  - Service level: a generator that returns an id with a control character or too long (an invalid id) also raises `IdGenerationError`.
  - CLI level: the first `add` with `id_generator=AlwaysSameIdGenerator("aaaa")` returns 0. The second returns 1 with stderr `error: Could not generate a unique task id.`, and the file is unchanged.
- **Exit 2 and 0 (argparse).** `main([])`, an unknown subcommand, and `list --filter bogus` each return 2 without raising `SystemExit`. `capsys` shows the usage text on stderr, and the `--file` target is not created. `main(["--help"])` returns 0 and `capsys` shows the help text on stdout.
- **Subprocess smoke test.** One subprocess test runs `python -m taskmgr --file <tmp> list`, with `PYTHONPATH` set to `src`. It expects process exit code 0 and `No tasks yet.`. It also runs the same command with a corrupt file and expects process exit code 3. This confirms that `__main__` turns the returned `int` into the real exit status.
- **Console encoding (F2).** A fake stdout built from `io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict")` receives `add` and `list` with a title containing an emoji. Both return 0 and do not raise `UnicodeEncodeError`. The test calls `flush()` before it reads the buffer. A reload of the file with a second repository shows the emoji intact.

**AC-15 test cases (B2)**

Missing file: `load_all` returns `[]`, no error, and the file is not created. A stale `.tasks-x.tmp` file beside it is ignored.

Corrupt-file cases, parametrized as (file content, expected reason code):

| Content | Reason |
|---|---|
| 0 bytes | `empty_file` |
| `b"\xff\xfe\x00"` and an invalid byte after valid JSON | `invalid_encoding` |
| Garbage, truncated JSON, whitespace only, a UTF-8 BOM before valid JSON | `invalid_json` |
| Top level `[]`, `"x"` or `null`; `tasks` not a list; a task that is not an object | `bad_shape` |
| No `version`; no `tasks`; a task without `title` | `missing_key` |
| `version` of `2`, `"1"`, `1.0`, `true`, `null` | `bad_version` |
| An extra top-level key; an extra per-task key | `unknown_key` |
| A numeric id; `null` title; numeric status | `bad_type` |
| Status `"done"` or `"PENDING"` | `bad_status` |
| Id `""`, `"a b"`, 65 characters, `"é"`, `"../x"`, one containing `\x1b`, one with a trailing `\n` | `bad_id` |
| Title `""`, `"   "`, `" padded "` (not stripped), 201 characters, `"a\x1b[31mb"`, `"a\nb"`, `"a\x9bb"` (C1 control) | `bad_title` |
| Two tasks with the same id | `duplicate_id` |

Each corrupt case asserts these:
1. `load_all` raises `CorruptStorageError` with the exact reason code.
2. The bytes on disk are identical afterwards.
3. `TaskService.add` on that file also raises `CorruptStorageError`, and the bytes are still identical.
4. The directory contains only the original file (no temp file).
5. The CLI `list` returns 3.

Further cases:
- Boundary values load: a title of exactly 200 characters, an id of exactly 64 characters, and a non-ASCII or emoji title.
- A directory as the path gives `StorageError` with `not_a_file`, and the object is not a `CorruptStorageError`.
- A round trip: `save_all`, then `load_all` returns equal tasks. The file text ends with `\n`, and a non-ASCII title appears literally (as UTF-8) in the bytes.
- No leakage (F5):
  - A file whose content embeds the marker `ZZ-MARKER-ZZ` is tested in several shapes: truncated JSON, invalid UTF-8 bytes plus the marker, and valid JSON with a bad title that contains the marker and a control character.
  - For each, `str(exc)` and the CLI stderr must not contain the marker.
  - `exc.__cause__ is None` and `exc.__suppress_context__` is true.
- Atomic write (FR-10, NFR-4, F1):
  - A failure injected into `json.dump` or `os.replace` leaves the old bytes intact and no `.tasks-*.tmp` file.
  - If `os.unlink` also raises `OSError`, the raised error is still the `StorageError(write_failed)`, not the cleanup error.

Also covered: NFR-6 (the id generator and file path are injectable) and NFR-5 (rendered output and error messages contain only id, title and status, never file contents).

### Packaging change to `pyproject.toml`
No change. `[tool.setuptools.packages.find] where = ["src"]` already discovers `taskmgr` once it has an `__init__.py`. `pythonpath = ["src"]` already lets pytest import it. The CLI is run as `python -m taskmgr` (with `src` on `PYTHONPATH`, or after `pip install -e .`). No `[project.scripts]` entry is added (F10). The distribution name (`pwreset`) and description stay unchanged (F11). The PR notes must mention that the distribution is still called `pwreset` and now ships two packages.

### Key decisions

| # | Decision | Alternatives rejected | Reason |
|---|---|---|---|
| D1 | New package `src/taskmgr`. | Add to `pwreset`. | The two are unrelated. A separate package leaves `pwreset` untouched, as required. |
| D2 | `TaskRepository` has two methods, `load_all` and `save_all`, and the service holds the logic. | CRUD methods on the repository. A cache loaded once at start-up. | Whole-list persistence is the natural fit for a single JSON file. Not-found and ordering logic is written once in the service. Reading on every operation keeps the service stateless and makes "restart" trivially testable. |
| D3 | JSON file with a `version` field, atomic write (temp file in the same directory, `fsync`, close, then `os.replace`), a missing file read as `[]`, and strict validation on read. | Write in place. Auto-backup and reset on corruption. `sqlite3` or `shelve`. | `os.replace` is atomic on Windows and POSIX. Aborting on corruption is the approved default and never destroys user data. JSON is human-inspectable. |
| D4 | Immutable `Task` with a `TaskStatus` enum (`pending` and `completed` stored as readable strings). | A mutable dataclass with a `completed: bool`. | Immutability means the in-memory repository cannot be corrupted by aliasing, and a rejected edit cannot leave a half-changed object. |
| D5 | Ids come from `IdGenerator` (`secrets.token_hex(4)`), checked by `validate_task_id` and for collisions in the service, with at most 20 attempts and then `IdGenerationError`. | Sequential integers (ids reused after a delete). Full `uuid4`. Title as the key. | Short ids are usable on the command line. Injection makes tests deterministic. The loop is bounded. A dedicated error gives id exhaustion a testable exit code. |
| D6 | One title rule in `validation.py`: strip, reject empty, cap at 200, reject control characters. Duplicate titles are allowed. | No cap. A uniqueness check. Allowing embedded control characters and escaping at render. | The cap was left to design by A6. Rejecting control characters at the source means every stored and displayed string is safe. The loader reuses the same rule. A single rule is smaller and safer than escaping in render. |
| D7 | `complete` and `reopen` are idempotent. | Raise when the status is already as requested. | The story defines no error for this case. Idempotent calls are simpler and safe to retry. |
| D8 | An unknown id raises `TaskNotFoundError` (FR-11). The message shows the id through `ascii()`, cut at 64 characters. | Silent no-op. Raw echo of the id. | A silent no-op hides typos. Escaping stops control characters reaching the terminal (F8). |
| D9 | Default store `~/.taskmgr/tasks.json`, resolved lazily, overridable with `--file`. No environment variable. | The current working directory. A `TASKMGR_FILE` variable. A platform-specific data directory. | A per-user location gives "my tasks" (A7) without configuration. Fewer config sources means less to test. |
| D10 | Rendering and error-to-exit-code mapping live in `cli.py`. The service returns data only. | Messages built inside the service. | NFR-3: the domain stays independent of the UI. |
| D11 | Filter state is not persisted. It is a per-invocation `--filter` argument. | Store the last filter in the file. | The story saves tasks only. |
| D12 | `OSError` becomes `StorageError`. The message is fixed text: a reason code plus the path, never the system error string. Raised with `from None`. | Let raw `OSError` propagate. Use `str(exc)`. | One catchable domain family and a clear exit code. System and parser messages can quote input or user names (F4, F5). |
| D13 | `main` always returns an `int`. It catches `StorageError` first (exit 3) and `TaskManagerError` second (exit 1). `SystemExit` from `parse_args` is converted (usage error 2, help 0). There is no catch-all. | Catch `TaskManagerError` first. Let `SystemExit` propagate. A catch-all `except Exception`. | A parent-first order would mis-map storage errors. Returning an `int` keeps `main` testable and `__main__` simple. A catch-all would hide bugs. |
| D14 | The loader is strict, with fixed reason codes: exact `version` 1, exact key sets, the same title rule as on write (so stored titles must already be stripped), a bounded ASCII id, and no control characters. Any failure is `CorruptStorageError`. | A lenient loader that ignores unknown keys or repairs titles. Escaping control characters in render. | A hand-edited file never silently changes meaning. The "corrupt" boundary for AC-15 is explicit and testable. Render stays trivial. |
| D15 | Console output degrades (`errors="replace"`) instead of raising. | `ensure_ascii=True` in the file. Reconfiguring `sys.stdout`. | The file stays readable UTF-8. The tool never crashes on a narrow console codec (F2). |

### Risks
- **Concurrent processes**: two simultaneous invocations can lose an update (load, load, save, save). It is out of scope (A7). `os.replace` still keeps the file valid, never half-written. It is documented, with no locking added.
- **Windows replace**: `os.replace` can fail with a `PermissionError` if another process holds the file open, for example an antivirus scan or an editor. It surfaces as `StorageError(write_failed)`, exit 3. The old file is intact and the temp file is removed. A hard crash can leave a stale `.tasks-*.tmp` file. It is ignored on load.
- **Corrupt file blocks use**: the approved default is to abort and tell the user. The user must fix or delete the file by hand. The error names the path and a reason code so the user can do that.
- **Strict loader and manual edits**: a hand-edited file that is slightly off is treated as corrupt rather than guessed at. This includes an unstripped title, an extra key and a different `version`. Chosen for data safety. A future format version will need an explicit migration.
- **Stricter titles**: embedded newlines, tabs and other control characters are now rejected on add and edit. The story does not mention them. Zero-width and other format characters (category Cf) and U+2028/U+2029 are still allowed. A title made only of such characters would count as non-empty. Both are accepted as minor.
- **Short id collisions**: 8 hex chars is about 4.3 billion values, so collisions are negligible. The service retries and then fails cleanly.
- **Package naming**: the distribution is still called `pwreset`, with a "Password reset" description, though it now ships two packages. This is cosmetic. It is left unchanged and noted for the PR (F11).
- **Test isolation**: `tests\conftest.py` imports `pwreset` modules. The new tests must not depend on it. They use `tmp_path` and their own fakes with distinct names.
- **Wording and exit codes** are design choices the story does not fix. They are covered by tests, so a later change would be deliberate.
- **Unexpected exceptions** (bugs) show a Python traceback and exit with status 1, the same number as a domain error. This is accepted because there is no catch-all.
- **Path display**: error messages show the `--file` path the user supplied. This is the user's own input, and it is not escaped.

### Changes from round 1

| Finding | How it was handled |
|---|---|
| B1 | Added "Exit codes and the shape of `main`" and D13. `StorageError` is caught first (exit 3), then `TaskManagerError` (exit 1). `SystemExit` from argparse becomes the returned code (2 for usage, 0 for help). Id exhaustion is a new `IdGenerationError` and exits 1. Added the "Exit-code and `main` tests" list. |
| B2 | Added "Validation rules" and "Storage rules" and D14. They define the exact `version` rule, exact key sets, the shared title rule (stored titles must already be stripped), an id charset and bound, rejection of control characters on write and load, and the `StorageReason` codes. Added the AC-15 case table. |
| F1 | The `save_all` steps use UTF-8 `NamedTemporaryFile`, close before `os.replace`, a non-masking `_discard`, a `.tasks-*.tmp` prefix, and stale temp files ignored. Added the monkeypatch targets and the failing-cleanup test. |
| F2 | Added `_emit` (D15) and the cp1252 stdout test. |
| F3 | Every CLI test passes `--file`. An autouse fixture redirects `Path.home`. One test checks the default path. |
| F4 | `StorageError` has fixed text with a reason code and the path. A directory path gives `StorageError(not_a_file)`. Added the directory test. |
| F5 | Reason codes are fixed. There is no `str(exc)`, and errors are raised `from None`. Added the marker no-leakage test. |
| F6 | The service method is `list_tasks`, and all modules use `from __future__ import annotations`. |
| F7 | The wording for an empty store under a non-all filter is fixed (`No pending tasks.`) and tested. |
| F8 | `TaskNotFoundError` uses `ascii()` of the id. Added the `\x1b` test. |
| F9 | The AC-17 scan allows stdlib names, relative imports and the own-package name. Added the subprocess `sys.modules` check. |
| F10 | No `[project.scripts]` entry. `pyproject.toml` is unchanged. |
| F11 | The distribution name is unchanged and is noted for the PR. |
| F12 | Added the end-to-end CLI restart test. |
| F13 | No change. The concurrency risk stays documented. |
