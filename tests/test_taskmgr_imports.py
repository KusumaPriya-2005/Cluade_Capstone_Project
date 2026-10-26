import ast
import os
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "src" / "taskmgr"


def foreign_imports(source: str) -> list[str]:
    allowed = set(sys.stdlib_module_names) | {"taskmgr"}
    bad = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names = [alias.name.split(".")[0] for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level > 0:
                continue
            names = [node.module.split(".")[0]]
        else:
            continue
        bad.extend(name for name in names if name not in allowed)
    return bad


def test_scanner_flags_third_party_names():
    assert foreign_imports("import requests") == ["requests"]
    assert foreign_imports("from yaml.x import y") == ["yaml"]
    assert foreign_imports("import os.path\nfrom . import x\nfrom .a import b") == []
    assert foreign_imports("import taskmgr.cli\nfrom __future__ import annotations") == []


def test_sources_import_only_stdlib_and_own_package():
    files = sorted(PACKAGE.glob("*.py"))
    assert len(files) >= 11
    for path in files:
        assert foreign_imports(path.read_text(encoding="utf-8")) == [], path.name


def test_no_third_party_import_at_runtime():
    code = (
        "import sys, taskmgr, taskmgr.cli\n"
        "std = set(sys.stdlib_module_names)\n"
        "bad = sorted(m for m in sys.modules if '.' not in m and m not in std\n"
        "             and not m.startswith('_') and m != 'taskmgr')\n"
        "print(','.join(bad))\n"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True,
        env={"PYTHONPATH": str(ROOT / "src"),
             "SYSTEMROOT": os.environ.get("SYSTEMROOT", "")},
    ).stdout.strip()
    assert out == ""


def test_pyproject_is_unchanged_in_the_relevant_parts():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["dependencies"] == []
    assert data["tool"]["pytest"]["ini_options"] == {
        "pythonpath": ["src"],
        "testpaths": ["tests"],
    }
    assert "scripts" not in data["project"]
