#!/usr/bin/env python3
"""
Generate parts metadata JSON for Godot.

Analyzes PRT files to determine which body regions each part covers,
then outputs a JSON file with hides_regions for each part.

Usage:
    uv run python scripts/14_generate_metadata.py
    uv run python scripts/14_generate_metadata.py --gender female
"""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.parsers.tmd_parser import TMDParser
from src.parsers.mlib_parser import MLIBParser
from src.parsers.swp_parser import SWPParser
from src.exporters.region_config import BodyRegion, get_vertex_region

# Configuration
YTREF_ROOT = Path(__file__).parent.parent.parent.parent / "refs"
AVATAR_IRD = YTREF_ROOT / "models" / "raw" / "Avatar.IRD"
CLIENT_DIR = Path(__file__).parent.parent.parent.parent / "ytavatar" / "client"

# Manual hides_regions overrides from visual QA (male)
MALE_HIDES_REGION_OVERRIDES: dict[str, list[str]] = {
    # Upper parts with long sleeves that fully cover forearm
    "male_upper_M0002": ["forearm"],
    "male_upper_M0014": ["forearm"],
    "male_upper_M0022": ["forearm"],
    "male_upper_M1002": ["forearm"],
    "male_upper_M1014": ["forearm"],
    "male_upper_M1017": ["forearm"],
    "male_upper_M1021": ["forearm"],
    # Lower parts with long pants that fully cover lower leg
    "male_lower_M0018": ["leg_lower"],
    "male_lower_M0023": ["leg_lower"],
    # Hand/glove parts that extend up the forearm
    "male_hand_M1019": ["forearm"],
    "male_hand_M1020": ["forearm"],
    "male_hand_M1027": ["forearm"],
    "male_hand_M9001": ["forearm"],
}

# Female overrides - empty initially, populate after visual QA
FEMALE_HIDES_REGION_OVERRIDES: dict[str, list[str]] = {}

