"""
evals/run_evals.py

Evaluation harness. Three suites:

  1. gate_behavior  — every golden layout fixture (evals/golden/*.json) must
                      produce the expected gate verdict (and the expected
                      first failing gate). The golden set has full G01–G04
                      coverage; see evals/golden/LABELING.md for the dataset,
                      label schema, and labeling procedure.
  2. comms_quality  — the generated weekly report must contain the required
                      sections; its stated counts must match the input
                      (deterministic judge — catches hallucinated numbers);
                      and the week-over-week diff section's added/removed
                      counts must match `compute_layout_diff`'s own output
                      for the same synthetic prev/new rows (diff-faithfulness
                      — catches a hallucinated diff, not just hallucinated
                      totals), across first-publish and with-previous cases.
  3. llm_judge      — OPTIONAL. If ANTHROPIC_API_KEY is set, an LLM-as-judge
                      rates the narrative's faithfulness 1–5 (threshold 4).

Runs offline for suites 1–2 (no API key). Exit non-zero on any failure so CI
blocks regressions.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agents.comms_agent import CommsAgent, compute_layout_diff  # noqa: E402
from agents.validation_agent import ValidationAgent  # noqa: E402
from agents.base import LLMAgent  # noqa: E402

GOLDEN = Path(__file__).resolve().parent / "golden"


def _load(name: str) -> dict:
    return json.loads((GOLDEN / name).read_text(encoding="utf-8"))


# --- Suite 1: gate behavior -----------------------------------------------------
def eval_gate_behavior() -> list[tuple[str, bool, str]]:
    results = []
    # Every fixture in the golden set (see LABELING.md — not itself a fixture,
    # so the *.json glob already skips it), sorted for deterministic ordering.
    fixtures = sorted(p.name for p in GOLDEN.glob("*.json"))
    for fixture in fixtures:
        data = _load(fixture)
        report = ValidationAgent().run({"rows": data["rows"], "tier": data["tier"]})
        ok = report.passed == data["expect_passed"]
        detail = f"passed={report.passed} expected={data['expect_passed']}"
        if not data["expect_passed"] and ok:
            first_fail = next((r.gate for r in report.results if not r.passed), None)
            ok = first_fail == data.get("expect_failed_gate")
            detail += f" | first_fail={first_fail} expected={data.get('expect_failed_gate')}"
        results.append((f"gate_behavior[{fixture}]", ok, detail))
    return results


# --- Suite 2: comms quality (deterministic judge) -------------------------------
def eval_comms_quality() -> list[tuple[str, bool, str]]:
    results: list[tuple[str, bool, str]] = []

    # --- case 1: baseline section/count checks, no previous publish ---------
    rows = {
        "Top Picks": [{"id": f"g{i}", "title": f"Game {i}", "genre": "action",
                       "rating": "T"} for i in range(5)],
        "Indie Spotlight": [{"id": f"i{i}", "title": f"Indie {i}", "genre": "indie",
                             "rating": "E"} for i in range(4)],
    }
    total = sum(len(v) for v in rows.values())
    path = CommsAgent().run({
        "week": "2026-W28e1", "tier": "standard", "region": "NA",
        "rows": rows, "publish_status": "published",
    })
    md = Path(path).read_text(encoding="utf-8")
    checks = [
        ("has_overview", "## Overview" in md),
        ("has_row_breakdown", "## Row Breakdown" in md),
        ("has_changes_section", "## Changes vs Previous Publish" in md),
        ("has_summary", "## Summary" in md),
        ("nonempty_summary", len(md.split("## Summary", 1)[-1].strip()) > 20),
        ("count_faithful", f"| Total titles | {total} |" in md),
        ("no_placeholder", "{narrative}" not in md and "{rows_table}" not in md),
    ]
    results.extend((f"comms_quality[{n}]", ok, "") for n, ok in checks)

    # --- case 2: no previous publish -> first-publish narrative --------------
    path_first = CommsAgent().run({
        "week": "2026-W28e2", "tier": "standard", "region": "NA",
        "rows": rows, "publish_status": "published", "previous_rows": None,
    })
    md_first = Path(path_first).read_text(encoding="utf-8")
    results.append((
        "comms_quality[first_publish_stated]",
        "First publish" in md_first,
        "",
    ))

    # --- case 3: with previous publish -> diff-faithfulness (deterministic) --
    prev_rows = {
        "Top Picks": [{"id": f"g{i}", "title": f"Game {i}", "genre": "action",
                       "rating": "T"} for i in range(3)],
        "Strategy Vault": [{"id": f"s{i}", "title": f"Strat {i}", "genre": "strategy",
                            "rating": "T"} for i in range(3)],
    }
    expected_diff = compute_layout_diff(prev_rows, rows)
    path_diff = CommsAgent().run({
        "week": "2026-W28e3", "tier": "standard", "region": "NA",
        "rows": rows, "publish_status": "published", "previous_rows": prev_rows,
    })
    md_diff = Path(path_diff).read_text(encoding="utf-8")
    s = expected_diff["summary"]
    diff_checks = [
        ("has_changes_section", "## Changes vs Previous Publish" in md_diff),
        ("added_count_faithful", f"| Added titles | {s['added_count']} |" in md_diff),
        ("removed_count_faithful", f"| Removed titles | {s['removed_count']} |" in md_diff),
        ("rows_added_faithful", f"| Rows added | {s['rows_added_count']} |" in md_diff),
        ("rows_removed_faithful", f"| Rows removed | {s['rows_removed_count']} |" in md_diff),
    ]
    results.extend((f"comms_quality[with_previous:{n}]", ok, "") for n, ok in diff_checks)

    return results


# --- Suite 3: LLM-as-judge (optional) -------------------------------------------
def eval_llm_judge() -> list[tuple[str, bool, str]]:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return [("llm_judge", True, "skipped (no ANTHROPIC_API_KEY)")]
    rows = {"Top Picks": [{"id": "g1", "title": "Neon Vanguard", "genre": "action",
                           "rating": "T"}]}
    path = CommsAgent().run({"week": "2026-W28", "tier": "standard", "region": "NA",
                             "rows": rows, "publish_status": "published"})
    summary = Path(path).read_text(encoding="utf-8").split("## Summary", 1)[-1].strip()
    judge = LLMAgent()
    verdict = judge.safe_json(
        system="You are a strict QA judge. Return only JSON.",
        user=("Rate 1-5 how faithful this weekly summary is to the facts "
              "(1 row, tier standard, published). Return "
              '{"score": <int>, "reason": "<str>"}.\n\n' + summary),
        required_keys=("score",),
    )
    if not verdict:
        return [("llm_judge", False, "judge returned malformed JSON")]
    ok = int(verdict["score"]) >= 4
    return [("llm_judge", ok, f"score={verdict['score']} — {verdict.get('reason', '')}")]


def main() -> int:
    suites = [eval_gate_behavior, eval_comms_quality, eval_llm_judge]
    all_results: list[tuple[str, bool, str]] = []
    for suite in suites:
        all_results.extend(suite())

    passed = sum(1 for _, ok, _ in all_results if ok)
    print("=" * 60)
    print("EVAL RESULTS")
    print("=" * 60)
    for name, ok, detail in all_results:
        mark = "✅" if ok else "❌"
        print(f"{mark} {name}" + (f"  — {detail}" if detail else ""))
    print("=" * 60)
    print(f"{passed}/{len(all_results)} checks passed")
    return 0 if passed == len(all_results) else 1


if __name__ == "__main__":
    sys.exit(main())
