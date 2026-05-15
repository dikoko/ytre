"""Tests for parsing PRT (part) files."""
from pathlib import Path

YTREF_ROOT = Path(__file__).parent.parent.parent.parent / "refs"
AVATAR_IRD = YTREF_ROOT / "models" / "raw" / "Avatar.IRD"
PRT_PATH = AVATAR_IRD / "swap" / "male" / "male_hair_M0101.PRT"


def test_prt_parses_as_tmd():
    """PRT files are TMD format - verify parser works."""
    from src.parsers.tmd_parser import TMDParser

    parser = TMDParser()
    model = parser.parse(PRT_PATH)

    assert model is not None
    assert len(model.meshes) >= 1, "Part should have at least one mesh"


def test_prt_has_vertices():
    """Part mesh should have vertices."""
    from src.parsers.tmd_parser import TMDParser

    parser = TMDParser()
    model = parser.parse(PRT_PATH)

    mesh = model.meshes[0]
    assert len(mesh.vertices) > 0, "Part mesh should have vertices"


def test_prt_has_skin_weights():
    """Part mesh should have bone weights for skinning."""
    from src.parsers.tmd_parser import TMDParser

    parser = TMDParser()
    model = parser.parse(PRT_PATH)

    mesh = model.meshes[0]
    has_skinning = len(mesh.vertex_skinning) > 0
    assert has_skinning, "Part should have skinning data"