# All male PRT parts to analyze (matching 10_export_parts.py)
MALE_PARTS_TO_ANALYZE = [
    # Hair (27)
    "male_hair_M0101", "male_hair_M0102", "male_hair_M0103",
    "male_hair_M0201", "male_hair_M0202", "male_hair_M0203",
    "male_hair_M0301", "male_hair_M0302", "male_hair_M0303",
    "male_hair_M0401", "male_hair_M0402", "male_hair_M0403",
    "male_hair_M0501", "male_hair_M0502", "male_hair_M0503",
    "male_hair_M0601", "male_hair_M0602", "male_hair_M0603",
    "male_hair_M0701", "male_hair_M0702", "male_hair_M0703",
    "male_hair_M0801", "male_hair_M0802", "male_hair_M0803",
    "male_hair_M0901", "male_hair_M0902", "male_hair_M0903",
    # Upper (38)
    "male_upper_M0001", "male_upper_M0002", "male_upper_M0003", "male_upper_M0004",
    "male_upper_M0008", "male_upper_M0009", "male_upper_M0011", "male_upper_M0012",
    "male_upper_M0013", "male_upper_M0014", "male_upper_M0016", "male_upper_M0017",
    "male_upper_M0018", "male_upper_M0019", "male_upper_M0022", "male_upper_M0023",
    "male_upper_M0024", "male_upper_M0025", "male_upper_M0026", "male_upper_M0031",
    "male_upper_M0032", "male_upper_M1001", "male_upper_M1002", "male_upper_M1009",
    "male_upper_M1011", "male_upper_M1012", "male_upper_M1013", "male_upper_M1014",
    "male_upper_M1016", "male_upper_M1017", "male_upper_M1018", "male_upper_M1021",
    "male_upper_M1024", "male_upper_M1026", "male_upper_M1029", "male_upper_M1031",
    "male_upper_M1032", "male_upper_M9002",
    # Lower (33)
    "male_lower_M0001", "male_lower_M0002", "male_lower_M0003", "male_lower_M0004",
    "male_lower_M0008", "male_lower_M0009", "male_lower_M0011", "male_lower_M0012",
    "male_lower_M0014", "male_lower_M0016", "male_lower_M0018", "male_lower_M0019",
    "male_lower_M0022", "male_lower_M0023", "male_lower_M0024", "male_lower_M0025",
    "male_lower_M0026", "male_lower_M0031", "male_lower_M0032", "male_lower_M1001",
    "male_lower_M1002", "male_lower_M1009", "male_lower_M1011", "male_lower_M1012",
    "male_lower_M1014", "male_lower_M1016", "male_lower_M1018", "male_lower_M1024",
    "male_lower_M1026", "male_lower_M1029", "male_lower_M1031", "male_lower_M1032",
    "male_lower_M9002",
    # Hand (13)
    "male_hand_M0004", "male_hand_M0019", "male_hand_M0022", "male_hand_M0025",
    "male_hand_M0032", "male_hand_M1004", "male_hand_M1005", "male_hand_M1019",
    "male_hand_M1020", "male_hand_M1026", "male_hand_M1027", "male_hand_M1029",
    "male_hand_M9001",
    # Foot (42)
    "male_foot_GMM0001",
    "male_foot_M0001", "male_foot_M0002", "male_foot_M0003", "male_foot_M0004",
    "male_foot_M0005", "male_foot_M0006", "male_foot_M0007", "male_foot_M0008",
    "male_foot_M0009", "male_foot_M0014", "male_foot_M0018", "male_foot_M0019",
    "male_foot_M0022", "male_foot_M0023", "male_foot_M0024", "male_foot_M0025",
    "male_foot_M0026", "male_foot_M0031", "male_foot_M0032", "male_foot_M1001",
    "male_foot_M1002", "male_foot_M1003", "male_foot_M1004", "male_foot_M1005",
    "male_foot_M1006", "male_foot_M1007", "male_foot_M1009", "male_foot_M1014",
    "male_foot_M1018", "male_foot_M1019", "male_foot_M1020", "male_foot_M1023",
    "male_foot_M1024", "male_foot_M1025", "male_foot_M1026", "male_foot_M1027",
    "male_foot_M1029", "male_foot_M1031", "male_foot_M1032", "male_foot_M9001",
    "male_foot_M9002",
    # Special (21)
    "male_special_GMM0001",
    "male_special_M0005", "male_special_M0006", "male_special_M0007",
    "male_special_M0010", "male_special_M0015", "male_special_M0021",
    "male_special_M1003", "male_special_M1004", "male_special_M1005",
    "male_special_M1006", "male_special_M1007", "male_special_M1010",
    "male_special_M1015", "male_special_M1019", "male_special_M1020",
    "male_special_M1023", "male_special_M1025", "male_special_M1027",
    "male_special_M9001", "male_special_M9004",
    # Glorb (26)
    "male_glorb_A0001", "male_glorb_A0002", "male_glorb_A0003",
    "male_glorb_A0005", "male_glorb_A0007", "male_glorb_A0008",
    "male_glorb_A0009", "male_glorb_A0010", "male_glorb_A0011",
    "male_glorb_A0013", "male_glorb_A0014", "male_glorb_A0015",
    "male_glorb_A0016", "male_glorb_A0019", "male_glorb_A0021",
    "male_glorb_A1001", "male_glorb_A1002", "male_glorb_A1003",
    "male_glorb_A1005", "male_glorb_A1007", "male_glorb_A1009",
    "male_glorb_A1013", "male_glorb_A1014", "male_glorb_A1015",
    "male_glorb_A1019", "male_glorb_A1021",
]

