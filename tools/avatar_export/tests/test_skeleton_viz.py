"""Tests for skeleton cube visualizer."""
from pathlib import Path
import tempfile

YTREF_ROOT = Path(__file__).parent.parent.parent.parent / "refs"
AVATAR_IRD = YTREF_ROOT / "models" / "raw" / "Avatar.IRD"
TMD_PATH = AVATAR_IRD / "male.TMD"


def test_skeleton_viz_creates_file():
    """Test that skeleton visualizer creates a GLB file."""
    from src.debug.skeleton_viz import create_skeleton_viz
    from src.parsers.tmd_parser import TMDParser

    parser = TMDParser()
    model = parser.parse(TMD_PATH)

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "debug_skeleton.glb"
        create_skeleton_viz(model, output_path)

        assert output_path.exists(), "GLB file should be created"


def test_skeleton_viz_has_54_nodes():
    """Test that the GLB has one node per bone (54 total)."""
    from pygltflib import GLTF2
    from src.debug.skeleton_viz import create_skeleton_viz
    from src.parsers.tmd_parser import TMDParser

    parser = TMDParser()
    model = parser.parse(TMD_PATH)

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "debug_skeleton.glb"
        create_skeleton_viz(model, output_path)

        gltf = GLTF2().load(str(output_path))
        assert len(gltf.nodes) == 54, f"Should have 54 nodes, got {len(gltf.nodes)}"


def test_skeleton_viz_nodes_have_mesh():
    """Test that each node has a cube mesh attached."""
    from pygltflib import GLTF2
    from src.debug.skeleton_viz import create_skeleton_viz
    from src.parsers.tmd_parser import TMDParser

    parser = TMDParser()
    model = parser.parse(TMD_PATH)

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "debug_skeleton.glb"
        create_skeleton_viz(model, output_path)

        gltf = GLTF2().load(str(output_path))
        # All nodes should have a mesh
        nodes_with_mesh = sum(1 for n in gltf.nodes if n.mesh is not None)
        assert nodes_with_mesh == 54, f"All 54 nodes should have mesh, got {nodes_with_mesh}"


def test_skeleton_viz_nodes_have_bone_names():
    """Test that nodes are named after bones."""
    from pygltflib import GLTF2
    from src.debug.skeleton_viz import create_skeleton_viz
    from src.parsers.tmd_parser import TMDParser

    parser = TMDParser()
    model = parser.parse(TMD_PATH)

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "debug_skeleton.glb"
        create_skeleton_viz(model, output_path)

        gltf = GLTF2().load(str(output_path))
        node_names = {n.name for n in gltf.nodes}

        # Check some expected bone names exist
        assert "@Root" in node_names or "Root" in node_names
        assert "@Spine1" in node_names or "Spine1" in node_names
        assert "@Head" in node_names or "Head" in node_names
