"""SFD parser — particle effect definitions (`.sfd`, the client's custom archive container).

Same in-house archive framing as `.skl` (see skl_parser's module docstring
for the container rules: NUL-terminated strings, `ffff <version> <len>
<name>` new-class tags, 0-based class back-references). `_Archive` is
reused as-is.

File layout (byte-walked against all 154 shipped files on 2026-09-05 —
every file ends exactly where this table says it ends):

    u8      object_type          (leading byte; 3 = polygon emitter,
                                  7 = billboard — must match the class)
    class tag                     (`SfCEmitterPolygon` or `SfCBillboard`;
                                  the tag's version is the SCHEMA the base
                                  object's layout follows — it VARIES per
                                  file: emitters 66x v2 + 52x v3,
                                  billboards 23x v2 + 13x v3)
    --- object base (every root) ---
    graph   opacity
    graph   color_r, color_g, color_b
    graph   texture_frame        (discrete: step function of 1-based
                                  texture ids; 0 = untextured)
    u8      object_type          (stored again)
    u8      texture_direction    (NONE 0, TOP 1, BOTTOM 2, LEFT 4, RIGHT 8)
    i32     n_textures
    n_textures * cstring texture names (resolve case-insensitively)
    [schema >= 2] f32 total_time          (else 1.0)
    [schema >= 3] i32 additive (a 4-byte bool)   (else TRUE — the default when absent)
    --- emitter_polygon only ---
    10 graphs: gravity, wind_x, wind_y, wind_z, wind_force, drag,
               blackhole_x, blackhole_y, blackhole_z, blackhole_force
    8 * f32   editor snapshot: net_force xyz, blackhole_pos xyz,
              blackhole_force, drag (runtime recomputes every frame)
    15 graphs: life, life_random, dir_x, dir_y, dir_z, speed, spread, rate,
               scale_t, scale_n, init_deg, init_deg_random, ang_vel,
               ang_vel_random, particle_opacity
    --- billboard only ---
    graph   width
    graph   height
    i32     alignment            (0 VIEWPLANE, 1 VIEWPOINT)

    graph = i32 count; count * (f32 time, f32 value, f32 c1, f32 c2)
            c1/c2 are the STORED line coefficients (value = c1*t + c2 on
            the segment starting at that point); the game evaluates the
            stored ones, never a recompute — 73/154 files store slopes
            that an equal-interval recompute would not reproduce.

Unshipped root types (plain object, dynamic, point/line/sprite emitters)
are rejected loudly: the fleet census is exactly 118 + 36.
"""
from dataclasses import dataclass, field
from pathlib import Path

from src.parsers.skl_parser import _Archive

ROOT_KINDS = {"SfCEmitterPolygon": "emitter_polygon", "SfCBillboard": "billboard"}
KIND_TYPE_BYTE = {"emitter_polygon": 3, "billboard": 7}

OBJECT_GRAPHS = ["opacity", "color_r", "color_g", "color_b"]
DYNAMIC_GRAPHS = ["gravity", "wind_x", "wind_y", "wind_z", "wind_force", "drag",
                  "blackhole_x", "blackhole_y", "blackhole_z", "blackhole_force"]
EMITTER_GRAPHS = ["life", "life_random", "dir_x", "dir_y", "dir_z", "speed",
                  "spread", "rate", "scale_t", "scale_n", "init_deg",
                  "init_deg_random", "ang_vel", "ang_vel_random",
                  "particle_opacity"]
BILLBOARD_GRAPHS = ["width", "height"]

_MAX_POINTS = 4096  # sanity bound; the fleet maximum is 16


@dataclass
class Graph:
    points: list[tuple[float, float, float, float]] = field(default_factory=list)


@dataclass
class SfxEffect:
    kind: str                     # "emitter_polygon" | "billboard"
    schema: int
    object_type: int
    texture_direction: int
    textures: list[str]
    total_time: float
    additive: bool
    graphs: dict[str, Graph]
    dynamic_state: list[float]    # 8 floats for emitters, [] for billboards
    alignment: int                # billboards: 0/1; emitters: -1


def _parse_graph(ar: _Archive) -> Graph:
    start = ar.pos
    n = ar.i32()
    if n < 0 or n > _MAX_POINTS:
        raise ar.fail(f"graph point count {n} out of range", start)
    return Graph([(ar.f32(), ar.f32(), ar.f32(), ar.f32()) for _ in range(n)])


def slope_mismatch(graph: Graph, rel_tol: float = 1e-3) -> bool:
    """Diagnostic only: does an equal-interval recompute of c1/c2 differ
    from the stored coefficients? (73/154 shipped files: yes.)"""
    pts = graph.points
    n = len(pts)
    if n <= 1:
        return False
    d = 1.0 / (n - 1)
    for i in range(n - 1):
        c1 = (pts[i + 1][1] - pts[i][1]) / d
        c2 = pts[i][1] - pts[i][0] * c1
        if abs(c1 - pts[i][2]) > rel_tol * max(1.0, abs(c1)):
            return True
        if abs(c2 - pts[i][3]) > rel_tol * max(1.0, abs(c2)):
            return True
    return False


def parse_sfd(path: Path | str) -> SfxEffect:
    path = Path(path)
    data = path.read_bytes()
    ar = _Archive(data, path=str(path))

    object_type = ar.u8()
    start = ar.pos
    class_name, schema = ar.read_class()
    if class_name not in ROOT_KINDS:
        raise ar.fail(f"unsupported .sfd root class {class_name!r} "
                      f"(fleet ships only SfCEmitterPolygon/SfCBillboard)", start)
    kind = ROOT_KINDS[class_name]
    if object_type != KIND_TYPE_BYTE[kind]:
        raise ar.fail(f"leading object type byte {object_type} does not match "
                      f"class {class_name!r} (expected {KIND_TYPE_BYTE[kind]})", 0)

    graphs: dict[str, Graph] = {}
    for key in OBJECT_GRAPHS:
        graphs[key] = _parse_graph(ar)
    graphs["texture_frame"] = _parse_graph(ar)
    stored_type = ar.u8()
    if stored_type != object_type:
        raise ar.fail(f"stored object type {stored_type} != leading byte {object_type}")
    texture_direction = ar.u8()
    n_tex = ar.i32()
    if n_tex < 0 or n_tex > 64:
        raise ar.fail(f"texture count {n_tex} out of range")
    textures = [ar.cstring() for _ in range(n_tex)]
    total_time = 1.0
    additive = True
    if schema >= 2:
        total_time = ar.f32()
    if schema >= 3:
        additive = ar.i32() != 0

    dynamic_state: list[float] = []
    alignment = -1
    if kind == "emitter_polygon":
        for key in DYNAMIC_GRAPHS:
            graphs[key] = _parse_graph(ar)
        dynamic_state = [ar.f32() for _ in range(8)]
        for key in EMITTER_GRAPHS:
            graphs[key] = _parse_graph(ar)
    else:
        for key in BILLBOARD_GRAPHS:
            graphs[key] = _parse_graph(ar)
        alignment = ar.i32()

    if ar.pos != len(data):
        raise ar.fail(f"{len(data) - ar.pos} trailing byte(s) after full parse")

    return SfxEffect(kind=kind, schema=schema, object_type=object_type,
                     texture_direction=texture_direction, textures=textures,
                     total_time=total_time, additive=additive, graphs=graphs,
                     dynamic_state=dynamic_state, alignment=alignment)
