"""Tests for prop exporter — static mesh with multi-material support."""
import tempfile
from pathlib import Path

from pygltflib import GLTF2

YTREF_ROOT = Path(__file__).parent.parent.parent.parent / "refs"
PROP_IRD = YTREF_ROOT / "models" / "raw" / "Terrain" / "Object"
ARTIFICIAL_DIR = PROP_IRD / "Artificial.IRD"
NATURE_DIR = PROP_IRD / "Nature.IRD"
STRUCTURE_DIR = PROP_IRD / "Structure.IRD"


def _find_prop_tmd(directory: Path, prefix: str = "") -> Path:
    """Find first TMD file in directory, optionally matching prefix."""
    for f in sorted(directory.iterdir()):
        if f.suffix.upper() == ".TMD" and f.name.startswith(prefix):
            return f
    raise FileNotFoundError(f"No TMD in {directory}")


def test_prop_export_creates_glb():
    """Export a simple prop and verify GLB is created."""
    from src.exporters.prop_exporter import export_prop
    from src.parsers.tmd_parser import TMDParser

    tmd_path = _find_prop_tmd(ARTIFICIAL_DIR, "a_book")
    model = TMDParser().parse(tmd_path)

    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir) / "test_prop.glb"
        export_prop(model, out, prop_id="a_book01")
        assert out.exists(), "GLB file should be created"


def test_prop_has_no_skeleton():
    """Props must not have skeleton/skin data."""
    from src.exporters.prop_exporter import export_prop
    from src.parsers.tmd_parser import TMDParser

    tmd_path = _find_prop_tmd(ARTIFICIAL_DIR, "a_book")
    model = TMDParser().parse(tmd_path)

    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir) / "test_prop.glb"
        export_prop(model, out, prop_id="a_book01")

        gltf = GLTF2().load(str(out))
        assert len(gltf.skins) == 0, "Props should have no skeleton"
        assert len(gltf.animations) == 0, "Props should have no animations"


def test_prop_node_named_after_prop_id():
    """Root node should be named after the prop_id argument."""
    from src.exporters.prop_exporter import export_prop
    from src.parsers.tmd_parser import TMDParser

    tmd_path = _find_prop_tmd(ARTIFICIAL_DIR, "a_book")
    model = TMDParser().parse(tmd_path)

    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir) / "test_prop.glb"
        export_prop(model, out, prop_id="my_custom_name")

        gltf = GLTF2().load(str(out))
        assert gltf.nodes[0].name == "my_custom_name"


def test_prop_multi_material_creates_multiple_primitives():
    """A structure TMD with many materials should produce multiple primitives."""
    from src.exporters.prop_exporter import export_prop
    from src.parsers.tmd_parser import TMDParser

    # Structures tend to have multiple materials
    tmd_path = _find_prop_tmd(STRUCTURE_DIR)
    model = TMDParser().parse(tmd_path)

    # Count expected material groups
    total_mat_groups = 0
    for mesh in model.meshes:
        if mesh.vertex_materials:
            unique = set(mesh.vertex_materials.values())
            total_mat_groups += len(unique) if len(unique) > 1 else 1
        else:
            total_mat_groups += 1

    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir) / "test_structure.glb"
        export_prop(model, out, prop_id="structure_test")

        gltf = GLTF2().load(str(out))
        prim_count = sum(len(m.primitives) for m in gltf.meshes)
        assert prim_count == total_mat_groups, (
            f"Expected {total_mat_groups} primitives, got {prim_count}"
        )


