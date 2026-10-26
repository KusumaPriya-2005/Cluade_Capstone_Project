import io
import os
import subprocess
import sys
from pathlib import Path

import pytest

from taskmgr.cli import (
    EXIT_DOMAIN,
    EXIT_OK,
    EXIT_STORAGE,
    EXIT_USAGE,
    build_parser,
    default_store_path,
    main,
    render_tasks,
)
from taskmgr.json_store import JsonFileTaskRepository
from taskmgr.model import StatusFilter, Task, TaskStatus

from taskmgr_helpers import AlwaysSameIdGenerator, SequenceIdGenerator, patch_replace_fails

SRC = str(Path(__file__).resolve().parent.parent / "src")


@pytest.fixture(autouse=True)
def fake_home(tmp_path, monkeypatch):
    home = tmp_path / "fakehome"
    home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    return home


@pytest.fixture
def store(tmp_path):
    return tmp_path / "data" / "tasks.json"


def run(store, *argv, gen=None):
    out, err = io.StringIO(), io.StringIO()
    code = main(["--file", str(store), *argv], id_generator=gen, stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


def test_default_store_path_uses_home(fake_home):
    assert default_store_path() == fake_home / ".taskmgr" / "tasks.json"


def test_empty_store_list(store):
    assert run(store, "list") == (EXIT_OK, "No tasks yet.\n", "")
    assert not store.exists()


def test_empty_filter_messages(store):
    assert run(store, "list", "--filter", "pending") == (EXIT_OK, "No pending tasks.\n", "")
    gen = SequenceIdGenerator()
    run(store, "add", "A", gen=gen)
    assert run(store, "list", "--filter", "completed") == (EXIT_OK, "No completed tasks.\n", "")


def test_rows_show_title_and_status_label(store):
    gen = SequenceIdGenerator()
    assert run(store, "add", "Buy milk", gen=gen) == (
        EXIT_OK, "Added: [ ] id000001  Buy milk  (pending)\n", "")
    run(store, "add", "Walk", gen=gen)
    run(store, "done", "id000002", gen=gen)
    code, out, err = run(store, "list")
    assert code == EXIT_OK and err == ""
    assert out == ("[ ] id000001  Buy milk  (pending)\n"
                   "[x] id000002  Walk  (completed)\n")
    assert run(store, "list", "--filter", "pending")[1] == "[ ] id000001  Buy milk  (pending)\n"
    assert run(store, "list", "--filter", "completed")[1] == "[x] id000002  Walk  (completed)\n"


@pytest.mark.parametrize("title", ["", "   ", "a\nb", "\t"])
def test_add_invalid_title(store, title):
    code, out, err = run(store, "add", title)
    assert code == EXIT_DOMAIN
    assert err.startswith("error:")
    assert out == ""
    assert not store.exists()


def test_add_invalid_title_leaves_existing_file_unchanged(store):
    run(store, "add", "A", gen=SequenceIdGenerator())
    before = store.read_bytes()
    assert run(store, "add", "  ")[0] == EXIT_DOMAIN
    assert run(store, "edit", "id000001", "")[0] == EXIT_DOMAIN
    assert store.read_bytes() == before


def test_done_and_undo(store):
    gen = SequenceIdGenerator()
    run(store, "add", "A", gen=gen)
    assert run(store, "done", "id000001") == (
        EXIT_OK, "Completed: [x] id000001  A  (completed)\n", "")
    assert run(store, "undo", "id000001") == (
        EXIT_OK, "Reopened: [ ] id000001  A  (pending)\n", "")


@pytest.mark.parametrize("command", [["done"], ["undo"], ["edit"], ["delete"]])
def test_unknown_id(store, command):
    run(store, "add", "A", gen=SequenceIdGenerator())
    before = store.read_bytes()
    extra = ["New"] if command == ["edit"] else []
    code, out, err = run(store, *command, "nope", *extra)
    assert (code, out) == (EXIT_DOMAIN, "")
    assert err == "error: Task not found: 'nope'\n"
    assert store.read_bytes() == before


def test_unknown_id_with_escape_sequence_is_escaped(store):
    code, _, err = run(store, "delete", "x\x1b[31m")
    assert code == EXIT_DOMAIN
    assert "\\x1b" in err
    assert "\x1b" not in err


def test_end_to_end_across_restarts(store):
    gen = SequenceIdGenerator()
    assert run(store, "add", "Buy milk", gen=gen)[0] == EXIT_OK
    assert run(store, "list")[1] == "[ ] id000001  Buy milk  (pending)\n"
    run(store, "done", "id000001")
    assert run(store, "list")[1] == "[x] id000001  Buy milk  (completed)\n"
    run(store, "edit", "id000001", "Buy oat milk")
    assert run(store, "list")[1] == "[x] id000001  Buy oat milk  (completed)\n"
    assert run(store, "delete", "id000001") == (EXIT_OK, "Deleted: id000001\n", "")
    assert run(store, "list")[1] == "No tasks yet.\n"


def test_corrupt_file_is_exit_3_and_unchanged(store):
    store.parent.mkdir(parents=True)
    content = b'{"version": 1, "tasks": [ZZ-MARKER-ZZ'
    store.write_bytes(content)
    for argv in (["list"], ["add", "x"]):
        code, out, err = run(store, *argv)
        assert (code, out) == (EXIT_STORAGE, "")
        assert err.startswith("error: Storage file is corrupt (invalid_json)")
        assert "ZZ-MARKER-ZZ" not in err
        assert store.read_bytes() == content


def test_directory_as_file_is_exit_3(tmp_path):
    code, out, err = run(tmp_path, "list")
    assert (code, out) == (EXIT_STORAGE, "")
    assert "not_a_file" in err


def test_write_failure_is_exit_3_and_old_file_intact(store, monkeypatch):
    run(store, "add", "A", gen=SequenceIdGenerator())
    before = store.read_bytes()
    patch_replace_fails(monkeypatch, store)
    code, out, err = run(store, "add", "B", gen=AlwaysSameIdGenerator("bbbb"))
    assert (code, out) == (EXIT_STORAGE, "")
    assert "write_failed" in err
    assert store.read_bytes() == before
    assert list(store.parent.glob(".tasks-*.tmp")) == []


def test_success_has_empty_stderr(store):
    assert run(store, "add", "A")[0] == EXIT_OK
    assert run(store, "list")[2] == ""


def test_id_exhaustion_is_exit_1(store):
    gen = AlwaysSameIdGenerator("aaaa")
    assert run(store, "add", "A", gen=gen)[0] == EXIT_OK
    before = store.read_bytes()
    code, out, err = run(store, "add", "B", gen=gen)
    assert (code, out) == (EXIT_DOMAIN, "")
    assert err == "error: Could not generate a unique task id.\n"
    assert store.read_bytes() == before


@pytest.mark.parametrize(
    "argv", [[], ["bogus"], ["list", "--filter", "bogus"], ["add"], ["--file", "", "list"]]
)
def test_usage_errors_return_2(argv, store, capsys):
    if "--file" not in argv:
        argv = ["--file", str(store), *argv]
    assert main(argv) == EXIT_USAGE
    assert capsys.readouterr().err.startswith("usage: taskmgr")
    assert not store.exists()


def test_help_returns_0(capsys):
    assert main(["--help"]) == EXIT_OK
    captured = capsys.readouterr()
    assert captured.out.startswith("usage: taskmgr")
    assert "--" in captured.out


def test_file_option_is_a_path(tmp_path, monkeypatch):
    args = build_parser().parse_args(["--file", "rel/tasks.json", "list"])
    assert isinstance(args.file, Path)
    assert build_parser().parse_args(["list"]).file is None
    monkeypatch.chdir(tmp_path)
    assert main(["--file", "rel/tasks.json", "add", "x"], stdout=io.StringIO()) == EXIT_OK
    assert (tmp_path / "rel" / "tasks.json").is_file()


def test_default_path_used_only_without_file(fake_home):
    assert main(["add", "x"], stdout=io.StringIO(), stderr=io.StringIO()) == EXIT_OK
    assert (fake_home / ".taskmgr" / "tasks.json").is_file()


def test_console_encoding_degrades_instead_of_raising(store):
    raw = io.BytesIO()
    console = io.TextIOWrapper(raw, encoding="cp1252", errors="strict")
    err = io.StringIO()
    gen = SequenceIdGenerator()
    argv = ["--file", str(store)]
    assert main([*argv, "add", "Milk 🥛"], id_generator=gen, stdout=console, stderr=err) == EXIT_OK
    assert main([*argv, "list"], stdout=console, stderr=err) == EXIT_OK
    console.flush()
    text = raw.getvalue().decode("cp1252")
    assert text.count("Milk ?") == 2
    assert err.getvalue() == ""
    assert JsonFileTaskRepository(store).load_all() == [Task("id000001", "Milk 🥛")]


def subprocess_env():
    return {"PYTHONPATH": SRC, "SYSTEMROOT": os.environ.get("SYSTEMROOT", "")}


def test_python_m_taskmgr_exit_status(tmp_path):
    path = tmp_path / "tasks.json"
    ok = subprocess.run(
        [sys.executable, "-m", "taskmgr", "--file", str(path), "list"],
        capture_output=True, text=True, env=subprocess_env(),
    )
    assert ok.returncode == 0
    assert ok.stdout.strip() == "No tasks yet."
    path.write_bytes(b"garbage")
    bad = subprocess.run(
        [sys.executable, "-m", "taskmgr", "--file", str(path), "list"],
        capture_output=True, text=True, env=subprocess_env(),
    )
    assert bad.returncode == 3
    assert "corrupt" in bad.stderr


def test_render_tasks_is_pure():
    tasks = [Task("a", "A"), Task("b", "B", TaskStatus.COMPLETED)]
    assert render_tasks([], StatusFilter.ALL) == "No tasks yet."
    assert render_tasks([], StatusFilter.PENDING) == "No pending tasks."
    assert render_tasks([], StatusFilter.COMPLETED) == "No completed tasks."
    assert render_tasks(tasks, StatusFilter.ALL) == "[ ] a  A  (pending)\n[x] b  B  (completed)"
    assert render_tasks(tasks[:1], StatusFilter.PENDING) == "[ ] a  A  (pending)"
