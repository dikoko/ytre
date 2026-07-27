"""Shared path constants for the eval harness."""
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
YTREF_ROOT = PROJECT_ROOT.parent.parent / "refs"
MAP_IRD = YTREF_ROOT / "models" / "raw" / "Terrain" / "Map.IRD"
TILE_IRD = YTREF_ROOT / "models" / "raw" / "Terrain" / "Tile.IRD"
TCG_PATH = TILE_IRD / "tileregistry.tcg"
CLIENT_DIR = PROJECT_ROOT.parent.parent / "ytlevel" / "client"
REPORTS_DIR = PROJECT_ROOT / "reports"
