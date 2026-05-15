"""
Region Configuration

Defines body region mappings for splitting the base avatar mesh.
Each region can be independently hidden when a corresponding part is equipped.
"""

from enum import Enum


class BodyRegion(Enum):
    """Body regions for mesh splitting."""
    HEAD = "head"  # Face - always visible
    HAIR_SCALP = "hair_scalp"  # Inner scalp cap - stays visible with skin texture
    HAIR_STRANDS = "hair_strands"  # Outer hair strands - hidden by hair parts
    NECK = "neck"
    ARM_UPPER = "arm_upper"  # Shoulder to elbow
    FOREARM = "forearm"  # Elbow to wrist
    HAND = "hand"  # Wrist to fingertips
    TORSO = "torso"
    WAIST = "waist"
    LEG_UPPER = "leg_upper"
    LEG_LOWER = "leg_lower"
    FOOT = "foot"


# Material index for hair submesh in base TMD
# The base mesh has separate submeshes with different materials:
# 0=upper, 1=arm, 2=foot, 3=hand, 4=leg, 5=lower, 6=HAIR, 7=face
HAIR_MATERIAL_INDEX = 6


# Map bone names to body regions
# Bones starting with @ - patterns use startswith matching
BONE_TO_REGION: dict[str, BodyRegion] = {
    # Head region (always visible - base mesh is bald, hair parts add styled hair)
    "@Head": BodyRegion.HEAD,
    "@Hair01B": BodyRegion.HEAD,
    "@Hair02B": BodyRegion.HEAD,
    "@Hair01RF": BodyRegion.HEAD,
    "@Hair00RF": BodyRegion.HEAD,
    "@Hair01LF": BodyRegion.HEAD,
    "@Hair00LF": BodyRegion.HEAD,
    # Female hair physics bones
    "@Hair01LS": BodyRegion.HEAD,
    "@Hair00LS": BodyRegion.HEAD,
    "@Hair01RS": BodyRegion.HEAD,
    "@Hair00RS": BodyRegion.HEAD,

    # Neck region (covered by upper)
    "@Neck": BodyRegion.NECK,

    # Arm upper region (covered by upper)
    "@ClavicleL": BodyRegion.ARM_UPPER,
    "@ClavicleR": BodyRegion.ARM_UPPER,
    "@Arm1L": BodyRegion.ARM_UPPER,
    "@Arm1R": BodyRegion.ARM_UPPER,

    # Forearm region (elbow to wrist)
    "@Arm2L": BodyRegion.FOREARM,
    "@Arm2R": BodyRegion.FOREARM,

    # Hand region (wrist to fingertips - covered by hand parts)
    "@HandL": BodyRegion.HAND,
    "@HandR": BodyRegion.HAND,
    "@Finger1L": BodyRegion.HAND,
    "@Finger2L": BodyRegion.HAND,
    "@Finger3L": BodyRegion.HAND,
    "@Finger4L": BodyRegion.HAND,
    "@Finger1R": BodyRegion.HAND,
    "@Finger2R": BodyRegion.HAND,
    "@Finger3R": BodyRegion.HAND,
    "@Finger4R": BodyRegion.HAND,

    # Torso region (covered by upper)
    "@Spine1": BodyRegion.TORSO,
    "@Spine2": BodyRegion.TORSO,
    "@Spine3": BodyRegion.TORSO,
    # Female breast bones
    "@BreastR": BodyRegion.TORSO,
    "@Breast00R": BodyRegion.TORSO,
    "@BreastL": BodyRegion.TORSO,
    "@Breast00L": BodyRegion.TORSO,

    # Waist region (covered by lower) - includes pelvis and skirt bones
    "@Pelvis": BodyRegion.WAIST,
    "@Skirt01RF": BodyRegion.WAIST,
    "@Skirt02RF": BodyRegion.WAIST,
    "@Skirt03RF": BodyRegion.WAIST,
    "@Skirt00RF": BodyRegion.WAIST,
    "@Skirt01LB": BodyRegion.WAIST,
    "@Skirt02LB": BodyRegion.WAIST,
    "@Skirt03LB": BodyRegion.WAIST,
    "@Skirt00LB": BodyRegion.WAIST,
    "@Skirt01RB": BodyRegion.WAIST,
    "@Skirt02RB": BodyRegion.WAIST,
    "@Skirt03RB": BodyRegion.WAIST,
    "@Skirt00RB": BodyRegion.WAIST,
    "@Skirt01LF": BodyRegion.WAIST,
    "@Skirt02LF": BodyRegion.WAIST,
    "@Skirt03LF": BodyRegion.WAIST,
    "@Skirt00LF": BodyRegion.WAIST,

    # Leg upper region (covered by lower)
    "@Leg1L": BodyRegion.LEG_UPPER,
    "@Leg1R": BodyRegion.LEG_UPPER,

    # Leg lower region (covered by lower)
    "@Leg2L": BodyRegion.LEG_LOWER,
    "@Leg2R": BodyRegion.LEG_LOWER,

    # Foot region (covered by feet)
    "@FootL": BodyRegion.FOOT,
    "@FootR": BodyRegion.FOOT,
    "@ToeL": BodyRegion.FOOT,
    "@ToeR": BodyRegion.FOOT,
}