def test_embed_textures_with_texture_dirs():
    """embed_textures should find textures in Texture.IRD when not in model dir."""
    from src.exporters.prop_exporter import export_prop
    from src.parsers.tmd_parser import TMDParser

    TEXTURE_IRD = PROP_IRD / "Texture.IRD"
    tmd_path = _find_prop_tmd(ARTIFICIAL_DIR, "a_book")
    model = TMDParser().parse(tmd_path)

    # Verify this prop has materials with texture references
    has_tex = any(m.texture_filename for m in model.materials)
    assert has_tex, "Test prop should have texture references"

    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir) / "test_prop.glb"
        export_prop(model, out, prop_id="a_book01")

        # Now embed textures using Texture.IRD as additional search dir
        from scripts._export_common import embed_textures
        embed_textures(out, ARTIFICIAL_DIR, model, texture_dirs=[TEXTURE_IRD])

        gltf = GLTF2().load(str(out))
        assert len(gltf.materials) > 0, "Should have at least one material with texture"
        assert len(gltf.images) > 0, "Should have at least one embedded image"


def test_self_illumination_exported_as_emissive():
    """A self-illumination value > 0 (rendered by the original client as an
    additive full-bright pass) must surface as glTF emissiveFactor so
    prop_lighting.gd can route the surface to the additive material."""
    from src.exporters.prop_exporter import export_prop
    from src.parsers.tmd_parser import TMDParser
    from scripts._export_common import embed_textures

    TEXTURE_IRD = PROP_IRD / "Texture.IRD"
    tmd_path = ARTIFICIAL_DIR / "a_selamp01.TMD"
    model = TMDParser().parse(tmd_path)
    si_names = {m.name for m in model.materials if m.self_illumination > 0}
    assert si_names == {"Masdaaaa332fedfe", "Masdaaaa332"}

    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir) / "a_selamp01.glb"
        export_prop(model, out, prop_id="a_selamp01")
        embed_textures(out, ARTIFICIAL_DIR, model, texture_dirs=[TEXTURE_IRD])

        gltf = GLTF2().load(str(out))
        emissive = {m.name for m in gltf.materials
                    if m.emissiveFactor and max(m.emissiveFactor) > 0}
        plain = {m.name for m in gltf.materials} - emissive
        assert emissive == si_names
        assert plain, "non-self-illum materials must stay non-emissive"


def test_skill_tmd_textures_resolve():
    """Glow-star textures referenced via ..\\..\\..\\SKILL\\TMD must resolve
    through TEXTURE_SEARCH_DIRS so all self-illum materials reach the GLB
    (n_SEbtree02_event01 has 7; 3 live under Skill.IRD/TMD)."""
    from src.exporters.prop_exporter import export_prop
    from src.parsers.tmd_parser import TMDParser
    from scripts._export_common import embed_textures
    from scripts._prop_config import TEXTURE_SEARCH_DIRS

    tmd_path = NATURE_DIR / "n_SEbtree02_event01.TMD"
    model = TMDParser().parse(tmd_path)
    si_names = {m.name for m in model.materials if m.self_illumination > 0}
    assert len(si_names) == 7

    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir) / "n_SEbtree02_event01.glb"
        export_prop(model, out, prop_id="n_SEbtree02_event01")
        embed_textures(out, NATURE_DIR, model, texture_dirs=TEXTURE_SEARCH_DIRS)

        gltf = GLTF2().load(str(out))
        emissive = {m.name for m in gltf.materials
                    if m.emissiveFactor and max(m.emissiveFactor) > 0}
        missing = si_names - emissive
        assert not missing, f"self-illum materials missing from GLB: {missing}"


def test_prop_no_v_flip_by_default():
    """UVs should NOT be V-flipped for props (same as monsters)."""
    from src.exporters.prop_exporter import export_prop
    from src.parsers.tmd_parser import TMDParser

    tmd_path = _find_prop_tmd(NATURE_DIR, "n_big")
    model = TMDParser().parse(tmd_path)

    # Get original UV V values
    original_vs = [uv.v for mesh in model.meshes for uv in mesh.uvs]

    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir) / "test_nature.glb"
        export_prop(model, out, prop_id="nature_test")

        gltf = GLTF2().load(str(out))
        # Read back UV data from the GLB accessor
        import numpy as np
        blob = gltf.binary_blob()
        # Find TEXCOORD_0 accessor for first primitive
        prim = gltf.meshes[0].primitives[0]
        uv_acc = gltf.accessors[prim.attributes.TEXCOORD_0]
        bv = gltf.bufferViews[uv_acc.bufferView]
        uv_data = np.frombuffer(
            blob[bv.byteOffset:bv.byteOffset + bv.byteLength],
            dtype=np.float32,
        ).reshape(-1, 2)
        # V values should match originals (not flipped)
        exported_vs = uv_data[:, 1].tolist()
        for orig, exp in zip(original_vs[:5], exported_vs[:5]):
            assert abs(orig - exp) < 0.001, (
                f"UV V should not be flipped: original={orig}, exported={exp}"
            )


