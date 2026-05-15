#!/usr/bin/env python3
"""
Export PRT (avatar part) files to GLB format.

Usage:
    uv run python scripts/10_export_parts.py
    uv run python scripts/10_export_parts.py --gender female

This script exports PRT files to GLB with mesh geometry and skin attributes.
Parts store bone indices/weights but not the skeleton itself - they'll be
attached to a skeleton at runtime.
"""

import argparse
import os
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.parsers.tmd_parser import TMDParser
from src.parsers.mlib_parser import MLIBParser
from src.exporters.part_exporter import export_part
from src.exporters.boundary_normals import build_boundary_map, fix_part_boundary_normals


# Configuration
YTREF_ROOT = Path(__file__).parent.parent.parent.parent / "refs"
AVATAR_IRD = YTREF_ROOT / "models" / "raw" / "Avatar.IRD"
CLIENT_DIR = Path(__file__).parent.parent.parent.parent / "ytavatar" / "client"

# All male PRT parts (201 files)
MALE_PARTS_TO_EXPORT = [
    # Hair (27)
    "male_hair_M0101.PRT", "male_hair_M0102.PRT", "male_hair_M0103.PRT",
    "male_hair_M0201.PRT", "male_hair_M0202.PRT", "male_hair_M0203.PRT",
    "male_hair_M0301.PRT", "male_hair_M0302.PRT", "male_hair_M0303.PRT",
    "male_hair_M0401.PRT", "male_hair_M0402.PRT", "male_hair_M0403.PRT",
    "male_hair_M0501.PRT", "male_hair_M0502.PRT", "male_hair_M0503.PRT",
    "male_hair_M0601.PRT", "male_hair_M0602.PRT", "male_hair_M0603.PRT",
    "male_hair_M0701.PRT", "male_hair_M0702.PRT", "male_hair_M0703.PRT",
    "male_hair_M0801.PRT", "male_hair_M0802.PRT", "male_hair_M0803.PRT",
    "male_hair_M0901.PRT", "male_hair_M0902.PRT", "male_hair_M0903.PRT",
    # Upper (38)
    "male_upper_M0001.PRT", "male_upper_M0002.PRT", "male_upper_M0003.PRT", "male_upper_M0004.PRT",
    "male_upper_M0008.PRT", "male_upper_M0009.PRT", "male_upper_M0011.PRT", "male_upper_M0012.PRT",
    "male_upper_M0013.PRT", "male_upper_M0014.PRT", "male_upper_M0016.PRT", "male_upper_M0017.PRT",
    "male_upper_M0018.PRT", "male_upper_M0019.PRT", "male_upper_M0022.PRT", "male_upper_M0023.PRT",
    "male_upper_M0024.PRT", "male_upper_M0025.PRT", "male_upper_M0026.PRT", "male_upper_M0031.PRT",
    "male_upper_M0032.PRT", "male_upper_M1001.PRT", "male_upper_M1002.PRT", "male_upper_M1009.PRT",
    "male_upper_M1011.PRT", "male_upper_M1012.PRT", "male_upper_M1013.PRT", "male_upper_M1014.PRT",
    "male_upper_M1016.PRT", "male_upper_M1017.PRT", "male_upper_M1018.PRT", "male_upper_M1021.PRT",
    "male_upper_M1024.PRT", "male_upper_M1026.PRT", "male_upper_M1029.PRT", "male_upper_M1031.PRT",
    "male_upper_M1032.PRT", "male_upper_M9002.PRT",
    # Lower (33)
    "male_lower_M0001.PRT", "male_lower_M0002.PRT", "male_lower_M0003.PRT", "male_lower_M0004.PRT",
    "male_lower_M0008.PRT", "male_lower_M0009.PRT", "male_lower_M0011.PRT", "male_lower_M0012.PRT",
    "male_lower_M0014.PRT", "male_lower_M0016.PRT", "male_lower_M0018.PRT", "male_lower_M0019.PRT",
    "male_lower_M0022.PRT", "male_lower_M0023.PRT", "male_lower_M0024.PRT", "male_lower_M0025.PRT",
    "male_lower_M0026.PRT", "male_lower_M0031.PRT", "male_lower_M0032.PRT", "male_lower_M1001.PRT",
    "male_lower_M1002.PRT", "male_lower_M1009.PRT", "male_lower_M1011.PRT", "male_lower_M1012.PRT",
    "male_lower_M1014.PRT", "male_lower_M1016.PRT", "male_lower_M1018.PRT", "male_lower_M1024.PRT",
    "male_lower_M1026.PRT", "male_lower_M1029.PRT", "male_lower_M1031.PRT", "male_lower_M1032.PRT",
    "male_lower_M9002.PRT",
    # Hand (13)
    "male_hand_M0004.PRT", "male_hand_M0019.PRT", "male_hand_M0022.PRT", "male_hand_M0025.PRT",
    "male_hand_M0032.PRT", "male_hand_M1004.PRT", "male_hand_M1005.PRT", "male_hand_M1019.PRT",
    "male_hand_M1020.PRT", "male_hand_M1026.PRT", "male_hand_M1027.PRT", "male_hand_M1029.PRT",
    "male_hand_M9001.PRT",
    # Foot (42)
    "male_foot_GMM0001.PRT",
    "male_foot_M0001.PRT", "male_foot_M0002.PRT", "male_foot_M0003.PRT", "male_foot_M0004.PRT",
    "male_foot_M0005.PRT", "male_foot_M0006.PRT", "male_foot_M0007.PRT", "male_foot_M0008.PRT",
    "male_foot_M0009.PRT", "male_foot_M0014.PRT", "male_foot_M0018.PRT", "male_foot_M0019.PRT",
    "male_foot_M0022.PRT", "male_foot_M0023.PRT", "male_foot_M0024.PRT", "male_foot_M0025.PRT",
    "male_foot_M0026.PRT", "male_foot_M0031.PRT", "male_foot_M0032.PRT", "male_foot_M1001.PRT",
    "male_foot_M1002.PRT", "male_foot_M1003.PRT", "male_foot_M1004.PRT", "male_foot_M1005.PRT",
    "male_foot_M1006.PRT", "male_foot_M1007.PRT", "male_foot_M1009.PRT", "male_foot_M1014.PRT",
    "male_foot_M1018.PRT", "male_foot_M1019.PRT", "male_foot_M1020.PRT", "male_foot_M1023.PRT",
    "male_foot_M1024.PRT", "male_foot_M1025.PRT", "male_foot_M1026.PRT", "male_foot_M1027.PRT",
    "male_foot_M1029.PRT", "male_foot_M1031.PRT", "male_foot_M1032.PRT", "male_foot_M9001.PRT",
    "male_foot_M9002.PRT",
    # Special (21)
    "male_special_GMM0001.PRT",
    "male_special_M0005.PRT", "male_special_M0006.PRT", "male_special_M0007.PRT",
    "male_special_M0010.PRT", "male_special_M0015.PRT", "male_special_M0021.PRT",
    "male_special_M1003.PRT", "male_special_M1004.PRT", "male_special_M1005.PRT",
    "male_special_M1006.PRT", "male_special_M1007.PRT", "male_special_M1010.PRT",
    "male_special_M1015.PRT", "male_special_M1019.PRT", "male_special_M1020.PRT",
    "male_special_M1023.PRT", "male_special_M1025.PRT", "male_special_M1027.PRT",
    "male_special_M9001.PRT", "male_special_M9004.PRT",
    # Glorb (26)
    "male_glorb_A0001.PRT", "male_glorb_A0002.PRT", "male_glorb_A0003.PRT",
    "male_glorb_A0005.PRT", "male_glorb_A0007.PRT", "male_glorb_A0008.PRT",
    "male_glorb_A0009.PRT", "male_glorb_A0010.PRT", "male_glorb_A0011.PRT",
    "male_glorb_A0013.PRT", "male_glorb_A0014.PRT", "male_glorb_A0015.PRT",
    "male_glorb_A0016.PRT", "male_glorb_A0019.PRT", "male_glorb_A0021.PRT",
    "male_glorb_A1001.PRT", "male_glorb_A1002.PRT", "male_glorb_A1003.PRT",
    "male_glorb_A1005.PRT", "male_glorb_A1007.PRT", "male_glorb_A1009.PRT",
    "male_glorb_A1013.PRT", "male_glorb_A1014.PRT", "male_glorb_A1015.PRT",
    "male_glorb_A1019.PRT", "male_glorb_A1021.PRT",
]

