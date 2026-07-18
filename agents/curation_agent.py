"""
agents/curation_agent.py

CurationAgent — fetches games and groups them into the weekly row set.
Reads the row set (row name, genre, target count) from the KB via
`policy.PolicyLoader` — a missing/unparseable KB warns loudly (or raises
under strict mode) rather than silently falling back (REFACTOR.md R3).
"""
from __future__ import annotations

from agents.base import BaseAgent
from models import Title
from policy import PolicyLoader
from tools.game_catalog import fetch_games


class CurationAgent(BaseAgent):
    name = "CurationAgent"

    def run(self, context: dict) -> dict[str, list[dict]]:
        """Build rows. Each pick is constructed as a `Title` (construction-time
        validation); the return type stays `dict[str, list[dict]]` — the
        downstream contract (gates, comms) is unchanged."""
        catalog = fetch_games()
        rows: dict[str, list[dict]] = {}
        used: set = set()
        for row_name, genre, target in PolicyLoader().row_set():
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
