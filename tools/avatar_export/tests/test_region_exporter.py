"""
Tests for region exporter.
"""

from pathlib import Path

import pytest
from pygltflib import GLTF2

from src.parsers.tmd_parser import TMDParser
from src.parsers.mlib_parser import MLIBParser
from src.exporters.region_config import BodyRegion, get_vertex_region, get_bone_region
from src.exporters.region_exporter import split_mesh_by_region, export_with_regions


# Test data paths
YTREF_ROOT = Path(__file__).parent.parent.parent.parent / "refs"
AVATAR_IRD = YTREF_ROOT / "models" / "raw" / "Avatar.IRD"
TMD_PATH = AVATAR_IRD / "male.TMD"
MLIB_PATH = AVATAR_IRD / "motion" / "male" / "male.mlib"


@pytest.fixture
def model():
    """Load TMD model."""
    parser = TMDParser()
    return parser.parse(TMD_PATH)


@pytest.fixture
def mlib():
    """Load MLIB file."""
    parser = MLIBParser()
    return parser.parse(MLIB_PATH)


class TestRegionConfig:
    """Tests for region configuration."""

    def test_bone_to_region_head(self):
        """Head bones map to HEAD region."""
        assert get_bone_region("@Head") == BodyRegion.HEAD
        assert get_bone_region("@Hair01B") == BodyRegion.HEAD

    def test_bone_to_region_arms(self):
        """Arm bones map to correct regions."""
        assert get_bone_region("@Arm1L") == BodyRegion.ARM_UPPER
        assert get_bone_region("@Arm1R") == BodyRegion.ARM_UPPER
        assert get_bone_region("@Arm2L") == BodyRegion.FOREARM
        assert get_bone_region("@HandL") == BodyRegion.HAND

    def test_bone_to_region_legs(self):
        """Leg bones map to correct regions."""
        assert get_bone_region("@Leg1L") == BodyRegion.LEG_UPPER
        assert get_bone_region("@Leg2L") == BodyRegion.LEG_LOWER
        assert get_bone_region("@FootL") == BodyRegion.FOOT

    def test_bone_to_region_torso(self):
        """Torso bones map to TORSO region."""
        assert get_bone_region("@Spine1") == BodyRegion.TORSO
        assert get_bone_region("@Spine2") == BodyRegion.TORSO

    def test_vertex_region_dominant_bone(self):
        """Vertex region is determined by dominant bone weight."""
        bone_names = ["@Root", "@Head", "@Spine1", "@Arm1L"]

        # Single bone with full weight
        weights = [(1, 1.0)]  # @Head
        assert get_vertex_region(weights, bone_names) == BodyRegion.HEAD

        # Multiple bones, highest weight wins
        weights = [(1, 0.6), (2, 0.4)]  # @Head dominant
        assert get_vertex_region(weights, bone_names) == BodyRegion.HEAD

        weights = [(1, 0.3), (2, 0.7)]  # @Spine1 dominant
        assert get_vertex_region(weights, bone_names) == BodyRegion.TORSO

    def test_vertex_region_empty_weights(self):
        """Empty weights return None."""
        bone_names = ["@Root", "@Head"]
        assert get_vertex_region([], bone_names) is None

    def test_vertex_region_hair_by_material(self):
        """Vertices with material index 6 are classified as HAIR_SCALP or HAIR_STRANDS."""
        bone_names = ["@Root", "@Head", "@Spine1"]

        # Material 6 = hair, split into scalp (inner) and strands (outer) based on distance
        weights = [(1, 1.0)]  # @Head bone
        # Without position, defaults to HAIR_STRANDS
        assert get_vertex_region(weights, bone_names, material_index=6) == BodyRegion.HAIR_STRANDS

        # With position near head center -> HAIR_SCALP
        scalp_pos = (0.009, 1.500, -0.029)  # At head center
        assert get_vertex_region(weights, bone_names, material_index=6, vertex_position=scalp_pos) == BodyRegion.HAIR_SCALP

        # With position far from head center -> HAIR_STRANDS
        strand_pos = (0.2, 1.6, 0.1)  # Far from center
        assert get_vertex_region(weights, bone_names, material_index=6, vertex_position=strand_pos) == BodyRegion.HAIR_STRANDS

        # Other materials use bone-based classification
        assert get_vertex_region(weights, bone_names, material_index=7) == BodyRegion.HEAD
        assert get_vertex_region(weights, bone_names, material_index=0) == BodyRegion.HEAD
        assert get_vertex_region(weights, bone_names, material_index=None) == BodyRegion.HEAD