def test_double_sided_follows_tmd_flag(tmp_path):
    """doubleSided mirrors the TMD material two-sided flag (the original
    client disables culling for flagged materials, CCW-culls otherwise),
    except colorkey-MASK materials which stay doubleSided.

    a_ENTcontrol verified 2026-07-12 to have BOTH two_sided=True and
    =False textured materials (also: a_ESDdoor02a, a_ESDlamp).
    """
    from src.exporters.prop_exporter import export_prop
    from src.parsers.tmd_parser import TMDParser
    from scripts._export_common import embed_textures
    from scripts._prop_config import TEXTURE_SEARCH_DIRS

    tmd_path = next(PROP_IRD.rglob("a_ENTcontrol.TMD"))
    model = TMDParser().parse(tmd_path)
    flags = {m.two_sided for m in model.materials if m.texture_filename}
    assert flags == {True, False}, "fixture prop no longer mixed — pick another from the census"

    glb_path = tmp_path / "a_ENTcontrol.glb"
    export_prop(model, glb_path, prop_id="a_ENTcontrol")
    embed_textures(glb_path, tmd_path.parent, model, texture_dirs=TEXTURE_SEARCH_DIRS)

    gltf = GLTF2().load(str(glb_path))
    tmd_by_name = {}
    for m in model.materials:
        if m.texture_filename:
            stem = Path(m.texture_filename.replace("\\", "/").split("/")[-1]).stem
            tmd_by_name[(m.name or stem)] = m
    checked = 0
    for gmat in gltf.materials:
        tmat = tmd_by_name.get(gmat.name)
        if tmat is None:
            continue
        if gmat.alphaMode == "MASK":
            assert gmat.doubleSided is True
        else:
            assert bool(gmat.doubleSided) == tmat.two_sided
        checked += 1
    assert checked >= 2  # both flag values actually exercised


def _synthetic_model():
    """One triangle with known coordinates, all normals (0,0,1).

    Note: TMDModel.meshes is a read-only property computed from
    TMDModel.objects (see src/parsers/tmd_parser.py), so the mesh is
    wired in via a TMDObject rather than assigning to `model.meshes`
    directly. Vertex/normal/UV/face data matches the task brief exactly.
    """
    from src.parsers.tmd_parser import TMDModel, TMDMesh, TMDMaterial, TMDObject, Vector3, Vector2
    mesh = TMDMesh(
        name="tri",
        vertices=[Vector3(0, 0, 0), Vector3(1, 0, 0), Vector3(0, 1, 0)],
        normals=[Vector3(0, 0, 1), Vector3(0, 0, 1), Vector3(0, 0, 1)],
        uvs=[Vector2(0, 0), Vector2(1, 0), Vector2(0, 1)],
        faces=[(0, 1, 2)],
        material_index=0,
    )
    model = TMDModel()
    model.objects = [TMDObject(object_id=0, name="tri", object_type="geometry", mesh=mesh)]
    model.materials = [TMDMaterial(name="m")]
    return model