# All female PRT parts to analyze (matching 10_export_parts.py)
FEMALE_PARTS_TO_ANALYZE = [
    # Hair (27)
    "female_hair_F0101", "female_hair_F0102", "female_hair_F0103",
    "female_hair_F0201", "female_hair_F0202", "female_hair_F0203",
    "female_hair_F0301", "female_hair_F0302", "female_hair_F0303",
    "female_hair_F0401", "female_hair_F0402", "female_hair_F0403",
    "female_hair_F0501", "female_hair_F0502", "female_hair_F0503",
    "female_hair_F0601", "female_hair_F0602", "female_hair_F0603",
    "female_hair_F0701", "female_hair_F0702", "female_hair_F0703",
    "female_hair_F0801", "female_hair_F0802", "female_hair_F0803",
    "female_hair_F0901", "female_hair_F0902", "female_hair_F0903",
    # Upper (29)
    "female_upper_F0001", "female_upper_F0002", "female_upper_F0003",
    "female_upper_F0008", "female_upper_F0009", "female_upper_F0011",
    "female_upper_F0012", "female_upper_F0013", "female_upper_F0016",
    "female_upper_F0018", "female_upper_F0019", "female_upper_F0023",
    "female_upper_F0025", "female_upper_F0026", "female_upper_F0031",
    "female_upper_F0032", "female_upper_F1002", "female_upper_F1009",
    "female_upper_F1012", "female_upper_F1013", "female_upper_F1014",
    "female_upper_F1016", "female_upper_F1018", "female_upper_F1021",
    "female_upper_F1026", "female_upper_F1029", "female_upper_F1031",
    "female_upper_F1032", "female_upper_F9002",
    # Lower (27)
    "female_lower_F0001", "female_lower_F0002", "female_lower_F0003",
    "female_lower_F0008", "female_lower_F0009", "female_lower_F0011",
    "female_lower_F0012", "female_lower_F0016", "female_lower_F0018",
    "female_lower_F0019", "female_lower_F0023", "female_lower_F0025",
    "female_lower_F0026", "female_lower_F0031", "female_lower_F0032",
    "female_lower_F1002", "female_lower_F1009", "female_lower_F1012",
    "female_lower_F1014", "female_lower_F1016", "female_lower_F1017",
    "female_lower_F1018", "female_lower_F1026", "female_lower_F1029",
    "female_lower_F1031", "female_lower_F1032", "female_lower_F9002",
    # Hand (14)
    "female_hand_F0004", "female_hand_F0019", "female_hand_F0022",
    "female_hand_F0023", "female_hand_F0032", "female_hand_F1004",
    "female_hand_F1005", "female_hand_F1019", "female_hand_F1020",
    "female_hand_F1025", "female_hand_F1026", "female_hand_F1027",
    "female_hand_F1029", "female_hand_F9001",
    # Foot (42)
    "female_foot_GMF0001",
    "female_foot_F0001", "female_foot_F0002", "female_foot_F0003",
    "female_foot_F0004", "female_foot_F0005", "female_foot_F0006",
    "female_foot_F0007", "female_foot_F0008", "female_foot_F0009",
    "female_foot_F0014", "female_foot_F0018", "female_foot_F0019",
    "female_foot_F0022", "female_foot_F0023", "female_foot_F0024",
    "female_foot_F0025", "female_foot_F0026", "female_foot_F0031",
    "female_foot_F0032", "female_foot_F1001", "female_foot_F1002",
    "female_foot_F1003", "female_foot_F1004", "female_foot_F1005",
    "female_foot_F1006", "female_foot_F1007", "female_foot_F1009",
    "female_foot_F1014", "female_foot_F1018", "female_foot_F1019",
    "female_foot_F1020", "female_foot_F1023", "female_foot_F1024",
    "female_foot_F1025", "female_foot_F1026", "female_foot_F1027",
    "female_foot_F1029", "female_foot_F1031", "female_foot_F1032",
    "female_foot_F9001", "female_foot_F9002",
    # Special (29)
    "female_special_GMF0001",
    "female_special_F0004", "female_special_F0005", "female_special_F0006",
    "female_special_F0007", "female_special_F0010", "female_special_F0014",
    "female_special_F0015", "female_special_F0017", "female_special_F0021",
    "female_special_F0022", "female_special_F0024", "female_special_F1001",
    "female_special_F1003", "female_special_F1004", "female_special_F1005",
    "female_special_F1006", "female_special_F1007", "female_special_F1010",
    "female_special_F1011", "female_special_F1015", "female_special_F1019",
    "female_special_F1020", "female_special_F1023", "female_special_F1024",
    "female_special_F1025", "female_special_F1027", "female_special_F9001",
    "female_special_F9004",
    # Glorb (26)
    "female_glorb_A0001", "female_glorb_A0002", "female_glorb_A0003",
    "female_glorb_A0005", "female_glorb_A0007", "female_glorb_A0008",
    "female_glorb_A0009", "female_glorb_A0010", "female_glorb_A0011",
    "female_glorb_A0013", "female_glorb_A0014", "female_glorb_A0015",
    "female_glorb_A0016", "female_glorb_A0019", "female_glorb_A0021",
    "female_glorb_A1001", "female_glorb_A1002", "female_glorb_A1003",
    "female_glorb_A1005", "female_glorb_A1007", "female_glorb_A1009",
    "female_glorb_A1013", "female_glorb_A1014", "female_glorb_A1015",
    "female_glorb_A1019", "female_glorb_A1021",
]

