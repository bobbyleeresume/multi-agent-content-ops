"""
models.py

Typed domain objects for the NexCurate pipeline — Title + Rating.

Malformed catalog data fails here, at construction, with a precise error —
not downstream at the validation gates. Gates still re-check serialized rows
as defense in depth (fixtures and external callers feed raw dicts).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Rating(str, Enum):
    """ESRB rating, normalized to its canonical code."""

    E = "E"
    E10 = "E10"
    T = "T"
    M = "M"
    AO = "AO"


# ESRB full names (lowercase, trimmed) -> canonical Rating. `normalize_rating`
# lowercases and strips the raw value before indexing into this map.
_ESRB_NAMES: dict[str, Rating] = {
    "everyone": Rating.E,
    "everyone 10+": Rating.E10,
    "teen": Rating.T,
    "mature": Rating.M,
    "mature 17+": Rating.M,
    "adults only": Rating.AO,
    "adults only 18+": Rating.AO,
}


def normalize_rating(raw: Rating | str) -> Rating:
    """Normalize a raw rating value to a canonical `Rating`.

    Accepts, in order:
      - a `Rating` instance — returned as-is (idempotent)
      - a code, case-insensitive (e.g. "e10", "t", "AO")
      - an ESRB full name, case-insensitive and whitespace-trimmed
        (e.g. "Everyone", "Mature 17+")

    Raises `ValueError` with a precise message for anything else.
    """
    if isinstance(raw, Rating):
        return raw
    if not isinstance(raw, str):
        raise ValueError(
            f"rating must be a str or Rating, got {type(raw).__name__}: {raw!r}"
        )
    candidate = raw.strip()
    for member in Rating:
        if candidate.upper() == member.value:
            return member
    mapped = _ESRB_NAMES.get(candidate.lower())
    if mapped is not None:
        return mapped
    raise ValueError(
        f"unrecognized rating {raw!r}: expected a code "
        f"({', '.join(m.value for m in Rating)}) or an ESRB name "
        f"({', '.join(sorted(_ESRB_NAMES))})"
    )


@dataclass(frozen=True)
class Title:
    """A single catalog title. Fields are validated in `__post_init__` so a
    malformed entry fails at construction, not downstream at the gates."""

    id: str
    title: str
    genre: str
    rating: Rating

    def __post_init__(self) -> None:
        for field_name in ("id", "title", "genre"):
            if not getattr(self, field_name):
                raise ValueError(f"Title.{field_name} must be a non-empty string")
        if not isinstance(self.rating, Rating):
            object.__setattr__(self, "rating", normalize_rating(self.rating))

    def to_dict(self) -> dict:
        """Serialize to the plain-dict shape the rest of the pipeline expects."""
        return {
            "id": self.id,
            "title": self.title,
            "genre": self.genre,
            "rating": self.rating.value,
        }
