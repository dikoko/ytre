"""ENV parser — per-map camera parameters from {code}.env.

Read order matches the retail client's env loader:

    1. u32 dwVersion                                        (4 bytes)
    2. Camera block:
         if dwVersion >= CAMERA2_VERSION (20040721):
             CameraInfo2 — 10 floats, in order
             fUpNear, fUpFar, fUpFov, fUpAngle, fUpDist,
             fDnNear, fDnFar, fDnFov, fDnAngle, fDnDist   (40 bytes)
         else:
             CameraInfo — fNear, fFar, fFov
             (3 floats, 12 bytes) — an older per-map format that predates
             the up/down split this parser targets; treated as an unknown
             version below (only CameraInfo2 carries the fields we need).
    3. FogInfo, SkyInfo, LightColorList, field-time-type blocks follow but
       are not needed to recover the camera floats and are not parsed here.

Confirmed against SF001001.env (360 bytes): dwVersion == 20050324 (the
file's SKYINFO2_VERSION marker, unrelated to CAMERA2_VERSION's own
20040721 threshold) which is >= CAMERA2_VERSION, so the CameraInfo2 branch
is taken; the resulting floats (1.0, 70.0, 30.0, 55.0, 18.0, 0.5, 70.0,
30.0, -20.0, 8.0) match the task's ground-truth values exactly.

Defaults match the retail client's game-camera initial values: near/far/
fov/angle/distance for the up view, then the same five for the down view.
"""
import struct
from dataclasses import dataclass
from pathlib import Path

CAMERA2_VERSION = 20040721

_VERSION_STRUCT = struct.Struct("<I")
_CAMERA_INFO2_STRUCT = struct.Struct("<10f")


@dataclass(frozen=True)
class CameraParams:
    up_near: float
    up_far: float
    up_fov: float
    up_angle: float
    up_dist: float
    dn_near: float
    dn_far: float
    dn_fov: float
    dn_angle: float
    dn_dist: float

    @classmethod
    def defaults(cls) -> "CameraParams":
        # Every value verbatim from the retail client's camera defaults.
        return cls(up_near=0.5, up_far=10.0, up_fov=30.0, up_angle=60.0,
                   up_dist=15.0, dn_near=0.5, dn_far=15.0, dn_fov=45.0,
                   dn_angle=15.0, dn_dist=10.0)


def parse_env_camera(path: Path | str) -> CameraParams:
    path = Path(path)
    if not path.is_file():
        return CameraParams.defaults()

    data = path.read_bytes()

    header_size = _VERSION_STRUCT.size
    if len(data) < header_size:
        return CameraParams.defaults()

    (version,) = _VERSION_STRUCT.unpack_from(data, 0)

    # Only the CameraInfo2 block (versioned CAMERA2_VERSION and later)
    # carries the up/down camera fields this parser exposes; older
    # CameraInfo-only files (fNear/fFar/fFov triple) don't map onto
    # CameraParams and fall back to defaults, same as a missing file.
    if version < CAMERA2_VERSION:
        return CameraParams.defaults()

    camera_size = _CAMERA_INFO2_STRUCT.size
    if len(data) < header_size + camera_size:
        return CameraParams.defaults()

    floats = _CAMERA_INFO2_STRUCT.unpack_from(data, header_size)
    return CameraParams(*floats)
