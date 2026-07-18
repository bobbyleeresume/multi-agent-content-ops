"""
tests/test_extras.py — guardrails, telemetry, JSON failure-mode handling, and
the week-over-week layout diff (CommsAgent, REFACTOR.md R5).
Runs standalone or under pytest. Offline; no API keys.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from guardrails import scrub  # noqa: E402
from obs.telemetry import Tracer  # noqa: E402
from agents.base import BaseAgent, LLMAgent  # noqa: E402
from agents.comms_agent import compute_layout_diff  # noqa: E402


# --- Guardrails -----------------------------------------------------------------
def test_guardrail_redacts_email():
    r = scrub("Contact me at bob@example.com for details.")
    assert "[redacted-email]" in r.text and r.redactions == 1


def test_guardrail_redacts_phone():
    r = scrub("Call (213) 505-1930 now.")
    assert "[redacted-phone]" in r.text and r.redactions == 1


def test_guardrail_flags_blocklist():
    r = scrub("This is CONFIDENTIAL material.")
    assert not r.clean and "confidential" in r.flags


def test_guardrail_clean_passthrough():
    r = scrub("Week 28 published 30 titles.")
    assert r.clean and r.redactions == 0


# --- Telemetry ------------------------------------------------------------------
def test_telemetry_cost_and_span():
    tr = Tracer()
    with tr.span("VALIDATE"):
        pass
    tr.record_llm("claude-3-5-haiku-20241022", 1000, 500, 42.0)
    s = tr.summary()
    assert s["llm_calls"] == 1
    assert s["total_tokens"] == 1500
    # 1000/1e6*0.80 + 500/1e6*4.00 = 0.0008 + 0.002 = 0.0028
    assert abs(s["total_cost_usd"] - 0.0028) < 1e-6
    assert len(s["spans"]) == 1


# --- Failure-mode: safe_json offline returns None (no crash) --------------------
def test_safe_json_offline_returns_none():
    os.environ.pop("ANTHROPIC_API_KEY", None)
    assert LLMAgent().safe_json("s", "u", required_keys=("score",)) is None


# --- Structural: BaseAgent carries no LLM capability (REFACTOR.md R4) ------------
def test_base_agent_has_no_llm_capability():
    assert not hasattr(BaseAgent, "llm") and not hasattr(BaseAgent, "safe_json")


# --- compute_layout_diff (REFACTOR.md R5) ----------------------------------------
def test_layout_diff_none_prev_marks_everything_added():
    rows = {"Top Picks": [{"id": "g1", "title": "Neon Vanguard", "genre": "action",
                           "rating": "T"}]}
    diff = compute_layout_diff(None, rows)
    assert diff["first_publish"] is True
    assert diff["summary"]["added_count"] == 1
    assert diff["summary"]["removed_count"] == 0
    assert diff["added_rows"] == ["Top Picks"]


def test_layout_diff_detects_added_and_removed_titles():
    prev = {"Top Picks": [{"id": "g1", "title": "A", "genre": "action", "rating": "T"},
                          {"id": "g2", "title": "B", "genre": "action", "rating": "T"}]}
    new = {"Top Picks": [{"id": "g1", "title": "A", "genre": "action", "rating": "T"},
                         {"id": "g3", "title": "C", "genre": "action", "rating": "T"}]}
    diff = compute_layout_diff(prev, new)
    assert diff["first_publish"] is False
    assert [t["id"] for t in diff["added_titles"]] == ["g3"]
    assert [t["id"] for t in diff["removed_titles"]] == ["g2"]


def test_layout_diff_detects_new_and_removed_rows_and_count_changes():
    prev = {"Row A": [{"id": "g1", "title": "A", "genre": "action", "rating": "T"}]}
    new = {
        "Row A": [{"id": "g1", "title": "A", "genre": "action", "rating": "T"},
                  {"id": "g2", "title": "B", "genre": "action", "rating": "T"}],
        "Row B": [{"id": "g3", "title": "C", "genre": "action", "rating": "T"}],
    }
    diff = compute_layout_diff(prev, new)
    assert diff["added_rows"] == ["Row B"]
    assert diff["removed_rows"] == []
    assert diff["row_count_changes"] == [
        {"row": "Row A", "prev_count": 1, "new_count": 2, "delta": 1}
    ]


def test_layout_diff_no_changes_is_all_zero():
    rows = {"Row A": [{"id": "g1", "title": "A", "genre": "action", "rating": "T"}]}
    diff = compute_layout_diff(rows, rows)
    s = diff["summary"]
    assert s["added_count"] == 0 and s["removed_count"] == 0
    assert s["rows_added_count"] == 0 and s["rows_removed_count"] == 0
    assert diff["row_count_changes"] == []


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
