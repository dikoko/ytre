"""NPC export configuration — shared between 21_export_npcs.py and tweak_test.py."""

# NPCs where reflection auto-detect is wrong (physics-only reflections)
FORCE_TMD_SCALE = {
    'cn0007',
    'cn0047',  # Reflections only in skirt physics bones
    'cn0109',  # Reflections only in skirt physics bones
}

# Skip auto-reparenting for these models (complex bone setups that break)
SKIP_REPARENT = {
    'cn0009',  # Hand sword + back swords share bone chain
    'cn0047',  # Tea cup - reparenting makes it disappear
}

# Per-model bone index overrides for physics smoothing
SMOOTH_BONES: dict[str, set[int]] = {
    'cn0007': set(range(25, 54)),
}

# Equip bones that need targeted rotation correction (on-hand but misaligned)
EQUIP_CORRECTION: dict[str, set[int]] = {
    'cn0007': {15, 16},      # @Pipe01, @Pipe00
    'cn0011': {22, 23, 24},  # @fan01, @fan02, @fan00
    'cn0021': {18},           # @abacus
    'cn0024': {23},           # Bip01 Prop1
    'cn0045': {14},           # @Sword
}

# Per-bone tweaks applied AFTER correction
# "rot": [rx,ry,rz] euler degrees, "pos": [x,y,z] position offset
BONE_TWEAKS: dict[str, dict[int, dict]] = {
    'cn0007': {
        15: {"pos": [-0.05, 0, 0]},  # @Pipe01: shift toward palm
    },
    'cn0011': {
        22: {"pos": [-0.1, 0, 0]},   # @fan01: shift toward hand
    },
    'cn0021': {
        18: {"pos": [0, 0, -0.1]},   # @abacus: shift toward hand
    },
    'cn0024': {
        23: {"rot": [10, 110, 0], "pos": [-0.20, 0.05, 0.05]},  # Bip01 Prop1: book position+angle
    },
    'cn0039': {
        87: {"pos": [-0.126, -0.258, -0.017]},  # @broom-stick: align to hand+chest
    },
    'cn0040': {
        77: {"pos": [-0.1, -0.6, 0]},  # @broom-stick: approximate hand position
    },
    'cn0045': {
        14: {"rot": [0, 0, -20], "pos": [0.30, 0.03, -0.20]},  # @Sword: position+angle
    },
}
