"""Tests for skeleton exporter."""
from pathlib import Path
import tempfile

YTREF_ROOT = Path(__file__).parent.parent.parent.parent / "refs"
AVATAR_IRD = YTREF_ROOT / "models" / "raw" / "Avatar.IRD"
TMD_PATH = AVATAR_IRD / "male.TMD"
MLIB_PATH = AVATAR_IRD / "motion" / "male" / "male.mlib"


def test_skeleton_exporter_creates_file():
    """Test that skeleton exporter creates a GLB file."""
    from src.exporters.skeleton_exporter import export_with_skeleton
    from src.parsers.tmd_parser import TMDParser
    from src.parsers.mlib_parser import MLIBParser

    tmd_parser = TMDParser()
    model = tmd_parser.parse(TMD_PATH)

    mlib_parser = MLIBParser()
    mlib = mlib_parser.parse(MLIB_PATH)

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "with_skeleton.glb"
        export_with_skeleton(model, mlib, output_path)

        assert output_path.exists(), "GLB file should be created"


def test_skeleton_exporter_has_skin():
    """Test that the GLB has a skin (skeleton)."""
    from pygltflib import GLTF2
    from src.exporters.skeleton_exporter import export_with_skeleton
    from src.parsers.tmd_parser import TMDParser
    from src.parsers.mlib_parser import MLIBParser

    tmd_parser = TMDParser()
    model = tmd_parser.parse(TMD_PATH)

    mlib_parser = MLIBParser()
    mlib = mlib_parser.parse(MLIB_PATH)

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "with_skeleton.glb"
        export_with_skeleton(model, mlib, output_path)

        gltf = GLTF2().load(str(output_path))
        assert len(gltf.skins) == 1, "Should have one skin"


def test_skeleton_has_54_joints():
    """Test that skeleton has 54 joints."""
    from pygltflib import GLTF2
    from src.exporters.skeleton_exporter import export_with_skeleton
    from src.parsers.tmd_parser import TMDParser
    from src.parsers.mlib_parser import MLIBParser

    tmd_parser = TMDParser()
    model = tmd_parser.parse(TMD_PATH)

    mlib_parser = MLIBParser()
    mlib = mlib_parser.parse(MLIB_PATH)

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "with_skeleton.glb"
        export_with_skeleton(model, mlib, output_path)

        gltf = GLTF2().load(str(output_path))
        skin = gltf.skins[0]
        assert len(skin.joints) == 54, f"Should have 54 joints, got {len(skin.joints)}"


def test_mesh_has_joints_and_weights():
    """Test that mesh primitive has JOINTS_0 and WEIGHTS_0 attributes."""
    from pygltflib import GLTF2
    from src.exporters.skeleton_exporter import export_with_skeleton
    from src.parsers.tmd_parser import TMDParser
    from src.parsers.mlib_parser import MLIBParser

    tmd_parser = TMDParser()
    model = tmd_parser.parse(TMD_PATH)

    mlib_parser = MLIBParser()
    mlib = mlib_parser.parse(MLIB_PATH)

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "with_skeleton.glb"
        export_with_skeleton(model, mlib, output_path)

        gltf = GLTF2().load(str(output_path))
        mesh = gltf.meshes[0]
        prim = mesh.primitives[0]

        assert prim.attributes.JOINTS_0 is not None, "Mesh should have JOINTS_0"
        assert prim.attributes.WEIGHTS_0 is not None, "Mesh should have WEIGHTS_0"


def test_skeleton_has_no_animations():
    """Test that skeleton-only export has no animations."""
    from pygltflib import GLTF2
    from src.exporters.skeleton_exporter import export_with_skeleton
    from src.parsers.tmd_parser import TMDParser
    from src.parsers.mlib_parser import MLIBParser

    tmd_parser = TMDParser()
    model = tmd_parser.parse(TMD_PATH)

    mlib_parser = MLIBParser()
    mlib = mlib_parser.parse(MLIB_PATH)

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "with_skeleton.glb"
        export_with_skeleton(model, mlib, output_path)

        gltf = GLTF2().load(str(output_path))
        assert len(gltf.animations) == 0, "Skeleton-only export should have no animations"
