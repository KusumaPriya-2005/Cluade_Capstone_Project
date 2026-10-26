from taskmgr.memory import InMemoryTaskRepository
from taskmgr.model import Task, TaskStatus

from taskmgr_helpers import AlwaysSameIdGenerator, SequenceIdGenerator, SpyTaskRepository


def test_new_repository_is_empty():
    assert InMemoryTaskRepository().load_all() == []


def test_round_trip_returns_equal_tasks():
    repo = InMemoryTaskRepository()
    tasks = [Task("a", "A"), Task("b", "B", TaskStatus.COMPLETED)]
    repo.save_all(tasks)
    assert repo.load_all() == tasks
    assert repo.snapshot() == tasks


def test_repository_stores_copies():
    repo = InMemoryTaskRepository()
    tasks = [Task("a", "A")]
    repo.save_all(tasks)
    tasks.append(Task("b", "B"))
    loaded = repo.load_all()
    loaded.clear()
    assert repo.load_all() == [Task("a", "A")]


def test_repr_is_class_name_only():
    repo = InMemoryTaskRepository()
    repo.save_all([Task("a", "secret title")])
    assert repr(repo) == "InMemoryTaskRepository()"


def test_helpers_import_and_work():
    gen = SequenceIdGenerator()
    assert [gen.new_id(), gen.new_id()] == ["id000001", "id000002"]
    same = AlwaysSameIdGenerator("zz")
    assert (same.new_id(), same.new_id(), same.calls) == ("zz", "zz", 2)
    spy = SpyTaskRepository(InMemoryTaskRepository())
    spy.save_all([Task("a", "A")])
    assert spy.load_all() == [Task("a", "A")]
    assert (spy.load_calls, spy.save_calls) == (1, 1)
