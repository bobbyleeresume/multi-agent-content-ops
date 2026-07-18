"""
agents/validation_agent.py

ValidationAgent — runs the G01–G04 gates. On any failure the pipeline halts
immediately (fail-fast). Loads the rating policy from the KB so rules and code
stay separate.
Deterministic by construction — the base class carries no LLM capability
(REFACTOR.md R4).
"""
from __future__ import annotations

import re

from agents.base import BaseAgent
from gates import validation_gates as vg


class ValidationAgent(BaseAgent):
    name = "ValidationAgent"

    def _rating_policy(self) -> dict[str, list[str]]:
        """Parse allowed ratings per tier from kb/domain/content_policy.md."""
        text = self.read_kb("domain/content_policy.md")
        policy: dict[str, list[str]] = {}
        for line in text.splitlines():
            m = re.match(r"\|\s*(premium|standard|casual)\s*\|\s*([^|]+?)\s*\|", line)
            if m:
                policy[m.group(1)] = [r.strip() for r in m.group(2).split(",")]
        return policy or {k: sorted(v) for k, v in vg.TIER_RATING_POLICY.items()}

    def run(self, context: dict) -> vg.ValidationReport:
        policy = {
            "tier": context.get("tier", "standard"),
            "rating_policy": self._rating_policy(),
        }
        return vg.run_all({"rows": context["rows"], "policy": policy})
