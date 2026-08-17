import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts._prop_config import discover_props
from src.parsers.tmd_parser import TMDParser
from tests.test_prop_static_identity import animated_props


def _first_prop_with_ranges():
    for _cat, prop_id, tmd_path in discover_props():
        model = TMDParser().parse(tmd_path)
        if model.anim_ranges:
            return prop_id, model
    raise AssertionError("no prop with animation ranges found")


def test_anim_range_shape():
    _prop_id, model = _first_prop_with_ranges()
    for rng in model.anim_ranges:
        assert isinstance(rng.range_id, int)
        assert rng.end_frame >= rng.start_frame
        assert rng.start_frame >= 0.0


def test_properties_are_named_and_typed():
    _prop_id, model = _first_prop_with_ranges()
    names = {p.name for p in model.properties}
    assert "ANIMATION" in names


def test_only_animation_properties_become_ranges():
    """SOUND records are parsed but must never produce an animation range."""
    checked = 0
    for _cat, _prop_id, tmd_path in discover_props():
        model = TMDParser().parse(tmd_path)
        if not model.properties:
            continue
        anim_records = [p for p in model.properties if p.name == "ANIMATION"]
        assert len(model.anim_ranges) == len(
            [p for p in anim_records if len(p.params) >= 3]
        )
        checked += 1
        if checked >= 50:
            break
    assert checked > 0


# Property names the original client acts on. Anything
# else is rejected by AddPropertyParam and never reaches the runtime.
ENGINE_PROPERTY_NAMES = {"ANIMATION", "SOUND"}

# Authoring-tool leftovers the files DO contain and the engine ignores:
# 3ds Max reactor/Havok rigid-body settings, all on a_SWIdoor01_03.
# ("ELLASTICITY" is reactor's own misspelling — kept verbatim.)
INERT_PROPERTY_NAMES = {
    "MASS", "ELLASTICITY", "FRICTION", "UNYIELDING", "PHANTOM",
    "SIMULATION_GEOMETRY", "PROXY_GEOMETRY", "USE_DISPLAY_PROXY",
    "DISABLE_COLLISIONS", "INACTIVE", "DISPLAY_PROXY",
}


def test_property_names_across_the_whole_library():
    """Every name in the library is either engine-recognised or known-inert.

    A name outside both sets means the param reader has desynced — that is
    the failure this guards, not the mere presence of extra names.
    """
    names: set[str] = set()
    for _cat, _prop_id, tmd_path in discover_props():
        for prop in TMDParser().parse(tmd_path).properties:
            names.add(prop.name)
    unexpected = names - ENGINE_PROPERTY_NAMES - INERT_PROPERTY_NAMES
    assert not unexpected, f"unexpected property names: {unexpected}"


def test_inert_properties_never_become_ranges():
    """Physics-authoring properties must not be mistaken for animation."""
    from scripts._prop_config import PROP_BASE

    model = TMDParser().parse(PROP_BASE / "Artificial.IRD" / "a_SWIdoor01_03.TMD")
    inert = [p for p in model.properties if p.name in INERT_PROPERTY_NAMES]
    assert inert, "fixture no longer carries reactor properties"
    for rng in model.anim_ranges:
        assert rng.range_id is not None
    # Ranges come only from ANIMATION records.
    animation_records = [p for p in model.properties
                         if p.name == "ANIMATION" and len(p.params) >= 3]
    assert len(model.anim_ranges) == len(animation_records)


def test_prop_with_ranges_census():
    """96 of the 188 animated props carry real PROPERTYTRACK records.

    Three props carry the chunk but declare objectID -1 and propertyCount 0 —
    a_SWWgate01, a_SWAboard01a, a_SWAlobby01a — so a chunk-presence census
    runs three ahead of the usable-range count.
    """
    animated = animated_props()
    with_ranges = 0
    empty = []
    for cat, prop_id, tmd_path in discover_props():
        if (cat, prop_id) not in animated:
            continue
        model = TMDParser().parse(tmd_path)
        if model.properties:
            with_ranges += 1
        elif model.anim_ranges:
            empty.append(prop_id)
    assert not empty
    assert with_ranges == 96
