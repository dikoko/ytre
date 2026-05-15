"""Tests for part exporter - exports PRT to GLB with skeleton and skin for proper binding."""
from pathlib import Path
import tempfile

YTREF_ROOT = Path(__file__).parent.parent.parent.parent / "refs"
AVATAR_IRD = YTREF_ROOT / "models" / "raw" / "Avatar.IRD"
PRT_PATH = AVATAR_IRD / "swap" / "male" / "male_hair_M0101.PRT"
BASE_TMD_PATH = AVATAR_IRD / "male.TMD"
MLIB_PATH = AVATAR_IRD / "motion" / "male" / "male.mlib"


def test_part_exporter_creates_file():
    """Test that part exporter creates a GLB file."""
    from src.exporters.part_exporter import export_part
    from src.parsers.tmd_parser import TMDParser
    from src.parsers.mlib_parser import MLIBParser

    tmd_parser = TMDParser()
    mlib_parser = MLIBParser()
    model = tmd_parser.parse(PRT_PATH)
    base_model = tmd_parser.parse(BASE_TMD_PATH)
    mlib = mlib_parser.parse(MLIB_PATH)

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "part.glb"
        export_part(model, base_model, mlib, output_path)

        assert output_path.exists(), "GLB file should be created"


def test_part_has_skin_attributes():
    """Test that the GLB has JOINTS_0 and WEIGHTS_0 attributes."""
    from pygltflib import GLTF2
    from src.exporters.part_exporter import export_part
    from src.parsers.tmd_parser import TMDParser
    from src.parsers.mlib_parser import MLIBParser

    tmd_parser = TMDParser()
    mlib_parser = MLIBParser()
    model = tmd_parser.parse(PRT_PATH)
    base_model = tmd_parser.parse(BASE_TMD_PATH)
    mlib = mlib_parser.parse(MLIB_PATH)

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "part.glb"
        export_part(model, base_model, mlib, output_path)

        gltf = GLTF2().load(str(output_path))
        mesh = gltf.meshes[0]
        prim = mesh.primitives[0]

        assert prim.attributes.JOINTS_0 is not None, "Mesh should have JOINTS_0"
        assert prim.attributes.WEIGHTS_0 is not None, "Mesh should have WEIGHTS_0"


def test_part_has_skeleton_and_skin():
    """Test that part export includes skeleton and skin for proper binding."""
    from pygltflib import GLTF2
    from src.exporters.part_exporter import export_part
    from src.parsers.tmd_parser import TMDParser
    from src.parsers.mlib_parser import MLIBParser

    tmd_parser = TMDParser()
    mlib_parser = MLIBParser()
    model = tmd_parser.parse(PRT_PATH)
    base_model = tmd_parser.parse(BASE_TMD_PATH)
    mlib = mlib_parser.parse(MLIB_PATH)

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "part.glb"
        export_part(model, base_model, mlib, output_path)

        gltf = GLTF2().load(str(output_path))

        # Part should have a skin for proper skeleton binding
        assert len(gltf.skins) == 1, "Part export should have one skin"

        skin = gltf.skins[0]
        assert len(skin.joints) == len(base_model.bones), "Skin should have all bones from base model"
        assert skin.inverseBindMatrices is not None, "Skin should have inverse bind matrices"


def test_part_mesh_references_skin():
    """Test that mesh node references the skin for skeletal animation."""
    from pygltflib import GLTF2
    from src.exporters.part_exporter import export_part
    from src.parsers.tmd_parser import TMDParser
    from src.parsers.mlib_parser import MLIBParser

    tmd_parser = TMDParser()
    mlib_parser = MLIBParser()
    model = tmd_parser.parse(PRT_PATH)
    base_model = tmd_parser.parse(BASE_TMD_PATH)
    mlib = mlib_parser.parse(MLIB_PATH)

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "part.glb"
        export_part(model, base_model, mlib, output_path)

        gltf = GLTF2().load(str(output_path))

        # Find mesh node and verify it references the skin
        mesh_node = None
        for node in gltf.nodes:
            if node.mesh is not None:
                mesh_node = node
                break

        assert mesh_node is not None, "Should have a mesh node"
        assert mesh_node.skin == 0, "Mesh node should reference skin 0"
