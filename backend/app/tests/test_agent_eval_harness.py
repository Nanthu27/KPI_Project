"""
Runs the full Goal Agent / Decision Advisor eval harness
(app/ai/scripts/eval_harness.py) as a pytest test, so it's part of the
normal CI run instead of something that has to be remembered and run by
hand. See eval_harness.py's module docstring for what this is (and isn't).

Each case in the harness is also exposed as its own parametrized pytest
case below, so a failure names the specific behavior that broke instead of
just "the harness failed".
"""
import pytest

from ..ai.scripts.eval_harness import CASES, _seeded_db


@pytest.mark.parametrize("case", CASES, ids=[c.name for c in CASES])
def test_eval_case(case):
    db = _seeded_db()
    try:
        case.run(db)
    finally:
        db.close()
