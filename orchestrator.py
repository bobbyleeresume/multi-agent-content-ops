"""
orchestrator.py — NexCurate weekly publishing pipeline.

State machine: INIT → CURATE → VALIDATE → PUBLISH → REPORT
Any gate failure HALTs the pipeline before PUBLISH (fail-fast).

Usage:
    python orchestrator.py --week 2026-W28 --tier standard --region NA
    python orchestrator.py --week 2026-W28 --tier casual --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from agents.curation_agent import CurationAgent
from agents.validation_agent import ValidationAgent
from agents.comms_agent import CommsAgent
from obs.telemetry import get_tracer
from policy import PolicyLoader, PolicyError, emergency_fallback_tiers


class Stage(Enum):
    INIT = "INIT"
    CURATE = "CURATE"
    VALIDATE = "VALIDATE"
    PUBLISH = "PUBLISH"
    REPORT = "REPORT"
    DONE = "DONE"
    HALT = "HALT"


class Orchestrator:
    """Drives stage transitions. Never does domain work itself — delegates to agents."""

    def __init__(self, week: str, tier: str, region: str, dry_run: bool = False):
        self.week = week
        self.tier = tier
        self.region = region
        self.dry_run = dry_run
        self.stage = Stage.INIT
        self.state: dict[str, Any] = {}
        self.tracer = get_tracer()
        self.tracer.reset()

    def log(self, msg: str) -> None:
        print(f"[{datetime.now(timezone.utc):%H:%M:%S}] {self.stage.value:<9} {msg}")

    def transition(self, to: Stage) -> None:
        self.log(f"→ {to.value}")
        self.stage = to

    def run(self) -> dict[str, Any]:
        self.transition(Stage.CURATE)
        with self.tracer.span("CURATE"):
            rows = CurationAgent().run(
                {"week": self.week, "tier": self.tier, "region": self.region}
            )
        self.state["rows"] = rows
        self.log(f"built {len(rows)} rows, {sum(len(v) for v in rows.values())} titles")

        self.transition(Stage.VALIDATE)
        with self.tracer.span("VALIDATE"):
            report = ValidationAgent().run({"rows": rows, "tier": self.tier})
        self.state["validation_report"] = report.summary()
        if not report.passed:
            self.state["failed_gates"] = [r.gate for r in report.results if not r.passed]
            self.transition(Stage.HALT)
            print(report.summary())
            return self._final(success=False)
        self.log("all gates passed")

        self.transition(Stage.PUBLISH)
        from tools.mock_publish import publish, read_published

        # Read the currently-published layout BEFORE publish() overwrites it —
        # this is the "previous" side of CommsAgent's week-over-week diff
        # narrative (REFACTOR.md R5). None means there's nothing published yet.
        previous_layout = read_published()
        previous_rows = previous_layout.get("rows") if previous_layout else None
        self.state["previous_rows"] = previous_rows

        with self.tracer.span("PUBLISH"):
            pub = publish(
                layout={"week": self.week, "tier": self.tier, "region": self.region,
                        "rows": rows},
                dry_run=self.dry_run,
            )
        self.state["publish_result"] = pub

        self.transition(Stage.REPORT)
        with self.tracer.span("REPORT"):
            report_path = CommsAgent().run(
                {"week": self.week, "tier": self.tier, "region": self.region, "rows": rows,
                 "publish_status": pub.get("status"), "previous_rows": previous_rows}
            )
        self.state["report_path"] = report_path

        self.transition(Stage.DONE)
        return self._final(success=True)

    def _final(self, success: bool) -> dict[str, Any]:
        summary = {
            "success": success,
            "final_stage": self.stage.name,
            "week": self.week,
            "tier": self.tier,
            "region": self.region,
            "report_path": self.state.get("report_path"),
            "publish_result": self.state.get("publish_result", {}),
            "rows_published": len(self.state.get("rows", {})),
            "titles_total": sum(len(v) for v in self.state.get("rows", {}).values()),
        }
        if not success:
            summary["validation_report"] = self.state.get("validation_report", "")
            summary["failed_gates"] = self.state.get("failed_gates", [])
        summary["telemetry"] = self.tracer.summary()
        self.tracer.flush(f"obs/trace/run_{self.week}_{self.tier}.json")
        print("\n" + "=" * 55)
        print(f"PIPELINE {'✅ SUCCESS' if success else '❌ FAILED'}")
        print(json.dumps({k: v for k, v in summary.items() if k != "telemetry"}, indent=2))
        print(self.tracer.summary_text())
        print("=" * 55 + "\n")
        return summary


# --- CLI ------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="NexCurate weekly publishing pipeline")
    parser.add_argument("--week", default="2026-W28", help="ISO week e.g. 2026-W28")
    # Tier choices load from the KB (kb/domain/platform_tiers.md) via
    # PolicyLoader — adding a tier there is enough, no code change (REFACTOR.md
    # R3). PolicyLoader itself already warns + falls back non-strictly; this
    # try/except only matters under POLICY_STRICT=1 with a broken KB, where we
    # still want `--help`/argument parsing to work rather than hard-crash here
    # — the pipeline run itself will raise again, loudly, once CurationAgent /
    # ValidationAgent construct their own PolicyLoader downstream.
    try:
        tier_choices = PolicyLoader().tiers()
    except PolicyError as e:
        tier_choices = emergency_fallback_tiers()
        print(f"[orchestrator] WARNING: tier list unavailable from the KB ({e}); "
              f"falling back to {tier_choices}", file=sys.stderr)
    parser.add_argument("--tier", default="standard", choices=tier_choices)
    parser.add_argument("--region", default="NA", choices=["NA", "EU", "APAC"])
    parser.add_argument("--dry-run", action="store_true",
                        help="validate only, do not publish")
    args = parser.parse_args()

    orch = Orchestrator(
        week=args.week, tier=args.tier, region=args.region, dry_run=args.dry_run
    )
    result = orch.run()
    sys.exit(0 if result["success"] else 1)


if __name__ == "__main__":
    main()
