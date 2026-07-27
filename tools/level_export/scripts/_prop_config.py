"""
Prop export configuration.

Maps prop categories to source directories and defines constants
for the prop export pipeline.
"""
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
YTREF_ROOT = PROJECT_ROOT.parent.parent / "refs"

# Source directories under the extracted client assets in refs/
PROP_BASE = YTREF_ROOT / "models" / "raw" / "Terrain" / "Object"
TEXTURE_IRD = PROP_BASE / "Texture.IRD"

# Output directories
CLIENT_DIR = PROJECT_ROOT.parent.parent / "ytlevel" / "client"
OUTPUT_BASE = CLIENT_DIR / "assets" / "props"
OUTPUT_MODELS = OUTPUT_BASE / "models"

# Category name → source directory name
CATEGORIES: dict[str, str] = {
    "artificial": "Artificial.IRD",
    "nature": "Nature.IRD",
    "active": "Active.IRD",
    "structure": "Structure.IRD",
    "chair": "Chair.IRD",
    "portal": "Portal.IRD",
    "sky": "Sky.IRD",
    "effect": "Effect.IRD",
    "pointlight": "PointLight.IRD",
}

# Directories evaluated and excluded (no TMD files):
# Fx.IRD — shader/FX definitions only
# Water.IRD — water animation textures only

# All directories to search for textures (central + sibling IRDs that contain textures)
TEXTURE_SEARCH_DIRS: list[Path] = [
    TEXTURE_IRD,
    *(PROP_BASE / d for d in [
        "Active.IRD", "Portal.IRD", "Sky.IRD",
        "PointLight.IRD", "Effect.IRD",
    ]),
    # Some prop TMDs reference skill-effect glow textures via
    # `..\..\..\SKILL\TMD\*.tga` (e.g. n_SEbtree02_event01's light stars).
    YTREF_ROOT / "models" / "raw" / "Skill.IRD" / "TMD",
]


def discover_props(categories: list[str] | None = None) -> list[tuple[str, str, Path]]:
    """Discover all prop TMD files across categories.

    Args:
        categories: Optional filter — only scan these categories.
                    If None, scans all categories.

    Returns:
        List of (category, prop_id, tmd_path) tuples, sorted by (category, prop_id).
    """
    results = []
    cats = categories or list(CATEGORIES.keys())

    for cat in cats:
        dir_name = CATEGORIES.get(cat)
        if not dir_name:
            continue
        cat_dir = PROP_BASE / dir_name
        if not cat_dir.exists():
            continue

        for f in sorted(cat_dir.iterdir()):
            if f.suffix.upper() == ".TMD":
                prop_id = f.stem
                results.append((cat, prop_id, f))

    return results
