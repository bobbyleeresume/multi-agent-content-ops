"""
tools/mock_publish.py

MCP-style publish tool. Writes the validated layout to a mock CMS target and
appends to an audit log. `dry_run=True` writes nothing — a safe-by-default
preview mode. Swap the body of publish() for a real CMS API call to go live;
the agent contract stays unchanged.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MOCK_DIR = Path(__file__).resolve().parent.parent / "mock"
PUBLISH_TARGET = MOCK_DIR / "published_layout.json"
PUBLISH_LOG = MOCK_DIR / "publish_log.jsonl"


def publish(layout: dict[str, Any], dry_run: bool = False) -> dict[str, Any]:
    timestamp = datetime.now(timezone.utc).isoformat()
    row_count = len(layout.get("rows", {}))
    total_titles = sum(len(v) for v in layout.get("rows", {}).values())

    if dry_run:
        return {
            "status": "dry_run",
            "message": "Validation passed. Dry-run — nothing written.",
            "payload_preview": {k: v for k, v in layout.items() if k != "rows"},
            "week": layout.get("week"),
            "tier": layout.get("tier"),
            "region": layout.get("region"),
            "published_at": timestamp,
            "row_count": row_count,
            "total_titles": total_titles,
        }

    MOCK_DIR.mkdir(exist_ok=True)
    with open(PUBLISH_TARGET, "w", encoding="utf-8") as f:
        json.dump(layout, f, indent=2, ensure_ascii=False)

    entry = {
        "status": "published",
        "path": str(PUBLISH_TARGET),
        "week": layout.get("week"),
        "tier": layout.get("tier"),
        "region": layout.get("region"),
        "row_count": row_count,
        "total_titles": total_titles,
        "published_at": timestamp,
    }
    with open(PUBLISH_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def read_published() -> dict[str, Any] | None:
    """Read the current published layout from the mock CMS."""
    if not PUBLISH_TARGET.exists():
        return None
    return json.loads(PUBLISH_TARGET.read_text(encoding="utf-8"))


if __name__ == "__main__":
    # Smoke test
    dummy = {
        "week": "2026-W28", "tier": "standard", "region": "NA",
        "rows": {"Top Picks": [{"id": "g1", "title": "Test Game"}]},
    }
    print(json.dumps(publish(dummy, dry_run=True), indent=2))
