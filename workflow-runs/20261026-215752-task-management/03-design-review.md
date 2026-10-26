## 3. Design review (KAN-1, run 20261026-215752-task-management) - round 2

Reviewed: `01-requirements.md` (approved, defaults A1-A8), `02-architecture.md` revision 2, and the round 1 review. I read, without changing anything, `pyproject.toml` and `tests/test_public_api.py`, and I re-checked the `pwreset` conventions from round 1.

Round 1 (summary): verdict approve with changes; blocking B1 (error-to-exit-code order) and B2 (loader validation rules); advisory F1-F13. The architect reworked the design once (rework round 1 of 2). The round 1 text is superseded by this review.

### Round 1 findings status

| ID | Status | Notes |
|---|---|---|
| B1 | Resolved | Catch order is `StorageError`, then `TaskManagerError`. `main` always returns an int. `parse_args` is the only call inside the `SystemExit` handler, so usage errors give 2 and `--help` gives 0. `IdGenerationError` gives exit 1. Every branch has a test, including a subprocess test that checks the real exit status. The hierarchy-lock test explains why the order matters. No new problem found in the sketch. |
| B2 | Resolved | The loader has a fixed step order, so the first failure decides a deterministic reason code. Rules are fixed for the `version` type, exact key sets, the shared title rule, the id charset and bound, control characters, and the BOM. The AC-15 case table is parametrized by reason code and has 5 assertions per case. I walked each table row through the step order and each lands on the stated code. |
| F1 | Handled, with a gap | The UTF-8 temp file, the close before replace, the non-masking `_discard`, the `.tasks-` prefix and the monkeypatch targets are all specified. See N1 and N4. |
| F2 | Handled | `_emit` degrades to `errors="replace"`. The cp1252 test is feasible, because `TextIOWrapper` encodes the whole string before it writes. |
| F3 | Handled | Every CLI test passes `--file`. An autouse fixture patches `Path.home` and the environment variables. The default path is resolved lazily. |
| F4 | Handled, with a gap | The directory case gives `StorageError(not_a_file)`, and the message is fixed text. See N1. |
| F5 | Handled | Reason codes are fixed, `from None` is used, and the marker no-leakage test covers three file shapes. |
| F6 | Handled | The method is `list_tasks`, and `from __future__ import annotations` is required in every module. |
| F7 | Handled | `No pending tasks.` is the stated wording for an empty store under a filter, and it is tested. |
| F8 | Handled | `ascii(task_id[:64])` is used, and there is a `\x1b` test. |
| F9 | Handled, with a gap | The `ast` scan allows the right name classes, and the subprocess check was added. See N3. |
| F10 | Handled | No `[project.scripts]` entry, and `pyproject.toml` is unchanged. |
| F11 | Handled | The distribution name is unchanged and is noted for the PR. |
| F12 | Handled | There is an end-to-end CLI test: add, list, done, list, edit, list, delete, list. |
| F13 | Deferred on purpose | Concurrency stays documented and out of scope (A7). |

### Coverage

| Requirement or AC | Design elements | Status |
|---|---|---|
| FR-1, AC-1, AC-3 | `TaskService.add` appends and saves once. `RandomIdGenerator` produces ids that satisfy `validate_task_id` (8 hex characters, within `[A-Za-z0-9_-]{1,64}`). | Covered |
| FR-2, AC-2, AC-9 | `normalize_title` runs before load and save. The spy counts `save_all` calls. Empty, space, tab and newline titles give `EMPTY`. | Covered. See N5. |
| FR-3, AC-4 | `list_tasks(ALL)` and `render_tasks` print the title and a text status label. | Covered |
| FR-4, AC-5, AC-12 | `No tasks yet.` and `No <filter> tasks.`, with the empty-store case fixed and tested. | Covered |
| FR-5, FR-6, AC-6, AC-7 | `complete` and `reopen`, idempotent (D7). | Covered |
| FR-7, AC-8 | `edit` keeps the id, status and position. | Covered |
| FR-8, AC-10 | `delete` keeps the relative order. | Covered |
| FR-9, AC-11 | `StatusFilter.matches`, `--filter` defaults to `all` (A8). | Covered |
| FR-10, AC-13, AC-14 | Load, change, one `save_all`. There is no cache. Restart tests use a second repository and service on the same file, plus the CLI end-to-end test. | Covered |
| FR-11, AC-16 | `TaskNotFoundError` is raised before any save. The id is escaped. The CLI exits 1. | Covered |
| AC-15, NFR-4 | Missing file gives `[]` and creates nothing. The strict loader is specified. Mutations load first, so a corrupt file is never overwritten. The atomic write is specified. The test matrix is complete. | Covered. See N1 and N2. |
| NFR-1, NFR-2, AC-17 | Standard library only, with the same layout as `pwreset`. The `ast` scan and subprocess check use the existing pytest settings. | Covered. See N3. |
| NFR-3 | The service has no I/O. Rendering and exit codes live in the CLI (D10). | Covered |
| NFR-5 | Only id, title and status are stored. Messages are fixed text, and ids are escaped. | Covered |
| NFR-6 | The id generator, file path and streams are injectable. | Covered |
| NFR-7 | Every AC has a mapped test. | Covered |

