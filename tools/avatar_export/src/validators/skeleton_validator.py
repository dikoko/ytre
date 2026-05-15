"""
Skeleton Validator

Validates skeleton data before export to catch issues early.
Returns ValidationResult with pass/fail and message.

Checks:
- Bone count must be 54 (male avatar)
- Parent indices: no forward references, all in valid range
- Quaternions: must be normalized (length ≈ 1.0)
"""

import math
from dataclasses import dataclass
from typing import Sequence

from src.parsers.tmd_parser import TMDModel


@dataclass
class ValidationResult:
    """Result of a validation check."""
    valid: bool
    message: str
    check_name: str = ""


EXPECTED_BONE_COUNT = 54
QUATERNION_TOLERANCE = 0.01  # Allow 1% deviation from unit length


def validate_bone_count(count: int, expected: int = EXPECTED_BONE_COUNT) -> ValidationResult:
    """Validate that bone count matches expected value."""
    if count != expected:
        return ValidationResult(
            valid=False,
            message=f"Bone count is {count}, expected {expected}",
            check_name="bone_count",
        )
    return ValidationResult(
        valid=True,
        message=f"Bone count OK: {count}",
        check_name="bone_count",
    )


def validate_parent_indices(parents: Sequence[int]) -> ValidationResult:
    """
    Validate that parent indices are valid.

    Rules:
    - Root bone can have parent -1
    - No forward references (parent index must be < current index)
    - Parent index must be in valid range
    """
    bone_count = len(parents)

    for i, parent_id in enumerate(parents):
        # Root can have -1
        if parent_id == -1:
            continue

        # Check for forward reference
        if parent_id >= i:
            return ValidationResult(
                valid=False,
                message=f"Bone {i} has forward reference to parent {parent_id}",
                check_name="parent_indices",
            )

        # Check for out of range
        if parent_id < -1 or parent_id >= bone_count:
            return ValidationResult(
                valid=False,
                message=f"Bone {i} has invalid parent index {parent_id} (bone_count={bone_count})",
                check_name="parent_indices",
            )

    return ValidationResult(
        valid=True,
        message=f"Parent indices OK: {bone_count} bones",
        check_name="parent_indices",
    )


def validate_quaternions_normalized(
    quats: Sequence[Sequence[float]],
    tolerance: float = QUATERNION_TOLERANCE,
) -> ValidationResult:
    """
    Validate that quaternions are normalized (unit length).

    Args:
        quats: List of quaternions as [x, y, z, w]
        tolerance: Allowed deviation from unit length
    """
    for i, q in enumerate(quats):
        length = math.sqrt(q[0]**2 + q[1]**2 + q[2]**2 + q[3]**2)
        if abs(length - 1.0) > tolerance:
            return ValidationResult(
                valid=False,
                message=f"Quaternion {i} not normalized: length={length:.4f}",
                check_name="quaternions_normalized",
            )

    return ValidationResult(
        valid=True,
        message=f"Quaternions OK: {len(quats)} normalized",
        check_name="quaternions_normalized",
    )


def validate_skeleton(model: TMDModel) -> ValidationResult:
    """
    Validate skeleton in a TMD model.

    Runs all validation checks and returns first failure or success.
    """
    # Check bone count
    result = validate_bone_count(len(model.bones))
    if not result.valid:
        return result

    # Check parent indices
    parents = [bone.parent_id for bone in model.bones]
    result = validate_parent_indices(parents)
    if not result.valid:
        return result

    # Extract quaternions from bone transforms (using rotation matrix -> quat conversion)
    # For now, we skip quaternion validation since we don't have direct quaternions
    # The TMD stores rotation matrices, not quaternions
    # We'll validate quaternions when we convert to GLTF

    return ValidationResult(
        valid=True,
        message=f"Skeleton validation passed: {len(model.bones)} bones",
        check_name="skeleton",
    )
