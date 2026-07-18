"""
policy.py

PolicyLoader — the single source of truth for pipeline policy at runtime:
rating policy per tier, required fields, row-size bounds, the weekly row set,
and the tier list. Every value is parsed from the KB (`kb/domain/*.md`);
code never hardcodes a policy value except as a clearly-labeled emergency
fallback below.

Loud by design (REFACTOR.md R3 / F4): a missing KB file, or a table that
fails to parse, prints `[policy] WARNING: ...` to stderr and falls back to
the matching `_EMERGENCY_FALLBACK_*` constant. Pass `strict=True` to the
constructor, or set `POLICY_STRICT=1` in the environment, to raise
`PolicyError` instead of warning — for CI or any context where a silent
KB/code drift must never pass quietly.

Before this module existed, `ValidationAgent._rating_policy` and
`CurationAgent._row_set` did this same regex parsing but swallowed failures
silently (fell back to code constants with no warning), and G01 (required
fields) / G03 (row-size bounds) were sourced straight from
`gates/validation_gates.py` code constants even though the KB documented
them — the KB copy was decorative. This module closes both gaps: the KB is
now what actually drives G01–G03 and the CLI's `--tier` choices.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

KB_ROOT = Path(__file__).resolve().parent / "kb"

# --- Emergency fallback ONLY -------------------------------------------------
# These exist so the pipeline can still run if the KB is deleted, unreadable,
# or corrupted. They are NOT the source of truth — kb/domain/*.md is. Outside
# of a deliberate degraded-mode run, PolicyLoader will already have printed a
# `[policy] WARNING` (or, under strict=True, raised `PolicyError`) before any
# of these values are used — a silent drift between these constants and the
# KB is a bug.
_EMERGENCY_FALLBACK_RATING_POLICY: dict[str, list[str]] = {
    "premium": ["E", "E10", "T", "M"],
    "standard": ["E", "E10", "T", "M"],
    "casual": ["E", "E10", "T"],
}
_EMERGENCY_FALLBACK_REQUIRED_FIELDS: tuple[str, ...] = ("id", "title", "genre", "rating")
_EMERGENCY_FALLBACK_ROW_MIN: int = 3
_EMERGENCY_FALLBACK_ROW_MAX: int = 10
_EMERGENCY_FALLBACK_ROW_SET: list[tuple[str, str, int]] = [
    ("Top Picks", "action", 8),
    ("Adventure Zone", "adventure", 6),
    ("Indie Spotlight", "indie", 6),
    ("Family Friendly", "family", 5),
    ("Strategy Vault", "strategy", 5),
]
_EMERGENCY_FALLBACK_TIERS: list[str] = ["premium", "standard", "casual"]


def emergency_fallback_tiers() -> list[str]:
    """A copy of the emergency-fallback tier list, for callers (the
    orchestrator CLI) that need something to fall back to if
    `PolicyLoader.tiers()` itself raises (strict mode + broken KB) rather
    than warning."""
    return list(_EMERGENCY_FALLBACK_TIERS)


class PolicyError(RuntimeError):
    """Raised by PolicyLoader in strict mode instead of warning to stderr."""


# --- markdown table parsing helpers ------------------------------------------
def _section(text: str, heading: str) -> str:
    """Text under a `## heading` line, up to the next `## ` heading or EOF.
    Used to isolate one table when a KB file has more than one (e.g.
    content_policy.md has both a Rating Policy and a Required Fields table)."""
    pattern = re.compile(
        rf"^##\s+{re.escape(heading)}\s*$(.*?)(?=^##\s+|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    m = pattern.search(text)
    return m.group(1) if m else ""


def _table_rows(text: str) -> list[list[str]]:
    """Body cell rows of the first (assumed only) markdown table in `text` —
    header and `---` separator rows excluded. Returns [] if no table is
    found, which callers treat as a parse failure."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip().startswith("|")]
    rows: list[list[str]] = []
    for i, line in enumerate(lines):
        cells = [c.strip() for c in line.strip("|").split("|")]
        if i == 0:
            continue  # header row
        if all(re.fullmatch(r":?-+:?", c) for c in cells):
            continue  # separator row, e.g. |------|------|
        rows.append(cells)
    return rows


