#!/usr/bin/env python3
"""
Export avatar textures to Godot client.

Usage:
    uv run python scripts/12_export_textures.py
    uv run python scripts/12_export_textures.py --gender female

This script copies TGA texture files from the source Avatar.IRD directory
to the Godot client assets folder. The textures are organized by type:

  - Base body textures → client/assets/avatars/textures/base/
  - Part textures → client/assets/avatars/textures/parts/

Godot will import TGA files automatically and create .import files.
"""

import argparse
import shutil
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


# Configuration
YTREF_ROOT = Path(__file__).parent.parent.parent.parent / "refs"
AVATAR_IRD = YTREF_ROOT / "models" / "raw" / "Avatar.IRD"
CLIENT_DIR = Path(__file__).parent.parent.parent.parent / "ytavatar" / "client"
OUTPUT_BASE_DIR = CLIENT_DIR / "assets" / "avatars" / "textures" / "base"
OUTPUT_PARTS_DIR = CLIENT_DIR / "assets" / "avatars" / "textures" / "parts"

# Male base body texture files (directly in Avatar.IRD)
MALE_BASE_TEXTURES = [
    "male_arm_M0000.tga",
    "male_foot_M0000.tga",
    "male_hair_M0000.tga",
    "male_hand_M0000.tga",
    "male_leg_M0000.tga",
    "male_lower_M0000.tga",
    "male_upper_M0000.tga",
]

# Female base body texture files
FEMALE_BASE_TEXTURES = [
    "female_arm_F0000.tga",
    "female_foot_F0000.tga",
    "female_hair_F0000.tga",
    "female_hand_F0000.tga",
    "female_leg_F0000.tga",
    "female_lower_F0000.tga",
    "female_upper_F0000.tga",
]

# All male PRT parts to export textures for (matching 10_export_parts.py)
MALE_PARTS_TO_EXPORT = [
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

# All female PRT parts to export textures for (matching 10_export_parts.py)
FEMALE_PARTS_TO_EXPORT = [
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


def get_config(gender: str):
    """Get texture lists and source paths for the given gender."""
    if gender == "male":
        return {
            "base_textures": MALE_BASE_TEXTURES,
            "parts": MALE_PARTS_TO_EXPORT,
            "source_base_dir": AVATAR_IRD,
            "source_parts_dir": AVATAR_IRD / "swap" / "male",
        }
    else:
        return {
            "base_textures": FEMALE_BASE_TEXTURES,
            "parts": FEMALE_PARTS_TO_EXPORT,
            "source_base_dir": AVATAR_IRD,
            "source_parts_dir": AVATAR_IRD / "swap" / "female",
        }


def export_base_textures(config: dict) -> int:
    """Export base body textures."""
    print("Exporting base body textures...")
    OUTPUT_BASE_DIR.mkdir(parents=True, exist_ok=True)

    success_count = 0
    for texture_name in config["base_textures"]:
        src_path = config["source_base_dir"] / texture_name
        dst_path = OUTPUT_BASE_DIR / texture_name

        if not src_path.exists():
            print(f"  WARNING: {texture_name} not found")
            continue

        shutil.copy2(src_path, dst_path)
        size_kb = dst_path.stat().st_size / 1024
        print(f"  {texture_name} ({size_kb:.1f} KB)")
        success_count += 1

    return success_count


def export_part_textures(config: dict) -> int:
    """Export part textures."""
    print("\nExporting part textures...")
    OUTPUT_PARTS_DIR.mkdir(parents=True, exist_ok=True)

    success_count = 0
    for part_name in config["parts"]:
        # Try TGA first, then BMP (case-insensitive for BMP)
        found = False
        for ext in [".tga", ".bmp", ".BMP"]:
            texture_name = f"{part_name}{ext}"
            src_path = config["source_parts_dir"] / texture_name

            if src_path.exists():
                dst_path = OUTPUT_PARTS_DIR / texture_name
                shutil.copy2(src_path, dst_path)
                size_kb = dst_path.stat().st_size / 1024
                print(f"  {texture_name} ({size_kb:.1f} KB)")
                success_count += 1
                found = True
                break

        if not found:
            print(f"  WARNING: {part_name}.tga/.bmp not found")

    return success_count


def main():
    parser = argparse.ArgumentParser(description="Export avatar textures")
    parser.add_argument("--gender", choices=["male", "female"], default="male")
    args = parser.parse_args()

    config = get_config(args.gender)

    print("=" * 60)
    print(f"Texture Exporter ({args.gender})")
    print("=" * 60)
    print()
    print(f"Source base: {config['source_base_dir']}")
    print(f"Source parts: {config['source_parts_dir']}")
    print(f"Output base: {OUTPUT_BASE_DIR}")
    print(f"Output parts: {OUTPUT_PARTS_DIR}")
    print()

    base_count = export_base_textures(config)
    parts_count = export_part_textures(config)

    print()
    print("=" * 60)
    print(f"Exported {base_count} base textures, {parts_count} part textures")
    print("=" * 60)


if __name__ == "__main__":
    main()
