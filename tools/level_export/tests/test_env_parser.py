"""Tests for ENV camera parser."""
from pathlib import Path

YTREF_ROOT = Path(__file__).parent.parent.parent.parent / "refs"
MAP_DIR = YTREF_ROOT / "models" / "raw" / "Terrain" / "Map.IRD"


def test_env_sf001001():
    from src.parsers.env_parser import parse_env_camera
    cam = parse_env_camera(MAP_DIR / "SF001001" / "SF001001.env")
    assert cam.up_angle == 55.0 and cam.up_dist == 18.0
    assert cam.dn_angle == -20.0 and cam.dn_dist == 8.0
    assert cam.up_fov == 30.0 and cam.up_far == 70.0
    assert cam.up_near == 1.0 and cam.dn_near == 0.5


def test_env_fd000100():
    from src.parsers.env_parser import parse_env_camera
    cam = parse_env_camera(MAP_DIR / "FD000100" / "FD000100.env")
    assert cam.up_far == 60.0 and cam.dn_far == 60.0


def test_env_missing_gives_defaults():
    from src.parsers.env_parser import parse_env_camera, CameraParams
    cam = parse_env_camera(MAP_DIR / "SF001001" / "does_not_exist.env")
    assert cam == CameraParams.defaults()
    assert cam.up_angle == 60.0 and cam.dn_angle == 15.0
    assert cam.up_dist == 15.0 and cam.dn_dist == 10.0


def test_env_fleet_sane():
    from src.parsers.env_parser import parse_env_camera
    checked = 0
    for d in sorted(MAP_DIR.iterdir()):
        env = d / f"{d.name}.env"
        if not env.is_file():
            continue
        cam = parse_env_camera(env)
        assert 0.0 < cam.up_fov < 120.0, d.name
        assert 0.0 < cam.up_dist < 100.0, d.name
        checked += 1
    assert checked > 300
