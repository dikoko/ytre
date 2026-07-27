#!/usr/bin/env python3
"""
Heightmap PNG Export Script

Regenerates the per-map viewer heightmap PNG (client/assets/maps/{code}/
{code}.png) from the original {code}_h.bmp, using the RG16 encoding
(R = high byte, G = low byte; see src/parsers/heightmap_bmp.py). The same
conversion runs inside 30_export_map.py — this script exists to sweep the
already-exported fleet without re-assembling every map scene.

Usage:
    python scripts/35_export_heightmaps.py --all
    python scripts/35_export_heightmaps.py SF002001 SF001008
"""
import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.parsers.heightmap_bmp import decode_height_bmp, write_height_png

YTREF_ROOT = PROJECT_ROOT.parent.parent / "refs"
MAP_IRD = YTREF_ROOT / "models" / "raw" / "Terrain" / "Map.IRD"
CLIENT_MAPS = PROJECT_ROOT.parent.parent / "ytlevel" / "client" / "assets" / "maps"


def export_heightmap(map_code: str) -> bool:
    bmp = MAP_IRD / map_code / f"{map_code}_h.bmp"
    dest_dir = CLIENT_MAPS / map_code
    if not bmp.is_file():
        print(f"  {map_code}: no height BMP — skipped")
        return False
    if not dest_dir.is_dir():
        print(f"  {map_code}: map not exported (no {dest_dir.name}/ assets) — skipped")
        return False
    write_height_png(decode_height_bmp(bmp), dest_dir / f"{map_code}.png")
    return True


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("codes", nargs="*", help="map codes (e.g. SF002001)")
    ap.add_argument("--all", action="store_true",
                    help="sweep every exported map with a height BMP")
    args = ap.parse_args()
    if args.all:
        codes = sorted(d.name for d in CLIENT_MAPS.iterdir() if d.is_dir())
    elif args.codes:
        codes = args.codes
    else:
        ap.error("give map codes or --all")
    done = sum(export_heightmap(c) for c in codes)
    print(f"Exported {done}/{len(codes)} heightmap PNGs")


if __name__ == "__main__":
    main()
