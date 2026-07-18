"""
agents/curation_agent.py

CurationAgent — fetches games and groups them into the weekly row set.
Reads the row set and target counts from the KB (code defaults as a silent
fallback — being made loud in REFACTOR.md R3).
"""
from __future__ import annotations

import re

from agents.base import BaseAgent
from models import Title
from tools.game_catalog import fetch_games


class CurationAgent(BaseAgent):
    name = "CurationAgent"

    def _row_set(self) -> list[tuple[str, str, int]]:
        """Parse (row_name, genre, target_count) from kb/domain/row_rules.md."""
        text = self.read_kb("domain/row_rules.md")
        rows: list[tuple[str, str, int]] = []
        for line in text.splitlines():
            m = re.match(r"\|\s*([^|]+?)\s*\|\s*([a-zA-Z]+)\s*\|\s*(\d+)\s*\|", line)
            if m and m.group(2).lower() not in ("genre",):
                rows.append((m.group(1).strip(), m.group(2).strip().lower(), int(m.group(3))))
        return rows or [
            ("Top Picks", "action", 8),
            ("Adventure Zone", "adventure", 6),
            ("Indie Spotlight", "indie", 6),
            ("Family Friendly", "family", 5),
            ("Strategy Vault", "strategy", 5),
        ]

    def run(self, context: dict) -> dict[str, list[dict]]:
        """Build rows. Each pick is constructed as a `Title` (construction-time
        validation); the return type stays `dict[str, list[dict]]` — the
        downstream contract (gates, comms) is unchanged."""
        catalog = fetch_games()
        rows: dict[str, list[dict]] = {}
        used: set = set()
        for row_name, genre, target in self._row_set():
            picks = [
                g for g in catalog
                if genre in [x.lower() for x in g.get("genres", [])] and g["id"] not in used
            ][:target]
            for g in picks:
                used.add(g["id"])
            titles: list[dict] = []
            for g in picks:
                try:
                    title = Title(id=g["id"], title=g["title"], genre=genre, rating=g["rating"])
                except ValueError as e:
                    print(f"[{self.name}] skipped '{g.get('title', g.get('id', '?'))}': {e}")
                    continue
                titles.append(title.to_dict())
            rows[row_name] = titles
        return rows
