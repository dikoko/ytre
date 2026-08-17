import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts._prop_config import PROP_BASE, discover_props
from src.parsers.tmd_parser import TMDParser
from tests.test_prop_static_identity import animated_props

FIRE = PROP_BASE / "Active.IRD" / "E_SCfire_1.TMD"


def test_visibility_tracks_parsed():
    model = TMDParser().parse(FIRE)
    assert len(model.visibility_tracks) > 0
    for track in model.visibility_tracks:
        assert track.object_ordinal >= 0
        assert len(track.keys) >= 1
        for frame, alpha in track.keys:
            assert frame >= 0.0            # negative frames clamp to 0
            assert -0.01 <= alpha <= 1.01  # authored alpha, tolerance for fp


def test_visibility_track_census_matches_spec():
    """Two counts, deliberately kept apart.

    160 of the 188 animated props carry a visibility track SOMEWHERE, but in
    3 of those every track sits on an object that does not itself animate.
    Only the 157 with a track on an animated object produce a sidecar curve,
    because the runtime samples the curve off that object's AnimationPlayer.
    """
    from src.exporters.prop_animation import build_animation_plan

    animated = animated_props()
    with_any_track = 0
    with_usable_curve = 0
    for cat, prop_id, tmd_path in discover_props():
        if (cat, prop_id) not in animated:
            continue
        model = TMDParser().parse(tmd_path)
        if model.visibility_tracks:
            with_any_track += 1
        if build_animation_plan(model, prop_id).visibility:
            with_usable_curve += 1
    assert with_any_track == 160
    assert with_usable_curve == 157
