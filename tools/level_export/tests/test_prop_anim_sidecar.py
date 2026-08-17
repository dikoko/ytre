import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts._prop_config import PROP_BASE, discover_props
from src.exporters.prop_anim_sidecar import build_sidecar, write_sidecar
from src.exporters.prop_animation import build_animation_plan
from src.parsers.tmd_parser import TMDParser
from tests.test_prop_static_identity import animated_props

FIRE = PROP_BASE / "Active.IRD" / "E_SCfire_1.TMD"
PORTAL = PROP_BASE / "Portal.IRD" / "p_portal003a.TMD"


def _first_static_prop() -> tuple[str, Path]:
    """A prop the plan resolver calls static.

    Deliberately not "the first TMD in some directory": three ids ship
    animated in one category and static in another, so a positional pick
    could silently land on an animated file and make the None-check vacuous.
    """
    animated = animated_props()
    for cat, prop_id, tmd_path in discover_props():
        if (cat, prop_id) not in animated:
            return prop_id, tmd_path
    raise AssertionError("no static prop found")


def test_sidecar_shape():
    model = TMDParser().parse(FIRE)
    data = build_sidecar(build_animation_plan(model, "E_SCfire_1"))
    assert data["fps"] == model.frame_speed
    assert data["total_frames"] == model.total_frames
    assert data["default_clip"] in data["clips"]
    for clip in data["clips"].values():
        assert clip["end"] >= clip["start"]
        assert isinstance(clip["loop"], bool)


def test_visibility_curves_keyed_by_node_name():
    model = TMDParser().parse(FIRE)
    plan = build_animation_plan(model, "E_SCfire_1")
    data = build_sidecar(plan)
    assert data["visibility"], "E_SCfire_1 is the visibility fixture"
    for name, curve in data["visibility"].items():
        assert name.startswith("E_SCfire_1_obj")
        assert len(curve) >= 1
        for frame, alpha in curve:
            assert frame >= 0.0
            assert -0.01 <= alpha <= 1.01


def test_visibility_names_match_real_gltf_nodes():
    """The curve keys are the runtime's lookup into the exported scene.

    A rename on either side turns every fade into a silent no-op, so tie
    the sidecar keys to the plan's own node names rather than a convention.
    """
    plan = build_animation_plan(TMDParser().parse(FIRE), "E_SCfire_1")
    known = {node.node_name for node in plan.animated.values()}
    assert set(build_sidecar(plan)["visibility"]) <= known


def test_prop_without_ranges_gets_a_looping_default():
    """Force-loop when no ANIMATION property exists (spec 1.6)."""
    model = TMDParser().parse(PORTAL)
    data = build_sidecar(build_animation_plan(model, "p_portal003a"))
    if len(data["clips"]) == 1:
        assert data["clips"]["default"]["loop"] is True


def test_static_prop_gets_no_sidecar(tmp_path):
    prop_id, tmd_path = _first_static_prop()
    model = TMDParser().parse(tmd_path)
    plan = build_animation_plan(model, prop_id)
    assert build_sidecar(plan) is None
    assert write_sidecar(plan, tmp_path / f"{prop_id}.glb") is None
    assert not list(tmp_path.iterdir())


def test_write_sidecar_lands_next_to_the_glb(tmp_path):
    plan = build_animation_plan(TMDParser().parse(FIRE), "E_SCfire_1")
    out = write_sidecar(plan, tmp_path / "E_SCfire_1.glb")
    assert out == tmp_path / "E_SCfire_1.anim.json"
    assert json.loads(out.read_text())["fps"] == plan.fps