# All female PRT parts (194 files)
FEMALE_PARTS_TO_EXPORT = [
    # Hair (27)
    "female_hair_F0101.PRT", "female_hair_F0102.PRT", "female_hair_F0103.PRT",
    "female_hair_F0201.PRT", "female_hair_F0202.PRT", "female_hair_F0203.PRT",
    "female_hair_F0301.PRT", "female_hair_F0302.PRT", "female_hair_F0303.PRT",
    "female_hair_F0401.PRT", "female_hair_F0402.PRT", "female_hair_F0403.PRT",
    "female_hair_F0501.PRT", "female_hair_F0502.PRT", "female_hair_F0503.PRT",
    "female_hair_F0601.PRT", "female_hair_F0602.PRT", "female_hair_F0603.PRT",
    "female_hair_F0701.PRT", "female_hair_F0702.PRT", "female_hair_F0703.PRT",
    "female_hair_F0801.PRT", "female_hair_F0802.PRT", "female_hair_F0803.PRT",
    "female_hair_F0901.PRT", "female_hair_F0902.PRT", "female_hair_F0903.PRT",
    # Upper (29)
    "female_upper_F0001.PRT", "female_upper_F0002.PRT", "female_upper_F0003.PRT",
    "female_upper_F0008.PRT", "female_upper_F0009.PRT", "female_upper_F0011.PRT",
    "female_upper_F0012.PRT", "female_upper_F0013.PRT", "female_upper_F0016.PRT",
    "female_upper_F0018.PRT", "female_upper_F0019.PRT", "female_upper_F0023.PRT",
    "female_upper_F0025.PRT", "female_upper_F0026.PRT", "female_upper_F0031.PRT",
    "female_upper_F0032.PRT", "female_upper_F1002.PRT", "female_upper_F1009.PRT",
    "female_upper_F1012.PRT", "female_upper_F1013.PRT", "female_upper_F1014.PRT",
    "female_upper_F1016.PRT", "female_upper_F1018.PRT", "female_upper_F1021.PRT",
    "female_upper_F1026.PRT", "female_upper_F1029.PRT", "female_upper_F1031.PRT",
    "female_upper_F1032.PRT", "female_upper_F9002.PRT",
    # Lower (27)
    "female_lower_F0001.PRT", "female_lower_F0002.PRT", "female_lower_F0003.PRT",
    "female_lower_F0008.PRT", "female_lower_F0009.PRT", "female_lower_F0011.PRT",
    "female_lower_F0012.PRT", "female_lower_F0016.PRT", "female_lower_F0018.PRT",
    "female_lower_F0019.PRT", "female_lower_F0023.PRT", "female_lower_F0025.PRT",
    "female_lower_F0026.PRT", "female_lower_F0031.PRT", "female_lower_F0032.PRT",
    "female_lower_F1002.PRT", "female_lower_F1009.PRT", "female_lower_F1012.PRT",
    "female_lower_F1014.PRT", "female_lower_F1016.PRT", "female_lower_F1017.PRT",
    "female_lower_F1018.PRT", "female_lower_F1026.PRT", "female_lower_F1029.PRT",
    "female_lower_F1031.PRT", "female_lower_F1032.PRT", "female_lower_F9002.PRT",
    # Hand (14)
    "female_hand_F0004.PRT", "female_hand_F0019.PRT", "female_hand_F0022.PRT",
    "female_hand_F0023.PRT", "female_hand_F0032.PRT", "female_hand_F1004.PRT",
    "female_hand_F1005.PRT", "female_hand_F1019.PRT", "female_hand_F1020.PRT",
    "female_hand_F1025.PRT", "female_hand_F1026.PRT", "female_hand_F1027.PRT",
    "female_hand_F1029.PRT", "female_hand_F9001.PRT",
    # Foot (42)
    "female_foot_GMF0001.PRT",
    "female_foot_F0001.PRT", "female_foot_F0002.PRT", "female_foot_F0003.PRT",
    "female_foot_F0004.PRT", "female_foot_F0005.PRT", "female_foot_F0006.PRT",
    "female_foot_F0007.PRT", "female_foot_F0008.PRT", "female_foot_F0009.PRT",
    "female_foot_F0014.PRT", "female_foot_F0018.PRT", "female_foot_F0019.PRT",
    "female_foot_F0022.PRT", "female_foot_F0023.PRT", "female_foot_F0024.PRT",
    "female_foot_F0025.PRT", "female_foot_F0026.PRT", "female_foot_F0031.PRT",
    "female_foot_F0032.PRT", "female_foot_F1001.PRT", "female_foot_F1002.PRT",
    "female_foot_F1003.PRT", "female_foot_F1004.PRT", "female_foot_F1005.PRT",
    "female_foot_F1006.PRT", "female_foot_F1007.PRT", "female_foot_F1009.PRT",
    "female_foot_F1014.PRT", "female_foot_F1018.PRT", "female_foot_F1019.PRT",
    "female_foot_F1020.PRT", "female_foot_F1023.PRT", "female_foot_F1024.PRT",
    "female_foot_F1025.PRT", "female_foot_F1026.PRT", "female_foot_F1027.PRT",
    "female_foot_F1029.PRT", "female_foot_F1031.PRT", "female_foot_F1032.PRT",
    "female_foot_F9001.PRT", "female_foot_F9002.PRT",
    # Special (29)
    "female_special_GMF0001.PRT",
    "female_special_F0004.PRT", "female_special_F0005.PRT", "female_special_F0006.PRT",
    "female_special_F0007.PRT", "female_special_F0010.PRT", "female_special_F0014.PRT",
    "female_special_F0015.PRT", "female_special_F0017.PRT", "female_special_F0021.PRT",
    "female_special_F0022.PRT", "female_special_F0024.PRT", "female_special_F1001.PRT",
    "female_special_F1003.PRT", "female_special_F1004.PRT", "female_special_F1005.PRT",
    "female_special_F1006.PRT", "female_special_F1007.PRT", "female_special_F1010.PRT",
    "female_special_F1011.PRT", "female_special_F1015.PRT", "female_special_F1019.PRT",
    "female_special_F1020.PRT", "female_special_F1023.PRT", "female_special_F1024.PRT",
    "female_special_F1025.PRT", "female_special_F1027.PRT", "female_special_F9001.PRT",
    "female_special_F9004.PRT",
    # Glorb (26)
    "female_glorb_A0001.PRT", "female_glorb_A0002.PRT", "female_glorb_A0003.PRT",
    "female_glorb_A0005.PRT", "female_glorb_A0007.PRT", "female_glorb_A0008.PRT",
    "female_glorb_A0009.PRT", "female_glorb_A0010.PRT", "female_glorb_A0011.PRT",
    "female_glorb_A0013.PRT", "female_glorb_A0014.PRT", "female_glorb_A0015.PRT",
    "female_glorb_A0016.PRT", "female_glorb_A0019.PRT", "female_glorb_A0021.PRT",
    "female_glorb_A1001.PRT", "female_glorb_A1002.PRT", "female_glorb_A1003.PRT",
    "female_glorb_A1005.PRT", "female_glorb_A1007.PRT", "female_glorb_A1009.PRT",
    "female_glorb_A1013.PRT", "female_glorb_A1014.PRT", "female_glorb_A1015.PRT",
    "female_glorb_A1019.PRT", "female_glorb_A1021.PRT",
]


