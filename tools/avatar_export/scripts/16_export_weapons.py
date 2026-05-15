#!/usr/bin/env python3
"""
Export weapon PRT files to GLB format and copy textures.

Usage:
    uv run python scripts/16_export_weapons.py

This script exports weapon PRTs (blade, mura) from the attach/ directory to GLB
files with vertices transformed to bone-local space. Textures are copied
alongside for Godot import.
"""

import shutil
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.parsers.tmd_parser import TMDParser
from src.exporters.weapon_exporter import export_weapon


# Configuration
YTREF_ROOT = Path(__file__).parent.parent.parent.parent / "refs"
AVATAR_IRD = YTREF_ROOT / "models" / "raw" / "Avatar.IRD"
SOURCE_ATTACH_DIR = AVATAR_IRD / "attach"
SOURCE_BASE_TMD = AVATAR_IRD / "male.TMD"

CLIENT_DIR = Path(__file__).parent.parent.parent.parent / "ytavatar" / "client"
OUTPUT_TEXTURES_DIR = CLIENT_DIR / "assets" / "avatars" / "textures" / "weapons"

# Blade weapons (27) — attach to @Sword (right hand)
OUTPUT_BLADE_DIR = CLIENT_DIR / "assets" / "avatars" / "weapons" / "blade"
BLADE_BONE = "@Sword"
BLADES_TO_EXPORT = [
    "weapon_blade_A0001", "weapon_blade_A0002", "weapon_blade_A0003",
    "weapon_blade_A0004", "weapon_blade_A0006", "weapon_blade_A0007",
    "weapon_blade_A0008", "weapon_blade_A0009", "weapon_blade_A0011",
    "weapon_blade_A0012", "weapon_blade_A0013", "weapon_blade_A0015",
    "weapon_blade_A0016", "weapon_blade_A0019", "weapon_blade_A0021",
    "weapon_blade_A0022", "weapon_blade_A1001", "weapon_blade_A1002",
    "weapon_blade_A1004", "weapon_blade_A1006", "weapon_blade_A1011",
    "weapon_blade_A1013", "weapon_blade_A1015", "weapon_blade_A1016",
    "weapon_blade_A1019", "weapon_blade_A1021", "weapon_blade_A1022",
]
TRAIL_TEXTURE = "weapon_blade_trail_01.tga"

# Mura weapons (26) — attach to @Head (headphone-style accessories)
OUTPUT_MURA_DIR = CLIENT_DIR / "assets" / "avatars" / "weapons" / "mura"
MURA_BONE = "@Head"
MURAS_TO_EXPORT = [
    "weapon_mura_A0001", "weapon_mura_A0002", "weapon_mura_A0004",
    "weapon_mura_A0005", "weapon_mura_A0006", "weapon_mura_A0007",
    "weapon_mura_A0008", "weapon_mura_A0009", "weapon_mura_A0010",
    "weapon_mura_A0011", "weapon_mura_A0012", "weapon_mura_A0017",
    "weapon_mura_A0020", "weapon_mura_A0022",
    "weapon_mura_A1001", "weapon_mura_A1002", "weapon_mura_A1004",
    "weapon_mura_A1005", "weapon_mura_A1006", "weapon_mura_A1007",
    "weapon_mura_A1008", "weapon_mura_A1011", "weapon_mura_A1017",
    "weapon_mura_A1022",
]

# Spirit weapons (25) — attach to @Pelvis (floating around torso)
OUTPUT_SPIRIT_DIR = CLIENT_DIR / "assets" / "avatars" / "weapons" / "spirit"
SPIRIT_BONE = "@Spine3"
SPIRITS_TO_EXPORT = [
    "weapon_spirit_A0001", "weapon_spirit_A0002", "weapon_spirit_A0003",
    "weapon_spirit_A0004", "weapon_spirit_A0005", "weapon_spirit_A0006",
    "weapon_spirit_A0008", "weapon_spirit_A0009", "weapon_spirit_A0010",
    "weapon_spirit_A0012", "weapon_spirit_A0013", "weapon_spirit_A0014",
    "weapon_spirit_A0015", "weapon_spirit_A0018",
    "weapon_spirit_A1001", "weapon_spirit_A1002", "weapon_spirit_A1003",
    "weapon_spirit_A1004", "weapon_spirit_A1005", "weapon_spirit_A1006",
    "weapon_spirit_A1008", "weapon_spirit_A1010", "weapon_spirit_A1013",
]


