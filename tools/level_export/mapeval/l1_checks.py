"""L1 convention checks — pure-data validation against retail client semantics.

Invariants of the original map editor's tile fringe solver:
- layer 0 of every palette combo is a full tile (index == 0xF)
  (the .cvs writer forces this)
- fringe layers (index != 0xF) have opt == 0 (the solver sets opt=0 on partials)
- no two layers of one combo share a kind (the solver merges same-kind layers)
"""
import numpy as np

from src.parsers.cvs_parser import CVSParser
from src.parsers.heightmap_bmp import decode_height_bmp, heights_from_values
from src.parsers.nnn_parser import parse_nnn, is_standable
from src.parsers.qqq_parser import QQQParser
from src.parsers.tcg_parser import TCGParser
from scripts._tile_compositor import _resolve_tile_texture
from mapeval.paths import MAP_IRD, TILE_IRD, TCG_PATH, CLIENT_DIR


def tile_fields(tile_id: int) -> tuple[int, int, int]:
    """(kind, index, opt) per the tile-id bit layout."""
    return (tile_id >> 8) & 0xFF, (tile_id >> 4) & 0xF, tile_id & 0xF


def check_cvs_invariants(canvas) -> dict:
    layer0_not_full = 0
    fringe_with_opt = 0
    duplicate_kind_layers = 0
    violations = []
    for i, entry in enumerate(canvas.palette):
        kinds = []
        for li, tid in enumerate(entry):
            if tid == 0:
                continue
            kind, index, opt = tile_fields(tid)
            kinds.append(kind)
            # layer 0 forced to full tile (index 0xF) by the .cvs writer
            if li == 0 and index != 0xF:
                layer0_not_full += 1
                violations.append(f"combo {i} layer0 index=0x{index:X}")
            # partial-corner layers get opt=0 from the editor's fringe solver
            if index != 0xF and opt != 0:
                fringe_with_opt += 1
                violations.append(f"combo {i} layer{li} fringe opt={opt}")
        # the fringe solver merges same-kind layers, so kinds are unique per combo
        if len(kinds) != len(set(kinds)):
            duplicate_kind_layers += 1
            violations.append(f"combo {i} duplicate kinds {kinds}")
    return {
        "palette_count": len(canvas.palette),
        "layer0_not_full": layer0_not_full,
        "fringe_with_opt": fringe_with_opt,
        "duplicate_kind_layers": duplicate_kind_layers,
        "violations": violations,
    }


def check_det_census(map_data) -> dict:
    items = map_data.objects + map_data.portals + map_data.triggers
    negative_ids = []
    for o in items:
        m = np.array(o.transform).reshape(4, 4)
        if np.linalg.det(m[:3, :3]) < 0:
            negative_ids.append(int(o.unique_id))
    # Informational only: negative-determinant placements are supported
    # (instanced as {model}_mirrorx.glb by 30_export_map since 2026-07-12).
    return {"total": len(items), "negative": len(negative_ids),
            "negative_ids": negative_ids, "violations": []}


def check_texture_resolution(canvas, registry) -> dict:
    """Violations = nonzero kinds absent from the registry (uninterpretable).

    Kind-0x00 ids (the original renderer treats them as an empty layer
    regardless of index/opt bits) and referenced tiles with no art
    (the original renderer silently skips them)
    are legal shipped data — counted informationally, not violations.
    """
    unresolved = []
    skipped_missing = 0
    for i, entry in enumerate(canvas.palette):
        for li, tid in enumerate(entry):
            if not tid:
                continue
            kind = (tid >> 8) & 0xFF
            if kind == 0:
                continue
            if kind not in registry.tile_sets:
                unresolved.append({"combo": i, "layer": li, "tile_id": f"0x{tid:04X}"})
            elif _resolve_tile_texture(tid, registry, TILE_IRD) is None:
                skipped_missing += 1
    return {"unresolved": unresolved, "skipped_missing_art": skipped_missing,
            "violations": unresolved}


# Navmesh cells legitimately sit ABOVE terrain (walkable prop floors — some
# FD maps have most of their navmesh 4-8 m up on structures), so absolute
# error is the wrong discriminator. Cells firmly BELOW the visible ground are
# physically impossible in healthy data: fleet-wide the 10th percentile of
# (navmesh - terrain) never drops under -1.34 m, while the SF002001 16bpp
# decode bug measured -11.3 m. -3.0 m splits the populations with wide margin.
HEIGHT_BELOW_P10_MIN = -3.0
HEIGHT_AGREE_MIN_CELLS = 50


