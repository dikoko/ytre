#!/usr/bin/env python3
"""
Navmesh + Wall Grid Export Script (.nnn/.opg -> navmesh.bin/walls.bin)

Exports per-map navigation data for the Godot runtime (Task 4 reader):
navmesh.bin packs the flattened, FILE-ORDER navigation cells plus the
tile -> cell-index lookup from .nnn; walls.bin packs the .opg wall grid
as a flat byte array. Both blobs stay in ORIGINAL (D3D) space — no
coordinate conversion happens at export; the Godot side negates Z on
load like every other map asset.

Usage:
    python scripts/34_export_navmesh.py
    python scripts/34_export_navmesh.py SF001001
    python scripts/34_export_navmesh.py --dry-run

Blob formats (little-endian):
  navmesh.bin: b"YTNV", uint32 version=1, uint32 cell_count,
    cell_count x 13 float32 (nx, ny, nz, d, x0, y0, z0, x1, y1, z1,
    x2, y2, z2), uint32 tile_count, per tile: uint16 x, uint16 z,
    uint16 n, n x uint32 cell_index.
  walls.bin: b"YTWL", uint32 version=1, uint16 width, uint16 height,
    width*height bytes (row 0 == world Z 0, per opg_parser).
  move.bin: b"YTMV", uint32 version=1, uint16 width, uint16 height,
    width*height SIGNED attribute bytes (row 0 == world Z 0, per
    map_parser; movable iff signed value > 0 — the original's movement
    authority — the grid the original client's pathfinder walks).

Files are NOT written when the source is empty/absent: an empty .nnn
(zero cells — 49/325 shipped maps) writes no navmesh.bin; a missing
.opg writes no walls.bin; a missing .map writes no move.bin.
"""
import argparse
import struct
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.parsers.nnn_parser import parse_nnn, NavMesh
from src.parsers.opg_parser import parse_opg, WallGrid
from src.parsers.map_parser import parse_map, MoveGrid

YTREF_ROOT = PROJECT_ROOT.parent.parent / "refs"
MAP_IRD = YTREF_ROOT / "models" / "raw" / "Terrain" / "Map.IRD"

CLIENT_DIR = PROJECT_ROOT.parent.parent / "ytlevel" / "client"
OUTPUT_DIR = CLIENT_DIR / "assets" / "maps"

NAVMESH_MAGIC = b"YTNV"
WALLS_MAGIC = b"YTWL"
MOVE_MAGIC = b"YTMV"
FORMAT_VERSION = 1


def _pack_navmesh(nav: NavMesh) -> bytes:
    """Serialize nav's cells + tile index. Pure function so --dry-run can
    report the real byte count without touching the filesystem."""
    parts = [NAVMESH_MAGIC, struct.pack("<II", FORMAT_VERSION, len(nav.cells))]
    for cell in nav.cells:
        nx, ny, nz = cell.normal
        (x0, y0, z0), (x1, y1, z1), (x2, y2, z2) = cell.verts
        parts.append(struct.pack("<13f", nx, ny, nz, cell.d,
                                  x0, y0, z0, x1, y1, z1, x2, y2, z2))
    parts.append(struct.pack("<I", len(nav.tiles)))
    for (tx, tz), cell_indices in nav.tiles.items():
        parts.append(struct.pack("<3H", tx, tz, len(cell_indices)))
        for idx in cell_indices:
            parts.append(struct.pack("<I", idx))
    return b"".join(parts)


def _pack_walls(grid: WallGrid) -> bytes:
    """Serialize grid's dims + flat cell bytes. Pure function, see
    `_pack_navmesh`."""
    return (WALLS_MAGIC + struct.pack("<I", FORMAT_VERSION)
            + struct.pack("<2H", grid.width, grid.height) + bytes(grid.cells))


def _pack_move(grid: MoveGrid) -> bytes:
    """Serialize grid's dims + flat SIGNED attribute bytes. Pure function,
    see `_pack_navmesh`."""
    return (MOVE_MAGIC + struct.pack("<I", FORMAT_VERSION)
            + struct.pack("<2H", grid.width, grid.height) + grid.attrs)


def write_navmesh_blob(nav: NavMesh, path: Path) -> int:
    """Write nav's cells + tile index to `path`. Returns bytes written."""
    data = _pack_navmesh(nav)
    path.write_bytes(data)
    return len(data)


