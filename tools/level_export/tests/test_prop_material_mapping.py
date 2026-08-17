"""Primitive -> material mapping must survive the animated node split.

The 2026-08-08 street-lamp regression: embed_textures assigned materials by
zipping primitives against model.meshes in TMD object order, but the animated
export path emits animated objects' meshes DURING the object walk and the
static chunk mesh AFTER it, so the glTF primitive order became
[animated..., static...] while the material list stayed interleaved. On
a_selamp01 the two glow-star quads got the lamp diffuse textures (opaque
"texture sheet" boxes) and the housing got the emissive sfx materials.

These tests pin the mapping per NODE, not as a multiset — the bug was a
permutation, so any order-insensitive check would have passed on it.
"""
import struct
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts._export_common import embed_textures
from scripts._prop_config import PROP_BASE, TEXTURE_SEARCH_DIRS, discover_props
from src.exporters.prop_animation import build_animation_plan
from src.exporters.prop_exporter import export_prop, _split_mesh_by_material
from src.parsers.tmd_parser import TMDParser

FIXTURES = [
    ("artificial", "a_selamp01"),    # the regression: 3 static + 2 animated objects
    ("active", "E_SCfire_1"),        # all-animated, many objects
    ("portal", "p_portal003a"),      # animated incl. a scale-axis factor chain
]


def _gltf_json(path: Path) -> dict:
    data = path.read_bytes()
    n = struct.unpack("<I", data[12:16])[0]
    return json.loads(data[20:20 + n])


def _export(category: str, prop_id: str, tmp_path: Path):
    match = [t for c, p, t in discover_props() if (c, p) == (category, prop_id)]
    model = TMDParser().parse(match[0])
    glb = tmp_path / f"{prop_id}.glb"
    export_prop(model, glb, prop_id=prop_id)
    embed_textures(glb, match[0].parent, model, texture_dirs=TEXTURE_SEARCH_DIRS)
    return model, _gltf_json(glb)


def _material_names_of(gltf: dict, mesh_idx: int) -> list[str]:
    return [gltf["materials"][p["material"]].get("name")
            for p in gltf["meshes"][mesh_idx]["primitives"]]


@pytest.mark.parametrize("category,prop_id", FIXTURES,
                         ids=[p for _, p in FIXTURES])
def test_every_node_keeps_its_tmd_materials(category, prop_id, tmp_path):
    model, gltf = _export(category, prop_id, tmp_path)
    plan = build_animation_plan(model, prop_id)
    nodes_by_name = {n.get("name"): n for n in gltf["nodes"]}

    # Animated objects: their own mesh, materials from their own splits.
    for obj_index, anim_node in plan.animated.items():
        mesh = model.objects[obj_index].mesh
        if mesh is None:
            continue
        node = nodes_by_name[anim_node.node_name]
        expected = [model.materials[m].name
                    for m, _ in _split_mesh_by_material(mesh)]
        got = _material_names_of(gltf, node["mesh"])
        assert got == expected, (
            f"{prop_id} {anim_node.node_name}: materials {got} != {expected}"
        )

    # Static objects: the chunk mesh(es), splits concatenated in object order.
    expected_static = []
    for obj_index, obj in enumerate(model.objects):
        if obj.mesh is None or obj_index in plan.animated:
            continue
        expected_static.extend(model.materials[m].name
                               for m, _ in _split_mesh_by_material(obj.mesh))
    got_static = []
    static_names = {prop_id} | {f"{prop_id}_{k}" for k in range(1, 40)}
    for n in gltf["nodes"]:
        if n.get("name") in static_names and "mesh" in n:
            got_static.extend(_material_names_of(gltf, n["mesh"]))
    assert got_static == expected_static, f"{prop_id}: static chunk mismatch"


def test_lamp_glow_stars_are_the_emissive_material(tmp_path):
    """The user-visible symptom, asserted directly: a_selamp01's animated
    star quads carry the sfx material (emissive), never the lamp diffuse."""
    model, gltf = _export("artificial", "a_selamp01", tmp_path)
    plan = build_animation_plan(model, "a_selamp01")
    assert plan.animated, "fixture is no longer animated"
    for obj_index, anim_node in plan.animated.items():
        node = next(n for n in gltf["nodes"]
                    if n.get("name") == anim_node.node_name)
        for prim in gltf["meshes"][node["mesh"]]["primitives"]:
            mat = gltf["materials"][prim["material"]]
            assert mat.get("emissiveFactor") == [1.0, 1.0, 1.0], (
                f"{anim_node.node_name} got non-emissive {mat.get('name')!r}"
            )
