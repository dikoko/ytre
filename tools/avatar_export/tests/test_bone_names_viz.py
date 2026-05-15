"""Tests for bone names visualizer."""
import json
from pathlib import Path
import tempfile

YTREF_ROOT = Path(__file__).parent.parent.parent.parent / "refs"
AVATAR_IRD = YTREF_ROOT / "models" / "raw" / "Avatar.IRD"
TMD_PATH = AVATAR_IRD / "male.TMD"


def test_bone_names_creates_json():
    """Test that bone names visualizer creates a JSON file."""
    from src.debug.bone_names_viz import create_bone_names_json
    from src.parsers.tmd_parser import TMDParser

    parser = TMDParser()
    model = parser.parse(TMD_PATH)

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "bone_names.json"
        create_bone_names_json(model, output_path)

        assert output_path.exists(), "JSON file should be created"


def test_bone_names_has_54_entries():
    """Test that JSON has 54 bone entries."""
    from src.debug.bone_names_viz import create_bone_names_json
    from src.parsers.tmd_parser import TMDParser

    parser = TMDParser()
    model = parser.parse(TMD_PATH)

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "bone_names.json"
        create_bone_names_json(model, output_path)

        with open(output_path) as f:
            data = json.load(f)

        assert len(data["bones"]) == 54, f"Should have 54 bones, got {len(data['bones'])}"


def test_bone_names_contains_required_fields():
    """Test that each bone entry has name and position."""
    from src.debug.bone_names_viz import create_bone_names_json
    from src.parsers.tmd_parser import TMDParser

    parser = TMDParser()
    model = parser.parse(TMD_PATH)

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "bone_names.json"
        create_bone_names_json(model, output_path)

        with open(output_path) as f:
            data = json.load(f)

        for bone in data["bones"]:
            assert "name" in bone, "Bone should have name"
            assert "position" in bone, "Bone should have position"
            assert len(bone["position"]) == 3, "Position should be [x, y, z]"


def test_bone_names_contains_spine1():
    """Test that Spine1 bone is included."""
    from src.debug.bone_names_viz import create_bone_names_json
    from src.parsers.tmd_parser import TMDParser

    parser = TMDParser()
    model = parser.parse(TMD_PATH)

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "bone_names.json"
        create_bone_names_json(model, output_path)

        with open(output_path) as f:
            data = json.load(f)

        bone_names = {b["name"] for b in data["bones"]}
        assert "@Spine1" in bone_names
