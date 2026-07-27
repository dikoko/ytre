"""Tests for props.yaml catalog writing in scripts/22_export_props.py.

Partial exports (--ids / --category) must MERGE into the existing catalog
instead of clobbering it with only the re-exported subset — a recurring
footgun that repeatedly reduced the 1,576-entry catalog to a handful of
entries. Only --all writes the catalog from scratch.
"""
import importlib

import yaml

export_props = importlib.import_module("scripts.22_export_props")


def _read(path):
    with open(path) as f:
        return yaml.safe_load(f)["props"]


def test_merge_updates_in_place_and_appends_new(tmp_path):
    catalog = tmp_path / "props.yaml"
    existing = [
        {"id": "a_bench01", "category": "artificial", "textures": ["old"]},
        {"id": "n_bigtree01", "category": "nature"},
        {"id": "a_gate01", "category": "artificial"},
    ]
    export_props.write_catalog(existing, catalog)

    export_props.write_catalog(
        [
            {"id": "n_bigtree01", "category": "nature", "textures": ["bark"]},
            {"id": "a_newprop01", "category": "artificial"},
        ],
        catalog,
        merge=True,
    )

    props = _read(catalog)
    # Untouched entries survive, updated entry replaced in place (order kept),
    # unseen id appended at the end.
    assert [p["id"] for p in props] == [
        "a_bench01", "n_bigtree01", "a_gate01", "a_newprop01",
    ]
    assert props[0]["textures"] == ["old"]
    assert props[1]["textures"] == ["bark"]


def test_merge_identical_reexport_is_a_noop(tmp_path):
    catalog = tmp_path / "props.yaml"
    existing = [
        {"id": "a_bench01", "category": "artificial", "textures": ["wood"]},
        {"id": "n_bigtree01", "category": "nature"},
    ]
    export_props.write_catalog(existing, catalog)
    before = catalog.read_text()

    export_props.write_catalog(
        [{"id": "a_bench01", "category": "artificial", "textures": ["wood"]}],
        catalog,
        merge=True,
    )

    assert catalog.read_text() == before


def test_merge_without_existing_catalog_writes_entries(tmp_path):
    catalog = tmp_path / "props.yaml"
    entries = [{"id": "a_bench01", "category": "artificial"}]

    export_props.write_catalog(entries, catalog, merge=True)

    assert _read(catalog) == entries


def test_full_write_replaces_catalog(tmp_path):
    catalog = tmp_path / "props.yaml"
    export_props.write_catalog(
        [{"id": "stale_prop", "category": "artificial"}], catalog,
    )

    export_props.write_catalog(
        [{"id": "a_bench01", "category": "artificial"}], catalog,
    )

    assert [p["id"] for p in _read(catalog)] == ["a_bench01"]