def test_winding_reversed_for_z_mirror(tmp_path):
    """Default fixture has an identity node world_transform (det(rotation) = +1,
    i.e. not a baked mirror). Our Z-mirror to Godot flips handedness once;
    the original client (CCW-culled front) and Godot (CCW front) both treat
    the +RH-cross side as front, so the mirror is the only flip in play and the
    index order must be reversed: D3D (0,1,2) -> emitted (0,2,1)."""
    import numpy as np
    from pygltflib import GLTF2
    from src.exporters.prop_exporter import export_prop
    model = _synthetic_model()
    out = tmp_path / "tri.glb"
    export_prop(model, out, prop_id="tri")
    gltf = GLTF2().load(str(out))
    blob = gltf.binary_blob()
    prim = gltf.meshes[0].primitives[0]
    idx_acc = gltf.accessors[prim.indices]
    bv = gltf.bufferViews[idx_acc.bufferView]
    idx = np.frombuffer(blob[bv.byteOffset:bv.byteOffset + bv.byteLength], dtype=np.uint16)
    assert idx.tolist() == [0, 2, 1]


def test_winding_reversed_for_baked_mirror_object(tmp_path):
    """153 objects library-wide were baked with a mirrored world_transform
    (det(rotation) = -1); node mirrors are now baked into geometry for ALL
    objects (see node-transform baking), so every exported mesh differs from
    D3D-world geometry by exactly the base Z-mirror — one flip, uniformly.
    The stored D3D order (0,1,2) must therefore be reversed regardless of the
    object's own det, same as any other object."""
    import numpy as np
    from pygltflib import GLTF2
    from src.exporters.prop_exporter import export_prop
    from src.parsers.tmd_parser import Matrix3x3
    model = _synthetic_model()
    model.objects[0].world_transform.rotation = Matrix3x3(data=[-1, 0, 0, 0, 1, 0, 0, 0, 1])
    out = tmp_path / "tri_mirror.glb"
    export_prop(model, out, prop_id="tri_mirror")
    gltf = GLTF2().load(str(out))
    blob = gltf.binary_blob()
    prim = gltf.meshes[0].primitives[0]
    idx_acc = gltf.accessors[prim.indices]
    bv = gltf.bufferViews[idx_acc.bufferView]
    idx = np.frombuffer(blob[bv.byteOffset:bv.byteOffset + bv.byteLength], dtype=np.uint16)
    assert idx.tolist() == [0, 2, 1]


def _read_normals(glb_path):
    """Read back the NORMAL accessor of a GLB's first primitive."""
    import numpy as np
    from pygltflib import GLTF2
    gltf = GLTF2().load(str(glb_path))
    blob = gltf.binary_blob()
    prim = gltf.meshes[0].primitives[0]
    n_acc = gltf.accessors[prim.attributes.NORMAL]
    bv = gltf.bufferViews[n_acc.bufferView]
    return np.frombuffer(blob[bv.byteOffset:bv.byteOffset + bv.byteLength],
                          dtype=np.float32).reshape(-1, 3)


def test_normals_sign_aligned_to_geometric_front(tmp_path):
    """Authored normals (0,0,1) mirror to exported (0,0,-1). With the default
    fixture (identity node transform, not a baked mirror), winding is now
    reversed for the Z-mirror: emitted face order is (0,2,1), so the
    geometric front is g = cross(q2-q0, q1-q0) = (0,0,-1) for positions
    (0,0,0),(1,0,0),(0,1,0). The mirrored normal (0,0,-1) already agrees
    with g -> no sign flip (vote >= 0).

    Round-3's per-vertex normal sign-alignment now runs AFTER winding is
    decided, using the EMITTED order so g matches what Godot treats as front.
    """
    import numpy as np
    from src.exporters.prop_exporter import export_prop
    model = _synthetic_model()  # normals (0,0,1) authored -> mirror to (0,0,-1)
    out = tmp_path / "tri.glb"
    export_prop(model, out, prop_id="tri")
    normals = _read_normals(out)
    assert np.allclose(normals, [[0, 0, -1]] * 3)