Gaps: none in AC coverage. The new items below are implementation-detail gaps in the revision.

Compatibility with the existing suite: nothing is broken. `pyproject.toml` needs no change. New tests use distinct names and do not touch `conftest.py`.

### Findings

| ID | Severity | Issue | Suggested fix |
|---|---|---|---|
| N1 | advisory | The `OSError` handling scope is stated only for `os.replace`. Steps that can raise `OSError` outside it: `path.is_dir()` in `load_all` (Python 3.11 re-raises some `OSError`s such as a permission error on stat), the parent `mkdir`, and creating the `NamedTemporaryFile`. In the last case `tmp` does not exist yet, so a cleanup call would fail on an unbound name. As written, these could surface as a raw traceback instead of exit 3. | In the plan, say that the whole body of `load_all` after the corrupt-file checks, and the whole body of `save_all`, is wrapped so any `OSError` becomes `StorageError(read_failed or write_failed) from None`. Bind `tmp = None` first and call `_discard` only when it is set. Add one test where the parent path is a file. |
| N2 | advisory | A title with a lone surrogate (Unicode category `Cs`) passes `normalize_title`, because only `Cc` is rejected. Such a string can come from non-UTF-8 bytes in argv on POSIX. `json.dump` to a UTF-8 file then raises `UnicodeEncodeError`. That is a `ValueError`, not an `OSError`, so it goes to the "any other exception, re-raise" branch and shows a traceback. The file is safe, because the temp file is discarded. The invariant "a stored title is always valid" is also weaker than claimed. | Reject category `Cs` in step 5 of `normalize_title` (report it as `CONTROL_CHARS`), so the loader gets the rule for free. Add `"a\ud800b"` to the validation tests and to the `bad_title` loader cases. |
| N3 | advisory | The AC-17 subprocess check says "every top-level name in `sys.modules` is stdlib or `taskmgr`". The existing `test_no_third_party_import` also skips names that start with `_` and uses a minimal environment. Without the `_` filter the check can fail spuriously from site and venv hooks (for example `_distutils_hack` or `_virtualenv`), and `__main__` is uncertain. The `ast` scan should compare the first segment of dotted imports (`import os.path`) and tolerate `from . import x`, where the module name is `None`. | Copy the existing filter (`'.' not in m`, no leading `_`, not stdlib, not `taskmgr`) and the minimal environment (`PYTHONPATH` plus `SYSTEMROOT`). In the `ast` scan, use `module.split('.')[0]` and treat `level > 0` as allowed. |
| N4 | advisory | `monkeypatch.setattr("taskmgr.json_store.os.replace", ...)` and `...os.unlink` patch the global `os` module, not just the module under test. Any other code that calls them during the test is also affected, including pytest's own cleanup if teardown ordering is unlucky. The same holds for `json.dump`. | Use fake functions that raise only for the expected target (the `.tasks-*.tmp` name, or `path` as the destination) and delegate to the real function otherwise. Keep the patch scoped to the test through the `monkeypatch` fixture. |
| N5 | advisory | (a) `str.strip()` also removes `\x1c`-`\x1f`, `\x0b`, `\x0c` and `\x85` at the edges. Test cases for `CONTROL_CHARS` must therefore use characters that are not stripped (`\x00`, `\x1b`, `\x9b`, or any control character inside the title). A title of only `\x85` gives `EMPTY`. (b) Rejecting embedded tabs and newlines in titles goes beyond the story. The design records it as a risk, but the human has not been asked about it. | (a) Say so in the plan's test notes. (b) List it under "Decisions needed from the human" in `04-plan.md`, with the default being to reject. |
| N6 | advisory | Small CLI details are unspecified. (a) `--file` arrives as a string, but `JsonFileTaskRepository` takes a `Path`. (b) `args.file or default_store_path()` treats `--file ""` as absent and silently uses the home directory file. (c) The id rule accepts ids that start with `-`, such as a hand-edited `-x`. `done -x` then fails in argparse unless `--` is used. Generated ids are hex, so this is only a hand-edit case. (d) `Path.home()` can raise `RuntimeError` in unusual environments. | (a) Use `type=Path`. (b) Compare with `is None`, or reject an empty value. (c) Either leave it, since `--` is already documented, or require the first id character to be alphanumeric. (d) Ignore it. Set `prog="taskmgr"` on the parser so the usage text is stable under `python -m`. |
| N7 | advisory | The design is larger than the story alone suggests: 7 error classes, 15 reason codes, and a roughly 60-case test matrix. It is justified by the B2 and F-findings, and it adds no dependency or abstraction beyond `Protocol` and a loader. The risk is in implementation, where a long if-chain would be hard to read. | In the plan, keep the loader table-driven (a small `_fail(reason)` helper and one function per step group). Do not add more codes. |

No finding is blocking.

### Verdict

**Approve.** B1 and B2 are fully resolved, F1-F13 are handled or deliberately deferred, and every FR, NFR and AC is covered. N1-N7 are implementation details that the plan should absorb without changing the design.
