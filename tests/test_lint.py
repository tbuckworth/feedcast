"""A static gate for the mistakes Python only reports at runtime.

`dead_sources += ...` placed above `dead_sources = []` in the same function is
a clean compile and an UnboundLocalError on the first real run — it shipped to
main and would have taken out the daily pipeline. Both ruff and pyflakes catch
it, so the cheapest guard is to run one.

Scoped to the rules that indicate a genuine defect. Style rules are left off
deliberately: a lint gate that fails on an unused import is a gate people learn
to ignore.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# E9  syntax and IO errors
# F82 undefined name / undefined local / undefined name in __all__
RULES = "E9,F82"


def test_no_undefined_names():
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--select", RULES,
         "--output-format", "concise", "src", "tests"],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0, f"\n{result.stdout}{result.stderr}"