def test_mirror_x_export(tmp_path):
    """mirror_x=True applies ONE additional X-mirror on top of the base
    Z-mirror export: positions/normals get x negated, and winding is XORed
    with the uniform base reversal (see prop_exporter._build_prop_primitive).

    Default fixture has an identity node transform (det=+1, not a baked
    mirror), so the base export alone emits [0,2,1] (see
    test_winding_reversed_for_z_mirror). The extra mirror_x mirror flips
    winding once more, back to [0,1,2]."""
    import numpy as np
    from pygltflib import GLTF2
    from src.exporters.prop_exporter import export_prop
    model = _synthetic_model()
    out = tmp_path / "tri_m.glb"
    export_prop(model, out, prop_id="tri", mirror_x=True)
    gltf = GLTF2().load(str(out))
    blob = gltf.binary_blob()
    prim = gltf.meshes[0].primitives[0]
    pos_bv = gltf.bufferViews[gltf.accessors[prim.attributes.POSITION].bufferView]
    pos = np.frombuffer(blob[pos_bv.byteOffset:pos_bv.byteOffset + pos_bv.byteLength], dtype=np.float32).reshape(-1, 3)
    idx_bv = gltf.bufferViews[gltf.accessors[prim.indices].bufferView]
    idx = np.frombuffer(blob[idx_bv.byteOffset:idx_bv.byteOffset + idx_bv.byteLength], dtype=np.uint16)
    assert pos[1][0] == -1.0            # x negated vs base export
    # base (identity node) emits [0,2,1]; ONE extra mirror XORs the winding back
    assert idx.tolist() == [0, 1, 2]


def test_normals_sign_flipped_when_disagreeing_with_front(tmp_path):
    """Authored normals (0,0,-1) mirror to exported (0,0,1), which now
    DISAGREES with the emitted geometric front (0,0,-1) (see
    test_normals_sign_aligned_to_geometric_front) -> sign-flipped to
    (0,0,-1). Both tests converge on (0,0,-1): this one pins the
    disagree-and-flip path, the other pins the agree-and-keep path."""
    import numpy as np
    from src.exporters.prop_exporter import export_prop
    model = _synthetic_model()
    for n in model.meshes[0].normals:
        n.x, n.y, n.z = 0.0, 0.0, -1.0  # mirrored to (0,0,1) = disagrees with emitted front
    out = tmp_path / "tri2.glb"
    export_prop(model, out, prop_id="tri2")
    assert np.allclose(_read_normals(out), [[0, 0, -1]] * 3)


def _read_positions(glb_path):
    """Read back the POSITION accessor of a GLB's first primitive."""
    import numpy as np
    from pygltflib import GLTF2
    gltf = GLTF2().load(str(glb_path))
    blob = gltf.binary_blob()
    prim = gltf.meshes[0].primitives[0]
    p_acc = gltf.accessors[prim.attributes.POSITION]
    bv = gltf.bufferViews[p_acc.bufferView]
    return np.frombuffer(blob[bv.byteOffset:bv.byteOffset + bv.byteLength],
                          dtype=np.float32).reshape(-1, 3)


def _read_indices(glb_path):
    """Read back the index accessor of a GLB's first primitive."""
    import numpy as np
    from pygltflib import GLTF2
    gltf = GLTF2().load(str(glb_path))
    blob = gltf.binary_blob()
    prim = gltf.meshes[0].primitives[0]
    idx_acc = gltf.accessors[prim.indices]
    bv = gltf.bufferViews[idx_acc.bufferView]
    dtype = np.uint32 if idx_acc.componentType == 5125 else np.uint16
    return np.frombuffer(blob[bv.byteOffset:bv.byteOffset + bv.byteLength], dtype=dtype)


def test_node_translation_baked(tmp_path):
    """TMD per-object world transforms are RENDER transforms, not metadata —
    the original client composes each object's world matrix at draw time.
    Vertices in the file are raw/local and must be baked by the node's
    world_transform before the D3D->Godot Z-mirror.

    t=(1,2,3), R=identity: baked D3D position = v + t, then Z-mirror ->
    (v.x+1, v.y+2, -(v.z+3)). Fixture verts (0,0,0),(1,0,0),(0,1,0) ->
    [[1,2,-3],[2,2,-3],[1,3,-3]]."""
    import numpy as np
    from src.exporters.prop_exporter import export_prop
    from src.parsers.tmd_parser import Vector3
    model = _synthetic_model()
    model.objects[0].world_transform.translation = Vector3(1, 2, 3)
    out = tmp_path / "tri_trans.glb"
    export_prop(model, out, prop_id="tri_trans")
    positions = _read_positions(out)
    assert np.allclose(positions, [[1, 2, -3], [2, 2, -3], [1, 3, -3]])


