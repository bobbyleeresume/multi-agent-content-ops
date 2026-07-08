"""
tests/test_extras.py — guardrails, telemetry, and JSON failure-mode handling.
Runs standalone or under pytest. Offline; no API keys.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from guardrails import scrub  # noqa: E402
from obs.telemetry import Tracer  # noqa: E402
from agents.base import BaseAgent  # noqa: E402


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
    assert BaseAgent().safe_json("s", "u", required_keys=("score",)) is None


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