# Threshold: if a part covers >20% of a region's typical vertex count, it hides that region
REGION_THRESHOLD = 0.20


def get_config(gender: str):
    """Get metadata generation config for the given gender."""
    if gender == "male":
        return {
            "prt_dir": AVATAR_IRD / "swap" / "male",
            "base_tmd": AVATAR_IRD / "male.TMD",
            "mlib": AVATAR_IRD / "motion" / "male" / "male.mlib",
            "swp": AVATAR_IRD / "male.swp",
            "output": CLIENT_DIR / "assets" / "avatars" / "parts" / "parts_metadata.json",
            "parts": MALE_PARTS_TO_ANALYZE,
            "overrides": MALE_HIDES_REGION_OVERRIDES,
        }
    else:
        return {
            "prt_dir": AVATAR_IRD / "swap" / "female",
            "base_tmd": AVATAR_IRD / "female.TMD",
            "mlib": AVATAR_IRD / "motion" / "female" / "female.mlib",
            "swp": AVATAR_IRD / "female.swp",
            "output": CLIENT_DIR / "assets" / "avatars" / "parts" / "parts_metadata_female.json",
            "parts": FEMALE_PARTS_TO_ANALYZE,
            "overrides": FEMALE_HIDES_REGION_OVERRIDES,
        }


def get_part_type(part_name: str) -> str:
    """Extract part type from name."""
    if "_hair_" in part_name:
        return "hair"
    elif "_upper_" in part_name:
        return "upper"
    elif "_lower_" in part_name:
        return "lower"
    elif "_hand_" in part_name:
        return "hands"
    elif "_foot_" in part_name:
        return "feet"
    elif "_special_" in part_name:
        return "special"
    elif "_glorb_" in part_name:
        return "glorb"
    return "unknown"


