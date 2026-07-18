"""
gates/validation_gates.py

Rule-based validation gates for the NexCurate weekly publishing pipeline.

    G01 — Required fields present
    G02 — Rating policy per tier
    G03 — Row size policy (min/max title count)
    G04 — No duplicate titles (intra-row + cross-row)

All gates return a GateResult. Any FAIL blocks publish immediately (fail-fast).

Gate policy (rating policy, required fields, row-size bounds) is loaded from
the KB at runtime by `policy.PolicyLoader` and passed in via the `policy`
dict each gate receives. The constants below are EMERGENCY FALLBACK ONLY,
used when a caller's `policy` dict omits a key — which in practice only
happens if `PolicyLoader` itself already fell back (and warned, or raised
under strict mode) because the KB was missing or failed to parse. A silent
drift between these constants and the KB is a bug (REFACTOR.md R3).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# --- Emergency fallback ONLY (see module docstring) ------------------------------
_EMERGENCY_FALLBACK_RATING_POLICY: dict[str, set[str]] = {
    "premium": {"E", "E10", "T", "M"},
    "standard": {"E", "E10", "T", "M"},
    "casual": {"E", "E10", "T"},
}
_EMERGENCY_FALLBACK_REQUIRED_FIELDS = ("id", "title", "genre", "rating")
_EMERGENCY_FALLBACK_ROW_MIN_TITLES = 3
_EMERGENCY_FALLBACK_ROW_MAX_TITLES = 10


# --- Data model -----------------------------------------------------------------
@dataclass
class GateResult:
    gate: str
    passed: bool
    violations: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        status = "✅ PASS" if self.passed else "❌ FAIL"
        lines = [f"[{self.gate}] {status}"]
        for v in self.violations:
            lines.append(f"   → {v}")
        return "\n".join(lines)


@dataclass
class ValidationReport:
    results: list[GateResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(r.passed for r in self.results)

    def summary(self) -> str:
        lines = ["=" * 50, "VALIDATION REPORT", "=" * 50]
        for r in self.results:
            lines.append(str(r))
        lines.append("=" * 50)
        overall = (
            "✅ ALL GATES PASSED — safe to publish"
            if self.passed
            else "🔴 BLOCKED — fix violations before publishing"
        )
        lines.append(overall)
        return "\n".join(lines)


# --- Gates ----------------------------------------------------------------------
def g01_required_fields(rows: dict[str, list[dict]], policy: dict) -> GateResult:
    required = policy.get("required_fields", _EMERGENCY_FALLBACK_REQUIRED_FIELDS)
    violations: list[str] = []
    for row_name, titles in rows.items():
        for t in titles:
            missing = [f for f in required if not t.get(f)]
            if missing:
                violations.append(
                    f"{row_name}: '{t.get('title', t.get('id', '?'))}' missing {missing}"
                )
    return GateResult("G01:RequiredFields", not violations, violations)


def g02_rating_policy(rows: dict[str, list[dict]], policy: dict) -> GateResult:
    tier = policy.get("tier", "standard")
    allowed = set(policy.get("rating_policy", {}).get(tier, _EMERGENCY_FALLBACK_RATING_POLICY[tier]))
    violations: list[str] = []
    for row_name, titles in rows.items():
        for t in titles:
            if t.get("rating") not in allowed:
                violations.append(
                    f"{row_name}: '{t.get('title')}' rating {t.get('rating')} "
                    f"not allowed for tier '{tier}' (allowed: {sorted(allowed)})"
                )
    return GateResult("G02:RatingPolicy", not violations, violations)


def g03_row_size(rows: dict[str, list[dict]], policy: dict) -> GateResult:
    mn = policy.get("row_min", _EMERGENCY_FALLBACK_ROW_MIN_TITLES)
    mx = policy.get("row_max", _EMERGENCY_FALLBACK_ROW_MAX_TITLES)
    violations: list[str] = []
    for row_name, titles in rows.items():
        n = len(titles)
        if n < mn or n > mx:
            violations.append(f"{row_name}: {n} titles (allowed {mn}–{mx})")
    return GateResult("G03:RowSize", not violations, violations)


def g04_no_duplicates(rows: dict[str, list[dict]], policy: dict) -> GateResult:
    violations: list[str] = []
    # intra-row
    for row_name, titles in rows.items():
        seen: set = set()
        for t in titles:
            tid = t.get("id")
            if tid in seen:
                violations.append(f"{row_name}: duplicate '{t.get('title')}' within row")
            seen.add(tid)
    # cross-row
    global_seen: dict[str, str] = {}
    for row_name, titles in rows.items():
        for t in titles:
            tid = t.get("id")
            if tid in global_seen:
                violations.append(
                    f"'{t.get('title')}' appears in both '{global_seen[tid]}' and '{row_name}'"
                )
            else:
                global_seen[tid] = row_name
    return GateResult("G04:NoDuplicates", not violations, violations)


GATES = [g01_required_fields, g02_rating_policy, g03_row_size, g04_no_duplicates]


def run_all(context: dict[str, Any]) -> ValidationReport:
    """Run every gate fail-fast. `context` = {'rows': {...}, 'policy': {...}}."""
    rows = context.get("rows", {})
    policy = context.get("policy", {})
    report = ValidationReport()
    for gate in GATES:
        result = gate(rows, policy)
        report.results.append(result)
        if not result.passed:
            break  # fail-fast: stop at first failing gate
    return report
