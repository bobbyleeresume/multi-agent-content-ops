"""
tests/test_models.py — typed domain boundary: Title dataclass, Rating enum,
ESRB normalization. Runs standalone or under pytest. Offline; no API keys.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import Rating, Title, normalize_rating  # noqa: E402
from tools.game_catalog import _from_csv  # noqa: E402


# --- normalize_rating -------------------------------------------------------------
def test_normalize_rating_idempotent_and_case_insensitive():
    assert normalize_rating("E10") == Rating.E10
    assert normalize_rating("e10") == Rating.E10
    assert normalize_rating("t") == Rating.T
    assert normalize_rating(normalize_rating("t")) == Rating.T
    assert normalize_rating(Rating.M) == Rating.M


def test_normalize_rating_full_names():
    assert normalize_rating("Everyone") == Rating.E
    assert normalize_rating("Everyone 10+") == Rating.E10
    assert normalize_rating("Teen") == Rating.T
    assert normalize_rating("Mature") == Rating.M
    assert normalize_rating("Adults Only") == Rating.AO


def test_normalize_rating_unknown_raises():
    try:
        normalize_rating("Kids")
        assert False, "expected ValueError for an unrecognized rating"
    except ValueError:
        pass


# --- Title -------------------------------------------------------------------------
def test_title_to_dict_normalizes_full_name_rating():
    t = Title(id="g1", title="Neon Vanguard", genre="action", rating="Mature")
    assert t.rating == Rating.M
    assert t.to_dict() == {
        "id": "g1", "title": "Neon Vanguard", "genre": "action", "rating": "M",
    }


def test_title_empty_field_raises():
    base = {"id": "g1", "title": "Neon Vanguard", "genre": "action", "rating": "E"}
    for field_name in ("id", "title", "genre"):
        kwargs = dict(base, **{field_name: ""})
        try:
            Title(**kwargs)
            assert False, f"expected ValueError for empty {field_name}"
        except ValueError:
            pass


def test_title_is_frozen():
    t = Title(id="g1", title="Neon Vanguard", genre="action", rating="E")
    try:
        t.title = "Renamed"
        assert False, "expected an exception assigning to a frozen dataclass"
    except AttributeError:
        pass


# --- game_catalog boundary ----------------------------------------------------------
def test_from_csv_rows_have_valid_codes():
    games = _from_csv()
    assert games, "expected the synthetic CSV to yield at least one game"
    assert all(g["rating"] in {r.value for r in Rating} for g in games)


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = failed = 0
    for t in tests:
        try:
            t()
            print(f"✅ {t.__name__}")
            passed += 1
        except Exception as e:  # noqa: BLE001
            print(f"❌ {t.__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
