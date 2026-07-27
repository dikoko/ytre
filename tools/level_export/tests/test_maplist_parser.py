"""Tests for maplist parser — map code → Korean display name table."""
from pathlib import Path

YTREF_ROOT = Path(__file__).parent.parent.parent.parent / "refs"
MAPLIST = YTREF_ROOT / "models" / "raw" / "Terrain" / "Map.IRD" / "maplist.lst"


def test_maplist_record_count():
    from src.parsers.maplist_parser import parse_maplist
    entries = parse_maplist(MAPLIST)
    assert len(entries) == 403


def test_maplist_sf001001():
    from src.parsers.maplist_parser import parse_maplist
    entries = parse_maplist(MAPLIST)
    e = next(x for x in entries if x.code == "SF001001")
    assert e.name_ko == "에스티바 운동장"
    assert e.map_id > 0


def test_maplist_ids_unique():
    from src.parsers.maplist_parser import parse_maplist
    entries = parse_maplist(MAPLIST)
    ids = [e.map_id for e in entries]
    assert len(ids) == len(set(ids))


def test_maplist_codes_ascii_prefixes():
    from src.parsers.maplist_parser import parse_maplist
    entries = parse_maplist(MAPLIST)
    prefixes = {e.code[:2] for e in entries}
    assert prefixes <= {"SF", "FD", "LW"}