class TestSplitMeshByRegion:
    """Tests for mesh splitting."""

    def test_split_creates_all_expected_regions(self, model, mlib):
        """Split creates meshes for all body regions."""
        region_meshes = split_mesh_by_region(model, mlib)

        # All 12 regions should have meshes (11 original + hair split into scalp/strands)
        assert len(region_meshes) == 12

        for region in BodyRegion:
            assert region in region_meshes, f"Missing region: {region}"

    def test_split_preserves_face_integrity(self, model, mlib):
        """Each region has complete faces (all 3 vertices present)."""
        region_meshes = split_mesh_by_region(model, mlib)

        for region, region_mesh in region_meshes.items():
            vertex_set = set(region_mesh.vertex_indices)
            for face in region_mesh.faces:
                v0, v1, v2 = face
                assert v0 in vertex_set, f"Region {region}: face vertex {v0} not in vertex set"
                assert v1 in vertex_set, f"Region {region}: face vertex {v1} not in vertex set"
                assert v2 in vertex_set, f"Region {region}: face vertex {v2} not in vertex set"

class TestExportWithRegions:
    """Tests for GLB export."""

    def test_export_creates_glb(self, model, mlib, tmp_path):
        """Export creates a valid GLB file."""
        output_path = tmp_path / "test_regions.glb"

        export_with_regions(model, mlib, output_path)

        assert output_path.exists()
        assert output_path.stat().st_size > 0

    def test_export_has_multiple_meshes(self, model, mlib, tmp_path):
        """Exported GLB has one mesh per region."""
        output_path = tmp_path / "test_regions.glb"

        export_with_regions(model, mlib, output_path)

        gltf = GLTF2.load(str(output_path))

        # Should have 12 meshes (one per region, including hair_scalp and hair_strands)
        assert len(gltf.meshes) == 12

    def test_export_mesh_names_match_regions(self, model, mlib, tmp_path):
        """Each mesh is named after its region."""
        output_path = tmp_path / "test_regions.glb"

        export_with_regions(model, mlib, output_path)

        gltf = GLTF2.load(str(output_path))

        mesh_names = {m.name for m in gltf.meshes}
        expected_names = {f"region_{r.value}" for r in BodyRegion}

        assert mesh_names == expected_names

    def test_export_has_skeleton(self, model, mlib, tmp_path):
        """Exported GLB has skeleton with correct bone count."""
        output_path = tmp_path / "test_regions.glb"

        export_with_regions(model, mlib, output_path)

        gltf = GLTF2.load(str(output_path))

        assert len(gltf.skins) == 1
        assert len(gltf.skins[0].joints) == len(model.bones)

    def test_export_mesh_nodes_have_skin(self, model, mlib, tmp_path):
        """All mesh nodes reference the shared skin."""
        output_path = tmp_path / "test_regions.glb"

        export_with_regions(model, mlib, output_path)

        gltf = GLTF2.load(str(output_path))

        mesh_nodes = [n for n in gltf.nodes if n.mesh is not None]
        assert len(mesh_nodes) == 12

        for node in mesh_nodes:
            assert node.skin == 0, f"Node {node.name} missing skin reference"

    def test_export_returns_region_stats(self, model, mlib, tmp_path):
        """Export returns vertex count per region."""
        output_path = tmp_path / "test_regions.glb"

        stats = export_with_regions(model, mlib, output_path)

        assert len(stats) == 12
        for region in BodyRegion:
            assert region in stats
            assert stats[region] > 0
