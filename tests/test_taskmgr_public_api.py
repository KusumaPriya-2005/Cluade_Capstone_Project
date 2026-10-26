import importlib
import os
import subprocess
import sys
from pathlib import Path

import taskmgr


def test_root_exports():
    for name in taskmgr.__all__:
        assert hasattr(taskmgr, name)
    from taskmgr import TaskService, TaskNotFoundError  # noqa: F401


def test_all_is_sorted_and_unique():
    assert taskmgr.__all__ == sorted(taskmgr.__all__)
    assert len(set(taskmgr.__all__)) == len(taskmgr.__all__)


def test_cli_is_importable_separately():
    cli = importlib.import_module("taskmgr.cli")
    assert callable(cli.main)
    assert "cli" not in taskmgr.__all__


def test_package_import_does_not_load_cli():
    code = "import sys, taskmgr\nprint('taskmgr.cli' in sys.modules)\n"
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True,
        env={"PYTHONPATH": str(Path(__file__).resolve().parent.parent / "src"),
             "SYSTEMROOT": os.environ.get("SYSTEMROOT", "")},
    ).stdout.strip()
    assert out == "False"
