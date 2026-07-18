"""
tests/test_gates.py — unit tests for the G01–G04 validation gates.

Runs standalone (`python tests/test_gates.py`) or under pytest.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gates import validation_gates as vg  # noqa: E402

STANDARD = {"tier": "standard", "rating_policy": {"standard": ["E", "E10", "T", "M"],
                                                   "casual": ["E", "E10", "T"]}}
CASUAL = {"tier": "casual", "rating_policy": {"casual": ["E", "E10", "T"]}}


def make_game(i, rating="T", genre="action"):
    return {"id": f"g{i}", "title": f"Game {i}", "genre": genre, "rating": rating}


# --- G01 Required fields --------------------------------------------------------
def test_g01_pass():
    rows = {"Row A": [make_game(i) for i in range(5)]}
    assert vg.g01_required_fields(rows, STANDARD).passed


def test_g01_fail_missing_field():
    bad = make_game(1)
    bad["rating"] = ""
    rows = {"Row A": [bad]}
    assert not vg.g01_required_fields(rows, STANDARD).passed


# --- G02 Rating policy ----------------------------------------------------------
def test_g02_pass_standard():
    rows = {"Row A": [make_game(i, rating="M") for i in range(3)]}
    assert vg.g02_rating_policy(rows, STANDARD).passed


def test_g02_fail_casual_M():
    rows = {"Row A": [make_game(1, rating="M")]}
    assert not vg.g02_rating_policy(rows, CASUAL).passed


def test_g02_fail_AO():
    rows = {"Row A": [make_game(1, rating="AO")]}
    assert not vg.g02_rating_policy(rows, STANDARD).passed


def test_g02_unknown_tier_is_violation_not_crash():
    # A tier present in platform_tiers.md but missing a rating row in
    # content_policy.md must fail G02 with a clear violation, not KeyError.
    rows = {"Row A": [make_game(1)]}
    result = vg.g02_rating_policy(rows, {"tier": "kids",
                                         "rating_policy": {"standard": ["E"]}})
    assert not result.passed and "kids" in result.violations[0]


# --- G03 Row size ---------------------------------------------------------------
def test_g03_pass():
    rows = {"Row A": [make_game(i) for i in range(5)]}
    assert vg.g03_row_size(rows, STANDARD).passed


def test_g03_fail_too_few():
    rows = {"Row A": [make_game(i) for i in range(2)]}
    assert not vg.g03_row_size(rows, STANDARD).passed


def test_g03_fail_too_many():
    rows = {"Row A": [make_game(i) for i in range(12)]}
    assert not vg.g03_row_size(rows, STANDARD).passed


# --- G04 No duplicates ----------------------------------------------------------
def test_g04_pass():
    rows = {"Row A": [make_game(i) for i in range(5)]}
    assert vg.g04_no_duplicates(rows, STANDARD).passed


def test_g04_fail_intra_row():
    rows = {"Row A": [make_game(1), make_game(1)]}  # same id twice
    assert not vg.g04_no_duplicates(rows, STANDARD).passed


def test_g04_fail_cross_row():
    rows = {
        "Row A": [make_game(i) for i in range(5)],
        "Row B": [make_game(i) for i in range(3, 8)],  # g3, g4 overlap
    }
    assert not vg.g04_no_duplicates(rows, STANDARD).passed


# --- run_all --------------------------------------------------------------------
def test_run_all_pass():
    rows = {"Row A": [make_game(i) for i in range(6)],
            "Row B": [make_game(i) for i in range(6, 12)]}
    report = vg.run_all({"rows": rows, "policy": STANDARD})
    assert report.passed
    assert len(report.results) == 4  # all 4 gates ran


def test_run_all_fail_fast():
    # G01 fails → should stop before G02
    bad = make_game(1)
    bad["id"] = ""
    rows = {"Row A": [bad] + [make_game(i, rating="AO") for i in range(2, 6)]}
    report = vg.run_all({"rows": rows, "policy": STANDARD})
    assert not report.passed
    assert report.results[0].gate == "G01:RequiredFields"
    assert len(report.results) == 1  # stopped after G01


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = failed = 0
    for t in tests:
        try:
            t()
            print(f"✅ {t.__name__}")
            passed += 1
        except Exception as e:  # noqa: BLE001
            print(f"❌ {t.__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
