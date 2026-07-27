"""Map compatibility classifier.

Answers "can the current pipeline export this map?" by parsing the map's
binary data and checking it against pipeline capabilities. Used by the
sweep driver (40_sweep_maps.py) to decide which maps to export and to
record concrete blockers for the rest.

Blocker kinds:
    no_data                 - map folder missing or lacks .qqq/.ocg/.cvs
    point_lights            - .plt carries point-light records (parser not implemented)
    missing_glbs            - .ocg references models with no exported GLB
    tile_texture_failures   - .cvs combos reference tile kinds the registry
                              cannot resolve to textures
    cvs_violations          - .cvs breaks authoring invariants
    parse_error:<file>      - a parser raised unexpectedly
"""
import importlib
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.parsers.plt_parser import PLTParser
from src.parsers.qqq_parser import QQQParser
from src.parsers.ocg_parser import OCGParser
from src.parsers.cvs_parser import CVSParser
from src.parsers.tcg_parser import TCGParser
from mapeval.l1_checks import check_cvs_invariants, check_texture_resolution

_export_map = importlib.import_module("scripts.30_export_map")

YTREF_ROOT = PROJECT_ROOT.parent.parent / "refs"
MAP_IRD = YTREF_ROOT / "models" / "raw" / "Terrain" / "Map.IRD"
TILE_IRD = YTREF_ROOT / "models" / "raw" / "Terrain" / "Tile.IRD"
PROPS_DIR = PROJECT_ROOT.parent.parent / "ytlevel" / "client" / "assets" / "props" / "models"

_registry = None


def _tile_registry():
    global _registry
    if _registry is None:
        _registry = TCGParser().parse(TILE_IRD / "tileregistry.tcg")
    return _registry


def _find(map_dir: Path, suffix: str) -> Path | None:
    for f in map_dir.iterdir():
        if f.name.lower().endswith(suffix):
            return f
    return None


def list_map_codes() -> list[str]:
    """All map folder names in Map.IRD, sorted."""
    return sorted(d.name for d in MAP_IRD.iterdir() if d.is_dir())


def classify_map(map_code: str) -> dict:
    """Classify one map. Returns {"blockers": [...], "detail": {...}}."""
    blockers: list[str] = []
    detail: dict = {}

    map_dir = MAP_IRD / map_code
    if not map_dir.is_dir():
        return {"blockers": ["no_data"], "detail": {}}

    qqq = _find(map_dir, ".qqq")
    ocg = _find(map_dir, ".ocg")
    cvs = _find(map_dir, ".cvs")
    plt = _find(map_dir, ".plt")
    if not all([qqq, ocg, cvs]):
        return {"blockers": ["no_data"], "detail": {}}

    # .plt — sun + point lights (both supported since 2026-07-16)
    detail["point_lights"] = 0
    if plt is not None:
        try:
            settings = PLTParser().parse(plt)
            detail["point_lights"] = settings.point_light_count
        except Exception as e:
            blockers.append("parse_error:plt")
            detail["plt_error"] = f"{type(e).__name__}: {e}"

    # .ocg — unresolvable refs are informational, not blockers: they
    # rendered NOTHING in the original client (unknown category -> object
    # skipped; missing/misnamed TMD -> the exact-name IRD lookup fails and
    # the object loads into an empty renderer). 30_export_map skips them
    # the same way.
    try:
        entries = OCGParser().parse(ocg)
        missing = [
            f"{e.category}/{e.model_name}"
            for e in entries
            if _export_map.resolve_glb_path(e, PROPS_DIR) is None
        ]
        detail["models_total"] = len(entries)
        detail["models_missing"] = missing
    except Exception as e:
        blockers.append("parse_error:ocg")
        detail["ocg_error"] = f"{type(e).__name__}: {e}"

    # .qqq — placement quadtree must parse
    try:
        QQQParser().parse(qqq)
    except Exception as e:
        blockers.append("parse_error:qqq")
        detail["qqq_error"] = f"{type(e).__name__}: {e}"

    # .cvs — authoring invariants + tile texture resolution
    try:
        canvas = CVSParser().parse(cvs)
        detail["grid"] = [canvas.grid_rows, canvas.grid_cols]
        inv = check_cvs_invariants(canvas)["violations"]
        tex = check_texture_resolution(canvas, _tile_registry())["violations"]
        detail["cvs_violations"] = inv
        detail["tile_texture_failures"] = tex
        if inv:
            blockers.append("cvs_violations")
        if tex:
            blockers.append("tile_texture_failures")
    except Exception as e:
        blockers.append("parse_error:cvs")
        detail["cvs_error"] = f"{type(e).__name__}: {e}"

    return {"blockers": blockers, "detail": detail}