def _heightmap_lerp(H: np.ndarray, x: float, z: float) -> float:
    """The original client's per-cell diagonal-split triangle lerp."""
    rows, cols = H.shape
    cx = min(max(int(x), 0), cols - 2)
    cz = min(max(int(z), 0), rows - 2)
    dx, dz = x - cx, z - cz
    h00, h10 = H[cz, cx], H[cz, cx + 1]
    h01, h11 = H[cz + 1, cx], H[cz + 1, cx + 1]
    if dx <= dz:
        return h00 + (h01 - h00) * (dz - dx) + (h11 - h01) * dx
    return h00 + (h10 - h00) * (dx - dz) + (h11 - h10) * dz


def check_heightmap(map_code: str) -> dict:
    """Height decode validation (added after the SF002001 16bpp bug).

    Two layers:
    - png_matches_bmp: the exported viewer PNG (RG16: R=high byte, G=low
      byte) must decode bit-exact to the original {code}_h.bmp via the
      retail decode rules (8bpp index bytes / 16bpp first-byte-high).
      Catches any future conversion regression deterministically.
    - navmesh agreement: signed (navmesh cell height - heightmap surface)
      over standable .nnn cells. The navmesh is an independent height
      source; a decode/orientation/stride error pushes a large share of
      cells UNDER the visible ground, which healthy data never does.
    """
    bmp_path = MAP_IRD / map_code / f"{map_code}_h.bmp"
    png_path = CLIENT_DIR / "assets" / "maps" / map_code / f"{map_code}.png"
    violations = []
    result = {"bpp": None, "png_matches_bmp": None, "navmesh_cells": 0,
              "median_navmesh_err": None, "below_terrain_p10": None,
              "violations": violations}
    if not bmp_path.is_file():
        return result
    import struct as _struct
    result["bpp"] = _struct.unpack_from(
        "<H", bmp_path.read_bytes()[:30], 28)[0]
    values = decode_height_bmp(bmp_path)

    if png_path.is_file():
        from PIL import Image
        arr = np.asarray(Image.open(png_path).convert("RGB")).astype(np.uint16)
        decoded = (arr[:, :, 0] << 8) | arr[:, :, 1]
        result["png_matches_bmp"] = bool(
            decoded.shape == values.shape and np.array_equal(decoded, values))
        if not result["png_matches_bmp"]:
            violations.append("exported PNG does not decode to the BMP heights")
    else:
        violations.append("no exported heightmap PNG")

    nnn_path = MAP_IRD / map_code / f"{map_code}.nnn"
    if nnn_path.is_file():
        H = heights_from_values(values)
        rows, cols = H.shape
        errs = []
        for cell in parse_nnn(nnn_path).cells:
            if not is_standable(cell):
                continue
            cx = sum(v[0] for v in cell.verts) / 3.0
            cz = sum(v[2] for v in cell.verts) / 3.0
            if not (0 <= cx < cols - 1 and 0 <= cz < rows - 1):
                continue
            nx, ny, nz = cell.normal
            cell_h = -(nx * cx + nz * cz + cell.d) / ny
            errs.append(cell_h - _heightmap_lerp(H, cx, cz))
        result["navmesh_cells"] = len(errs)
        if len(errs) >= HEIGHT_AGREE_MIN_CELLS:
            result["median_navmesh_err"] = float(np.median(np.abs(errs)))
            p10 = float(np.percentile(errs, 10))
            result["below_terrain_p10"] = p10
            if p10 < HEIGHT_BELOW_P10_MIN:
                violations.append(
                    "navmesh sinks below the heightmap surface "
                    f"(p10 {p10:.2f} m) — height decode suspect")
    return result


def run_l1(map_code: str) -> dict:
    map_dir = MAP_IRD / map_code
    canvas = CVSParser().parse(map_dir / f"{map_code}.cvs")
    registry = TCGParser().parse(TCG_PATH)
    map_data = QQQParser().parse(map_dir / f"{map_code}.qqq")
    return {
        "cvs_invariants": check_cvs_invariants(canvas),
        "det_census": check_det_census(map_data),
        "texture_resolution": check_texture_resolution(canvas, registry),
        "heightmap": check_heightmap(map_code),
    }
