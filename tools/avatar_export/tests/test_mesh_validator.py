"""Tests for mesh validator."""
import math
from pathlib import Path

YTREF_ROOT = Path(__file__).parent.parent.parent.parent / "refs"
AVATAR_IRD = YTREF_ROOT / "models" / "raw" / "Avatar.IRD"
TMD_PATH = AVATAR_IRD / "male.TMD"


def test_validate_vertex_count_passes_for_positive():
    from src.validators.mesh_validator import validate_vertex_count
    result = validate_vertex_count(100)
    assert result.valid is True


def test_validate_vertex_count_fails_for_zero():
    from src.validators.mesh_validator import validate_vertex_count
    result = validate_vertex_count(0)
    assert result.valid is False
    assert "zero" in result.message.lower() or "0" in result.message


def test_validate_no_nan_passes_for_valid_vertices():
    from src.validators.mesh_validator import validate_no_nan
    vertices = [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]
    result = validate_no_nan(vertices)
    assert result.valid is True


def test_validate_no_nan_fails_for_nan():
    from src.validators.mesh_validator import validate_no_nan
    vertices = [[1.0, float('nan'), 3.0], [4.0, 5.0, 6.0]]
    result = validate_no_nan(vertices)
    assert result.valid is False
    assert "nan" in result.message.lower()


def test_validate_no_nan_fails_for_inf():
    from src.validators.mesh_validator import validate_no_nan
    vertices = [[1.0, float('inf'), 3.0]]
    result = validate_no_nan(vertices)
    assert result.valid is False
    assert "inf" in result.message.lower()


def test_validate_bounds_passes_for_human_size():
    from src.validators.mesh_validator import validate_bounds
    # Human-sized model: ~1.8m tall, ~0.5m wide
    result = validate_bounds(min_bound=[-0.3, 0.0, -0.2], max_bound=[0.3, 1.8, 0.2])
    assert result.valid is True


def test_validate_bounds_fails_for_too_small():
    from src.validators.mesh_validator import validate_bounds
    # Tiny model: < 0.1m
    result = validate_bounds(min_bound=[0.0, 0.0, 0.0], max_bound=[0.01, 0.01, 0.01])
    assert result.valid is False
    assert "small" in result.message.lower()


def test_validate_bounds_fails_for_too_large():
    from src.validators.mesh_validator import validate_bounds
    # Giant model: > 5m
    result = validate_bounds(min_bound=[0.0, 0.0, 0.0], max_bound=[10.0, 10.0, 10.0])
    assert result.valid is False
    assert "large" in result.message.lower()


def test_validate_faces_passes_for_valid_indices():
    from src.validators.mesh_validator import validate_faces
    faces = [[0, 1, 2], [1, 2, 3]]
    result = validate_faces(faces, vertex_count=4)
    assert result.valid is True


def test_validate_faces_fails_for_out_of_range():
    from src.validators.mesh_validator import validate_faces
    faces = [[0, 1, 5]]  # Index 5 is out of range for 4 vertices
    result = validate_faces(faces, vertex_count=4)
    assert result.valid is False
    assert "out of range" in result.message.lower() or "invalid" in result.message.lower()


def test_validate_faces_fails_for_negative_index():
    from src.validators.mesh_validator import validate_faces
    faces = [[0, -1, 2]]
    result = validate_faces(faces, vertex_count=4)
    assert result.valid is False


def test_validate_mesh_passes_for_male_tmd():
    """Integration test: validate the actual male TMD mesh."""
    from src.validators.mesh_validator import validate_mesh
    from src.parsers.tmd_parser import TMDParser

    parser = TMDParser()
    model = parser.parse(TMD_PATH)

    result = validate_mesh(model)
    assert result.valid is True, f"Male TMD should pass validation: {result.message}"
