"""
Bone Names Visualizer

Creates a JSON sidecar file mapping bone positions to names.
This can be used by Godot scripts to display bone name labels.

Output format:
{
    "bones": [
        {"index": 0, "name": "@Root", "position": [0.0, 0.0, 0.0]},
        ...
    ]
}
"""

import json
from pathlib import Path

from src.parsers.tmd_parser import TMDModel


def create_bone_names_json(model: TMDModel, output_path: Path | str) -> None:
    """
    Create JSON file with bone names and positions.

    Args:
        model: Parsed TMD model
        output_path: Path to output JSON file
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    bones = []
    for i, bone in enumerate(model.bones):
        position = [
            bone.world_transform.translation.x,
            bone.world_transform.translation.y,
            bone.world_transform.translation.z,
        ]
        bones.append({
            "index": i,
            "name": bone.name.strip(),
            "position": position,
            "parent_id": bone.parent_id,
        })

    data = {
        "bone_count": len(bones),
        "bones": bones,
    }

    with open(output_path, 'w') as f:
        json.dump(data, f, indent=2)
