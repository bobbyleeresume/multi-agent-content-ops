"""
tests/test_policy.py — PolicyLoader: the KB is the source of truth, loudly.

Covers: (1) happy path — parsed values match the real KB, (2) a missing KB
warns to stderr and falls back to the emergency default, (3) strict mode
(constructor arg and POLICY_STRICT=1 env var) raises instead of warning,
(4) a tampered/unparseable table warns and falls back.

Runs standalone (`python tests/test_policy.py`) or under pytest. Offline; no
API keys.
"""
import contextlib
import io
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from policy import (  # noqa: E402
    PolicyError,
    PolicyLoader,
    _EMERGENCY_FALLBACK_RATING_POLICY,
    _EMERGENCY_FALLBACK_REQUIRED_FIELDS,
    _EMERGENCY_FALLBACK_ROW_MAX,
    _EMERGENCY_FALLBACK_ROW_MIN,
    _EMERGENCY_FALLBACK_ROW_SET,
    _EMERGENCY_FALLBACK_TIERS,
)


# --- Happy path: parsed values match the real KB --------------------------------
def test_rating_policy_matches_kb():
    loader = PolicyLoader()
    assert loader.rating_policy() == {
        "premium": ["E", "E10", "T", "M"],
        "standard": ["E", "E10", "T", "M"],
        "casual": ["E", "E10", "T"],
    }


def test_required_fields_matches_kb():
    loader = PolicyLoader()
    assert loader.required_fields() == ("id", "title", "genre", "rating")


def test_row_bounds_matches_kb():
    loader = PolicyLoader()
    assert loader.row_bounds() == (3, 10)


def test_row_set_matches_kb():
    loader = PolicyLoader()
    assert loader.row_set() == [
        ("Top Picks", "action", 8),
        ("Adventure Zone", "adventure", 6),
        ("Indie Spotlight", "indie", 6),
        ("Family Friendly", "family", 5),
        ("Strategy Vault", "strategy", 5),
    ]


def test_tiers_matches_kb():
    loader = PolicyLoader()
    assert loader.tiers() == ["premium", "standard", "casual"]


# --- Missing KB: warns loudly, falls back ----------------------------------------
def test_missing_kb_root_warns_and_falls_back():
    loader = PolicyLoader(kb_root="/nonexistent/kb-root-for-testing")
    stderr = io.StringIO()
    with contextlib.redirect_stderr(stderr):
        result = loader.tiers()
    assert result == list(_EMERGENCY_FALLBACK_TIERS)
    assert "[policy] WARNING" in stderr.getvalue()
    assert "not found" in stderr.getvalue()


def test_missing_kb_falls_back_for_every_accessor():
    loader = PolicyLoader(kb_root="/nonexistent/kb-root-for-testing")
    with contextlib.redirect_stderr(io.StringIO()):
        assert loader.rating_policy() == {
            k: list(v) for k, v in _EMERGENCY_FALLBACK_RATING_POLICY.items()
        }
        assert loader.required_fields() == _EMERGENCY_FALLBACK_REQUIRED_FIELDS
        assert loader.row_bounds() == (_EMERGENCY_FALLBACK_ROW_MIN, _EMERGENCY_FALLBACK_ROW_MAX)
        assert loader.row_set() == list(_EMERGENCY_FALLBACK_ROW_SET)


# --- Strict mode: raises instead of warning --------------------------------------
def test_strict_mode_ctor_arg_raises_on_missing_kb():
    loader = PolicyLoader(kb_root="/nonexistent/kb-root-for-testing", strict=True)
    try:
        loader.tiers()
        assert False, "expected PolicyError in strict mode with a missing KB"
    except PolicyError as e:
        assert "not found" in str(e)


def test_strict_mode_env_var_raises_on_missing_kb():
    os.environ["POLICY_STRICT"] = "1"
    try:
        loader = PolicyLoader(kb_root="/nonexistent/kb-root-for-testing")
        assert loader.strict is True
        try:
            loader.row_bounds()
            assert False, "expected PolicyError with POLICY_STRICT=1"
        except PolicyError:
            pass
    finally:
        os.environ.pop("POLICY_STRICT", None)


# --- Tampered table: warns and falls back ----------------------------------------
def test_tampered_table_warns_and_falls_back():
    with tempfile.TemporaryDirectory() as tmp:
        domain = Path(tmp) / "domain"
        domain.mkdir()
        # No markdown table at all — just prose. Parsing must find zero rows.
        (domain / "content_policy.md").write_text(
            "# Content Policy\n\nThis file has been tampered with; no tables here.\n",
            encoding="utf-8",
        )
        loader = PolicyLoader(kb_root=tmp)
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            result = loader.rating_policy()
        assert result == {k: list(v) for k, v in _EMERGENCY_FALLBACK_RATING_POLICY.items()}
        assert "[policy] WARNING" in stderr.getvalue()
        assert "no rating-policy rows parsed" in stderr.getvalue()


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
