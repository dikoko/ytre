#!/usr/bin/env python3
"""
Generate parts metadata JSON for Godot.

Ports the original client's part-swap bookkeeping exactly: each avatar part's
.swp entry lists the base-body swap slots (== base TMD material meshes) that
the part REPLACES. Equipping a part removes those whole base meshes; nothing
is hidden per-vertex or inferred from geometry.

The slot -> material-name mapping is derived per gender from the base TMD's
material order (male and female orders differ, e.g. female slot 0 is "lower").

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
from src.parsers.swp_parser import SWPParser

# Configuration
YTREF_ROOT = Path(__file__).parent.parent.parent.parent / "refs"
AVATAR_IRD = YTREF_ROOT / "models" / "raw" / "Avatar.IRD"
CLIENT_DIR = Path(__file__).parent.parent.parent.parent / "ytavatar" / "client"


def get_config(gender: str):
    """Get metadata generation config for the given gender."""
    if gender == "male":
        return {
            "prt_dir": AVATAR_IRD / "swap" / "male",
            "base_tmd": AVATAR_IRD / "male.TMD",
            "swp": AVATAR_IRD / "male.swp",
            "output": CLIENT_DIR / "assets" / "avatars" / "parts" / "parts_metadata.json",
        }
    else:
        return {
            "prt_dir": AVATAR_IRD / "swap" / "female",
            "base_tmd": AVATAR_IRD / "female.TMD",
            "swp": AVATAR_IRD / "female.swp",
            "output": CLIENT_DIR / "assets" / "avatars" / "parts" / "parts_metadata_female.json",
        }


def get_part_type(part_name: str) -> str:
    """Extract part type from name."""
    for token, ptype in (
        ("_hair_", "hair"), ("_upper_", "upper"), ("_lower_", "lower"),
        ("_hand_", "hands"), ("_foot_", "feet"), ("_special_", "special"),
        ("_glorb_", "glorb"),
    ):
        if token in part_name:
            return ptype
    return "unknown"


def slot_material_names(base_model) -> dict[int, list[str]]:
    """Map swap-slot ID -> viewer material-mesh names, from the base TMD's
    material order (slot ID == material index == base mesh order).

    The viewer splits the hair material into two meshes (scalp cap and
    strands), so the hair slot maps to both.
    """
    mapping: dict[int, list[str]] = {}
    for idx, mat in enumerate(base_model.materials):
        name = mat.name.lower()
        if name == "face":
            mapping[idx] = ["face"]
        elif "_hair_" in name:
            mapping[idx] = ["hair_scalp", "hair_strands"]
        else:
            # e.g. "male_upper_M0000" / "female_lower_F0000" -> "upper"/"lower"
            mapping[idx] = [name.split("_")[1]]
    return mapping


def main():
    arg_parser = argparse.ArgumentParser(description="Generate parts metadata JSON")
    arg_parser.add_argument("--gender", choices=["male", "female"], default="male")
    args = arg_parser.parse_args()

    config = get_config(args.gender)

    print("=" * 60)
    print(f"Parts Metadata Generator ({args.gender})")
    print("=" * 60)

    base_model = TMDParser().parse(config["base_tmd"])
    swp = SWPParser().parse(config["swp"])

    slot_to_materials = slot_material_names(base_model)
    print("\nSwap slots (base TMD material order):")
    for slot, names in slot_to_materials.items():
        print(f"  slot {slot}: {names}")

    parts_data = {}
    skipped = 0
    for entry in swp.swp_data:
        part_name = entry.tmd_name.split("\\")[-1].replace(".PRT", "")
        prt_path = config["prt_dir"] / f"{part_name}.PRT"
        if not prt_path.exists():
            skipped += 1
            continue

        slots = entry.get_slot_ids()
        materials = sorted({m for s in slots for m in slot_to_materials[s]})
        parts_data[part_name] = {
            "type": get_part_type(part_name),
            "hides_slots": slots,
            "hides_materials": materials,
        }

    print(f"\nParts: {len(parts_data)} (skipped {skipped} without PRT files)")

    output_data = {"parts": parts_data}
    config["output"].parent.mkdir(parents=True, exist_ok=True)
    with open(config["output"], "w") as f:
        json.dump(output_data, f, indent=2)

    print(f"Wrote metadata to: {config['output']}")


if __name__ == "__main__":
    main()
