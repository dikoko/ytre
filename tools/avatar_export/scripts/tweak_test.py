#!/usr/bin/env python3
"""
Tweak testing tool — exports a model with multiple rotation variants for a bone.

Generates separate GLB files for each variant so you can compare in Godot.

Usage:
    python scripts/tweak_test.py cn0007 15 --axes x y z --angles 90 180
    python scripts/tweak_test.py cn0007 15 --rot 0 0 180
    python scripts/tweak_test.py cn0007 15 --rot 45 0 0 --rot 90 0 0 --rot 0 90 0

Output goes to client/assets/npcs/models/ with suffixed filenames:
    cn0007_base.glb          (no tweak, baseline)
    cn0007_x90.glb           (90° around X)
    cn0007_z180.glb          (180° around Z)
    cn0007_rot_45_0_0.glb    (custom rotation)
"""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import scripts._export_common as common
from src.parsers.tmd_parser import TMDParser
from src.parsers.mlib_parser import MLIBParser
from src.exporters.animation_exporter import _build_tmd_to_mlib_map

YTREF_ROOT = PROJECT_ROOT.parent.parent / "refs"
NPC_IRD = YTREF_ROOT / "models" / "raw" / "NPC.IRD"
MONSTER_IRD = YTREF_ROOT / "models" / "raw" / "Monster.IRD"
CLIENT_DIR = PROJECT_ROOT.parent.parent / "ytavatar" / "client"

# Import NPC-specific configs
from scripts import _npc_config as npc_cfg


def find_model_dir(model_id: str) -> Path:
    if model_id.startswith("cn"):
        return NPC_IRD / model_id
    elif model_id.startswith("ct"):
        return MONSTER_IRD / model_id
    raise ValueError(f"Unknown model prefix: {model_id}")


def output_dir(model_id: str) -> Path:
    if model_id.startswith("cn"):
        return CLIENT_DIR / "assets" / "npcs" / "models"
    return CLIENT_DIR / "assets" / "monsters" / "models"


def export_variant(model_id: str, bone_idx: int, suffix: str,
                   rot: list[float] | None = None, pos: list[float] | None = None):
    model_dir = find_model_dir(model_id)
    out_dir = output_dir(model_id)
    out_dir.mkdir(parents=True, exist_ok=True)

    tweak_entry = {}
    if rot and rot != [0, 0, 0]:
        tweak_entry["rot"] = rot
    if pos and pos != [0, 0, 0]:
        tweak_entry["pos"] = pos
    tweaks = {model_id: {bone_idx: tweak_entry}} if tweak_entry else None

    # Use NPC configs for cn models
    kwargs = {}
    if model_id.startswith("cn"):
        kwargs = dict(
            force_tmd_scale_ids=npc_cfg.FORCE_TMD_SCALE,
            smooth_bone_overrides=npc_cfg.SMOOTH_BONES,
            equip_correction=npc_cfg.EQUIP_CORRECTION,
            skip_reparent_ids=npc_cfg.SKIP_REPARENT,
        )

    # Temporarily rename output
    original_path = out_dir / f"{model_id}.glb"
    variant_path = out_dir / f"{model_id}_{suffix}.glb"

    ok, msg = common.export_model(
        model_id, model_dir, out_dir,
        bone_tweaks=tweaks,
        **kwargs,
    )
    if ok and original_path.exists():
        original_path.rename(variant_path)
        print(f"  {suffix}: {msg} -> {variant_path.name}")
    else:
        print(f"  {suffix}: {msg}")


def main():
    parser = argparse.ArgumentParser(description="Export model with rotation tweaks for testing")
    parser.add_argument("model_id", help="Model ID (e.g., cn0007)")
    parser.add_argument("bone_idx", type=int, help="TMD bone index to tweak")
    parser.add_argument("--axes", nargs="+", default=[], help="Axes to test (x, y, z)")
    parser.add_argument("--angles", nargs="+", type=float, default=[90, 180], help="Angles to test per axis")
    parser.add_argument("--rot", nargs=3, type=float, action="append", default=[], metavar=("RX", "RY", "RZ"),
                        help="Custom rotation (degrees), can specify multiple")
    parser.add_argument("--pos", nargs=3, type=float, action="append", default=[], metavar=("X", "Y", "Z"),
                        help="Position offset (units), can specify multiple")
    parser.add_argument("--pos-grid", nargs="+", type=float, default=[], metavar="OFFSET",
                        help="Test position offsets on each axis (e.g., --pos-grid 0.05 0.1)")
    parser.add_argument("--base-rot", nargs=3, type=float, default=None, metavar=("RX", "RY", "RZ"),
                        help="Base rotation applied to ALL position variants (e.g., --base-rot 0 90 0)")
    parser.add_argument("--info", action="store_true", help="Show bone info and exit")
    args = parser.parse_args()

    model_dir = find_model_dir(args.model_id)
    tmd = TMDParser().parse(model_dir / f"{args.model_id}.TMD")

    if args.info:
        print(f"{args.model_id} bones:")
        for i, b in enumerate(tmd.bones):
            name = b.name.strip()
            t = b.world_transform.translation
            marker = " <--" if i == args.bone_idx else ""
            print(f"  [{i}] {name:25s} pos=({t.x:.3f}, {t.y:.3f}, {t.z:.3f}){marker}")
        return

    bone_name = tmd.bones[args.bone_idx].name.strip()
    print(f"Tweak testing: {args.model_id} bone[{args.bone_idx}] {bone_name}")

    # Always export baseline
    export_variant(args.model_id, args.bone_idx, "base")

    # Axis-based rotation variants
    for axis in args.axes:
        for angle in args.angles:
            rot = [0, 0, 0]
            axis_idx = {"x": 0, "y": 1, "z": 2}[axis.lower()]
            rot[axis_idx] = angle
            suffix = f"{axis}{int(angle)}"
            export_variant(args.model_id, args.bone_idx, suffix, rot=rot)

    # Custom rotation variants
    for rot in args.rot:
        suffix = f"rot_{int(rot[0])}_{int(rot[1])}_{int(rot[2])}"
        export_variant(args.model_id, args.bone_idx, suffix, rot=list(rot))

    # Custom position variants (with base-rot if specified)
    base_rot = list(args.base_rot) if args.base_rot else None
    for pos in args.pos:
        suffix = f"pos_{pos[0]:.2f}_{pos[1]:.2f}_{pos[2]:.2f}"
        export_variant(args.model_id, args.bone_idx, suffix, rot=base_rot, pos=list(pos))

    # Position grid: test each axis with each offset value
    for offset in args.pos_grid:
        for axis_name, axis_idx in [("px", 0), ("py", 1), ("pz", 2),
                                     ("nx", 0), ("ny", 1), ("nz", 2)]:
            pos = [0, 0, 0]
            sign = -1 if axis_name.startswith("n") else 1
            pos[axis_idx] = offset * sign
            suffix = f"{axis_name}{offset:.2f}"
            export_variant(args.model_id, args.bone_idx, suffix, rot=base_rot, pos=pos)

    print(f"\nDone. Load variants in Godot from: {output_dir(args.model_id)}")


if __name__ == "__main__":
    main()
