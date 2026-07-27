"""Tests for QQQ parser — map object placement data."""
from pathlib import Path

YTREF_ROOT = Path(__file__).parent.parent.parent.parent / "refs"
MAP_DIR = YTREF_ROOT / "models" / "raw" / "Terrain" / "Map.IRD"
SF001001_QQQ = MAP_DIR / "SF001001" / "SF001001.qqq"


def test_qqq_parser_reads_file():
    from src.parsers.qqq_parser import QQQParser
    data = QQQParser().parse(SF001001_QQQ)
    assert len(data.objects) == 857, f"Expected 857 objects, got {len(data.objects)}"


def test_qqq_portals():
    from src.parsers.qqq_parser import QQQParser
    data = QQQParser().parse(SF001001_QQQ)
    assert len(data.portals) > 0, "Expected at least 1 portal"


def test_qqq_tree_info():
    from src.parsers.qqq_parser import QQQParser
    data = QQQParser().parse(SF001001_QQQ)
    assert data.tree_info is not None
    cx, cz = data.tree_info.center
    assert 70 < cx < 80, f"Unexpected center X: {cx}"
    assert 70 < cz < 80, f"Unexpected center Z: {cz}"


def test_qqq_objects_have_valid_transforms():
    from src.parsers.qqq_parser import QQQParser
    data = QQQParser().parse(SF001001_QQQ)
    for obj in data.objects[:10]:
        assert len(obj.transform) == 16
        x, y, z = obj.transform[12], obj.transform[13], obj.transform[14]
        assert -50 < x < 200, f"Object {obj.unique_id} X={x} out of range"
        assert -50 < z < 200, f"Object {obj.unique_id} Z={z} out of range"


def test_qqq_objects_have_model_ids_in_range():
    from src.parsers.qqq_parser import QQQParser
    data = QQQParser().parse(SF001001_QQQ)
    max_id = max(obj.model_id for obj in data.objects)
    assert max_id < 200, f"Suspiciously high model_id: {max_id}"


def test_qqq_triggers():
    from src.parsers.qqq_parser import QQQParser
    data = QQQParser().parse(SF001001_QQQ)
    assert len(data.triggers) >= 0  # may be 0, just verify no crash


PORTAL_CENSUS = {
    "SF001001": 4, "SF001002": 4, "SF001003": 3, "SF001004": 1, "SF001005": 1,
    "SF001006": 4, "SF001007": 2, "SF001008": 1, "SF001010": 1, "SF002001": 7,
    "SF002002": 1, "SF002003": 2, "SF002004": 2, "SF002005": 1, "SF002006": 1,
    "SF002007": 2, "SF002008": 1, "SF002009": 3, "SF002010": 3, "SF002011": 1,
    "SF002013": 1, "FD008302": 1, "FD008303": 1, "FD013502": 1, "FD014302": 1,
}


def test_portal_fleet_census():
    from src.parsers.qqq_parser import QQQParser
    found = {}
    for d in sorted(MAP_DIR.iterdir()):
        qqq = d / f"{d.name}.qqq"
        if not qqq.is_file():
            continue
        n = len(QQQParser().parse(qqq).portals)
        if n:
            found[d.name] = n
    assert found == PORTAL_CENSUS


def test_portal_sf001001_details():
    from src.parsers.qqq_parser import QQQParser
    portals = QQQParser().parse(SF001001_QQQ).portals
    by_uid = {p.unique_id: p for p in portals}
    assert set(by_uid) == {904, 905, 906, 722}
    p = by_uid[904]
    x, y, z = p.transform[12], p.transform[13], p.transform[14]
    assert abs(x - 75.4) < 0.01 and abs(y) < 0.01 and abs(z - 106.5) < 0.01
    assert p.model_id == 78
