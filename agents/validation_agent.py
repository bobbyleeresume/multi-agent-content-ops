"""
agents/validation_agent.py

ValidationAgent — runs the G01–G04 gates. On any failure the pipeline halts
immediately (fail-fast). Rating policy, required fields, and row-size bounds
are all loaded from the KB via `policy.PolicyLoader` at runtime — the KB is
the actual source of truth for every gate, not just G02 (REFACTOR.md R3).
Deterministic by construction — the base class carries no LLM capability
(REFACTOR.md R4).
"""
from __future__ import annotations

from agents.base import BaseAgent
from gates import validation_gates as vg
from policy import PolicyLoader


class ValidationAgent(BaseAgent):
    name = "ValidationAgent"

    def run(self, context: dict) -> vg.ValidationReport:
        loader = PolicyLoader()
        row_min, row_max = loader.row_bounds()
        policy = {
            "tier": context.get("tier", "standard"),
            "rating_policy": loader.rating_policy(),
            "required_fields": loader.required_fields(),
            "row_min": row_min,
            "row_max": row_max,
        }
        return vg.run_all({"rows": context["rows"], "policy": policy})
