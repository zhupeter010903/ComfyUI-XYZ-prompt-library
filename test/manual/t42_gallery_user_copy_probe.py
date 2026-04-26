#!/usr/bin/env python3
"""T42 static probe — delegates to ``test/t42_test.py`` (same machine, no ComfyUI).

Run from ``ComfyUI-XYZNodes/``:
    python test/manual/t42_gallery_user_copy_probe.py

Exit code follows pytest. Success example::

    .....                                                                    [100%]
    5 passed in 0.03s

Failure example::

    F...
    FAILED test/t42_test.py::test_no_writequeue_in_gallery_dist_sources
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_T42 = _ROOT / "test" / "t42_test.py"


def main() -> int:
    cmd = [sys.executable, "-m", "pytest", str(_T42), "-q"]
    p = subprocess.run(cmd, cwd=str(_ROOT))
    return int(p.returncode)


if __name__ == "__main__":
    sys.exit(main())
