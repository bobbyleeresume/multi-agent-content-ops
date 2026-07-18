"""
agents/comms_agent.py

CommsAgent — reads final state and generates a weekly narrative report. The
LLM's one job is a week-over-week change narrative: what's different in this
layout vs. the previously published one (`compute_layout_diff`, deterministic;
REFACTOR.md R5). Falls back to a deterministic template built from the same
diff facts when offline. Writes reports/WK<week>_summary.md.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from agents.base import LLMAgent
from guardrails import scrub

REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"


# --- Deterministic diff: current layout vs. the previously published one -------
def compute_layout_diff(prev_rows: dict[str, list[dict]] | None,
                         rows: dict[str, list[dict]]) -> dict:
    """Diff the current `rows` against the previously published layout.

    `prev_rows=None` means there is nothing to diff against (first publish) —
    every current title/row counts as added. Diffing is by title `id`, which
    is what makes this deterministic and reproducible from the same inputs
    (no LLM involved).

    Returns:
        {
          "first_publish": bool,
          "added_titles": [{"id", "title", "row"}, ...],    # in rows, not prev_rows
          "removed_titles": [{"id", "title", "row"}, ...],  # in prev_rows, not rows
          "added_rows": [row_name, ...],                    # new in rows
          "removed_rows": [row_name, ...],                  # gone from prev_rows
          "row_count_changes": [
              {"row", "prev_count", "new_count", "delta"}, ...
          ],                                                 # rows in both, count differs
          "summary": {
              "added_count", "removed_count",
              "rows_added_count", "rows_removed_count",
              "prev_total_titles", "new_total_titles",
          },
        }
    """
    new_total = sum(len(v) for v in rows.values())

    if prev_rows is None:
        added_titles = [
            {"id": t["id"], "title": t.get("title", t["id"]), "row": row_name}
            for row_name, titles in rows.items() for t in titles
        ]
        return {
            "first_publish": True,
            "added_titles": added_titles,
            "removed_titles": [],
            "added_rows": list(rows.keys()),
            "removed_rows": [],
            "row_count_changes": [],
            "summary": {
                "added_count": len(added_titles),
                "removed_count": 0,
                "rows_added_count": len(rows),
                "rows_removed_count": 0,
                "prev_total_titles": 0,
                "new_total_titles": new_total,
            },
        }

    prev_by_id: dict[str, tuple[str, str]] = {
        t["id"]: (t.get("title", t["id"]), row_name)
        for row_name, titles in prev_rows.items() for t in titles
    }
    new_by_id: dict[str, tuple[str, str]] = {
        t["id"]: (t.get("title", t["id"]), row_name)
        for row_name, titles in rows.items() for t in titles
    }

    added_titles = [
        {"id": tid, "title": title, "row": row_name}
        for tid, (title, row_name) in new_by_id.items() if tid not in prev_by_id
    ]
    removed_titles = [
        {"id": tid, "title": title, "row": row_name}
        for tid, (title, row_name) in prev_by_id.items() if tid not in new_by_id
    ]
    added_rows = [r for r in rows if r not in prev_rows]
    removed_rows = [r for r in prev_rows if r not in rows]
    row_count_changes = [
        {"row": r, "prev_count": len(prev_rows[r]), "new_count": len(rows[r]),
         "delta": len(rows[r]) - len(prev_rows[r])}
        for r in rows if r in prev_rows and len(rows[r]) != len(prev_rows[r])
    ]
    prev_total = sum(len(v) for v in prev_rows.values())

    return {
        "first_publish": False,
        "added_titles": added_titles,
        "removed_titles": removed_titles,
        "added_rows": added_rows,
        "removed_rows": removed_rows,
        "row_count_changes": row_count_changes,
        "summary": {
            "added_count": len(added_titles),
            "removed_count": len(removed_titles),
            "rows_added_count": len(added_rows),
            "rows_removed_count": len(removed_rows),
            "prev_total_titles": prev_total,
            "new_total_titles": new_total,
        },
    }


def _diff_section_md(diff: dict) -> str:
    """Deterministic, code-generated markdown for the 'Changes vs Previous
    Publish' section — a table so the eval harness can check the LLM's
    narrative claims against these exact numbers (no hallucinated counts)."""
    s = diff["summary"]
    if diff["first_publish"]:
        return (
            f"First publish — no previous layout to diff against. "
            f"All {s['rows_added_count']} rows / {s['new_total_titles']} titles are new."
        )
    lines = [
        "| Metric | Value |",
        "|--------|-------|",
        f"| Added titles | {s['added_count']} |",
        f"| Removed titles | {s['removed_count']} |",
        f"| Rows added | {s['rows_added_count']} |",
        f"| Rows removed | {s['rows_removed_count']} |",
        f"| Previous total titles | {s['prev_total_titles']} |",
        f"| New total titles | {s['new_total_titles']} |",
    ]
    if diff["added_titles"]:
        names = ", ".join(f"{t['title']} ({t['row']})" for t in diff["added_titles"])
        lines.append(f"\n**Added:** {names}")
    if diff["removed_titles"]:
        names = ", ".join(f"{t['title']} ({t['row']})" for t in diff["removed_titles"])
        lines.append(f"\n**Removed:** {names}")
    if diff["added_rows"]:
        lines.append(f"\n**New rows:** {', '.join(diff['added_rows'])}")
    if diff["removed_rows"]:
        lines.append(f"\n**Removed rows:** {', '.join(diff['removed_rows'])}")
    if diff["row_count_changes"]:
        changes = "; ".join(
            f"{c['row']} {c['prev_count']}→{c['new_count']}"
            for c in diff["row_count_changes"]
        )
        lines.append(f"\n**Row size changes:** {changes}")
    if not any([diff["added_titles"], diff["removed_titles"], diff["added_rows"],
                diff["removed_rows"], diff["row_count_changes"]]):
        lines.append("\nNo changes from the previous publish.")
    return "\n".join(lines)


class CommsAgent(LLMAgent):
    name = "CommsAgent"

    def _diff_prompt(self, stats: dict, diff: dict) -> str:
        """Build the LLM user turn from diff facts — this is the actual
        generative material: what changed, not a restatement of this week's
        raw stats (which the reader already sees in Overview/Row Breakdown)."""
        s = diff["summary"]
        lines = [
            f"Week: {stats['week']} | Tier: {stats['tier']} | Region: {stats['region']}",
            f"Publish status: {stats['publish_status']}",
        ]
        if diff["first_publish"]:
            lines.append(
                f"This is the FIRST publish for this layout — no previous publish "
                f"exists. {s['new_total_titles']} titles across "
                f"{s['rows_added_count']} rows, all new."
            )
        else:
            lines.append(
                f"Compared to the previous publish: {s['added_count']} title(s) "
                f"added, {s['removed_count']} removed; {s['rows_added_count']} "
                f"row(s) added, {s['rows_removed_count']} row(s) removed."
            )
            if diff["added_titles"]:
                lines.append("Added: " + ", ".join(
                    f"{t['title']} ({t['row']})" for t in diff["added_titles"]))
            if diff["removed_titles"]:
                lines.append("Removed: " + ", ".join(
                    f"{t['title']} ({t['row']})" for t in diff["removed_titles"]))
            if diff["row_count_changes"]:
                lines.append("Row size changes: " + "; ".join(
                    f"{c['row']} {c['prev_count']}→{c['new_count']}"
                    for c in diff["row_count_changes"]))
            if not any([diff["added_titles"], diff["removed_titles"],
                        diff["added_rows"], diff["removed_rows"],
                        diff["row_count_changes"]]):
                lines.append("No changes from the previous publish.")
        lines.append("Write the weekly summary — focus on what changed and why it matters.")
        return "\n".join(lines)

    def _offline_diff_narrative(self, stats: dict, diff: dict) -> str:
        """Deterministic fallback narrative, built only from diff facts —
        used offline (no ANTHROPIC_API_KEY) instead of the LLM."""
        s = diff["summary"]
        if diff["first_publish"]:
            return (
                f"First publish for {stats['tier']}/{stats['region']}, week "
                f"{stats['week']}: {s['new_total_titles']} titles across "
                f"{s['rows_added_count']} rows, all new. "
                f"Publish status {stats['publish_status']}."
            )
        if not any([s["added_count"], s["removed_count"], s["rows_added_count"],
                    s["rows_removed_count"], diff["row_count_changes"]]):
            return (
                f"Week {stats['week']} ({stats['tier']}/{stats['region']}) is "
                f"unchanged from the previous publish — same {stats['row_count']} "
                f"rows, same {stats['total_titles']} titles. "
                f"Publish status {stats['publish_status']}."
            )
        parts = [
            f"Week {stats['week']} ({stats['tier']}/{stats['region']}) vs. the "
            f"previous publish: {s['added_count']} title(s) added, "
            f"{s['removed_count']} removed."
        ]
        if s["rows_added_count"] or s["rows_removed_count"]:
            parts.append(
                f"{s['rows_added_count']} new row(s), "
                f"{s['rows_removed_count']} row(s) removed."
            )
        if diff["row_count_changes"]:
            changes = "; ".join(
                f"{c['row']} {c['prev_count']}→{c['new_count']}"
                for c in diff["row_count_changes"]
            )
            parts.append(f"Row size changes: {changes}.")
        parts.append(f"Publish status {stats['publish_status']}.")
        return " ".join(parts)

    def _narrative(self, stats: dict, diff: dict) -> str:
        system = (
            "You are a content ops lead writing a concise internal weekly summary "
            "for a game streaming platform curation team. Be direct and factual. "
            "Describe what changed since the previous publish — do not restate "
            "raw stats the reader already saw above. Max 3 short paragraphs."
        )
        user = self._diff_prompt(stats, diff)
        text = self.llm(system=system, user=user, max_tokens=512)
        text = text or self._offline_diff_narrative(stats, diff)
        # Output guardrail: redact PII / flag blocked terms before it leaves the pipeline.
        guarded = scrub(text)
        if guarded.redactions or guarded.flags:
            print(f"[CommsAgent] guardrail: {guarded.redactions} redaction(s), "
                  f"flags={guarded.flags}")
        return guarded.text

    def run(self, context: dict) -> str:
        rows = context["rows"]
        prev_rows = context.get("previous_rows")
        diff = compute_layout_diff(prev_rows, rows)
        stats = {
            "week": context["week"],
            "tier": context["tier"],
            "region": context["region"],
            "row_count": len(rows),
            "total_titles": sum(len(v) for v in rows.values()),
            "publish_status": context.get("publish_status", "unknown"),
        }
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        rows_table = "\n".join(f"| {name} | {len(t)} |" for name, t in rows.items())
        md = f"""# Weekly Curation Summary — {stats['week']}

> Generated: {now} · Auto-generated by CommsAgent · NexCurate Multi-Agent Pipeline

## Overview

| Field | Value |
|-------|-------|
| Week | {stats['week']} |
| Tier | {stats['tier']} |
| Region | {stats['region']} |
| Rows | {stats['row_count']} |
| Total titles | {stats['total_titles']} |
| Publish status | {stats['publish_status']} |

## Row Breakdown

| Row | Title Count |
|-----|-------------|
{rows_table}

## Changes vs Previous Publish

{_diff_section_md(diff)}

## Summary

{self._narrative(stats, diff)}
"""
        REPORTS_DIR.mkdir(exist_ok=True)
        out = REPORTS_DIR / f"WK{stats['week']}_summary.md"
        out.write_text(md, encoding="utf-8")
        return str(out)