def analyze_part(
    part_name: str,
    tmd_parser: TMDParser,
    mlib_to_tmd: dict[int, int],
    bone_names: list[str],
    swp_data: dict[str, list[int]],
    scalp_upper_vertices: list[int],
    source_prt_dir: Path = None,
    hides_overrides: dict[str, list[str]] = None,
) -> dict:
    """Analyze a single part and return its metadata."""
    prt_path = source_prt_dir / f"{part_name}.PRT"
    if not prt_path.exists():
        return None

    model = tmd_parser.parse(prt_path)
    mesh = model.meshes[0]
    part_type = get_part_type(part_name)

    # Count vertices per region
    region_counts: dict[str, int] = {}
    for v_idx in range(len(mesh.vertices)):
        bone_weights = mesh.vertex_skinning.get(v_idx, [])
        tmd_bone_weights = []
        for mlib_bone_idx, weight in bone_weights:
            tmd_bone_idx = mlib_to_tmd.get(mlib_bone_idx, -1)
            if tmd_bone_idx >= 0:
                tmd_bone_weights.append((tmd_bone_idx, weight))

        region = get_vertex_region(tmd_bone_weights, bone_names)
        if region:
            region_name = region.value
            region_counts[region_name] = region_counts.get(region_name, 0) + 1

    # Determine which regions to hide based on part type
    # Each part type should only hide regions relevant to its body area
    if part_type == "hands":
        hides_regions = ["hand"]
    elif part_type == "hair":
        hides_regions = ["hair_strands"]
    elif part_type == "upper":
        # Upper parts can hide: neck, arm_upper, torso (NOT forearm - that's for hand/glove parts)
        # Forearm excluded because upper parts with sleeve-edge vertices in the forearm region
        # would cause the entire arm base mesh to disappear (requires both arm_upper+forearm)
        allowed_regions = {"neck", "arm_upper", "torso"}
        hides_regions = [r for r, c in region_counts.items() if r in allowed_regions and c >= 5]
    elif part_type == "lower":
        # Lower parts can hide: waist, leg_upper, torso (NOT leg_lower - that's for foot/boot parts)
        # leg_lower excluded because lower parts with hem vertices in the leg_lower region
        # would cause the entire leg base mesh to disappear (requires both leg_upper+leg_lower)
        allowed_regions = {"waist", "leg_upper", "torso"}
        hides_regions = [r for r, c in region_counts.items() if r in allowed_regions and c >= 5]
    elif part_type == "feet":
        # Feet parts only hide foot - leg_lower is controlled by lower clothing
        hides_regions = ["foot"]
    elif part_type == "special":
        # Special parts are full-body outfits that hide everything
        # Use same threshold logic as upper for arm regions and lower for leg regions
        hides_regions = []
        for region, count in region_counts.items():
            if region in {"torso", "arm_upper", "waist", "leg_upper", "leg_lower"}:
                if count >= 5:
                    hides_regions.append(region)
            elif region == "forearm":
                if count >= 30:
                    hides_regions.append(region)
    elif part_type == "glorb":
        # Glorb parts are arm accessories - default to empty hides_regions
        hides_regions = []
    else:
        hides_regions = []

    # For hair parts, use spatial detection to find scalp vertices to hide
    # The SWP clone indices target wrong area (neck not scalp), so we use Y-threshold instead
    if part_type == "hair":
        # Hide all UPPER vertices above Y=1.32 (scalp/top-of-neck area)
        # These are the vertices that show through gaps in hair
        hides_upper_vertices = scalp_upper_vertices  # Passed from main()
        hides_arm_vertices = []  # ARM doesn't have scalp vertices
    else:
        # For non-hair parts, use SWP clone data
        swp_part_data = swp_data.get(part_name, {})
        hides_upper_vertices = swp_part_data.get(0, [])  # Material 0 = UPPER
        hides_arm_vertices = swp_part_data.get(1, [])    # Material 1 = ARM

    # Apply manual overrides from visual QA
    if hides_overrides and part_name in hides_overrides:
        for region in hides_overrides[part_name]:
            if region not in hides_regions:
                hides_regions.append(region)

    result = {
        "type": part_type,
        "vertices": len(mesh.vertices),
        "region_counts": region_counts,
        "hides_regions": sorted(hides_regions),
    }

    # Only include vertex hiding data if present
    if hides_upper_vertices:
        result["hides_upper_vertices"] = hides_upper_vertices
    if hides_arm_vertices:
        result["hides_arm_vertices"] = hides_arm_vertices

    return result


