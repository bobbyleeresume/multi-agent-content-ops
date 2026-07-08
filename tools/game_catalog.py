"""
tools/game_catalog.py

Game catalog source. Prefers the RAWG public API when RAWG_API_KEY is set;
otherwise falls back to the offline synthetic CSV so the pipeline runs anywhere
(CI, planes, demos) with zero external dependencies.
"""
from __future__ import annotations

import csv
import os
from pathlib import Path

DATA_CSV = Path(__file__).resolve().parent.parent / "data" / "synthetic_games.csv"


def _from_csv() -> list[dict]:
    games: list[dict] = []
    with open(DATA_CSV, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            games.append({
                "id": r["id"],
                "title": r["title"],
                "genres": [g.strip() for g in r["genres"].split(";") if g.strip()],
                "rating": r["rating"],
            })
    return games


def _from_rawg(api_key: str, page_size: int = 40) -> list[dict]:
    import requests  # imported lazily so CSV path needs no deps

    resp = requests.get(
        "https://api.rawg.io/api/games",
        params={"key": api_key, "page_size": page_size, "ordering": "-added"},
        timeout=15,
    )
    resp.raise_for_status()
    games: list[dict] = []
    for g in resp.json().get("results", []):
        games.append({
            "id": f"rawg-{g['id']}",
            "title": g["name"],
            "genres": [x["name"] for x in g.get("genres", [])],
            "rating": (g.get("esrb_rating") or {}).get("name", "E") if g.get("esrb_rating") else "E",
        })
    return games


def fetch_games() -> list[dict]:
    api_key = os.environ.get("RAWG_API_KEY")
    if api_key:
        try:
            games = _from_rawg(api_key)
            if games:
                return games
        except Exception as e:  # noqa: BLE001 — any failure → offline fallback
            print(f"[game_catalog] RAWG unavailable ({e}); using synthetic CSV")
    return _from_csv()
