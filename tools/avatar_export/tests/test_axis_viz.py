"""Tests for axis rotation visualizer."""
from pathlib import Path
import tempfile

YTREF_ROOT = Path(__file__).parent.parent.parent.parent / "refs"
AVATAR_IRD = YTREF_ROOT / "models" / "raw" / "Avatar.IRD"
TMD_PATH = AVATAR_IRD / "male.TMD"


def test_axis_viz_creates_file():
    """Test that axis visualizer creates a GLB file with 3 animations."""
    from src.debug.axis_viz import create_axis_viz
    from src.parsers.tmd_parser import TMDParser

    parser = TMDParser()
    model = parser.parse(TMD_PATH)

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "debug_axes.glb"
        create_axis_viz(model, output_path)

        assert output_path.exists(), "GLB file should be created"


def test_axis_viz_has_three_animations():
    """Test that the GLB has debug_rot_X, debug_rot_Y, debug_rot_Z animations."""
    from pygltflib import GLTF2
    from src.debug.axis_viz import create_axis_viz
    from src.parsers.tmd_parser import TMDParser

    parser = TMDParser()
    model = parser.parse(TMD_PATH)

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "debug_axes.glb"
        create_axis_viz(model, output_path)

        gltf = GLTF2().load(str(output_path))
        assert len(gltf.animations) == 3, "Should have 3 animations"

        anim_names = {a.name for a in gltf.animations}
        assert "debug_rot_X" in anim_names
        assert "debug_rot_Y" in anim_names
        assert "debug_rot_Z" in anim_names


def test_axis_viz_targets_spine_bones():
    """Test that animations target Spine1 and Spine2 bones."""
    from pygltflib import GLTF2
    from src.debug.axis_viz import create_axis_viz
    from src.parsers.tmd_parser import TMDParser

    parser = TMDParser()
    model = parser.parse(TMD_PATH)

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "debug_axes.glb"
        create_axis_viz(model, output_path)

        gltf = GLTF2().load(str(output_path))

        # Get node names for targeted bones
        targeted_nodes = set()
        for anim in gltf.animations:
            for channel in anim.channels:
                node_idx = channel.target.node
                targeted_nodes.add(gltf.nodes[node_idx].name)

        assert "@Spine1" in targeted_nodes or "Spine1" in targeted_nodes
        assert "@Spine2" in targeted_nodes or "Spine2" in targeted_nodes
