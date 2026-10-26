import pytest

from taskmgr.errors import IdGenerationError, InvalidTitleError, TaskNotFoundError, TitleProblem
from taskmgr.memory import InMemoryTaskRepository
from taskmgr.model import StatusFilter, Task, TaskStatus
from taskmgr.service import TaskService
from taskmgr.system import RandomIdGenerator
from taskmgr.validation import validate_task_id

from taskmgr_helpers import AlwaysSameIdGenerator, SequenceIdGenerator, SpyTaskRepository


def make(initial=()):
    inner = InMemoryTaskRepository()
    inner.save_all(list(initial))
    spy = SpyTaskRepository(inner)
    return TaskService(spy, SequenceIdGenerator()), spy, inner


ABC = [
    Task("a", "A"),
    Task("b", "B", TaskStatus.COMPLETED),
    Task("c", "C"),
]


def test_add_to_empty_list_gives_pending_task_with_generated_id():
    service, spy, inner = make()
    task = service.add("Buy milk")
    assert task == Task("id000001", "Buy milk", TaskStatus.PENDING)
    assert inner.snapshot() == [task]
    assert spy.save_calls == 1


def test_add_keeps_existing_tasks_and_creation_order():
    service, _, inner = make(ABC)
    new = service.add("D")
    assert inner.snapshot() == [*ABC, new]
    assert service.list_tasks() == [*ABC, new]


def test_add_strips_title():
    service, _, _ = make()
    assert service.add("  x  ").title == "x"


@pytest.mark.parametrize("title", ["", "   ", "\t", "\n", "\t \n", "a\nb"])
def test_add_rejects_bad_titles_without_saving(title):
    service, spy, inner = make(ABC)
    with pytest.raises(InvalidTitleError):
        service.add(title)
    assert spy.save_calls == 0
    assert inner.snapshot() == ABC


def test_add_invalid_type():
    service, spy, _ = make()
    with pytest.raises(InvalidTitleError) as info:
        service.add(None)
    assert info.value.problem is TitleProblem.INVALID_TYPE
    assert spy.save_calls == 0


def test_list_tasks_filters():
    service, _, _ = make(ABC)
    assert service.list_tasks() == ABC
    assert service.list_tasks(StatusFilter.ALL) == ABC
    assert service.list_tasks(StatusFilter.PENDING) == [ABC[0], ABC[2]]
    assert service.list_tasks(StatusFilter.COMPLETED) == [ABC[1]]


def test_list_tasks_empty():
    service, _, _ = make()
    assert service.list_tasks() == []


def test_complete_and_reopen_with_idempotency():
    service, spy, inner = make(ABC)
    assert service.complete("a").status is TaskStatus.COMPLETED
    assert service.complete("a").status is TaskStatus.COMPLETED
    assert inner.snapshot()[0] == Task("a", "A", TaskStatus.COMPLETED)
    assert service.reopen("b").status is TaskStatus.PENDING
    assert service.reopen("b").status is TaskStatus.PENDING
    assert inner.snapshot()[1] == Task("b", "B", TaskStatus.PENDING)
    assert inner.snapshot()[2] == ABC[2]
    assert spy.save_calls == 4


def test_edit_keeps_id_status_and_position():
    service, _, inner = make(ABC)
    updated = service.edit("b", "  New  ")
    assert updated == Task("b", "New", TaskStatus.COMPLETED)
    assert inner.snapshot() == [ABC[0], updated, ABC[2]]


@pytest.mark.parametrize("title", ["", "   ", "\n"])
def test_blank_edit_is_rejected_without_saving(title):
    service, spy, inner = make(ABC)
    with pytest.raises(InvalidTitleError):
        service.edit("a", title)
    assert spy.save_calls == 0
    assert inner.snapshot() == ABC


def test_delete_keeps_order_of_the_rest():
    service, _, inner = make(ABC)
    assert service.delete("b") is None
    assert inner.snapshot() == [ABC[0], ABC[2]]


@pytest.mark.parametrize(
    "call",
    [
        lambda s, i: s.complete(i),
        lambda s, i: s.reopen(i),
        lambda s, i: s.edit(i, "New"),
        lambda s, i: s.delete(i),
    ],
    ids=["complete", "reopen", "edit", "delete"],
)
def test_unknown_id_raises_and_changes_nothing(call):
    service, spy, inner = make(ABC)
    with pytest.raises(TaskNotFoundError) as info:
        call(service, "nope")
    assert info.value.task_id == "nope"
    assert spy.save_calls == 0
    assert inner.snapshot() == ABC


def test_unknown_id_with_escape_is_escaped_in_message():
    service, _, _ = make(ABC)
    with pytest.raises(TaskNotFoundError) as info:
        service.delete("x\x1b[31m")
    assert "\\x1b" in str(info.value)
    assert "\x1b" not in str(info.value)


def test_lookup_ids_are_not_format_validated():
    service, _, _ = make([Task("a", "A")])
    with pytest.raises(TaskNotFoundError):
        service.complete("")


def test_id_exhaustion_after_exactly_twenty_attempts():
    inner = InMemoryTaskRepository()
    inner.save_all([Task("aaaa", "A")])
    spy = SpyTaskRepository(inner)
    gen = AlwaysSameIdGenerator("aaaa")
    with pytest.raises(IdGenerationError):
        TaskService(spy, gen).add("B")
    assert gen.calls == 20
    assert spy.save_calls == 0
    assert inner.snapshot() == [Task("aaaa", "A")]


@pytest.mark.parametrize("bad_id", ["a\x1bb", "a" * 65, "", "a b"])
def test_generator_returning_invalid_id_is_rejected(bad_id):
    inner = InMemoryTaskRepository()
    spy = SpyTaskRepository(inner)
    gen = AlwaysSameIdGenerator(bad_id)
    with pytest.raises(IdGenerationError):
        TaskService(spy, gen).add("B")
    assert gen.calls == 20
    assert spy.save_calls == 0


def test_collision_is_retried_until_a_free_id():
    class Flaky:
        def __init__(self):
            self.ids = iter(["aaaa", "aaaa", "bbbb"])

        def new_id(self):
            return next(self.ids)

    inner = InMemoryTaskRepository()
    inner.save_all([Task("aaaa", "A")])
    task = TaskService(inner, Flaky()).add("B")
    assert task.id == "bbbb"


def test_random_id_generator_output_is_valid_hex():
    gen = RandomIdGenerator()
    for _ in range(50):
        value = gen.new_id()
        assert len(value) == 8
        assert value == value.lower()
        int(value, 16)
        assert validate_task_id(value) == value


def test_id_generator_is_injectable():
    service = TaskService(InMemoryTaskRepository(), AlwaysSameIdGenerator("fixed"))
    assert service.add("x").id == "fixed"