# Special bones that don't belong to body mesh (attachments)
NON_BODY_BONES = {"@Root", "@Sword"}

# Mapping from part slots to regions they hide when equipped (fallback only)
PART_SLOT_TO_HIDDEN_REGIONS: dict[str, list[BodyRegion]] = {
    "hair": [BodyRegion.HAIR_STRANDS],  # Only hide strands, scalp stays visible
    "upper": [BodyRegion.NECK, BodyRegion.ARM_UPPER, BodyRegion.TORSO],
    "lower": [BodyRegion.WAIST, BodyRegion.LEG_UPPER, BodyRegion.LEG_LOWER],
    "hands": [BodyRegion.HAND],  # Only hand, not forearm
    "feet": [BodyRegion.FOOT],
}

# Head center position for hair scalp/strands split (estimated from mesh analysis)
# Inner vertices (distance < threshold) = scalp cap, outer = hair strands
HAIR_HEAD_CENTER = (0.009, 1.500, -0.029)
HAIR_SCALP_DISTANCE_THRESHOLD = 0.18  # Vertices within this distance are scalp (covers Y up to ~1.67)


def get_bone_region(bone_name: str) -> BodyRegion | None:
    """
    Get the body region for a bone name.

    Args:
        bone_name: Bone name (e.g., "@Head", "@Arm1L")

    Returns:
        BodyRegion or None if bone is not mapped
    """
    bone_name = bone_name.strip()
    return BONE_TO_REGION.get(bone_name)


def _distance_from_head_center(pos: tuple[float, float, float]) -> float:
    """Calculate distance from vertex position to hair head center."""
    import math
    dx = pos[0] - HAIR_HEAD_CENTER[0]
    dy = pos[1] - HAIR_HEAD_CENTER[1]
    dz = pos[2] - HAIR_HEAD_CENTER[2]
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def get_vertex_region(
    bone_weights: list[tuple[int, float]],
    bone_names: list[str],
    material_index: int | None = None,
    vertex_position: tuple[float, float, float] | None = None,
) -> BodyRegion | None:
    """
    Classify a vertex by its dominant bone's region and material.

    Args:
        bone_weights: List of (bone_index, weight) tuples for the vertex
        bone_names: List of all bone names (indexed by bone_index)
        material_index: Material index from TMD submesh (6 = hair)
        vertex_position: Vertex world position (x, y, z) for hair scalp/strands split

    Returns:
        BodyRegion of the dominant bone, or None if unclassified
    """
    # Hair submesh is identified by material index, not bone
    # Split into scalp (inner) and strands (outer) based on distance from head center
    if material_index == HAIR_MATERIAL_INDEX:
        if vertex_position is not None:
            dist = _distance_from_head_center(vertex_position)
            if dist < HAIR_SCALP_DISTANCE_THRESHOLD:
                return BodyRegion.HAIR_SCALP
            else:
                return BodyRegion.HAIR_STRANDS
        # Fallback if no position provided - treat as strands
        return BodyRegion.HAIR_STRANDS

    if not bone_weights:
        return None

    # Find dominant bone (highest weight)
    dominant_bone_idx = max(bone_weights, key=lambda x: x[1])[0]

    if dominant_bone_idx < 0 or dominant_bone_idx >= len(bone_names):
        return None

    bone_name = bone_names[dominant_bone_idx].strip()

    # Skip non-body bones
    if bone_name in NON_BODY_BONES:
        return None

    region = get_bone_region(bone_name)

    return region