def test_node_rotation_baked(tmp_path):
    """R = yaw 90 degrees, D3D row-vector convention (data row-major):
    rows [[0,0,-1],[0,1,0],[1,0,0]], t=0.

    Baked D3D position (column form) p_d3d = R.T @ v; R.T =
    [[0,0,1],[0,1,0],[-1,0,0]]. For v=(1,0,0): p_d3d=(0,0,-1) -> Z-mirror
    -> (0,0,1). For v=(0,1,0): p_d3d=(0,1,0) -> Z-mirror -> (0,1,0). Origin
    is unaffected."""
    import numpy as np
    from src.exporters.prop_exporter import export_prop
    from src.parsers.tmd_parser import Matrix3x3
    model = _synthetic_model()
    model.objects[0].world_transform.rotation = Matrix3x3(data=[0, 0, -1, 0, 1, 0, 1, 0, 0])
    out = tmp_path / "tri_rot.glb"
    export_prop(model, out, prop_id="tri_rot")
    positions = _read_positions(out)
    assert np.allclose(positions, [[0, 0, 0], [0, 0, 1], [0, 1, 0]])


def test_node_mirror_baked_geometry(tmp_path):
    """R=diag(1,1,-1) (the a_SEstand03_1 case). Baked D3D position
    p_d3d=(x,y,-z); the subsequent Z-mirror negates z again -> exported
    position equals the ORIGINAL vertex (x,y,z) — a different sign path
    than the plain (unbaked) Z-mirror, which would have exported (x,y,-z).

    Uses verts with nonzero z (0,0,1),(1,0,1),(0,1,1) so the baked path is
    distinguishable from the old unbaked export (which produced z=-1).

    Winding is uniform now (node mirrors are baked into geometry, so every
    export differs from D3D-world by exactly the base Z-mirror): indices ==
    [0,2,1] regardless of this object's own det(R)."""
    import numpy as np
    from src.exporters.prop_exporter import export_prop
    from src.parsers.tmd_parser import Matrix3x3
    model = _synthetic_model()
    for v in model.meshes[0].vertices:
        v.z = 1.0
    model.objects[0].world_transform.rotation = Matrix3x3(data=[1, 0, 0, 0, 1, 0, 0, 0, -1])
    out = tmp_path / "tri_mirror_geom.glb"
    export_prop(model, out, prop_id="tri_mirror_geom")
    positions = _read_positions(out)
    assert np.allclose(positions, [[0, 0, 1], [1, 0, 1], [0, 1, 1]])
    indices = _read_indices(out)
    assert indices.tolist() == [0, 2, 1]


def test_over_256_primitives_chunk_into_multiple_meshes():
    """Godot drops surfaces past 256/mesh (RS::MAX_MESH_SURFACES) with
    per-surface import errors — a_fountain01 has 314 object x material
    primitives and lost 58 of them until export_prop learned to chunk."""
    from src.exporters.prop_exporter import export_prop, MAX_MESH_SURFACES
    from src.parsers.tmd_parser import TMDParser

    model = TMDParser().parse(ARTIFICIAL_DIR / "a_fountain01.TMD")
    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir) / "a_fountain01.glb"
        export_prop(model, out, prop_id="a_fountain01")
        gltf = GLTF2().load(str(out))
        total = sum(len(m.primitives) for m in gltf.meshes)
        assert total == 314
        assert len(gltf.meshes) == 2
        assert all(len(m.primitives) <= MAX_MESH_SURFACES for m in gltf.meshes)
        # Every mesh must be reachable from the scene through its own node.
        scene_nodes = gltf.scenes[gltf.scene].nodes
        assert sorted(gltf.nodes[n].mesh for n in scene_nodes) == [0, 1]
