import io
import json

import pytest

from taskmgr.cli import main
from taskmgr.errors import CorruptStorageError, StorageError, StorageReason
from taskmgr.json_store import JsonFileTaskRepository
from taskmgr.model import Task, TaskStatus
from taskmgr.service import TaskService

from taskmgr_helpers import (
    SequenceIdGenerator,
    patch_dump_fails,
    patch_replace_fails,
    patch_unlink_fails,
)

MARKER = "ZZ-MARKER-ZZ"
BOM = b"\xef\xbb\xbf"


def good(**over):
    task = {"id": "a1b2c3d4", "title": "Buy milk", "status": "pending"}
    task.update(over)
    return task


def doc(tasks=None, **top):
    body = {"version": 1, "tasks": [good()] if tasks is None else tasks}
    body.update(top)
    return json.dumps(body).encode("utf-8")


def raw_doc(obj):
    return json.dumps(obj).encode("utf-8")


def temp_files(directory):
    return sorted(p.name for p in directory.glob(".tasks-*.tmp"))


R = StorageReason

CORRUPT_CASES = [
    (b"", R.EMPTY_FILE),
    (b"\xff\xfe\x00", R.INVALID_ENCODING),
    (b'{"version": 1, "tasks": []}\xff', R.INVALID_ENCODING),
    (b"garbage", R.INVALID_JSON),
    (b'{"version": 1, "tasks": [', R.INVALID_JSON),
    (b"  \n\t ", R.INVALID_JSON),
    (BOM + doc(), R.INVALID_JSON),
    (b"[]", R.BAD_SHAPE),
    (b'"x"', R.BAD_SHAPE),
    (b"null", R.BAD_SHAPE),
    (raw_doc({"version": 1, "tasks": {}}), R.BAD_SHAPE),
    (doc([5]), R.BAD_SHAPE),
    (raw_doc({"tasks": []}), R.MISSING_KEY),
    (raw_doc({"version": 1}), R.MISSING_KEY),
    (doc([{"id": "a", "status": "pending"}]), R.MISSING_KEY),
    (raw_doc({"version": 2, "tasks": []}), R.BAD_VERSION),
    (raw_doc({"version": "1", "tasks": []}), R.BAD_VERSION),
    (raw_doc({"version": 1.0, "tasks": []}), R.BAD_VERSION),
    (raw_doc({"version": True, "tasks": []}), R.BAD_VERSION),
    (raw_doc({"version": None, "tasks": []}), R.BAD_VERSION),
    (raw_doc({"version": 1, "tasks": [], "extra": 1}), R.UNKNOWN_KEY),
    (doc([good(extra=1)]), R.UNKNOWN_KEY),
    (doc([good(id=5)]), R.BAD_TYPE),
    (doc([good(title=None)]), R.BAD_TYPE),
    (doc([good(status=5)]), R.BAD_TYPE),
    (doc([good(status="done")]), R.BAD_STATUS),
    (doc([good(status="PENDING")]), R.BAD_STATUS),
    (doc([good(id="")]), R.BAD_ID),
    (doc([good(id="a b")]), R.BAD_ID),
    (doc([good(id="a" * 65)]), R.BAD_ID),
    (doc([good(id="é")]), R.BAD_ID),
    (doc([good(id="../x")]), R.BAD_ID),
    (doc([good(id="a\x1bb")]), R.BAD_ID),
    (doc([good(id="abc\n")]), R.BAD_ID),
    (doc([good(title="")]), R.BAD_TITLE),
    (doc([good(title="   ")]), R.BAD_TITLE),
    (doc([good(title=" padded ")]), R.BAD_TITLE),
    (doc([good(title="x" * 201)]), R.BAD_TITLE),
    (doc([good(title="a\x1b[31mb")]), R.BAD_TITLE),
    (doc([good(title="a\nb")]), R.BAD_TITLE),
    (doc([good(title="a\x9bb")]), R.BAD_TITLE),
    (doc([good(title="a\ud800b")]), R.BAD_TITLE),
    (doc([good(), good(title="Other")]), R.DUPLICATE_ID),
]


@pytest.fixture
def store(tmp_path):
    return tmp_path / "tasks.json"


def test_missing_file_gives_empty_list_and_creates_nothing(tmp_path, store):
    (tmp_path / ".tasks-x.tmp").write_bytes(b"stale")
    assert JsonFileTaskRepository(store).load_all() == []
    assert not store.exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == [".tasks-x.tmp"]


def test_constructor_does_no_io(tmp_path):
    JsonFileTaskRepository(tmp_path / "sub" / "tasks.json")
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("content,reason", CORRUPT_CASES)
def test_corrupt_file(tmp_path, store, content, reason):
    store.write_bytes(content)
    with pytest.raises(CorruptStorageError) as info:
        JsonFileTaskRepository(store).load_all()
    assert info.value.reason is reason
    assert store.read_bytes() == content
    with pytest.raises(CorruptStorageError):
        TaskService(JsonFileTaskRepository(store), SequenceIdGenerator()).add("New")
    assert store.read_bytes() == content
    assert main(["--file", str(store), "list"], stdout=io.StringIO(), stderr=io.StringIO()) == 3
    assert store.read_bytes() == content
    assert [p.name for p in tmp_path.iterdir()] == ["tasks.json"]


def test_boundary_values_load(store):
    tasks = [
        Task("a" * 64, "t" * 200),
        Task("b", "Buy 🥛 café 日本語", TaskStatus.COMPLETED),
    ]
    repo = JsonFileTaskRepository(store)
    repo.save_all(tasks)
    assert repo.load_all() == tasks


