#!/usr/bin/env python3
# tools/avatar_export/scripts/48_export_sfx.py
"""Particle-effect exporter (`.sfd` fleet -> sfx.json + textures + random
tables + the random-helper parity fixture).

Outputs (under --out-dir, default client/assets):
  effects/sfx.json           one entry per .sfd (raw control points, ORIGINAL
                             D3D space — the Godot side converts at load)
  effects/sfx_random.json    the two shipped random tables (ints, floats)
  effects/sfx_textures/      all 143 shipped .tga copied with LOWERCASE
                             names + a .gdignore (loaded raw at runtime via
                             Image.load_tga_from_buffer, never imported)
  --parity-out (default client/scripts/tests/fixtures/sfx_random_parity.json)
                             fixture replayed by test_sfx_random.gd

A file that fails to parse lands in sfx.json's `errors` map and does not
abort the export (spec §5). Texture refs that do not resolve (case-
insensitively) land in the entry's `missing_textures` (spec §5).

Usage:
    python scripts/48_export_sfx.py
    python scripts/48_export_sfx.py --out-dir /tmp/out --parity-out /tmp/p.json
    python scripts/48_export_sfx.py --dry-run
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.parsers.sfd_parser import SfxEffect, parse_sfd, slope_mismatch
from src.sfx_random_ref import SfxRandomRef, build_parity, load_tables

YTREF_ROOT = PROJECT_ROOT.parent.parent / "refs"
SKILL_IRD = YTREF_ROOT / "models" / "raw" / "Skill.IRD"
SFD_DIR = SKILL_IRD / "SFD"
TEXTURE_DIR = SKILL_IRD / "SFDTexture"
INT_TABLE = SKILL_IRD / "intrand.dat"
FLOAT_TABLE = SKILL_IRD / "floatrand.dat"

CLIENT_DIR = PROJECT_ROOT.parent.parent / "ytavatar" / "client"
DEFAULT_OUT_DIR = CLIENT_DIR / "assets"
DEFAULT_PARITY_OUT = CLIENT_DIR / "scripts" / "tests" / "fixtures" / "sfx_random_parity.json"

FORMAT_VERSION = 1


def discover_sfd_files() -> list[Path]:
    return sorted(SFD_DIR.glob("*.sfd"))


def texture_index() -> dict[str, Path]:
    """lowercase name -> on-disk path (9 shipped files have uppercase .TGA)."""
    return {p.name.lower(): p for p in TEXTURE_DIR.iterdir() if p.is_file()}


def resolve_texture(name: str, index: dict[str, Path]) -> Path | None:
    return index.get(name.lower())


def effect_to_json(effect: SfxEffect, index: dict[str, Path]) -> dict:
    textures = [t.lower() for t in effect.textures]
    missing = [t for t in textures if resolve_texture(t, index) is None]
    entry = {
        "kind": effect.kind,
        "schema": effect.schema,
        "textures": textures,
        "missing_textures": missing,
        "texture_direction": effect.texture_direction,
        "additive": effect.additive,
        "total_time": effect.total_time,
        "alignment": effect.alignment,
        "dynamic_state": effect.dynamic_state,
    }
    for key, graph in effect.graphs.items():
        entry[key] = {"points": [list(p) for p in graph.points]}
    return entry


def export_sfx(out_dir: Path, parity_out: Path, dry_run: bool = False) -> dict:
    index = texture_index()
    effects: dict[str, dict] = {}
    errors: dict[str, str] = {}
    mismatch = 0
    for path in discover_sfd_files():
        stem = path.stem.lower()
        try:
            effect = parse_sfd(path)
        except Exception as e:  # noqa: BLE001 — per-file error entry, keep going
            errors[stem] = str(e)
            continue
        effects[stem] = effect_to_json(effect, index)
        if any(slope_mismatch(g) for g in effect.graphs.values()):
            mismatch += 1

    ints, floats = load_tables(INT_TABLE, FLOAT_TABLE)
    parity = build_parity(SfxRandomRef(ints, floats))

    if not dry_run:
        effects_dir = out_dir / "effects"
        tex_out = effects_dir / "sfx_textures"
        tex_out.mkdir(parents=True, exist_ok=True)
        for lower, src in sorted(index.items()):
            dest = tex_out / lower
            if not dest.exists():
                shutil.copy2(src, dest)
        (tex_out / ".gdignore").write_text("")
        with (effects_dir / "sfx.json").open("w", encoding="utf-8") as f:
            json.dump({"version": FORMAT_VERSION, "effects": effects, "errors": errors},
                      f, indent=1, sort_keys=True)
        with (effects_dir / "sfx_random.json").open("w", encoding="utf-8") as f:
            json.dump({"version": 1, "ints": ints, "floats": floats}, f)
        parity_out.parent.mkdir(parents=True, exist_ok=True)
        parity_out.write_text(json.dumps(parity, indent=1), encoding="utf-8")

    return dict(total=len(effects) + len(errors), errors=len(errors),
                missing_texture_effects=sum(1 for e in effects.values() if e["missing_textures"]),
                textures=len(index), slope_mismatch_files=mismatch)


def main() -> None:
    ap = argparse.ArgumentParser(description="Export the .sfd fleet to sfx.json + textures + random tables")
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    ap.add_argument("--parity-out", type=Path, default=DEFAULT_PARITY_OUT)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    r = export_sfx(args.out_dir, args.parity_out, dry_run=args.dry_run)
    print(f"{r['total']} effects, errors: {r['errors']}, "
          f"missing-texture effects: {r['missing_texture_effects']}, "
          f"textures: {r['textures']}, slope-mismatch files: {r['slope_mismatch_files']}")
    if args.dry_run:
        print("Dry run — no files written.")
    if r["errors"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
