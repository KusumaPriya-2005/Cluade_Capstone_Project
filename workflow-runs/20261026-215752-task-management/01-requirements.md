## 1. Requirements (KAN-1, run 20261026-215752-task-management)

Source: `Inputs/test_user_story.md` (Jira KAN-1, US-01 to US-07).

### Goal
Let a user manage a personal task list: add, view, edit, delete, complete or un-complete, and filter tasks by status. The list must persist across application restarts.

### Functional requirements
- FR-1 (US-01): Add a task from a title. The task starts as pending, gets a unique id, and appears in the task list.
- FR-2 (US-01, US-04): Reject empty or whitespace-only titles on add and on edit. A rejected operation changes nothing.
- FR-3 (US-02): List all tasks, showing each task's title and completion status (pending or completed).
- FR-4 (US-02, US-06): When there are no tasks, show a clear "no tasks" message. When a filter matches nothing, show a distinct "no matching tasks" message that names the filter.
- FR-5 (US-03): Mark a pending task completed. The new status is visible in the list.
- FR-6 (US-03): Mark a completed task pending again.
- FR-7 (US-04): Update the title of an existing task. The id and status are unchanged. The new title appears in the list.
- FR-8 (US-05): Delete an existing task by id. It no longer appears in the list, and all other tasks are unchanged.
- FR-9 (US-06): Provide three filters, All, Pending and Completed. Each shows only tasks that match it.
- FR-10 (US-07): Save tasks to persistent storage. Restore them on application start. Every add, edit, status change and delete is reflected in the saved data.
- FR-11 (cross-cutting): An operation on an unknown task id fails with a clear error and changes nothing. The story does not cover this case. It follows from US-03, US-04 and US-05.

### Non-functional requirements
- NFR-1: Standard library only. Python 3.11 or later, matching `pyproject.toml`. No new dependencies.
- NFR-2: Follow the conventions of the existing `src/pwreset` library:
  - a `src/` layout;
  - dataclasses and `Protocol` interfaces for injected collaborators (here, a task repository);
  - an in-memory implementation of the repository (for tests);
  - domain errors in a dedicated module;
  - pytest tests in `tests/`.
- NFR-3: Domain logic is independent of the UI and the storage format. The same logic can be tested without a UI or real files.
- NFR-4: Persistence is robust. A missing file is treated as an empty list. A corrupt file produces a clear error and is never silently overwritten. Writes are as atomic as is practical, for example write to a temp file, then replace.
- NFR-5: Tasks hold only the title, status and id. No secrets or personal data are stored or logged.
- NFR-6: Behaviour is deterministic and testable. Id generation and file paths are injectable.
- NFR-7: Each AC has an automated test.

### Acceptance criteria
- AC-1 (US-01): Given an empty list, when I add "Buy milk", then the list contains one task titled "Buy milk" with status pending.
- AC-2 (US-01): Given any list, when I add a title that is empty, only spaces, or only tabs or newlines, then it is rejected with a validation error and the list is unchanged.
- AC-3 (US-01): Given tasks exist, when I add a new task, then it appears in the list (view all) and the existing tasks are unchanged.
- AC-4 (US-02): Given tasks exist, when I view all tasks, then every task is returned or shown with its title and status.
- AC-5 (US-02): Given no tasks, when I view all, then a clear "no tasks" message is shown (not a blank output).
- AC-6 (US-03): Given a pending task, when I mark it completed, then its status is completed and the list shows this.
- AC-7 (US-03): Given a completed task, when I mark it pending, then its status is pending.
- AC-8 (US-04): Given an existing task, when I edit its title to a valid new title, then the list shows the new title, and the id and status are unchanged.
- AC-9 (US-04): Given an existing task, when I edit its title to empty or whitespace-only, then it is rejected and the old title is retained.
- AC-10 (US-05): Given tasks A, B and C, when I delete B, then B is absent from the list, A and C remain with unchanged title and status, and their relative order is preserved.
- AC-11 (US-06): Given a mix of pending and completed tasks, when I select Pending, then only pending tasks are shown. Selecting Completed shows only completed tasks. Selecting All shows every task.
- AC-12 (US-06): Given no task matches the selected filter, then an appropriate message (naming the filter) is shown. For example, "no completed tasks" when the filter is Completed and none are completed.
- AC-13 (US-07): Given tasks were added, edited or completed, when the application is restarted (a new instance reading the same storage), then the same tasks with the same titles and statuses are restored.
- AC-14 (US-07): Given a task was deleted, edited or its status changed, when the application is restarted, then the saved data reflects the change. The deleted task is absent, and the edited or changed values are present.
- AC-15 (US-07, NFR-4): Given no storage exists yet, then start-up yields an empty list without error. Given a corrupt storage file, then a clear error is raised and the file is not overwritten.
- AC-16 (FR-11): Given an unknown task id, when I complete, un-complete, edit or delete it, then a "task not found" error is raised and no other task is changed.
- AC-17 (NFR-1, NFR-2): The implementation imports only the standard library, and tests run with `pytest` using the existing `pyproject.toml` settings.

### Assumptions / out of scope
Assumptions (each with a proposed default, pending human confirmation):
- A1, technology: Python 3.11+, standard library only, in the same repo. Default: a new package `src/taskmgr`, separate from `pwreset`, with `pyproject.toml` packaging extended minimally. This is inferred from the repo, not stated in the story.
- A2, UI type: the story does not say. Default: a domain and service library, plus a thin stdlib CLI (`argparse`) so the stories are usable end to end. No web or GUI.
- A3, storage format: not stated. Default: a single JSON file (stdlib `json`) behind a `TaskRepository` Protocol, with an in-memory implementation for tests. The default location is a file in the current user's directory or a path given by the caller.
- A4, task identity: tasks are addressed by a generated id, not by title. Duplicate titles are allowed.
- A5, ordering: tasks are listed in creation order.
- A6, title normalisation: leading and trailing whitespace is stripped before saving. No maximum length is enforced beyond a sensible limit decided in design.
- A7, a single local user and one process at a time. "My tasks" does not imply accounts.
- A8, the default filter is All.

Out of scope: user accounts or authentication, multi-user sync, concurrent access and locking, due dates, priorities, categories, search, reordering, undo, bulk operations, and web or GUI front ends. Also out of scope are the Jira write-back and the `pwreset` library (unchanged).

### Open questions for the human
1. Technology and UI: is Python, standard library only, as a library plus a small CLI acceptable (A1, A2)? Or do you need a web app or GUI, or a different language?
2. Storage: is a local JSON file acceptable (A3)? Where should the default file live, for example the working directory or a per-user data directory? Should the location be configurable?
3. Should the code live in a new package `src/taskmgr` (default), or be added to the existing `pwreset` package? We recommend the former because they are unrelated.
4. Are duplicate titles allowed (A4)? Should the title length be capped, and if so at what value?
5. For FR-11, is an error on an unknown id the right behaviour, or should it be a silent no-op?
6. Does "visibly updated" in US-03 need a particular display (for example `[x]` and `[ ]`), or is any clear status label fine?
7. Is the "Filter" state meant to persist across restarts, or only the tasks?
8. Should a corrupt storage file abort start-up (default), or be backed up and replaced with an empty list?
