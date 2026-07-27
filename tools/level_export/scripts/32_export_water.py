#!/usr/bin/env python3
"""
Water Export Script (.wtr -> water.json + shared textures)

Exports per-map water data for the runtime loader (water_loader.gd):
meshes in Godot space (positions z-negated, triangles rewound, baked
vertex colors), per-region render params (textures, anim coefficients),
and converts the fleet-wide Water.IRD textures once into
client/assets/water/.

Usage:
    python scripts/32_export_water.py SF001001
    python scripts/32_export_water.py --all
"""

import argparse
import json
import sys
from pathlib import Path

from PIL import Image

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.parsers.wtr_parser import WTRParser, strip_to_triangles

YTREF_ROOT = PROJECT_ROOT.parent.parent / "refs"
MAP_IRD = YTREF_ROOT / "models" / "raw" / "Terrain" / "Map.IRD"
WATER_IRD = YTREF_ROOT / "models" / "raw" / "Terrain" / "Object" / "Water.IRD"
CLIENT_DIR = PROJECT_ROOT.parent.parent / "ytlevel" / "client"
OUTPUT_DIR = CLIENT_DIR / "assets" / "maps"
WATER_TEX_DIR = CLIENT_DIR / "assets" / "water"

# Only 5 textures exist fleet-wide; Korean stems get ASCII-safe names.
_STEM_MAP = {"파도": "pado"}


def _safe_stem(name: str) -> str:
    stem = Path(name).stem
    for src, dst in _STEM_MAP.items():
        stem = stem.replace(src, dst)
    return "".join(c if c.isascii() else "_" for c in stem).lower()


def ensure_water_textures() -> list[Path]:
    """Convert the Water.IRD surface textures to PNG in client/assets/water.

    Only the .tga files — the 5 textures any .wtr references fleet-wide.
    The FF00x0.BMP frame sequence + WATERANI.TXT are the beach/shore wave
    animation (Tier 2), never referenced by .wtr texture lists.
    """
    WATER_TEX_DIR.mkdir(parents=True, exist_ok=True)
    written = []
    for src in sorted(WATER_IRD.iterdir()):
        if src.suffix.lower() != ".tga":
            continue
        dst = WATER_TEX_DIR / f"{_safe_stem(src.name)}.png"
        if not dst.exists():
            Image.open(src).convert("RGBA").save(dst)
        written.append(dst)
    return written


def _mesh_to_json(mesh, vertices) -> dict:
    positions, normals, colors, uvs = [], [], [], []
    for v in vertices:
        x, y, z = v.position
        nx, ny, nz = v.normal
        positions += [x, y, -z]
        normals += [nx, ny, -nz]
        a = (v.diffuse >> 24) & 0xFF
        r = (v.diffuse >> 16) & 0xFF
        g = (v.diffuse >> 8) & 0xFF
        b = v.diffuse & 0xFF
        colors += [r / 255, g / 255, b / 255, a / 255]
        uvs += list(v.uv1)

    indices = []
    for a_i, b_i, c_i in strip_to_triangles(mesh.strip_indices):
        # Same convention as props: after z-negation every mesh is one
        # Z-mirror from D3D world -> uniformly reversed winding.
        indices += [a_i, c_i, b_i]

    return {"positions": positions, "normals": normals, "colors": colors,
            "uvs": uvs, "indices": indices}


def _vec3s_to_json(vecs) -> list[float]:
    """Flatten (x, y, z) triples into Godot space (z negated). Applies to
    beach positions AND the N/U direction vectors alike."""
    out = []
    for x, y, z in vecs:
        out += [x, y, -z]
    return out


def export_water(map_code: str, out_root: Path = OUTPUT_DIR) -> Path | None:
    """Parse {map}.wtr and write {out_root}/{map}/water.json.

    Returns the json path, or None when the map has no .wtr.
    """
    map_dir = MAP_IRD / map_code
    wtr = next(map_dir.glob("*.wtr"), None) if map_dir.is_dir() else None
    if wtr is None:
        return None

    info = WTRParser().parse(wtr)
    tex_paths = [
        f"res://assets/water/{_safe_stem(t)}.png" for t in info.textures
    ]

    # Indices are into the shared vertex pool; each mesh entry carries the
    # full (tiny — fleet max 104 verts) pool so the loader can build each
    # surface from one dict.
    data = {
        "textures": tex_paths,
        "beach": {
            "size_u": info.beach_size_u,
            "size_n": info.beach_size_n,
            "delta": info.beach_delta,
            "frequency": info.beach_frequency,
            "velocity": info.beach_velocity,
            "life": info.beach_life,
            "texture_ids": list(info.beach_texture_ids),
        },
        "meshes": [_mesh_to_json(m, info.vertices) for m in info.meshes],
        "side_meshes": [
            _mesh_to_json(m, info.side_vertices) for m in info.side_meshes
        ],
        "objects": [
            {
                "type": o.type,
                "texture0": o.texture0,
                "texture1": o.texture1,
                "side_texture0": o.side_texture0,
                "side_texture1": o.side_texture1,
                "water_height": o.water_height,
                "fog_color": o.fog_color,
                "mesh_ids": o.mesh_ids,
                "side_mesh_ids": o.side_mesh_ids,
                "mat_info": o.mat_info,
                "beach_points": {
                    "normals": _vec3s_to_json(o.beach_normals),
                    "us": _vec3s_to_json(o.beach_us),
                    "positions": _vec3s_to_json(o.beach_positions),
                },
            }
            for o in info.water_objects
        ],
    }

    out_dir = out_root / map_code
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "water.json"
    out_path.write_text(json.dumps(data))
    return out_path


def main() -> None:
    ap = argparse.ArgumentParser(description="Export map water to water.json")
    ap.add_argument("map_code", nargs="?", help="Map code, e.g., SF001001")
    ap.add_argument("--all", action="store_true", help="Export all maps with .wtr")
    args = ap.parse_args()

    ensure_water_textures()

    codes = ([args.map_code] if args.map_code
             else sorted(d.name for d in MAP_IRD.iterdir()
                         if d.is_dir() and next(d.glob("*.wtr"), None)))
    if not codes:
        ap.print_help()
        sys.exit(1)

    done = 0
    for code in codes:
        out = export_water(code)
        if out is not None:
            done += 1
            print(f"  OK {code}: {out}")
        else:
            print(f"  -- {code}: no .wtr")
    print(f"Done: {done}/{len(codes)} water exports")


if __name__ == "__main__":
    main()
