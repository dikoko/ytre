"""Reference (Python) mirror of the original particle library's random
helpers — spec §3.3. The original never calls rand(): it walks two
pre-recorded tables (Skill.IRD/intrand.dat: 10,000 int32 in [2, 32763];
floatrand.dat: 10,000 float64 in (0,1), cast to float32 on load) with two
global cursors that wrap at the table length. Every formula here is the
contract the GDScript port (client/scripts/sfx_random.gd) must reproduce;
`build_parity` writes the fixture that port replays.

Draw order inside one particle spawn (the order the original client
consumes the tables — an evaluation-order detail the shipped data alone
cannot confirm, see spec §8): random_direction first (1 float for the cone
angle, then the tangent vector's z, y, x = 3 ints), then ang_vel (1 int),
init_deg (1 int), life (1 float).
"""
import math
import struct
from pathlib import Path

RAND_MAX = 32767
ANGLE_360 = 65536
ANGLE_1 = ANGLE_360 // 360   # 182 — integer division, the original's angle unit


def load_tables(int_path: Path, float_path: Path) -> tuple[list[int], list[float]]:
    ib = Path(int_path).read_bytes()
    _itype, inum = struct.unpack_from("<ii", ib, 0)
    ints = list(struct.unpack_from(f"<{inum}i", ib, 8))
    fb = Path(float_path).read_bytes()
    _ftype, fnum = struct.unpack_from("<ii", fb, 0)
    doubles = struct.unpack_from(f"<{fnum}d", fb, 8)
    # the original stores (float)double — round through float32 once
    floats = [struct.unpack("<f", struct.pack("<f", d))[0] for d in doubles]
    return ints, floats


def deg_units(x: float) -> int:
    """The original's float-to-angle conversion: (unsigned short)(x * 182) — truncate toward zero, wrap."""
    return int(x * ANGLE_1) & 0xFFFF


def sin_units(u: int) -> float:
    return math.sin((u & 0xFFFF) * 2.0 * math.pi / ANGLE_360)


def cos_units(u: int) -> float:
    return math.cos((u & 0xFFFF) * 2.0 * math.pi / ANGLE_360)


class SfxRandomRef:
    def __init__(self, ints: list[int], floats: list[float]):
        self.ints = ints
        self.floats = floats
        self.ii = 0
        self.fi = 0

    def reset(self) -> None:
        self.ii = 0
        self.fi = 0

    def irand(self) -> int:
        v = self.ints[self.ii]
        self.ii = (self.ii + 1) % len(self.ints)
        return v

    def frand(self) -> float:
        v = self.floats[self.fi]
        self.fi = (self.fi + 1) % len(self.floats)
        return v

    def random_float(self, base: float, spread: float) -> float:
        half = RAND_MAX * 0.5
        return base + spread * ((self.irand() - half) / half)

    def random_life(self, life_max: float, life_random: float) -> float:
        life_max = abs(life_max)
        life_random = abs(life_random)
        if life_random > life_max:
            life_random = life_max
        return life_max - self.frand() * life_random

    def random_direction(self, d: tuple[float, float, float], spread_deg: float):
        alpha = deg_units(self.frand() * spread_deg)
        ca, sa = cos_units(alpha), sin_units(alpha)
        normal = (ca * d[0], ca * d[1], ca * d[2])
        tz = self.random_float(0.0, 1.0)    # original draw order: z, y, x
        ty = self.random_float(0.0, 1.0)
        tx = self.random_float(0.0, 1.0)
        length = math.sqrt(d[0] * d[0] + d[1] * d[1] + d[2] * d[2])
        if length != 0.0:
            if d[2] == 0.0:
                if d[1] == 0.0:
                    tx = 0.0
                elif d[0] == 0.0:
                    ty = 0.0
                else:
                    tx = -(d[1] * ty) / d[0]
            else:
                if d[1] == 0.0:
                    if d[0] == 0.0:
                        tz = 0.0
                    else:
                        tx = -(d[2] * tz) / d[0]
                else:
                    if d[0] == 0.0:
                        ty = -(d[2] * tz) / d[1]
                    else:
                        tx = (-d[1] * ty - d[2] * tz) / d[0]
        tl = math.sqrt(tx * tx + ty * ty + tz * tz)
        if tl > 0.0:
            tx, ty, tz = tx / tl, ty / tl, tz / tl
        k = sa * length
        return (normal[0] + tx * k, normal[1] + ty * k, normal[2] + tz * k)

    def spawn_draws(self, d, spread, ang_vel, ang_vel_random,
                    init_deg, init_deg_random, life, life_random) -> dict:
        """The exact per-particle draw sequence of the emitter (spec §3.3)."""
        out_dir = self.random_direction(d, spread)
        av = deg_units(self.random_float(ang_vel, ang_vel_random))
        ideg = deg_units(self.random_float(init_deg, init_deg_random))
        lf = self.random_life(life, life_random)
        return {"dir": list(out_dir), "ang_vel": av, "init_deg": ideg, "life": lf}


def build_parity(ref: SfxRandomRef) -> dict:
    """Fixture replayed by client/scripts/tests/test_sfx_random.gd. Every
    section starts from a reset cursor pair."""
    out: dict = {"version": 1}
    ref.reset()
    out["irand"] = [ref.irand() for _ in range(20)]
    ref.reset()
    out["frand"] = [ref.frand() for _ in range(20)]
    ref.reset()
    out["random_float"] = [ref.random_float(0.5, 2.0) for _ in range(50)]
    ref.reset()
    out["random_life"] = [ref.random_life(2.0, 1.0) for _ in range(50)]
    ref.reset()
    out["random_direction"] = [list(ref.random_direction((1.0, 2.0, 3.0), 35.065))
                               for _ in range(50)]
    ref.reset()
    out["spawn"] = [ref.spawn_draws((0.0, 5.07, 0.0), 35.065, 0.0, 90.0,
                                    0.0, 180.0, 2.0, 1.0) for _ in range(20)]
    return out
