"""Repo-root conftest that puts the repo root on sys.path.

This makes `eval.*` importable when pytest is run from any directory
inside the repo (used by test_eval.py and run_eval.py).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))