#!/usr/bin/env python3
"""
Export face textures to Godot client.

Usage:
    uv run python scripts/15_export_faces.py
    uv run python scripts/15_export_faces.py --gender female

Face textures have the naming pattern: {gender}_face_{G}{type}{frame}.tga
- type: 3-digit face type (e.g., 001, 002, 011)
- frame: blink frame (0=open, 1=half, 2=closed)

Each face type requires 3 textures for blink animation.
"""

import argparse
import shutil
from pathlib import Path

# Configuration
YTREF_ROOT = Path(__file__).parent.parent.parent.parent / "refs"
AVATAR_IRD = YTREF_ROOT / "models" / "raw" / "Avatar.IRD"
CLIENT_DIR = Path(__file__).parent.parent.parent.parent / "ytavatar" / "client"
OUTPUT_FACES_DIR = CLIENT_DIR / "assets" / "avatars" / "textures" / "faces"

# Male: 10 face types
MALE_FACE_TYPES = [
    "001", "002", "003", "011", "012",
    "021", "031", "041", "051", "052",
]

# Female: 20 face types
FEMALE_FACE_TYPES = [
    "001", "002", "003", "004", "005",
    "011", "012", "013",
    "021", "022", "023",
    "031", "032", "033",
    "041", "042", "043",
    "051", "052", "053",
]

# Each face type has 3 blink frames
BLINK_FRAMES = ["0", "1", "2"]


def get_config(gender: str):
    """Get face export config for the given gender."""
    if gender == "male":
        return {
            "source_dir": AVATAR_IRD / "face" / "male",
            "face_types": MALE_FACE_TYPES,
            "prefix": "male_face_M",
        }
    else:
        return {
            "source_dir": AVATAR_IRD / "face" / "female",
            "face_types": FEMALE_FACE_TYPES,
            "prefix": "female_face_F",
        }


def export_face_textures(config: dict) -> int:
    """Export face textures for all face types."""
    print("Exporting face textures...")
    OUTPUT_FACES_DIR.mkdir(parents=True, exist_ok=True)

    success_count = 0
    for face_type in config["face_types"]:
        for frame in BLINK_FRAMES:
            texture_name = f"{config['prefix']}{face_type}{frame}.tga"
            src_path = config["source_dir"] / texture_name
            dst_path = OUTPUT_FACES_DIR / texture_name

            if not src_path.exists():
                print(f"  WARNING: {texture_name} not found")
                continue

            shutil.copy2(src_path, dst_path)
            size_kb = dst_path.stat().st_size / 1024
            print(f"  {texture_name} ({size_kb:.1f} KB)")
            success_count += 1

    return success_count


def main():
    parser = argparse.ArgumentParser(description="Export face textures")
    parser.add_argument("--gender", choices=["male", "female"], default="male")
    args = parser.parse_args()

    config = get_config(args.gender)

    print("=" * 60)
    print(f"Face Texture Exporter ({args.gender})")
    print("=" * 60)
    print()
    print(f"Source: {config['source_dir']}")
    print(f"Output: {OUTPUT_FACES_DIR}")
    print()

    face_count = export_face_textures(config)

    print()
    print("=" * 60)
    print(f"Exported {face_count} face textures ({face_count // 3} face types)")
    print("=" * 60)


if __name__ == "__main__":
    main()