def test_directory_path_is_not_a_file_error(tmp_path):
    repo = JsonFileTaskRepository(tmp_path)
    for call in (repo.load_all, lambda: repo.save_all([])):
        with pytest.raises(StorageError) as info:
            call()
        assert info.value.reason is StorageReason.NOT_A_FILE
        assert not isinstance(info.value, CorruptStorageError)


def test_round_trip_text_format(store):
    tasks = [Task("a", "Café 🥛"), Task("b", "B", TaskStatus.COMPLETED)]
    repo = JsonFileTaskRepository(store)
    repo.save_all(tasks)
    assert repo.load_all() == tasks
    raw = store.read_bytes()
    assert raw.endswith(b"\n")
    assert "Café 🥛".encode("utf-8") in raw
    assert json.loads(raw) == {
        "version": 1,
        "tasks": [
            {"id": "a", "title": "Café 🥛", "status": "pending"},
            {"id": "b", "title": "B", "status": "completed"},
        ],
    }


def test_save_creates_parent_directories(tmp_path):
    path = tmp_path / "x" / "y" / "tasks.json"
    JsonFileTaskRepository(path).save_all([Task("a", "A")])
    assert JsonFileTaskRepository(path).load_all() == [Task("a", "A")]


def test_restart_state_changes(store):
    service = TaskService(JsonFileTaskRepository(store), SequenceIdGenerator())
    a = service.add("A")
    b = service.add("B")
    c = service.add("C")

    def fresh():
        return TaskService(JsonFileTaskRepository(store), SequenceIdGenerator())

    assert fresh().list_tasks() == [a, b, c]
    fresh().edit(a.id, "A2")
    fresh().complete(b.id)
    after = fresh().list_tasks()
    assert after == [Task(a.id, "A2"), Task(b.id, "B", TaskStatus.COMPLETED), c]
    fresh().reopen(b.id)
    fresh().delete(c.id)
    assert fresh().list_tasks() == [Task(a.id, "A2"), Task(b.id, "B")]


@pytest.mark.parametrize(
    "content",
    [
        f'{{"version": 1, "tasks": [{MARKER}'.encode(),
        b"\xff" + MARKER.encode(),
        doc([good(title=f"{MARKER}\x1b")]),
    ],
    ids=["truncated_json", "bad_utf8", "bad_title"],
)
def test_no_leakage_of_file_contents(store, content):
    store.write_bytes(content)
    with pytest.raises(CorruptStorageError) as info:
        JsonFileTaskRepository(store).load_all()
    exc = info.value
    assert MARKER not in str(exc)
    assert exc.__cause__ is None
    assert exc.__suppress_context__ is True


def old_state(store):
    JsonFileTaskRepository(store).save_all([Task("old", "Old")])
    return store.read_bytes()


def test_failing_json_dump_keeps_old_bytes(tmp_path, store, monkeypatch):
    before = old_state(store)
    patch_dump_fails(monkeypatch)
    with pytest.raises(StorageError) as info:
        JsonFileTaskRepository(store).save_all([Task("new", "New")])
    assert info.value.reason is StorageReason.WRITE_FAILED
    assert store.read_bytes() == before
    assert temp_files(tmp_path) == []


def test_failing_replace_keeps_old_bytes(tmp_path, store, monkeypatch):
    before = old_state(store)
    patch_replace_fails(monkeypatch, store)
    with pytest.raises(StorageError) as info:
        JsonFileTaskRepository(store).save_all([Task("new", "New")])
    assert info.value.reason is StorageReason.WRITE_FAILED
    assert info.value.__cause__ is None
    assert store.read_bytes() == before
    assert temp_files(tmp_path) == []


def test_failing_cleanup_does_not_mask_the_write_error(tmp_path, store, monkeypatch):
    before = old_state(store)
    patch_replace_fails(monkeypatch, store)
    patch_unlink_fails(monkeypatch)
    with pytest.raises(StorageError) as info:
        JsonFileTaskRepository(store).save_all([Task("new", "New")])
    assert info.value.reason is StorageReason.WRITE_FAILED
    assert "unlink" not in str(info.value)
    assert store.read_bytes() == before
    # The unlink fake blocks every cleanup, so the temp file cannot be removed
    # here; it is stale and ignored on load. Remove it so tmp_path stays clean.
    for name in temp_files(tmp_path):
        (tmp_path / name).unlink()


def test_parent_is_a_file(tmp_path):
    (tmp_path / "afile").write_text("not a directory")
    path = tmp_path / "afile" / "tasks.json"
    repo = JsonFileTaskRepository(path)
    with pytest.raises(StorageError) as info:
        repo.save_all([Task("a", "A")])
    assert info.value.reason is StorageReason.WRITE_FAILED
    assert info.value.__cause__ is None
    # Windows may report a missing file here and return [], POSIX raises
    # NotADirectoryError. Either way a raw OSError must never escape.
    try:
        assert repo.load_all() == []
    except StorageError as exc:
        assert not isinstance(exc, CorruptStorageError)
        assert exc.reason is StorageReason.READ_FAILED
    service = TaskService(JsonFileTaskRepository(path), SequenceIdGenerator())
    with pytest.raises(StorageError) as add_info:
        service.add("A")
    assert not isinstance(add_info.value, CorruptStorageError)
    assert add_info.value.reason in (StorageReason.READ_FAILED, StorageReason.WRITE_FAILED)