def get_config(gender: str):
    """Get source paths and parts list for the given gender."""
    if gender == "male":
        return {
            "prt_dir": AVATAR_IRD / "swap" / "male",
            "base_tmd": AVATAR_IRD / "male.TMD",
            "mlib": AVATAR_IRD / "motion" / "male" / "male.mlib",
            "output_dir": CLIENT_DIR / "assets" / "avatars" / "parts" / "male",
            "parts": MALE_PARTS_TO_EXPORT,
            "hair_prefix": "male_hair_",
        }
    else:
        return {
            "prt_dir": AVATAR_IRD / "swap" / "female",
            "base_tmd": AVATAR_IRD / "female.TMD",
            "mlib": AVATAR_IRD / "motion" / "female" / "female.mlib",
            "output_dir": CLIENT_DIR / "assets" / "avatars" / "parts" / "female",
            "parts": FEMALE_PARTS_TO_EXPORT,
            "hair_prefix": "female_hair_",
        }


def main():
    arg_parser = argparse.ArgumentParser(description="Export PRT avatar parts to GLB")
    arg_parser.add_argument("--gender", choices=["male", "female"], default="male")
    args = arg_parser.parse_args()

    config = get_config(args.gender)

    print("=" * 60)
    print(f"Part Exporter ({args.gender})")
    print("=" * 60)
    print()

    # Parse base TMD and MLIB (for bone names and index mapping)
    print(f"Loading base TMD: {config['base_tmd'].name}")
    tmd_parser = TMDParser()
    mlib_parser = MLIBParser()
    base_model = tmd_parser.parse(config["base_tmd"])
    mlib = mlib_parser.parse(config["mlib"])
    print(f"  TMD Bones: {len(base_model.bones)}")
    print(f"  MLIB Bones: {len(mlib.bones)}")
    print()

    # Build face boundary map for hair normal fixing (TMD material index 7 = face)
    print("Building face boundary map for hair normal fixing...")
    face_grid, face_cell_size = build_boundary_map(base_model, material_index=7)
    print()

    # Create output directory
    config["output_dir"].mkdir(parents=True, exist_ok=True)
    print(f"Output directory: {config['output_dir']}")
    print()

    # Export each part
    success_count = 0
    parts_to_export = config["parts"]

    for prt_name in parts_to_export:
        prt_path = config["prt_dir"] / prt_name
        glb_name = prt_name.replace(".PRT", ".glb")
        glb_path = config["output_dir"] / glb_name

        print(f"Processing: {prt_name}")

        if not prt_path.exists():
            print(f"  ERROR: File not found: {prt_path}")
            continue

        try:
            # Parse PRT file
            model = tmd_parser.parse(prt_path)
            stats = model.get_stats()

            print(f"  Meshes: {stats['mesh_count']}")
            print(f"  Vertices: {stats['total_vertices']}")
            print(f"  Faces: {stats['total_faces']}")

            # Count bones used in skinning
            used_bones = set()
            for mesh in model.meshes:
                for skin_data in mesh.vertex_skinning.values():
                    for bone_idx, _ in skin_data:
                        used_bones.add(bone_idx)
            print(f"  Bones used: {len(used_bones)}")

            # Fix boundary normals for hair parts (eliminates forehead seam)
            if prt_name.startswith(config["hair_prefix"]):
                fixed = fix_part_boundary_normals(model, face_grid, face_cell_size)
                if fixed > 0:
                    print(f"  Boundary normals fixed: {fixed}")

            # Export to GLB (with MLIB for bone index remapping)
            export_part(model, base_model, mlib, glb_path)

            # Report output size
            output_size = glb_path.stat().st_size
            print(f"  Output: {glb_name} ({output_size:,} bytes)")
            print()

            success_count += 1

        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback
            traceback.print_exc()
            print()

    print("=" * 60)
    print(f"Exported {success_count}/{len(parts_to_export)} parts successfully")
    print("=" * 60)


if __name__ == "__main__":
    main()
