"""
PLT Parser — per-map light settings.

Binary format (matches the retail client's light-settings loader):
  DirectionLight  sun;
  int32           point_count;
  PointLightData  points[point_count];
  // optional (day/night light sets, appended if not EOF):
  int32           dir_set_count;
  DirectionLight  dir_set[dir_set_count];

DirectionLight (60 bytes):
  float x, y, z;        // D3D light direction (points FROM the sun)
  float Diffuse[4];     // RGBA
  float Specular[4];    // RGBA
  float Ambient[4];     // RGBA

The original client renders with a BLACK world ambient, so all ambient
lighting comes from the sun's Ambient scaled by the material's ambient
(terrain material: Ambient=0.7, Diffuse=1.0).
"""

import struct
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DirectionLight:
    direction: tuple[float, float, float]  # D3D light direction (from sun)
    diffuse: tuple[float, float, float, float]
    specular: tuple[float, float, float, float]
    ambient: tuple[float, float, float, float]


@dataclass
class PointLight:
    """PointLightData (324 bytes; the bool field is a 4-byte int).

    Only color row [0] of the 4 authored rows is ever read at runtime;
    rows 1-3 and Specular are reserved/dead. FileName and dummy are
    map-editor bookkeeping — the runtime lights the scene with every entry
    regardless. Attenuation: 1/(a0 + a1*d + a2*d^2), lights beyond
    max_range hard-skipped by the range cutoff.
    """
    name: str
    matrix: tuple[float, ...]  # 4x4 D3D placement; translation = [12:15]
    light_id: int
    color_num: int
    diffuse: tuple[float, float, float, float]   # row [0]
    ambient: tuple[float, float, float, float]   # row [0]
    max_range: float
    attenuation: tuple[float, float, float]      # a0, a1, a2
    dummy: int

    @property
    def position(self) -> tuple[float, float, float]:
        return self.matrix[12:15]


@dataclass
class LightSettings:
    sun: DirectionLight
    point_light_count: int = 0
    point_lights: list[PointLight] = field(default_factory=list)
    dir_light_set: list[DirectionLight] = field(default_factory=list)


_DIRLIGHT_SIZE = 60  # 15 floats
_POINTLIGHT_SIZE = 324


def _read_pointlight(data: bytes, offset: int) -> PointLight:
    name = data[offset:offset + 32].split(b"\0")[0].decode("cp949", errors="replace")
    matrix = struct.unpack_from("<16f", data, offset + 32)
    light_id, color_num = struct.unpack_from("<2i", data, offset + 96)
    diffuse = struct.unpack_from("<4f", data, offset + 104)   # Diffuse[0]
    # Specular[4][4] at +168 is dead data (the client never enables specular)
    ambient = struct.unpack_from("<4f", data, offset + 232)   # Ambient[0]
    _min_range, max_range = struct.unpack_from("<2f", data, offset + 296)
    a0, a1, a2 = struct.unpack_from("<3f", data, offset + 308)
    dummy = struct.unpack_from("<i", data, offset + 320)[0]
    return PointLight(
        name=name, matrix=matrix, light_id=light_id, color_num=color_num,
        diffuse=diffuse, ambient=ambient, max_range=max_range,
        attenuation=(a0, a1, a2), dummy=dummy,
    )


def _read_dirlight(data: bytes, offset: int) -> DirectionLight:
    v = struct.unpack_from("<15f", data, offset)
    return DirectionLight(
        direction=v[0:3],
        diffuse=v[3:7],
        specular=v[7:11],
        ambient=v[11:15],
    )


class PLTParser:
    def parse(self, path: Path | str) -> LightSettings:
        data = Path(path).read_bytes()
        if len(data) < _DIRLIGHT_SIZE + 4:
            raise ValueError(f"PLT file too small: {len(data)} bytes")

        sun = _read_dirlight(data, 0)
        offset = _DIRLIGHT_SIZE
        point_count = struct.unpack_from("<i", data, offset)[0]
        offset += 4
        point_lights = []
        for _ in range(max(0, point_count)):
            point_lights.append(_read_pointlight(data, offset))
            offset += _POINTLIGHT_SIZE

        dir_light_set: list[DirectionLight] = []
        if offset < len(data):
            set_count = struct.unpack_from("<i", data, offset)[0]
            offset += 4
            for _ in range(max(0, set_count)):
                dir_light_set.append(_read_dirlight(data, offset))
                offset += _DIRLIGHT_SIZE

        return LightSettings(
            sun=sun,
            point_light_count=point_count,
            point_lights=point_lights,
            dir_light_set=dir_light_set,
        )
