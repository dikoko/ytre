#!/usr/bin/env python3
"""
NPC Export Script

Exports NPC TMD models with skeleton and animations from MLIB to GLB.
NPCs use the same format as monsters (TMD + MLIB + BMP).

Usage:
    python scripts/21_export_npcs.py              # Export pilot NPCs (5)
    python scripts/21_export_npcs.py --all        # Export all NPCs
    python scripts/21_export_npcs.py --ids cn0001 cn0005  # Export specific NPCs
"""

import argparse
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts import _export_common as common
from scripts import _npc_config as cfg

YTREF_ROOT = PROJECT_ROOT.parent.parent / "refs"
NPC_IRD = YTREF_ROOT / "models" / "raw" / "NPC.IRD"
CLIENT_DIR = PROJECT_ROOT.parent.parent / "ytavatar" / "client"
OUTPUT_MODELS_DIR = CLIENT_DIR / "assets" / "npcs" / "models"

PILOT_NPCS = ["cn0001", "cn0003", "cn0005", "cn0010", "cn0020"]


def discover_npcs() -> list[str]:
    """Find all NPC directories in NPC.IRD."""
    dirs = sorted(
        d.name for d in NPC_IRD.iterdir()
        if d.is_dir() and d.name.startswith("cn")
    )
    return dirs


def export_npc(npc_id: str) -> tuple[bool, str]:
    """Export a single NPC's GLB with embedded texture."""
    return common.export_model(
        npc_id, NPC_IRD / npc_id, OUTPUT_MODELS_DIR,
        force_tmd_scale_ids=cfg.FORCE_TMD_SCALE,
        smooth_bone_overrides=cfg.SMOOTH_BONES,
        equip_correction=cfg.EQUIP_CORRECTION,
        bone_tweaks=cfg.BONE_TWEAKS,
        skip_reparent_ids=cfg.SKIP_REPARENT,
    )


def main():
    parser = argparse.ArgumentParser(description="Export NPC models to GLB")
    parser.add_argument("--all", action="store_true", help="Export all NPCs")
    parser.add_argument("--ids", nargs="+", help="Export specific NPC IDs")
    args = parser.parse_args()

    if args.ids:
        npc_ids = args.ids
    elif args.all:
        npc_ids = discover_npcs()
    else:
        npc_ids = PILOT_NPCS

    OUTPUT_MODELS_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Exporting {len(npc_ids)} NPCs...")
    start = time.time()
    success_count = 0

    for nid in npc_ids:
        ok, msg = export_npc(nid)
        print(f"  {'OK' if ok else 'FAIL'} {msg}")
        if ok:
            success_count += 1

    elapsed = time.time() - start
    print(f"\nDone: {success_count}/{len(npc_ids)} exported in {elapsed:.1f}s")


if __name__ == "__main__":
    main()