def export_weapons(base_model, weapon_list: list, bone_name: str, output_dir: Path, label: str, use_local_transform: bool = True) -> int:
    """Export weapon GLBs for a given weapon type."""
    print(f"Exporting {label} weapons...")
    output_dir.mkdir(parents=True, exist_ok=True)

    tmd_parser = TMDParser()
    success_count = 0

    for weapon_name in weapon_list:
        prt_path = SOURCE_ATTACH_DIR / f"{weapon_name}.PRT"
        glb_path = output_dir / f"{weapon_name}.glb"

        print(f"  Processing: {weapon_name}.PRT")

        if not prt_path.exists():
            print(f"    ERROR: File not found: {prt_path}")
            continue

        try:
            model = tmd_parser.parse(prt_path)
            stats = model.get_stats()
            print(f"    Objects: {len(model.objects)}, Vertices: {stats['total_vertices']}, Faces: {stats['total_faces']}")

            export_weapon(model, base_model, bone_name, glb_path, use_local_transform=use_local_transform)

            output_size = glb_path.stat().st_size
            print(f"    Output: {glb_path.name} ({output_size:,} bytes)")
            success_count += 1

        except Exception as e:
            print(f"    ERROR: {e}")
            import traceback
            traceback.print_exc()

    return success_count


def export_textures(weapon_list: list, extra_textures: list[str] | None = None) -> int:
    """Copy weapon textures."""
    print("\nExporting weapon textures...")
    OUTPUT_TEXTURES_DIR.mkdir(parents=True, exist_ok=True)

    success_count = 0

    for weapon_name in weapon_list:
        for ext in [".bmp", ".tga"]:
            texture_name = f"{weapon_name}{ext}"
            src_path = SOURCE_ATTACH_DIR / texture_name

            if src_path.exists():
                dst_path = OUTPUT_TEXTURES_DIR / texture_name
                shutil.copy2(src_path, dst_path)
                size_kb = dst_path.stat().st_size / 1024
                print(f"  {texture_name} ({size_kb:.1f} KB)")
                success_count += 1
                break
        else:
            print(f"  WARNING: {weapon_name}.bmp/.tga not found")

    for tex_name in (extra_textures or []):
        src = SOURCE_ATTACH_DIR / tex_name
        if src.exists():
            dst = OUTPUT_TEXTURES_DIR / tex_name
            shutil.copy2(src, dst)
            size_kb = dst.stat().st_size / 1024
            print(f"  {tex_name} ({size_kb:.1f} KB)")
            success_count += 1
        else:
            print(f"  WARNING: {tex_name} not found")

    return success_count


def main():
    print("=" * 60)
    print("Weapon Exporter")
    print("=" * 60)
    print()
    print(f"Source: {SOURCE_ATTACH_DIR}")
    print(f"Base TMD: {SOURCE_BASE_TMD}")
    print()

    # Parse base TMD for bone transforms
    print(f"Loading base TMD: {SOURCE_BASE_TMD.name}")
    tmd_parser = TMDParser()
    base_model = tmd_parser.parse(SOURCE_BASE_TMD)
    print(f"  Bones: {len(base_model.bones)}")
    print()

    # Export blades
    blade_count = export_weapons(base_model, BLADES_TO_EXPORT, BLADE_BONE, OUTPUT_BLADE_DIR, "blade")
    blade_tex = export_textures(BLADES_TO_EXPORT, [TRAIL_TEXTURE])
    print()

    # Export muras
    mura_count = export_weapons(base_model, MURAS_TO_EXPORT, MURA_BONE, OUTPUT_MURA_DIR, "mura")
    mura_tex = export_textures(MURAS_TO_EXPORT)
    print()

    # Export spirits
    spirit_count = export_weapons(base_model, SPIRITS_TO_EXPORT, SPIRIT_BONE, OUTPUT_SPIRIT_DIR, "spirit")
    spirit_tex = export_textures(SPIRITS_TO_EXPORT)

    print()
    print("=" * 60)
    print(f"Blades:  {blade_count}/{len(BLADES_TO_EXPORT)} GLBs, {blade_tex} textures")
    print(f"Muras:   {mura_count}/{len(MURAS_TO_EXPORT)} GLBs, {mura_tex} textures")
    print(f"Spirits: {spirit_count}/{len(SPIRITS_TO_EXPORT)} GLBs, {spirit_tex} textures")
    print("=" * 60)


if __name__ == "__main__":
    main()