def main():
    arg_parser = argparse.ArgumentParser(description="Generate parts metadata JSON")
    arg_parser.add_argument("--gender", choices=["male", "female"], default="male")
    args = arg_parser.parse_args()

    config = get_config(args.gender)

    print("=" * 60)
    print(f"Parts Metadata Generator ({args.gender})")
    print("=" * 60)

    # Load base model for bone mapping
    print("\nLoading base model...")
    tmd_parser = TMDParser()
    mlib_parser = MLIBParser()
    swp_parser = SWPParser()
    base_model = tmd_parser.parse(config["base_tmd"])
    mlib = mlib_parser.parse(config["mlib"])
    swp = swp_parser.parse(config["swp"])

    # Build mapping from original vertex indices to per-material local indices
    # Material slots: 0=UPPER, 1=ARM, 2=FOOT, 3=HAND, 4=LEG, 5=LOWER, 6=HAIR, 7=FACE
    base_mesh = base_model.meshes[0]
    original_to_material_local: dict[int, dict[int, int]] = {}  # {material: {orig_idx: local_idx}}

    for mat in range(8):
        original_to_material_local[mat] = {}
        local_idx = 0
        for orig_idx in range(len(base_mesh.vertices)):
            if base_mesh.vertex_materials.get(orig_idx, 0) == mat:
                original_to_material_local[mat][orig_idx] = local_idx
                local_idx += 1

    print(f"  Material 0 (UPPER) has {len(original_to_material_local[0])} vertices")
    print(f"  Material 6 (HAIR) has {len(original_to_material_local[6])} vertices")

    # Build SWP clone indices map with per-material local indices
    swp_data: dict[str, dict] = {}  # part_name -> {material: [local_indices]}
    for swp_entry in swp.swp_data:
        tmd_name = swp_entry.tmd_name
        part_name = tmd_name.split("\\")[-1].replace(".PRT", "")
        clone_indices = swp_entry.get_all_clone_indices()

        if clone_indices:
            # Group clone indices by their material and map to local indices
            material_local_indices: dict[int, list[int]] = {}
            for orig_idx in clone_indices:
                mat = base_mesh.vertex_materials.get(orig_idx, 0)
                if mat not in material_local_indices:
                    material_local_indices[mat] = []
                local_idx = original_to_material_local[mat].get(orig_idx)
                if local_idx is not None:
                    material_local_indices[mat].append(local_idx)

            # Sort indices within each material
            for mat in material_local_indices:
                material_local_indices[mat] = sorted(material_local_indices[mat])

            swp_data[part_name] = material_local_indices

    print(f"  SWP parts with clone data: {len(swp_data)}")

    # Find UPPER vertices in scalp region (Y > 1.32) for hair parts to hide
    # The SWP clone data targets wrong area (neck not scalp), so we use spatial detection
    SCALP_Y_THRESHOLD = 1.32
    scalp_upper_vertices = []
    for orig_idx, v in enumerate(base_mesh.vertices):
        if base_mesh.vertex_materials.get(orig_idx, 0) == 0:  # UPPER material
            if v.y > SCALP_Y_THRESHOLD:
                local_idx = original_to_material_local[0].get(orig_idx)
                if local_idx is not None:
                    scalp_upper_vertices.append(local_idx)
    scalp_upper_vertices = sorted(scalp_upper_vertices)
    print(f"  Scalp UPPER vertices (Y>{SCALP_Y_THRESHOLD}): {len(scalp_upper_vertices)}")

    # Build bone mapping
    tmd_name_to_idx = {b.name.strip(): i for i, b in enumerate(base_model.bones)}
    mlib_to_tmd = {}
    for mlib_idx, mlib_bone in enumerate(mlib.bones):
        tmd_idx = tmd_name_to_idx.get(mlib_bone.name.strip(), -1)
        if tmd_idx >= 0:
            mlib_to_tmd[mlib_idx] = tmd_idx

    bone_names = [b.name.strip() for b in base_model.bones]

    # Analyze all parts
    parts_to_analyze = config["parts"]
    print(f"\nAnalyzing {len(parts_to_analyze)} parts...")
    parts_data = {}
    for part_name in parts_to_analyze:
        metadata = analyze_part(
            part_name, tmd_parser, mlib_to_tmd, bone_names, swp_data, scalp_upper_vertices,
            source_prt_dir=config["prt_dir"], hides_overrides=config["overrides"],
        )
        if metadata:
            parts_data[part_name] = metadata
            upper_count = len(metadata.get('hides_upper_vertices', []))
            arm_count = len(metadata.get('hides_arm_vertices', []))
            print(f"  {part_name}: regions={metadata['hides_regions']}, upper_verts={upper_count}, arm_verts={arm_count}")

    # Write output
    output_data = {"parts": parts_data}
    config["output"].parent.mkdir(parents=True, exist_ok=True)
    with open(config["output"], "w") as f:
        json.dump(output_data, f, indent=2)

    print(f"\nWrote metadata to: {config['output']}")
    print(f"Total parts: {len(parts_data)}")


if __name__ == "__main__":
    main()
