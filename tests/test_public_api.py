import os
import subprocess
import sys
from pathlib import Path

import pwreset


def test_root_exports():
    for name in pwreset.__all__:
        assert hasattr(pwreset, name)
    from pwreset import PasswordResetService, InvalidResetTokenError  # noqa: F401


def test_no_third_party_import():
    code = (
        "import sys, pwreset\n"
        "std = set(sys.stdlib_module_names)\n"
        "bad = sorted(m for m in sys.modules if '.' not in m and m not in std\n"
        "             and not m.startswith('_') and m != 'pwreset')\n"
        "print(','.join(bad))\n"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True,
        env={"PYTHONPATH": str(Path(__file__).resolve().parent.parent / "src"),
             "SYSTEMROOT": os.environ.get("SYSTEMROOT", "")},
    ).stdout.strip()
    assert out == ""
