"""Tests for mesh-only exporter."""
from pathlib import Path
import tempfile

YTREF_ROOT = Path(__file__).parent.parent.parent.parent / "refs"
AVATAR_IRD = YTREF_ROOT / "models" / "raw" / "Avatar.IRD"
TMD_PATH = AVATAR_IRD / "male.TMD"


def test_mesh_exporter_creates_file():
    """Test that mesh exporter creates a GLB file."""
    from src.exporters.mesh_exporter import export_mesh_only
    from src.parsers.tmd_parser import TMDParser

    parser = TMDParser()
    model = parser.parse(TMD_PATH)

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "mesh_only.glb"
        export_mesh_only(model, output_path)

        assert output_path.exists(), "GLB file should be created"


def test_mesh_exporter_has_mesh():
    """Test that the GLB has at least one mesh."""
    from pygltflib import GLTF2
    from src.exporters.mesh_exporter import export_mesh_only
    from src.parsers.tmd_parser import TMDParser

    parser = TMDParser()
    model = parser.parse(TMD_PATH)

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "mesh_only.glb"
        export_mesh_only(model, output_path)

        gltf = GLTF2().load(str(output_path))
        assert len(gltf.meshes) >= 1, "Should have at least one mesh"


def test_mesh_exporter_has_no_skeleton():
    """Test that mesh-only export has no skin (skeleton)."""
    from pygltflib import GLTF2
    from src.exporters.mesh_exporter import export_mesh_only
    from src.parsers.tmd_parser import TMDParser

    parser = TMDParser()
    model = parser.parse(TMD_PATH)

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "mesh_only.glb"
        export_mesh_only(model, output_path)

        gltf = GLTF2().load(str(output_path))
        # No skins means no skeleton
        assert len(gltf.skins) == 0, "Mesh-only export should have no skeleton"


def test_mesh_exporter_validates_before_export():
    """Test that exporter runs validation."""
    from src.exporters.mesh_exporter import export_mesh_only
    from src.parsers.tmd_parser import TMDParser

    parser = TMDParser()
    model = parser.parse(TMD_PATH)

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "mesh_only.glb"
        # Should not raise - male TMD passes validation
        export_mesh_only(model, output_path, validate=True)

        assert output_path.exists()


def test_mesh_has_uvs():
    """Test that mesh has texture coordinates."""
    from pygltflib import GLTF2
    from src.exporters.mesh_exporter import export_mesh_only
    from src.parsers.tmd_parser import TMDParser

    parser = TMDParser()
    model = parser.parse(TMD_PATH)

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "mesh_only.glb"
        export_mesh_only(model, output_path)

        gltf = GLTF2().load(str(output_path))
        # Check first mesh has TEXCOORD_0
        mesh = gltf.meshes[0]
        prim = mesh.primitives[0]
        assert prim.attributes.TEXCOORD_0 is not None, "Mesh should have UVs"