def write_walls_blob(grid: WallGrid, path: Path) -> int:
    """Write grid's dims + flat cell bytes to `path`. Returns bytes written."""
    data = _pack_walls(grid)
    path.write_bytes(data)
    return len(data)


def write_move_blob(grid: MoveGrid, path: Path) -> int:
    """Write grid's dims + flat attribute bytes to `path`. Returns bytes
    written."""
    data = _pack_move(grid)
    path.write_bytes(data)
    return len(data)


def export_map(code: str, out_dir: Path = OUTPUT_DIR, dry_run: bool = False) -> dict:
    """Export {code}'s navmesh.bin and walls.bin. Returns {"navmesh": bytes,
    "walls": bytes, "cells": int}: navmesh/walls is 0 when the source was
    empty/absent and nothing was written — for --dry-run this is the byte
    count that WOULD be written, computed the same way as a real write, not
    a sentinel; cells is the navmesh cell count regardless of dry_run."""
    result = {"navmesh": 0, "walls": 0, "move": 0, "cells": 0}
    map_dir = MAP_IRD / code

    nnn_path = map_dir / f"{code}.nnn"
    nav = parse_nnn(nnn_path) if nnn_path.exists() else None

    opg_path = map_dir / f"{code}.opg"
    grid = parse_opg(opg_path) if opg_path.exists() else None

    map_path = map_dir / f"{code}.map"
    move = parse_map(map_path) if map_path.exists() else None

    has_navmesh = nav is not None and nav.cells
    if has_navmesh or grid is not None or move is not None:
        if not dry_run:
            (out_dir / code).mkdir(parents=True, exist_ok=True)

    if has_navmesh:
        result["cells"] = len(nav.cells)
        if dry_run:
            result["navmesh"] = len(_pack_navmesh(nav))
        else:
            result["navmesh"] = write_navmesh_blob(nav, out_dir / code / "navmesh.bin")

    if grid is not None:
        if dry_run:
            result["walls"] = len(_pack_walls(grid))
        else:
            result["walls"] = write_walls_blob(grid, out_dir / code / "walls.bin")

    if move is not None:
        if dry_run:
            result["move"] = len(_pack_move(move))
        else:
            result["move"] = write_move_blob(move, out_dir / code / "move.bin")

    return result


def _included_map_codes() -> list[str]:
    """Same inclusion rule as the level catalog (33_export_levels.py): a
    real Map.IRD/{code}/ folder with a `.qqq` file present."""
    codes = []
    for d in sorted(MAP_IRD.iterdir()):
        if d.is_dir() and (d / f"{d.name}.qqq").exists():
            codes.append(d.name)
    return codes


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export navmesh + wall grid blobs for one map or every map")
    parser.add_argument("map_code", nargs="?",
                         help="Export only this map (default: every map with a .qqq)")
    parser.add_argument("--dry-run", action="store_true",
                         help="Parse and summarize without writing any files")
    args = parser.parse_args()

    codes = [args.map_code] if args.map_code else _included_map_codes()

    # Validate that a positional map code exists
    if args.map_code:
        map_dir = MAP_IRD / args.map_code
        if not map_dir.exists():
            print(f"ERROR: Map directory not found: {map_dir}")
            sys.exit(1)

    navmesh_count = 0
    navmesh_cells_total = 0
    walls_count = 0
    move_count = 0
    no_navmesh_count = 0
    error_count = 0

    for code in codes:
        try:
            result = export_map(code, dry_run=args.dry_run)
        except Exception as e:
            print(f"ERROR: {code}: {e}")
            error_count += 1
            continue
        wrote_navmesh = result["navmesh"] > 0
        wrote_walls = result["walls"] > 0
        if wrote_navmesh:
            navmesh_count += 1
            navmesh_cells_total += result["cells"]
        else:
            no_navmesh_count += 1
        if wrote_walls:
            walls_count += 1
        if result["move"] > 0:
            move_count += 1
        if args.map_code:
            print(f"{code}: navmesh={result['navmesh']} bytes "
                  f"({result['cells']} cells), walls={result['walls']} bytes, "
                  f"move={result['move']} bytes")

    summary = (f"navmeshes: {navmesh_count} ({navmesh_cells_total} cells total), "
               f"walls: {walls_count}, move: {move_count}, "
               f"no-navmesh: {no_navmesh_count}")
    if error_count:
        summary += f", errors: {error_count}"
    print(summary)

    if args.dry_run:
        print("Dry run — no files written.")

    if error_count:
        sys.exit(1)


if __name__ == "__main__":
    main()
