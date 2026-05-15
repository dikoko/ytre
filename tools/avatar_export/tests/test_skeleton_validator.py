"""Tests for skeleton validator."""
from pathlib import Path

YTREF_ROOT = Path(__file__).parent.parent.parent.parent / "refs"
AVATAR_IRD = YTREF_ROOT / "models" / "raw" / "Avatar.IRD"
TMD_PATH = AVATAR_IRD / "male.TMD"


def test_validate_bone_count_passes_for_54():
    from src.validators.skeleton_validator import validate_bone_count
    result = validate_bone_count(54)
    assert result.valid is True


def test_validate_bone_count_fails_for_wrong_count():
    from src.validators.skeleton_validator import validate_bone_count
    result = validate_bone_count(50)
    assert result.valid is False
    assert "54" in result.message


def test_validate_parent_indices_passes_for_valid():
    from src.validators.skeleton_validator import validate_parent_indices
    # Root has parent -1, others have valid parents
    parents = [-1, 0, 1, 2, 3]
    result = validate_parent_indices(parents)
    assert result.valid is True


def test_validate_parent_indices_fails_for_forward_reference():
    from src.validators.skeleton_validator import validate_parent_indices
    # Bone 1 references bone 3 which comes later (forward reference)
    parents = [-1, 3, 0, 1]
    result = validate_parent_indices(parents)
    assert result.valid is False
    assert "forward" in result.message.lower()


def test_validate_parent_indices_fails_for_out_of_range():
    from src.validators.skeleton_validator import validate_parent_indices
    # Bone 2 references bone 10 which doesn't exist
    parents = [-1, 0, 10]
    result = validate_parent_indices(parents)
    assert result.valid is False


def test_validate_quaternions_passes_for_normalized():
    from src.validators.skeleton_validator import validate_quaternions_normalized
    # Unit quaternions: [x, y, z, w]
    quats = [
        [0.0, 0.0, 0.0, 1.0],
        [0.5, 0.5, 0.5, 0.5],  # sqrt(4*0.25) = 1.0
    ]
    result = validate_quaternions_normalized(quats)
    assert result.valid is True


def test_validate_quaternions_fails_for_unnormalized():
    from src.validators.skeleton_validator import validate_quaternions_normalized
    quats = [
        [0.0, 0.0, 0.0, 2.0],  # Length = 2.0
    ]
    result = validate_quaternions_normalized(quats)
    assert result.valid is False
    assert "normalized" in result.message.lower()


def test_validate_skeleton_passes_for_male_tmd():
    """Integration test: validate the actual male TMD skeleton."""
    from src.validators.skeleton_validator import validate_skeleton
    from src.parsers.tmd_parser import TMDParser

    parser = TMDParser()
    model = parser.parse(TMD_PATH)

    result = validate_skeleton(model)
    assert result.valid is True, f"Male TMD skeleton should pass validation: {result.message}"
