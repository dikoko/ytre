"""Tests for TMD parser."""
from pathlib import Path

YTREF_ROOT = Path(__file__).parent.parent.parent.parent / "refs"
AVATAR_IRD = YTREF_ROOT / "models" / "raw" / "Avatar.IRD"
TMD_PATH = AVATAR_IRD / "male.TMD"


def test_parse_male_tmd_returns_model():
    from src.parsers.tmd_parser import TMDParser
    parser = TMDParser()
    model = parser.parse(TMD_PATH)
    assert model is not None


def test_male_tmd_has_expected_vertex_count():
    from src.parsers.tmd_parser import TMDParser
    parser = TMDParser()
    model = parser.parse(TMD_PATH)
    total_vertices = sum(len(m.vertices) for m in model.meshes)
    assert 1000 <= total_vertices <= 1500


def test_male_tmd_has_54_bones():
    from src.parsers.tmd_parser import TMDParser
    parser = TMDParser()
    model = parser.parse(TMD_PATH)
    assert len(model.bones) == 54