class PolicyLoader:
    """Parses pipeline policy from the KB. See the module docstring for the
    loud/strict contract."""

    def __init__(self, kb_root: Path | str = KB_ROOT, strict: bool | None = None):
        self.kb_root = Path(kb_root)
        if strict is None:
            strict = os.environ.get("POLICY_STRICT") == "1"
        self.strict = strict

    # --- internal -------------------------------------------------------
    def _read(self, relpath: str) -> str | None:
        path = self.kb_root / relpath
        if not path.exists():
            self._warn_or_raise(f"KB file not found: {path}")
            return None
        text = path.read_text(encoding="utf-8")
        if not text.strip():
            self._warn_or_raise(f"KB file is empty: {path}")
            return None
        return text

    def _warn_or_raise(self, message: str) -> None:
        full = f"[policy] WARNING: {message} — falling back to emergency default"
        if self.strict:
            raise PolicyError(full)
        print(full, file=sys.stderr)

    # --- rating policy per tier (kb/domain/content_policy.md) ------------
    def rating_policy(self) -> dict[str, list[str]]:
        text = self._read("domain/content_policy.md")
        if text is None:
            return {k: list(v) for k, v in _EMERGENCY_FALLBACK_RATING_POLICY.items()}
        rows = _table_rows(_section(text, "Rating Policy"))
        policy = {
            cells[0].strip().lower(): [r.strip() for r in cells[1].split(",")]
            for cells in rows if len(cells) >= 2 and cells[0].strip()
        }
        if not policy:
            self._warn_or_raise("no rating-policy rows parsed from domain/content_policy.md")
            return {k: list(v) for k, v in _EMERGENCY_FALLBACK_RATING_POLICY.items()}
        return policy

    # --- required fields (kb/domain/content_policy.md) -------------------
    def required_fields(self) -> tuple[str, ...]:
        text = self._read("domain/content_policy.md")
        if text is None:
            return _EMERGENCY_FALLBACK_REQUIRED_FIELDS
        rows = _table_rows(_section(text, "Required Fields"))
        fields = []
        for cells in rows:
            if not cells or not cells[0]:
                continue
            m = re.match(r"`([^`]+)`", cells[0].strip())
            if m:
                fields.append(m.group(1))
        if not fields:
            self._warn_or_raise("no required-field rows parsed from domain/content_policy.md")
            return _EMERGENCY_FALLBACK_REQUIRED_FIELDS
        return tuple(fields)

    # --- row-size bounds (kb/domain/row_rules.md) ------------------------
    def row_bounds(self) -> tuple[int, int]:
        text = self._read("domain/row_rules.md")
        if text is None:
            return (_EMERGENCY_FALLBACK_ROW_MIN, _EMERGENCY_FALLBACK_ROW_MAX)
        # NB: the KB writes an en dash ("3–10 titles"), not a hyphen.
        m = re.search(r"allows\s+(\d+)\s*[-–]\s*(\d+)\s+titles", text)
        if not m:
            self._warn_or_raise("row-size bounds not found in domain/row_rules.md")
            return (_EMERGENCY_FALLBACK_ROW_MIN, _EMERGENCY_FALLBACK_ROW_MAX)
        return int(m.group(1)), int(m.group(2))

    # --- row set: (row_name, genre, target_count) (kb/domain/row_rules.md) --
    def row_set(self) -> list[tuple[str, str, int]]:
        text = self._read("domain/row_rules.md")
        if text is None:
            return list(_EMERGENCY_FALLBACK_ROW_SET)
        rows = _table_rows(_section(text, "Standard Weekly Row Set"))
        row_set = [
            (cells[0].strip(), cells[1].strip().lower(), int(cells[2].strip()))
            for cells in rows if len(cells) >= 3 and cells[2].strip().isdigit()
        ]
        if not row_set:
            self._warn_or_raise("no row-set rows parsed from domain/row_rules.md")
            return list(_EMERGENCY_FALLBACK_ROW_SET)
        return row_set

    # --- tier list (kb/domain/platform_tiers.md) -------------------------
    def tiers(self) -> list[str]:
        text = self._read("domain/platform_tiers.md")
        if text is None:
            return list(_EMERGENCY_FALLBACK_TIERS)
        rows = _table_rows(text)
        tiers = [cells[0].strip().lower() for cells in rows if cells and cells[0].strip()]
        if not tiers:
            self._warn_or_raise("no tiers parsed from domain/platform_tiers.md")
            return list(_EMERGENCY_FALLBACK_TIERS)
        return tiers
