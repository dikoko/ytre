extends Node3D
## Unified avatar tool for viewing and testing both male and female avatars.
##
## Controls:
## - `: Switch between male/female
## - 0: Remove all parts (show base mesh only)
## - 1-5: Cycle forward  (1=hair, 2=upper, 3=lower, 4=hands, 5=feet)
## - Q-T: Cycle backward (q=hair, w=upper, e=lower, r=hands, t=feet)
## - F/V: Cycle face type forward/backward
## - 6-9: Equip equipment (6=blade, 7=glorb, 8=mura, 9=spirit); press again to cycle variants
## - Y-O: Same as 6-9 (y=blade, u=glorb, i=mura, o=spirit)
## - P: Remove equipment (unequip + detach weapon)
## - Tab: Cycle animation mode (T-pose → basic → equip → T-pose)
##         Without equipment: T-pose → basic → T-pose
## - Space: Pause/resume animation (animation mode only)
## - Left/Right: Cycle through animations (animation mode only)
## - H: Toggle parts visibility (debug - see which regions are hidden)
## - D: Print debug state (regions, materials, visibility)

# Node references
var skeleton: Skeleton3D
var animation_player: AnimationPlayer

# Material mesh references - maps material name to MeshInstance3D
var material_meshes: Dictionary = {}

# Camera orbit controls
var camera: Camera3D
var camera_pivot: Node3D
var camera_distance: float = 3.0
var camera_angle_x: float = 0.0  # Horizontal rotation
var camera_angle_y: float = 15.0  # Vertical angle (degrees)
var is_dragging: bool = false
var mouse_sensitivity: float = 0.3

# Debug: toggle parts visibility to see which base regions are hidden
var parts_visible: bool = true

# Equipment types - determines which animations are available
enum EquipmentType { NONE, BLADE, GLORB, MURA, SPIRIT }
var current_equipment: EquipmentType = EquipmentType.NONE

# Animation mode
enum AnimMode { TPOSE, BASIC, EQUIP }
var animation_mode: int = AnimMode.TPOSE
var all_animations: PackedStringArray = []
var animation_list: PackedStringArray = []
var animation_index: int = 0
var animation_paused: bool = false

# Procedural scalp cap to fill gaps behind hair parts
var scalp_cap: MeshInstance3D = null

# Currently attached parts by slot
var current_parts: Dictionary = {
	"hair": null, "upper": null, "lower": null,
	"hands": null, "feet": null, "glorb": null,
}

# Part variants for each slot (set from GENDER_CONFIG on init)
var part_variants: Dictionary = {}

# Current variant index for each slot
var variant_index: Dictionary = {
	"hair": 0, "upper": 0, "lower": 0,
	"hands": 0, "feet": 0, "glorb": 0,
}

# Per-part metadata loaded from JSON (maps part name to hides_regions)
var parts_metadata: Dictionary = {}

# Shared skin material for base mesh fill behind transparent parts
var shared_skin_material: ShaderMaterial

# Debug: neck line investigation
var debug_base_hidden: bool = false
var debug_part_solid: bool = false
var debug_individual_mat: String = ""

# Track which part file is currently equipped in each slot
var current_part_names: Dictionary = {
	"hair": "", "upper": "", "lower": "",
	"hands": "", "feet": "", "glorb": "",
}

# Face state
var current_face_type_index: int = 0
var current_blink_frame: int = 0
var blink_sequence_index: int = 0
var is_blinking: bool = false

# Weapon attachment state
var weapon_attachment: BoneAttachment3D = null
var current_weapon_node: Node3D = null

# GUI references
var gui_layer: CanvasLayer
var character_select: OptionButton
var anim_mode_select: OptionButton
var animation_select: OptionButton
var play_pause_btn: Button
# Monster selector GUI (top bar, visible in monster mode only)
var monster_prev_btn: Button
var monster_select: OptionButton
var monster_next_btn: Button
var monster_selector_container: HBoxContainer  # Container to show/hide
var left_panel: PanelContainer  # Reference for show/hide in monster mode
var slot_name_labels: Dictionary = {}  # slot_name -> Label showing current variant
var blade_variant_index: int = 0
var blade_variants: PackedStringArray = [
	"weapon_blade_A0001.glb", "weapon_blade_A0002.glb", "weapon_blade_A0003.glb",
	"weapon_blade_A0004.glb", "weapon_blade_A0006.glb", "weapon_blade_A0007.glb",
	"weapon_blade_A0008.glb", "weapon_blade_A0009.glb", "weapon_blade_A0011.glb",
	"weapon_blade_A0012.glb", "weapon_blade_A0013.glb", "weapon_blade_A0015.glb",
	"weapon_blade_A0016.glb", "weapon_blade_A0019.glb", "weapon_blade_A0021.glb",
	"weapon_blade_A0022.glb", "weapon_blade_A1001.glb", "weapon_blade_A1002.glb",
	"weapon_blade_A1004.glb", "weapon_blade_A1006.glb", "weapon_blade_A1011.glb",
	"weapon_blade_A1013.glb", "weapon_blade_A1015.glb", "weapon_blade_A1016.glb",
	"weapon_blade_A1019.glb", "weapon_blade_A1021.glb", "weapon_blade_A1022.glb",
]
var mura_variant_index: int = 0
var mura_variants: PackedStringArray = [
	"weapon_mura_A0001.glb", "weapon_mura_A0002.glb", "weapon_mura_A0004.glb",
	"weapon_mura_A0005.glb", "weapon_mura_A0006.glb", "weapon_mura_A0007.glb",
	"weapon_mura_A0008.glb", "weapon_mura_A0009.glb", "weapon_mura_A0010.glb",
	"weapon_mura_A0011.glb", "weapon_mura_A0012.glb", "weapon_mura_A0017.glb",
	"weapon_mura_A0020.glb", "weapon_mura_A0022.glb",
	"weapon_mura_A1001.glb", "weapon_mura_A1002.glb", "weapon_mura_A1004.glb",
	"weapon_mura_A1005.glb", "weapon_mura_A1006.glb", "weapon_mura_A1007.glb",
	"weapon_mura_A1008.glb", "weapon_mura_A1011.glb", "weapon_mura_A1017.glb",
	"weapon_mura_A1022.glb",
]
var spirit_variant_index: int = 0
var spirit_variants: PackedStringArray = [
	"weapon_spirit_A0001.glb", "weapon_spirit_A0002.glb", "weapon_spirit_A0003.glb",
	"weapon_spirit_A0004.glb", "weapon_spirit_A0005.glb", "weapon_spirit_A0006.glb",
	"weapon_spirit_A0008.glb", "weapon_spirit_A0009.glb", "weapon_spirit_A0010.glb",
	"weapon_spirit_A0012.glb", "weapon_spirit_A0013.glb", "weapon_spirit_A0014.glb",
	"weapon_spirit_A0015.glb", "weapon_spirit_A0018.glb",
	"weapon_spirit_A1001.glb", "weapon_spirit_A1002.glb", "weapon_spirit_A1003.glb",
	"weapon_spirit_A1004.glb", "weapon_spirit_A1005.glb", "weapon_spirit_A1006.glb",
	"weapon_spirit_A1008.glb", "weapon_spirit_A1010.glb", "weapon_spirit_A1013.glb",
]

# Pre-compiled shaders (created once in _ready to avoid recompilation on every part swap)
var hair_shader: Shader
var clothing_shader: Shader
var skin_shader: Shader

# Timers (created in _ready)
var blink_timer: Timer
var blink_frame_timer: Timer

# Monster mode state
var monster_root: Node3D
var monster_list: Array[String] = []       # Monster IDs from config
var monster_names: Dictionary = {}         # id -> display name (optional override)
var monster_zooms: Dictionary = {}         # id -> zoom distance (optional override)
var monster_index: int = 0                 # Current monster index
var monster_instance: Node3D = null        # Currently instantiated monster
var monster_anim_player: AnimationPlayer = null
var monster_anim_names: Array[String] = []
var monster_anim_index: int = 0
var monster_cache: Dictionary = {}         # index -> PackedScene (loaded resources)
const MONSTER_CACHE_RADIUS := 5
const MONSTER_DEFAULT_ZOOM := 4.0

# Model viewer paths per category
const MODEL_VIEWER_CONFIG := {
	CharacterMode.MONSTER: {
		"models_path": "res://assets/monsters/models/",
		"config_path": "res://assets/monsters/monsters.yaml",
		"config_key": "monsters:",
		"label": "Monster",
	},
	CharacterMode.NPC: {
		"models_path": "res://assets/npcs/models/",
		"config_path": "res://assets/npcs/npcs.yaml",
		"config_key": "npcs:",
		"label": "NPC",
	},
}
var _viewer_models_path := ""
var _viewer_config_key := ""

# Shared paths
const TEXTURES_BASE_PATH := "res://assets/avatars/textures/base/"
const TEXTURES_PARTS_PATH := "res://assets/avatars/textures/parts/"
const WEAPONS_BLADE_PATH := "res://assets/avatars/weapons/blade/"
const WEAPONS_MURA_PATH := "res://assets/avatars/weapons/mura/"
const WEAPONS_SPIRIT_PATH := "res://assets/avatars/weapons/spirit/"
const TEXTURES_WEAPONS_PATH := "res://assets/avatars/textures/weapons/"
const TEXTURES_FACES_PATH := "res://assets/avatars/textures/faces/"

# Materials that require ALL listed regions to be hidden before hiding the material
const MATERIAL_REQUIRED_REGIONS: Dictionary = {
	"hair_scalp": ["hair_strands"],
	"hair_strands": ["hair_strands"],
	"upper": ["torso", "arm_upper"],
	"arm": ["arm_upper", "forearm"],
	"hand": ["hand"],
	"lower": ["waist"],
	"leg": ["leg_upper", "leg_lower"],
	"foot": ["foot"],
}

# Blink animation configuration
const BLINK_INTERVAL_MIN := 2.0
const BLINK_INTERVAL_MAX := 5.0
const BLINK_FRAME_DURATION := 0.06
const BLINK_SEQUENCE: Array[int] = [0, 1, 2, 1, 0]

# === GENDER CONFIGURATION ===

enum CharacterMode { MALE, FEMALE, MONSTER, NPC }
var current_mode: int = CharacterMode.MALE
var base_avatar_node: Node = null  # Currently active base avatar node

const GENDER_CONFIG: Dictionary = {
	CharacterMode.MALE: {
		"name": "male",
		"base_node_name": "male_base_materials",
		"parts_path": "res://assets/avatars/parts/male/",
		"metadata_path": "res://assets/avatars/parts/parts_metadata.json",
		"anim_prefix": "basic",
		"anim_prefixes": {
			EquipmentType.NONE: ["basic"],
			EquipmentType.BLADE: ["basic", "blade"],
			EquipmentType.GLORB: ["basic", "glorb"],
			EquipmentType.MURA: ["basic", "mura"],
			EquipmentType.SPIRIT: ["basic", "spirit"],
		},
		"stand_anim": "basic_stand",
		"face_prefix": "male_face_M",
		"face_types": ["001", "002", "003", "011", "012", "021", "031", "041", "051", "052"],
		"material_to_texture": {
			"upper": "male_upper_M0000.tga",
			"arm": "male_arm_M0000.tga",
			"foot": "male_foot_M0000.tga",
			"hand": "male_hand_M0000.tga",
			"leg": "male_leg_M0000.tga",
			"lower": "male_lower_M0000.tga",
			"hair_scalp": "male_hair_M0000.tga",
			"hair_strands": "male_hair_M0000.tga",
			"face": null,
		},
		"part_variants": {
			"hair": [
				"male_hair_M0101.glb", "male_hair_M0102.glb", "male_hair_M0103.glb",
				"male_hair_M0201.glb", "male_hair_M0202.glb", "male_hair_M0203.glb",
				"male_hair_M0301.glb", "male_hair_M0302.glb", "male_hair_M0303.glb",
				"male_hair_M0401.glb", "male_hair_M0402.glb", "male_hair_M0403.glb",
				"male_hair_M0501.glb", "male_hair_M0502.glb", "male_hair_M0503.glb",
				"male_hair_M0601.glb", "male_hair_M0602.glb", "male_hair_M0603.glb",
				"male_hair_M0701.glb", "male_hair_M0702.glb", "male_hair_M0703.glb",
				"male_hair_M0801.glb", "male_hair_M0802.glb", "male_hair_M0803.glb",
				"male_hair_M0901.glb", "male_hair_M0902.glb", "male_hair_M0903.glb",
			],
			"upper": [
				"male_upper_M0001.glb", "male_upper_M0002.glb", "male_upper_M0003.glb",
				"male_upper_M0004.glb", "male_upper_M0008.glb", "male_upper_M0009.glb",
				"male_upper_M0011.glb", "male_upper_M0012.glb", "male_upper_M0013.glb",
				"male_upper_M0014.glb", "male_upper_M0016.glb", "male_upper_M0017.glb",
				"male_upper_M0018.glb", "male_upper_M0019.glb", "male_upper_M0022.glb",
				"male_upper_M0023.glb", "male_upper_M0024.glb", "male_upper_M0025.glb",
				"male_upper_M0026.glb", "male_upper_M0031.glb", "male_upper_M0032.glb",
				"male_upper_M1001.glb", "male_upper_M1002.glb", "male_upper_M1009.glb",
				"male_upper_M1011.glb", "male_upper_M1012.glb", "male_upper_M1013.glb",
				"male_upper_M1014.glb", "male_upper_M1016.glb", "male_upper_M1017.glb",
				"male_upper_M1018.glb", "male_upper_M1021.glb", "male_upper_M1024.glb",
				"male_upper_M1026.glb", "male_upper_M1029.glb", "male_upper_M1031.glb",
				"male_upper_M1032.glb", "male_upper_M9002.glb",
			],
			"lower": [
				"male_lower_M0001.glb", "male_lower_M0002.glb", "male_lower_M0003.glb",
				"male_lower_M0004.glb", "male_lower_M0008.glb", "male_lower_M0009.glb",
				"male_lower_M0011.glb", "male_lower_M0012.glb", "male_lower_M0014.glb",
				"male_lower_M0016.glb", "male_lower_M0018.glb", "male_lower_M0019.glb",
				"male_lower_M0022.glb", "male_lower_M0023.glb", "male_lower_M0024.glb",
				"male_lower_M0025.glb", "male_lower_M0026.glb", "male_lower_M0031.glb",
				"male_lower_M0032.glb", "male_lower_M1001.glb", "male_lower_M1002.glb",
				"male_lower_M1009.glb", "male_lower_M1011.glb", "male_lower_M1012.glb",
				"male_lower_M1014.glb", "male_lower_M1016.glb", "male_lower_M1018.glb",
				"male_lower_M1024.glb", "male_lower_M1026.glb", "male_lower_M1029.glb",
				"male_lower_M1031.glb", "male_lower_M1032.glb", "male_lower_M9002.glb",
			],
			"hands": [
				"male_hand_M0004.glb", "male_hand_M0019.glb", "male_hand_M0022.glb",
				"male_hand_M0025.glb", "male_hand_M0032.glb", "male_hand_M1004.glb",
				"male_hand_M1005.glb", "male_hand_M1019.glb", "male_hand_M1020.glb",
				"male_hand_M1026.glb", "male_hand_M1027.glb", "male_hand_M1029.glb",
				"male_hand_M9001.glb",
			],
			"feet": [
				"male_foot_GMM0001.glb",
				"male_foot_M0001.glb", "male_foot_M0002.glb", "male_foot_M0003.glb",
				"male_foot_M0004.glb", "male_foot_M0005.glb", "male_foot_M0006.glb",
				"male_foot_M0007.glb", "male_foot_M0008.glb", "male_foot_M0009.glb",
				"male_foot_M0014.glb", "male_foot_M0018.glb", "male_foot_M0019.glb",
				"male_foot_M0022.glb", "male_foot_M0023.glb", "male_foot_M0024.glb",
				"male_foot_M0025.glb", "male_foot_M0026.glb", "male_foot_M0031.glb",
				"male_foot_M0032.glb", "male_foot_M1001.glb", "male_foot_M1002.glb",
				"male_foot_M1003.glb", "male_foot_M1004.glb", "male_foot_M1005.glb",
				"male_foot_M1006.glb", "male_foot_M1007.glb", "male_foot_M1009.glb",
				"male_foot_M1014.glb", "male_foot_M1018.glb", "male_foot_M1019.glb",
				"male_foot_M1020.glb", "male_foot_M1023.glb", "male_foot_M1024.glb",
				"male_foot_M1025.glb", "male_foot_M1026.glb", "male_foot_M1027.glb",
				"male_foot_M1029.glb", "male_foot_M1031.glb", "male_foot_M1032.glb",
				"male_foot_M9001.glb", "male_foot_M9002.glb",
			],
			"glorb": [
				"male_glorb_A0001.glb", "male_glorb_A0002.glb", "male_glorb_A0003.glb",
				"male_glorb_A0005.glb", "male_glorb_A0007.glb", "male_glorb_A0008.glb",
				"male_glorb_A0009.glb", "male_glorb_A0010.glb", "male_glorb_A0011.glb",
				"male_glorb_A0013.glb", "male_glorb_A0014.glb", "male_glorb_A0015.glb",
				"male_glorb_A0016.glb", "male_glorb_A0019.glb", "male_glorb_A0021.glb",
				"male_glorb_A1001.glb", "male_glorb_A1002.glb", "male_glorb_A1003.glb",
				"male_glorb_A1005.glb", "male_glorb_A1007.glb", "male_glorb_A1009.glb",
				"male_glorb_A1013.glb", "male_glorb_A1014.glb", "male_glorb_A1015.glb",
				"male_glorb_A1019.glb", "male_glorb_A1021.glb",
			],
		},
	},
	CharacterMode.FEMALE: {
		"name": "female",
		"base_node_name": "female_base_materials",
		"parts_path": "res://assets/avatars/parts/female/",
		"metadata_path": "res://assets/avatars/parts/parts_metadata_female.json",
		"anim_prefix": "febasic",
		"anim_prefixes": {
			EquipmentType.NONE: ["febasic"],
			EquipmentType.BLADE: ["febasic", "feblade"],
			EquipmentType.GLORB: ["febasic", "feglorb"],
			EquipmentType.MURA: ["febasic", "femura"],
			EquipmentType.SPIRIT: ["febasic", "fespirit"],
		},
		"stand_anim": "febasic_stand",
		"face_prefix": "female_face_F",
		"face_types": [
			"001", "002", "003", "004", "005",
			"011", "012", "013",
			"021", "022", "023",
			"031", "032", "033",
			"041", "042", "043",
			"051", "052", "053",
		],
		"material_to_texture": {
			"upper": "female_upper_F0000.tga",
			"arm": "female_arm_F0000.tga",
			"foot": "female_foot_F0000.tga",
			"hand": "female_hand_F0000.tga",
			"leg": "female_leg_F0000.tga",
			"lower": "female_lower_F0000.tga",
			"hair_scalp": "female_hair_F0000.tga",
			"hair_strands": "female_hair_F0000.tga",
			"face": null,
		},
		"part_variants": {
			"hair": [
				"female_hair_F0101.glb", "female_hair_F0102.glb", "female_hair_F0103.glb",
				"female_hair_F0201.glb", "female_hair_F0202.glb", "female_hair_F0203.glb",
				"female_hair_F0301.glb", "female_hair_F0302.glb", "female_hair_F0303.glb",
				"female_hair_F0401.glb", "female_hair_F0402.glb", "female_hair_F0403.glb",
				"female_hair_F0501.glb", "female_hair_F0502.glb", "female_hair_F0503.glb",
				"female_hair_F0601.glb", "female_hair_F0602.glb", "female_hair_F0603.glb",
				"female_hair_F0701.glb", "female_hair_F0702.glb", "female_hair_F0703.glb",
				"female_hair_F0801.glb", "female_hair_F0802.glb", "female_hair_F0803.glb",
				"female_hair_F0901.glb", "female_hair_F0902.glb", "female_hair_F0903.glb",
			],
			"upper": [
				"female_upper_F0001.glb", "female_upper_F0002.glb", "female_upper_F0003.glb",
				"female_upper_F0008.glb", "female_upper_F0009.glb", "female_upper_F0011.glb",
				"female_upper_F0012.glb", "female_upper_F0013.glb", "female_upper_F0016.glb",
				"female_upper_F0018.glb", "female_upper_F0019.glb", "female_upper_F0023.glb",
				"female_upper_F0025.glb", "female_upper_F0026.glb", "female_upper_F0031.glb",
				"female_upper_F0032.glb", "female_upper_F1002.glb", "female_upper_F1009.glb",
				"female_upper_F1012.glb", "female_upper_F1013.glb", "female_upper_F1014.glb",
				"female_upper_F1016.glb", "female_upper_F1018.glb", "female_upper_F1021.glb",
				"female_upper_F1026.glb", "female_upper_F1029.glb", "female_upper_F1031.glb",
				"female_upper_F1032.glb", "female_upper_F9002.glb",
			],
			"lower": [
				"female_lower_F0001.glb", "female_lower_F0002.glb", "female_lower_F0003.glb",
				"female_lower_F0008.glb", "female_lower_F0009.glb", "female_lower_F0011.glb",
				"female_lower_F0012.glb", "female_lower_F0016.glb", "female_lower_F0018.glb",
				"female_lower_F0019.glb", "female_lower_F0023.glb", "female_lower_F0025.glb",
				"female_lower_F0026.glb", "female_lower_F0031.glb", "female_lower_F0032.glb",
				"female_lower_F1002.glb", "female_lower_F1009.glb", "female_lower_F1012.glb",
				"female_lower_F1014.glb", "female_lower_F1016.glb", "female_lower_F1017.glb",
				"female_lower_F1018.glb", "female_lower_F1026.glb", "female_lower_F1029.glb",
				"female_lower_F1031.glb", "female_lower_F1032.glb", "female_lower_F9002.glb",
			],
			"hands": [
				"female_hand_F0004.glb", "female_hand_F0019.glb", "female_hand_F0022.glb",
				"female_hand_F0023.glb", "female_hand_F0032.glb", "female_hand_F1004.glb",
				"female_hand_F1005.glb", "female_hand_F1019.glb", "female_hand_F1020.glb",
				"female_hand_F1025.glb", "female_hand_F1026.glb", "female_hand_F1027.glb",
				"female_hand_F1029.glb", "female_hand_F9001.glb",
			],
			"feet": [
				"female_foot_GMF0001.glb",
				"female_foot_F0001.glb", "female_foot_F0002.glb", "female_foot_F0003.glb",
				"female_foot_F0004.glb", "female_foot_F0005.glb", "female_foot_F0006.glb",
				"female_foot_F0007.glb", "female_foot_F0008.glb", "female_foot_F0009.glb",
				"female_foot_F0014.glb", "female_foot_F0018.glb", "female_foot_F0019.glb",
				"female_foot_F0022.glb", "female_foot_F0023.glb", "female_foot_F0024.glb",
				"female_foot_F0025.glb", "female_foot_F0026.glb", "female_foot_F0031.glb",
				"female_foot_F0032.glb", "female_foot_F1001.glb", "female_foot_F1002.glb",
				"female_foot_F1003.glb", "female_foot_F1004.glb", "female_foot_F1005.glb",
				"female_foot_F1006.glb", "female_foot_F1007.glb", "female_foot_F1009.glb",
				"female_foot_F1014.glb", "female_foot_F1018.glb", "female_foot_F1019.glb",
				"female_foot_F1020.glb", "female_foot_F1023.glb", "female_foot_F1024.glb",
				"female_foot_F1025.glb", "female_foot_F1026.glb", "female_foot_F1027.glb",
				"female_foot_F1029.glb", "female_foot_F1031.glb", "female_foot_F1032.glb",
				"female_foot_F9001.glb", "female_foot_F9002.glb",
			],
			"glorb": [
				"female_glorb_A0001.glb", "female_glorb_A0002.glb", "female_glorb_A0003.glb",
				"female_glorb_A0005.glb", "female_glorb_A0007.glb", "female_glorb_A0008.glb",
				"female_glorb_A0009.glb", "female_glorb_A0010.glb", "female_glorb_A0011.glb",
				"female_glorb_A0013.glb", "female_glorb_A0014.glb", "female_glorb_A0015.glb",
				"female_glorb_A0016.glb", "female_glorb_A0019.glb", "female_glorb_A0021.glb",
				"female_glorb_A1001.glb", "female_glorb_A1002.glb", "female_glorb_A1003.glb",
				"female_glorb_A1005.glb", "female_glorb_A1007.glb", "female_glorb_A1009.glb",
				"female_glorb_A1013.glb", "female_glorb_A1014.glb", "female_glorb_A1015.glb",
				"female_glorb_A1019.glb", "female_glorb_A1021.glb",
			],
		},
	},
}

# Helper accessors for current gender config
func _cfg() -> Dictionary:
	return GENDER_CONFIG[current_mode]

func _parts_path() -> String:
	return _cfg()["parts_path"]

func _face_types() -> Array:
	return _cfg()["face_types"]

func _material_to_texture() -> Dictionary:
	return _cfg()["material_to_texture"]

func _anim_prefixes() -> Dictionary:
	return _cfg()["anim_prefixes"]

func _basic_prefix() -> String:
	return _cfg()["anim_prefix"]

func _stand_anim() -> String:
	return _cfg()["stand_anim"]


# === METADATA ===

func _load_parts_metadata() -> void:
	"""Load per-part region hiding metadata from JSON file."""
	var metadata_path = _cfg()["metadata_path"]
	var file = FileAccess.open(metadata_path, FileAccess.READ)
	if not file:
		push_warning("Could not load parts metadata from: " + metadata_path)
		return

	var json_text = file.get_as_text()
	file.close()

	var json = JSON.new()
	var error = json.parse(json_text)
	if error != OK:
		push_error("Failed to parse parts metadata JSON: " + json.get_error_message())
		return

	var data = json.get_data()
	if data.has("parts"):
		parts_metadata = data["parts"]
		print("Loaded metadata for ", parts_metadata.size(), " parts")


func _get_part_hides_regions(part_name: String) -> Array:
	"""Get the regions that a specific part hides."""
	if parts_metadata.has(part_name):
		return parts_metadata[part_name].get("hides_regions", [])
	push_warning("No metadata for part: " + part_name)
	return []


func _load_model_viewer_config(mode: int) -> void:
	"""Load model viewer config from YAML file for the given mode."""
	var cfg = MODEL_VIEWER_CONFIG[mode]
	var config_path: String = cfg["config_path"]
	_viewer_models_path = cfg["models_path"]
	_viewer_config_key = cfg["config_key"]

	var file = FileAccess.open(config_path, FileAccess.READ)
	if not file:
		push_warning("Could not load config: " + config_path)
		return
	var text = file.get_as_text()
	file.close()

	monster_list.clear()
	monster_names.clear()
	monster_zooms.clear()

	var current_id := ""
	for line in text.split("\n"):
		var stripped := line.strip_edges()
		if stripped.is_empty() or stripped.begins_with("#") or stripped == _viewer_config_key:
			continue
		if stripped.begins_with("- id:"):
			current_id = stripped.substr(5).strip_edges()
			monster_list.append(current_id)
		elif stripped.begins_with("name:") and current_id != "":
			monster_names[current_id] = stripped.substr(5).strip_edges()
		elif stripped.begins_with("zoom:") and current_id != "":
			monster_zooms[current_id] = stripped.substr(5).strip_edges().to_float()

	print("Loaded %s config: %d models" % [cfg["label"], monster_list.size()])


func _monster_display_name(monster_id: String) -> String:
	"""Get display name for a monster (custom name or ID)."""
	return monster_names.get(monster_id, monster_id)


func _monster_zoom(monster_id: String) -> float:
	"""Get zoom distance for a monster (custom or default)."""
	return monster_zooms.get(monster_id, MONSTER_DEFAULT_ZOOM)


func _monster_cache_update() -> void:
	"""Update the cache window around current monster_index."""
	if monster_list.is_empty():
		return
	var lo := maxi(0, monster_index - MONSTER_CACHE_RADIUS)
	var hi := mini(monster_list.size() - 1, monster_index + MONSTER_CACHE_RADIUS)

	# Evict entries outside window
	var to_evict: Array[int] = []
	for idx in monster_cache:
		if idx < lo or idx > hi:
			to_evict.append(idx)
	for idx in to_evict:
		monster_cache.erase(idx)

	# Load missing entries in window
	for idx in range(lo, hi + 1):
		if not monster_cache.has(idx):
			var path := _viewer_models_path + monster_list[idx] + ".glb"
			var scene := load(path) as PackedScene
			if scene:
				monster_cache[idx] = scene
			else:
				push_warning("Failed to load monster: " + path)


func _load_monster(index: int) -> void:
	"""Instantiate a monster from cache and set up animation."""
	# Free previous instance
	if monster_instance:
		monster_instance.queue_free()
		monster_instance = null
		monster_anim_player = null
		monster_anim_names.clear()

	monster_index = index
	_monster_cache_update()

	if not monster_cache.has(index):
		push_warning("Monster not in cache: " + monster_list[index])
		return

	var scene: PackedScene = monster_cache[index]
	monster_instance = scene.instantiate()
	monster_root.add_child(monster_instance)

	# Find AnimationPlayer
	monster_anim_player = _find_animation_player(monster_instance)
	if monster_anim_player:
		monster_anim_names.clear()
		for anim_name in monster_anim_player.get_animation_list():
			monster_anim_names.append(anim_name)
		monster_anim_names.sort()

		# Start with "stand" animation if available, else first
		monster_anim_index = 0
		for i in range(monster_anim_names.size()):
			if "stand" in monster_anim_names[i]:
				monster_anim_index = i
				break
		_play_monster_animation()

	# Auto-fit camera
	_camera_auto_fit()

	var mid := monster_list[index]
	var display := _monster_display_name(mid)
	var label := display if display == mid else "%s (%s)" % [display, mid]
	print("Monster: %s (%d/%d) - %d anims, zoom=%.1f" % [
		label, index + 1, monster_list.size(), monster_anim_names.size(), _monster_zoom(mid)
	])


func _play_monster_animation() -> void:
	"""Play the current monster animation."""
	if not monster_anim_player or monster_anim_names.is_empty():
		return
	var anim_name := monster_anim_names[monster_anim_index]
	var anim = monster_anim_player.get_animation(anim_name)
	if anim:
		anim.loop_mode = Animation.LOOP_LINEAR
	monster_anim_player.play(anim_name)
	print("  Animation: %s (%d/%d)" % [
		anim_name, monster_anim_index + 1, monster_anim_names.size()
	])


func _cycle_monster(direction: int) -> void:
	"""Cycle to next/previous monster."""
	if monster_list.is_empty():
		return
	var new_index := (monster_index + direction + monster_list.size()) % monster_list.size()
	_load_monster(new_index)
	_sync_gui()


func _cycle_monster_animation(direction: int) -> void:
	"""Cycle to next/previous monster animation."""
	if monster_anim_names.is_empty():
		return
	monster_anim_index = (monster_anim_index + direction + monster_anim_names.size()) % monster_anim_names.size()
	_play_monster_animation()
	_sync_gui()


func _toggle_monster_pause() -> void:
	"""Toggle pause on monster AnimationPlayer."""
	if not monster_anim_player:
		return
	if monster_anim_player.is_playing():
		monster_anim_player.pause()
	else:
		monster_anim_player.play()
	_sync_gui()


# === MATERIALS ===

func _create_textured_material(texture_path: String, use_hair_shader: bool = false, use_alpha_scissor: bool = false) -> Material:
	"""Create a material with the given texture, reusing pre-compiled shaders."""
	var texture = load(texture_path) as Texture2D
	if not texture:
		push_warning("Could not load texture: " + texture_path)
		return null

	if use_hair_shader:
		var shader_mat = ShaderMaterial.new()
		shader_mat.shader = hair_shader
		shader_mat.set_shader_parameter("hair_texture", texture)
		shader_mat.set_shader_parameter("skin_color", Color(0.992, 0.812, 0.635, 1.0))
		shader_mat.set_shader_parameter("alpha_threshold", 0.3)
		return shader_mat

	if use_alpha_scissor:
		var shader_mat = ShaderMaterial.new()
		shader_mat.shader = clothing_shader
		shader_mat.set_shader_parameter("clothing_texture", texture)
		shader_mat.set_shader_parameter("skin_color", Color(0.992, 0.812, 0.635, 1.0))
		shader_mat.set_shader_parameter("alpha_threshold", 0.5)
		return shader_mat

	var material = StandardMaterial3D.new()
	material.albedo_texture = texture
	material.roughness = 1.0
	material.specular_mode = BaseMaterial3D.SPECULAR_DISABLED
	return material


func _apply_material_textures() -> void:
	"""Apply base textures to material meshes."""
	print("Applying textures to material meshes: ", material_meshes.keys())

	shared_skin_material = ShaderMaterial.new()
	shared_skin_material.shader = skin_shader
	shared_skin_material.set_shader_parameter("skin_color", Color(0.992, 0.812, 0.635, 1.0))

	var mat_to_tex = _material_to_texture()
	for mat_name in material_meshes:
		if mat_name in ["arm", "leg", "hand", "foot"]:
			material_meshes[mat_name].material_override = shared_skin_material
			print("  ", mat_name, " -> shared skin material")
			continue

		var texture_file = mat_to_tex.get(mat_name)
		if texture_file == null:
			print("  No texture mapping for: ", mat_name)
			continue

		var texture_path = TEXTURES_BASE_PATH + texture_file
		print("  ", mat_name, " -> ", texture_file)
		var use_hair_shader = mat_name in ["hair_scalp", "hair_strands"]
		var use_clothing_shader = mat_name in ["upper", "lower"]
		var material = _create_textured_material(texture_path, use_hair_shader, use_clothing_shader)
		if material:
			material_meshes[mat_name].material_override = material
		else:
			print("    FAILED to load texture: ", texture_path)

	print("\n=== FINAL MATERIAL STATE ===")
	for mat_name in material_meshes:
		var mesh: MeshInstance3D = material_meshes[mat_name]
		var mat = mesh.material_override
		if mat is StandardMaterial3D:
			var tex = mat.albedo_texture
			var col = mat.albedo_color
			print("  ", mat_name, ": color=", col, " tex=", tex)
		elif mat is ShaderMaterial:
			print("  ", mat_name, ": ShaderMaterial")
		else:
			print("  ", mat_name, ": ", mat)


func _create_scalp_cap() -> void:
	"""Disabled - procedural scalp cap approach didn't work."""
	pass


# === TEXTURES ===

func _get_part_texture_path(part_name: String) -> String:
	"""Get the texture path for a part, trying TGA then BMP."""
	var tga_path = TEXTURES_PARTS_PATH + part_name + ".tga"
	if ResourceLoader.exists(tga_path):
		return tga_path

	var bmp_path = TEXTURES_PARTS_PATH + part_name + ".bmp"
	if ResourceLoader.exists(bmp_path):
		return bmp_path

	return ""


func _get_face_texture_path(face_type: String, blink_frame: int) -> String:
	"""Get the texture path for a face type and blink frame."""
	var texture_name = _cfg()["face_prefix"] + face_type + str(blink_frame) + ".tga"
	return TEXTURES_FACES_PATH + texture_name


func _update_face_texture() -> void:
	"""Apply current face texture to the face material mesh."""
	if not material_meshes.has("face"):
		return

	var face_types = _face_types()
	var face_type = face_types[current_face_type_index]
	var texture_path = _get_face_texture_path(face_type, current_blink_frame)

	var texture = load(texture_path) as Texture2D
	if not texture:
		push_warning("Could not load face texture: " + texture_path)
		return

	var material = material_meshes["face"].material_override as ShaderMaterial
	if not material:
		var shader = Shader.new()
		shader.code = """
shader_type spatial;

uniform sampler2D face_texture : source_color;
uniform vec4 skin_color : source_color = vec4(0.992, 0.812, 0.635, 1.0);

void fragment() {
	vec4 tex = texture(face_texture, UV);
	ALBEDO = mix(skin_color.rgb, tex.rgb, tex.a);
	ROUGHNESS = 1.0;
	SPECULAR = 0.0;
}
"""
		material = ShaderMaterial.new()
		material.shader = shader
		material.set_shader_parameter("skin_color", Color(0.992, 0.812, 0.635, 1.0))
		material_meshes["face"].material_override = material

	material.set_shader_parameter("face_texture", texture)


# === BLINK ===

func _setup_blink_timers() -> void:
	"""Create and configure blink timers."""
	blink_timer = Timer.new()
	blink_timer.one_shot = true
	blink_timer.timeout.connect(_on_blink_timer_timeout)
	add_child(blink_timer)

	blink_frame_timer = Timer.new()
	blink_frame_timer.one_shot = true
	blink_frame_timer.timeout.connect(_on_blink_frame_timeout)
	add_child(blink_frame_timer)

	_start_blink_timer()


func _start_blink_timer() -> void:
	var interval = randf_range(BLINK_INTERVAL_MIN, BLINK_INTERVAL_MAX)
	blink_timer.start(interval)


func _on_blink_timer_timeout() -> void:
	is_blinking = true
	blink_sequence_index = 0
	_play_blink_frame()


func _on_blink_frame_timeout() -> void:
	blink_sequence_index += 1
	if blink_sequence_index >= BLINK_SEQUENCE.size():
		is_blinking = false
		current_blink_frame = 0
		_update_face_texture()
		_start_blink_timer()
	else:
		_play_blink_frame()


func _play_blink_frame() -> void:
	current_blink_frame = BLINK_SEQUENCE[blink_sequence_index]
	_update_face_texture()
	blink_frame_timer.start(BLINK_FRAME_DURATION)


func _select_face_type(index: int) -> void:
	var face_types = _face_types()
	current_face_type_index = index % face_types.size()
	if current_face_type_index < 0:
		current_face_type_index += face_types.size()
	current_blink_frame = 0
	_update_face_texture()
	print("Face type: ", face_types[current_face_type_index])


func _cycle_face_next() -> void:
	_select_face_type(current_face_type_index + 1)


func _cycle_face_prev() -> void:
	_select_face_type(current_face_type_index - 1)


# === INITIALIZATION ===

func _ready() -> void:
	# Pre-compile shaders
	hair_shader = Shader.new()
	hair_shader.code = """
shader_type spatial;
render_mode cull_disabled;

uniform sampler2D hair_texture : source_color;
uniform vec4 skin_color : source_color = vec4(0.992, 0.812, 0.635, 1.0);
uniform float alpha_threshold : hint_range(0.0, 1.0) = 0.3;

void fragment() {
	vec4 tex = texture(hair_texture, UV);
	ROUGHNESS = 1.0;
	SPECULAR = 0.0;
	if (tex.a < alpha_threshold) {
		ALBEDO = skin_color.rgb;
	} else {
		ALBEDO = tex.rgb;
	}
}
"""

	clothing_shader = Shader.new()
	clothing_shader.code = """
shader_type spatial;

uniform sampler2D clothing_texture : source_color;
uniform vec4 skin_color : source_color = vec4(0.992, 0.812, 0.635, 1.0);
uniform float alpha_threshold : hint_range(0.0, 1.0) = 0.5;

void vertex() {
	VERTEX += NORMAL * 0.001;
}

void fragment() {
	vec4 tex = texture(clothing_texture, UV);
	ROUGHNESS = 1.0;
	SPECULAR = 0.0;
	if (tex.a < alpha_threshold) {
		ALBEDO = skin_color.rgb;
	} else {
		ALBEDO = tex.rgb;
	}
}
"""

	skin_shader = Shader.new()
	skin_shader.code = """
shader_type spatial;

uniform vec4 skin_color : source_color = vec4(0.992, 0.812, 0.635, 1.0);

void fragment() {
	ALBEDO = skin_color.rgb;
	ROUGHNESS = 1.0;
	SPECULAR = 0.0;
}
"""

	# Setup orbit camera
	camera = $Camera3D
	monster_root = $MonsterRoot
	_setup_orbit_camera()

	# Setup blink timers (shared across genders)
	_setup_blink_timers()

	# Initialize with male avatar
	_initialize_avatar()

	_build_gui()
	_sync_gui()


func _initialize_avatar() -> void:
	"""Initialize (or reinitialize) the avatar for the current gender."""
	var cfg = _cfg()
	var gender_name = cfg["name"]
	print("\n=== Initializing ", gender_name.to_upper(), " avatar ===")

	# Load gender-specific part variants
	part_variants = cfg["part_variants"]

	# Show/hide base avatar nodes
	for g in GENDER_CONFIG:
		var node_name = GENDER_CONFIG[g]["base_node_name"]
		var node = get_node_or_null(node_name)
		if node:
			node.visible = (g == current_mode)

	# Find the active base avatar
	var base_node_name = cfg["base_node_name"]
	base_avatar_node = get_node_or_null(base_node_name)
	if not base_avatar_node:
		push_warning("No base avatar found: " + base_node_name)
		return

	# Find skeleton and animation player
	skeleton = _find_skeleton(base_avatar_node)
	animation_player = _find_animation_player(base_avatar_node)

	if not skeleton:
		push_error("Could not find Skeleton3D in base avatar")
		return

	print("Found skeleton: ", skeleton.get_path())
	print("Skeleton has ", skeleton.get_bone_count(), " bones")

	if animation_player:
		all_animations = animation_player.get_animation_list()
		all_animations.sort()
		_update_available_animations()
		print("Found AnimationPlayer with ", all_animations.size(), " animations (", animation_list.size(), " available)")

	# Find material meshes
	material_meshes.clear()
	_find_material_meshes(base_avatar_node)
	print("Found ", material_meshes.size(), " material meshes: ", material_meshes.keys())

	# Load parts metadata
	_load_parts_metadata()

	# Apply textures to base mesh
	_apply_material_textures()

	# Create procedural scalp cap
	_create_scalp_cap()

	# Load default parts
	for slot in ["hair", "upper", "lower", "hands", "feet"]:
		_swap_part(slot, 0)

	# Initialize face
	current_face_type_index = 0
	_update_face_texture()
	print("Face system initialized with ", _face_types().size(), " face types")

	print("Avatar: ", gender_name.to_upper(), ". Animation: T-POSE. Press ` to switch gender, Tab for animation mode.")


func _switch_gender() -> void:
	"""Switch between male and female avatars."""
	# Tear down current state
	_remove_all_parts()
	_unequip()
	_enter_tpose()

	# Switch gender
	if current_mode == CharacterMode.MALE:
		current_mode = CharacterMode.FEMALE
	else:
		current_mode = CharacterMode.MALE

	# Reset variant indices
	for slot in variant_index:
		variant_index[slot] = 0

	# Reinitialize
	_initialize_avatar()
	_sync_gui()


func _enter_model_viewer(mode: int) -> void:
	"""Switch to model viewer (monster or NPC). Handles avatar->viewer and viewer->viewer."""
	# Clean up previous model viewer state (if switching between Monster/NPC)
	if monster_instance:
		monster_instance.queue_free()
		monster_instance = null
	monster_anim_player = null
	monster_anim_names.clear()
	monster_cache.clear()

	# Tear down avatar state
	_remove_all_parts()
	_unequip()
	if animation_player:
		animation_player.stop()
	if skeleton:
		skeleton.reset_bone_poses()
	animation_mode = AnimMode.TPOSE
	animation_paused = false
	blink_timer.stop()
	blink_frame_timer.stop()

	# Set mode and load config
	current_mode = mode
	_load_model_viewer_config(mode)

	# Hide avatar base meshes
	for g in GENDER_CONFIG:
		var node_name = GENDER_CONFIG[g]["base_node_name"]
		var node = get_node_or_null(node_name)
		if node:
			node.visible = false

	# Load first model
	if monster_list.size() > 0:
		_load_monster(0)

	var label: String = MODEL_VIEWER_CONFIG[mode]["label"]
	_sync_gui()
	print("%s mode. %d models available." % [label, monster_list.size()])


func _exit_monster_mode(target_mode: int) -> void:
	"""Switch from monster mode back to avatar mode."""
	# Free monster instance and cache
	if monster_instance:
		monster_instance.queue_free()
		monster_instance = null
	monster_anim_player = null
	monster_anim_names.clear()
	monster_cache.clear()

	# Reset camera for avatar
	camera_pivot.position.y = 1.0
	camera_distance = 3.0
	camera_angle_x = 0.0
	camera_angle_y = 15.0
	_update_camera_position()

	# Switch to target avatar mode
	current_mode = target_mode
	_start_blink_timer()
	_initialize_avatar()
	_sync_gui()


# === CAMERA ===

func _setup_orbit_camera() -> void:
	if not camera:
		return
	camera_pivot = Node3D.new()
	camera_pivot.name = "CameraPivot"
	add_child(camera_pivot)
	camera_pivot.position = Vector3(0, 1.0, 0)
	_update_camera_position()
	print("Camera controls: Left-drag to rotate, Scroll to zoom")


func _update_camera_position() -> void:
	if not camera:
		return
	var angle_y_rad = deg_to_rad(camera_angle_y)
	var angle_x_rad = deg_to_rad(camera_angle_x)
	var offset = Vector3(
		sin(angle_x_rad) * cos(angle_y_rad),
		sin(angle_y_rad),
		cos(angle_x_rad) * cos(angle_y_rad)
	) * camera_distance
	camera.position = camera_pivot.position + offset
	camera.look_at(camera_pivot.position, Vector3.UP)


func _camera_auto_fit() -> void:
	"""Auto-fit camera distance and pivot to frame the current monster."""
	if not monster_instance or not camera:
		return
	var aabb := _compute_monster_aabb(monster_instance)
	if aabb.size == Vector3.ZERO:
		return
	# Set pivot to AABB center Y
	camera_pivot.position.y = aabb.get_center().y
	# Use per-monster zoom from config (default 4.0)
	var monster_id := monster_list[monster_index]
	camera_distance = _monster_zoom(monster_id)
	_update_camera_position()


func _compute_monster_aabb(node: Node) -> AABB:
	"""Compute combined AABB of all MeshInstance3D children."""
	var meshes: Array[MeshInstance3D] = []
	_find_all_meshes(node, meshes)
	if meshes.is_empty():
		return AABB()
	var result := meshes[0].global_transform * meshes[0].get_aabb()
	for i in range(1, meshes.size()):
		result = result.merge(meshes[i].global_transform * meshes[i].get_aabb())
	return result


func _find_all_meshes(node: Node, out: Array[MeshInstance3D]) -> void:
	if node is MeshInstance3D:
		var mi := node as MeshInstance3D
		if mi.visible and mi.mesh:
			out.append(mi)
	for child in node.get_children():
		_find_all_meshes(child, out)


# === NODE FINDING ===

func _find_skeleton(node: Node) -> Skeleton3D:
	if node is Skeleton3D:
		return node
	for child in node.get_children():
		var result = _find_skeleton(child)
		if result:
			return result
	return null


func _find_animation_player(node: Node) -> AnimationPlayer:
	if node is AnimationPlayer:
		return node
	for child in node.get_children():
		var result = _find_animation_player(child)
		if result:
			return result
	return null


func _find_material_meshes(node: Node) -> void:
	if node is MeshInstance3D:
		var mesh_name = node.name as String
		if mesh_name.begins_with("mesh_"):
			var mat_name = mesh_name.substr(5)
			material_meshes[mat_name] = node
			print("    -> Added material: ", mat_name)

	for child in node.get_children():
		_find_material_meshes(child)


func _find_mesh_in_part(node: Node) -> MeshInstance3D:
	if node is MeshInstance3D:
		return node
	for child in node.get_children():
		var result = _find_mesh_in_part(child)
		if result:
			return result
	return null


# === MATERIAL VISIBILITY ===

func _update_material_visibility() -> void:
	for mat_name in material_meshes:
		material_meshes[mat_name].visible = true

	var all_hidden_regions: Array[String] = []
	for slot in current_parts:
		if current_parts[slot] != null:
			var part_name = current_part_names[slot]
			var hidden_regions = _get_part_hides_regions(part_name)
			for region_name in hidden_regions:
				if not all_hidden_regions.has(region_name):
					all_hidden_regions.append(region_name)

	var hidden_list: Array[String] = []
	for mat_name in MATERIAL_REQUIRED_REGIONS:
		var required_regions = MATERIAL_REQUIRED_REGIONS[mat_name]
		var all_required_hidden = true
		for region_name in required_regions:
			if not all_hidden_regions.has(region_name):
				all_required_hidden = false
				break
		if all_required_hidden:
			if material_meshes.has(mat_name):
				material_meshes[mat_name].visible = false
				hidden_list.append(mat_name)

	if hidden_list.size() > 0:
		print("Hidden materials: ", hidden_list)
	if all_hidden_regions.size() > 0:
		print("All hidden regions: ", all_hidden_regions)


# === PARTS ===

func _swap_part(slot: String, variant_idx: int) -> void:
	if not skeleton:
		push_error("No skeleton available")
		return

	if current_parts[slot]:
		current_parts[slot].queue_free()
		current_parts[slot] = null
		current_part_names[slot] = ""

	variant_index[slot] = variant_idx

	var part_file = part_variants[slot][variant_idx]
	var part_path = _parts_path() + part_file
	var part_scene = load(part_path) as PackedScene

	if not part_scene:
		push_error("Failed to load part: " + part_path)
		return

	var part_instance = part_scene.instantiate()
	var mesh_instance: MeshInstance3D = _find_mesh_in_part(part_instance)

	if not mesh_instance:
		push_error("No MeshInstance3D found in part: " + part_path)
		part_instance.queue_free()
		return

	var part_skin = mesh_instance.skin
	print("  Part skin: ", part_skin)

	mesh_instance.get_parent().remove_child(mesh_instance)
	skeleton.add_child(mesh_instance)

	mesh_instance.skeleton = skeleton.get_path()
	if part_skin:
		mesh_instance.skin = part_skin
		print("  Skin applied from part")

	print("  Skeleton path: ", mesh_instance.skeleton)
	part_instance.queue_free()

	current_parts[slot] = mesh_instance
	var part_name = part_file.replace(".glb", "")
	current_part_names[slot] = part_name
	print("Attached ", slot, ": ", part_file)

	var texture_path = _get_part_texture_path(part_name)
	if texture_path != "":
		var use_hair_shader = slot == "hair"
		var use_alpha = slot in ["upper", "lower", "hands", "feet", "special", "glorb"]
		var material = _create_textured_material(texture_path, use_hair_shader, use_alpha)
		if material:
			mesh_instance.material_override = material
			print("  Applied texture: ", texture_path.get_file(), " (hair_shader: ", use_hair_shader, ", alpha_scissor: ", use_alpha, ")")

	_update_material_visibility()


func _cycle_part(slot: String) -> void:
	var next_idx = (variant_index[slot] + 1) % part_variants[slot].size()
	_swap_part(slot, next_idx)


func _cycle_part_prev(slot: String) -> void:
	var count = part_variants[slot].size()
	var prev_idx = (variant_index[slot] - 1 + count) % count
	_swap_part(slot, prev_idx)


func _remove_all_parts() -> void:
	print("Removing all parts...")
	for slot in current_parts:
		if current_parts[slot]:
			current_parts[slot].queue_free()
			current_parts[slot] = null
			current_part_names[slot] = ""
	_update_material_visibility()


func _toggle_parts_visibility() -> void:
	parts_visible = not parts_visible
	for slot in current_parts:
		if current_parts[slot]:
			current_parts[slot].visible = parts_visible

	if parts_visible:
		print("Parts VISIBLE - normal view")
	else:
		print("Parts HIDDEN - showing base mesh materials only")
		for mat_name in material_meshes:
			if not material_meshes[mat_name].visible:
				print("  ", mat_name, " (hidden by equipped part)")


# === DEBUG ===

func _print_debug_state() -> void:
	print("\n=== DEBUG STATE ===")
	print("Gender: ", _cfg()["name"])
	print("\nEquipped parts:")
	for slot in current_parts:
		if current_parts[slot]:
			var part_name = current_part_names[slot]
			var hidden_regions = _get_part_hides_regions(part_name)
			print("  ", slot, ": ", part_name)
			print("    hides regions: ", hidden_regions)
		else:
			print("  ", slot, ": (none)")

	var face_types = _face_types()
	print("\nFace:")
	print("  Type: ", face_types[current_face_type_index], " (index ", current_face_type_index, ")")
	print("  Blink frame: ", current_blink_frame)
	print("  Is blinking: ", is_blinking)

	print("\nBase mesh materials:")
	for mat_name in material_meshes:
		var mesh: MeshInstance3D = material_meshes[mat_name]
		var has_material = mesh.material_override != null
		var has_texture = false
		if has_material and mesh.material_override is StandardMaterial3D:
			has_texture = mesh.material_override.albedo_texture != null
		print("  ", mat_name, ": visible=", mesh.visible, ", material=", has_material, ", texture=", has_texture)

	print("\nPart textures:")
	for slot in current_parts:
		if current_parts[slot]:
			var mesh: MeshInstance3D = current_parts[slot]
			var has_material = mesh.material_override != null
			var has_texture = false
			if has_material:
				has_texture = mesh.material_override.albedo_texture != null
			print("  ", slot, ": material=", has_material, ", texture=", has_texture)
	print("===================\n")


func _debug_color_meshes() -> void:
	var colors = {
		"upper": Color.RED, "arm": Color.GREEN, "foot": Color.BLUE,
		"hand": Color.YELLOW, "leg": Color.CYAN, "lower": Color.MAGENTA,
		"hair_scalp": Color.ORANGE, "hair_strands": Color.PURPLE, "face": Color.WHITE,
	}
	print("\n=== DEBUG COLOR MODE ===")
	for mat_name in material_meshes:
		var mesh: MeshInstance3D = material_meshes[mat_name]
		var mat = StandardMaterial3D.new()
		mat.albedo_color = colors.get(mat_name, Color.GRAY)
		mesh.material_override = mat
		print("  ", mat_name, " -> ", colors.get(mat_name, Color.GRAY))
	print("Press R to restore normal textures")


func _restore_textures() -> void:
	_apply_material_textures()
	_update_face_texture()
	print("Textures restored")


func _debug_toggle_base_mesh() -> void:
	debug_base_hidden = not debug_base_hidden
	for mat_name in material_meshes:
		material_meshes[mat_name].visible = not debug_base_hidden
	if debug_base_hidden:
		print("[DIAG] Base mesh HIDDEN")
	else:
		print("[DIAG] Base mesh VISIBLE")
		_update_material_visibility()


func _debug_toggle_part_solid() -> void:
	debug_part_solid = not debug_part_solid
	var upper_mesh = current_parts.get("upper")
	if not upper_mesh:
		print("[DIAG] No upper part equipped!")
		return
	if debug_part_solid:
		var mat = StandardMaterial3D.new()
		mat.albedo_color = Color(0.0, 0.8, 0.0)
		upper_mesh.material_override = mat
		print("[DIAG] Upper part -> SOLID GREEN")
	else:
		var part_name = current_part_names["upper"]
		var texture_path = _get_part_texture_path(part_name)
		if texture_path != "":
			var material = _create_textured_material(texture_path)
			if material:
				upper_mesh.material_override = material
		_apply_material_textures()
		_update_material_visibility()
		print("[DIAG] Upper part + base mesh RESTORED")


func _debug_cycle_base_material() -> void:
	var neck_materials = ["arm", "face", "upper", ""]
	var current_idx = neck_materials.find(debug_individual_mat)
	var next_idx = (current_idx + 1) % neck_materials.size()
	debug_individual_mat = neck_materials[next_idx]

	for mat_name in material_meshes:
		material_meshes[mat_name].visible = true
	_update_material_visibility()

	if debug_individual_mat != "":
		if material_meshes.has(debug_individual_mat):
			material_meshes[debug_individual_mat].visible = false
			print("[DIAG] Hiding base '", debug_individual_mat, "'")
	else:
		print("[DIAG] All base materials RESTORED")


# === ANIMATIONS ===

func _update_available_animations() -> void:
	var prefixes: Array
	var basic = _basic_prefix()
	if animation_mode == AnimMode.EQUIP:
		var equip_prefixes = _anim_prefixes().get(current_equipment, [])
		prefixes = equip_prefixes.filter(func(p): return p != basic)
	else:
		prefixes = [basic]
	var filtered: PackedStringArray = []
	for anim_name in all_animations:
		for prefix in prefixes:
			if anim_name.begins_with(prefix):
				filtered.append(anim_name)
				break
	animation_list = filtered


func _cycle_animation_mode() -> void:
	match animation_mode:
		AnimMode.TPOSE:
			animation_mode = AnimMode.BASIC
			animation_paused = false
			_update_available_animations()
			var stand_idx = animation_list.find(_stand_anim())
			animation_index = stand_idx if stand_idx >= 0 else 0
			_play_current_animation()
			print("Animation: BASIC (", animation_list.size(), " animations). Tab=next mode.")
		AnimMode.BASIC:
			if current_equipment != EquipmentType.NONE:
				animation_mode = AnimMode.EQUIP
				animation_paused = false
				_update_available_animations()
				if animation_list.is_empty():
					animation_mode = AnimMode.BASIC
					_update_available_animations()
					print("No equip animations available, staying in BASIC mode.")
				else:
					animation_index = 0
					_play_current_animation()
					var equip_name = EquipmentType.keys()[current_equipment].to_lower()
					print("Animation: EQUIP/", equip_name, " (", animation_list.size(), " animations). Tab=T-pose.")
			else:
				_enter_tpose()
		AnimMode.EQUIP:
			_enter_tpose()
	_sync_gui()


func _enter_tpose() -> void:
	animation_mode = AnimMode.TPOSE
	animation_paused = false
	if animation_player:
		animation_player.stop()
	if skeleton:
		skeleton.reset_bone_poses()
	print("Animation: T-POSE. Tab=enter animation mode.")
	_sync_gui()


func _play_current_animation() -> void:
	if not animation_player or animation_list.is_empty():
		return
	var anim_name = animation_list[animation_index]
	var anim = animation_player.get_animation(anim_name)
	if anim:
		anim.loop_mode = Animation.LOOP_LINEAR
	animation_player.play(anim_name)
	print("Playing [", animation_index + 1, "/", animation_list.size(), "]: ", anim_name)
	_sync_gui()


func _toggle_animation_pause() -> void:
	if not animation_player:
		return
	animation_paused = not animation_paused
	if animation_paused:
		animation_player.pause()
		print("Paused")
	else:
		animation_player.play()
		print("Resumed")
	_sync_gui()


func _cycle_animation(direction: int) -> void:
	if animation_list.is_empty():
		return
	animation_index = (animation_index + direction) % animation_list.size()
	if animation_index < 0:
		animation_index += animation_list.size()
	animation_paused = false
	_play_current_animation()


# === WEAPONS ===

func _attach_weapon(glb_filename: String, weapons_path: String, bone: String) -> void:
	_detach_weapon()

	var weapon_path = weapons_path + glb_filename
	var weapon_scene = load(weapon_path) as PackedScene
	if not weapon_scene:
		push_error("Failed to load weapon: " + weapon_path)
		return

	weapon_attachment = BoneAttachment3D.new()
	weapon_attachment.bone_name = bone
	skeleton.add_child(weapon_attachment)

	current_weapon_node = weapon_scene.instantiate()
	weapon_attachment.add_child(current_weapon_node)

	var weapon_name = glb_filename.replace(".glb", "")
	for child in current_weapon_node.get_children():
		if child is MeshInstance3D:
			var mesh_name = child.name as String
			if mesh_name.begins_with("blade_low") or mesh_name.begins_with("blade_high"):
				child.visible = false
			elif mesh_name.begins_with("weapon_"):
				var tex_path = _get_weapon_texture_path(weapon_name)
				if tex_path != "":
					var material = _create_textured_material(tex_path)
					if material:
						child.material_override = material
						print("  Applied weapon texture: ", tex_path.get_file())

	print("Attached weapon: ", glb_filename, " -> ", bone)


func _detach_weapon() -> void:
	if weapon_attachment:
		weapon_attachment.queue_free()
		weapon_attachment = null
		current_weapon_node = null


func _get_weapon_texture_path(weapon_name: String) -> String:
	var bmp_path = TEXTURES_WEAPONS_PATH + weapon_name + ".bmp"
	if ResourceLoader.exists(bmp_path):
		return bmp_path
	var tga_path = TEXTURES_WEAPONS_PATH + weapon_name + ".tga"
	if ResourceLoader.exists(tga_path):
		return tga_path
	return ""


# === EQUIPMENT ===

func _set_equipment(equip_type: EquipmentType) -> void:
	var was_blade = current_equipment == EquipmentType.BLADE
	var was_glorb = current_equipment == EquipmentType.GLORB
	var was_mura = current_equipment == EquipmentType.MURA
	var was_spirit = current_equipment == EquipmentType.SPIRIT
	if current_equipment == equip_type:
		if equip_type == EquipmentType.BLADE:
			blade_variant_index = (blade_variant_index + 1) % blade_variants.size()
			_attach_weapon(blade_variants[blade_variant_index], WEAPONS_BLADE_PATH, "@Sword")
			print("Blade variant [", blade_variant_index + 1, "/", blade_variants.size(), "]: ", blade_variants[blade_variant_index])
		elif equip_type == EquipmentType.GLORB:
			_cycle_part("glorb")
			print("Glorb variant [", variant_index["glorb"] + 1, "/", part_variants["glorb"].size(), "]: ", part_variants["glorb"][variant_index["glorb"]])
		elif equip_type == EquipmentType.MURA:
			mura_variant_index = (mura_variant_index + 1) % mura_variants.size()
			_attach_weapon(mura_variants[mura_variant_index], WEAPONS_MURA_PATH, "@Head")
			print("Mura variant [", mura_variant_index + 1, "/", mura_variants.size(), "]: ", mura_variants[mura_variant_index])
		elif equip_type == EquipmentType.SPIRIT:
			spirit_variant_index = (spirit_variant_index + 1) % spirit_variants.size()
			_attach_weapon(spirit_variants[spirit_variant_index], WEAPONS_SPIRIT_PATH, "@Spine3")
			print("Spirit variant [", spirit_variant_index + 1, "/", spirit_variants.size(), "]: ", spirit_variants[spirit_variant_index])
	else:
		current_equipment = equip_type
		var equip_name = EquipmentType.keys()[current_equipment].to_lower()
		print("Equipped: ", equip_name)

	if current_equipment == EquipmentType.BLADE:
		if not was_blade:
			_attach_weapon(blade_variants[blade_variant_index], WEAPONS_BLADE_PATH, "@Sword")
	elif current_equipment == EquipmentType.MURA:
		if not was_mura:
			_attach_weapon(mura_variants[mura_variant_index], WEAPONS_MURA_PATH, "@Head")
	elif current_equipment == EquipmentType.SPIRIT:
		if not was_spirit:
			_attach_weapon(spirit_variants[spirit_variant_index], WEAPONS_SPIRIT_PATH, "@Spine3")
	else:
		_detach_weapon()

	if current_equipment == EquipmentType.GLORB:
		if not was_glorb:
			if current_parts["hands"]:
				current_parts["hands"].queue_free()
				current_parts["hands"] = null
				current_part_names["hands"] = ""
				print("Removed hands (mutually exclusive with glorb)")
			_swap_part("glorb", variant_index["glorb"])
	elif was_glorb:
		if current_parts["glorb"]:
			current_parts["glorb"].queue_free()
			current_parts["glorb"] = null
			current_part_names["glorb"] = ""
			_update_material_visibility()

	if animation_mode == AnimMode.EQUIP:
		_update_available_animations()
		if animation_list.is_empty():
			animation_mode = AnimMode.BASIC
			_update_available_animations()
		animation_index = 0
		_play_current_animation()
		print("  Animations updated: ", animation_list.size(), " available")
	_sync_gui()


func _unequip() -> void:
	if current_equipment == EquipmentType.NONE:
		return
	var was_glorb = current_equipment == EquipmentType.GLORB
	current_equipment = EquipmentType.NONE
	_detach_weapon()
	if was_glorb and current_parts["glorb"]:
		current_parts["glorb"].queue_free()
		current_parts["glorb"] = null
		current_part_names["glorb"] = ""
		_update_material_visibility()
	print("Unequipped. No equipment.")
	if animation_mode == AnimMode.EQUIP:
		animation_mode = AnimMode.BASIC
		animation_paused = false
		_update_available_animations()
		var stand_idx = animation_list.find(_stand_anim())
		animation_index = stand_idx if stand_idx >= 0 else 0
		_play_current_animation()
		print("  Fell back to BASIC mode (no equipment).")
	_sync_gui()


# === GUI ===

func _build_gui() -> void:
	gui_layer = CanvasLayer.new()
	gui_layer.layer = 10
	add_child(gui_layer)

	# Root layout: full-screen VBox with top bar + content area
	var root = VBoxContainer.new()
	root.set_anchors_preset(Control.PRESET_FULL_RECT)
	root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	gui_layer.add_child(root)

	# === TOP BAR ===
	var top_bar = PanelContainer.new()
	top_bar.mouse_filter = Control.MOUSE_FILTER_STOP
	root.add_child(top_bar)

	var top_layout = HBoxContainer.new()
	top_layout.add_theme_constant_override("separation", 12)
	top_bar.add_child(top_layout)

	# Character selector
	character_select = OptionButton.new()
	character_select.add_item("Male", CharacterMode.MALE)
	character_select.add_item("Female", CharacterMode.FEMALE)
	character_select.add_item("Monster", CharacterMode.MONSTER)
	character_select.add_item("NPC", CharacterMode.NPC)
	character_select.selected = current_mode
	character_select.item_selected.connect(_on_character_selected)
	top_layout.add_child(character_select)

	# Animation mode selector
	anim_mode_select = OptionButton.new()
	anim_mode_select.add_item("T-pose", AnimMode.TPOSE)
	anim_mode_select.add_item("Basic", AnimMode.BASIC)
	anim_mode_select.add_item("Equip", AnimMode.EQUIP)
	anim_mode_select.selected = animation_mode
	anim_mode_select.item_selected.connect(_on_anim_mode_selected)
	top_layout.add_child(anim_mode_select)

	# Monster selector (visible in monster mode only)
	monster_selector_container = HBoxContainer.new()
	monster_selector_container.visible = false
	top_layout.add_child(monster_selector_container)

	monster_prev_btn = Button.new()
	monster_prev_btn.text = "<"
	monster_prev_btn.custom_minimum_size.x = 30
	monster_prev_btn.pressed.connect(func(): _cycle_monster(-1))
	monster_selector_container.add_child(monster_prev_btn)

	monster_select = OptionButton.new()
	monster_select.custom_minimum_size.x = 120
	monster_select.item_selected.connect(_on_monster_selected)
	monster_selector_container.add_child(monster_select)

	monster_next_btn = Button.new()
	monster_next_btn.text = ">"
	monster_next_btn.custom_minimum_size.x = 30
	monster_next_btn.pressed.connect(func(): _cycle_monster(1))
	monster_selector_container.add_child(monster_next_btn)

	# Animation name selector
	animation_select = OptionButton.new()
	animation_select.custom_minimum_size.x = 200
	animation_select.disabled = true  # Disabled in T-pose
	animation_select.item_selected.connect(_on_animation_selected)
	top_layout.add_child(animation_select)

	# Play/pause button
	play_pause_btn = Button.new()
	play_pause_btn.text = ">"
	play_pause_btn.custom_minimum_size.x = 40
	play_pause_btn.disabled = true  # Disabled in T-pose
	play_pause_btn.pressed.connect(_on_play_pause_pressed)
	top_layout.add_child(play_pause_btn)

	# Content area below top bar (left panel + viewport fill)
	var content = HBoxContainer.new()
	content.size_flags_vertical = Control.SIZE_EXPAND_FILL
	content.mouse_filter = Control.MOUSE_FILTER_IGNORE
	root.add_child(content)

	# === LEFT PANEL ===
	left_panel = PanelContainer.new()
	left_panel.custom_minimum_size.x = 220
	left_panel.size_flags_vertical = Control.SIZE_EXPAND_FILL
	left_panel.mouse_filter = Control.MOUSE_FILTER_STOP
	content.add_child(left_panel)

	var scroll = ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.mouse_filter = Control.MOUSE_FILTER_PASS
	left_panel.add_child(scroll)

	var left_layout = VBoxContainer.new()
	left_layout.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	left_layout.add_theme_constant_override("separation", 4)
	scroll.add_child(left_layout)

	# Part slots
	_build_slot_row(left_layout, "hair", "Hair")
	_build_slot_row(left_layout, "upper", "Upper")
	_build_slot_row(left_layout, "lower", "Lower")
	_build_slot_row(left_layout, "hands", "Hands")
	_build_slot_row(left_layout, "feet", "Feet")
	_build_slot_row(left_layout, "face", "Face")

	# Separator
	var separator = HSeparator.new()
	left_layout.add_child(separator)

	# Equipment slots
	_build_slot_row(left_layout, "blade", "Blade")
	_build_slot_row(left_layout, "glorb", "Glorb")
	_build_slot_row(left_layout, "mura", "Mura")
	_build_slot_row(left_layout, "spirit", "Spirit")

	# Viewport fill (transparent, passes input to 3D scene)
	var viewport_fill = Control.new()
	viewport_fill.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	viewport_fill.mouse_filter = Control.MOUSE_FILTER_IGNORE
	content.add_child(viewport_fill)


func _build_slot_row(parent: Control, slot_name: String, display_name: String) -> void:
	var container = VBoxContainer.new()
	parent.add_child(container)

	var label = Label.new()
	label.text = display_name
	label.add_theme_font_size_override("font_size", 11)
	container.add_child(label)

	var row = HBoxContainer.new()
	container.add_child(row)

	var prev_btn = Button.new()
	prev_btn.text = "<"
	prev_btn.custom_minimum_size.x = 30
	prev_btn.pressed.connect(_on_slot_prev.bind(slot_name))
	row.add_child(prev_btn)

	var name_label = Label.new()
	name_label.text = "None"
	name_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	name_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	name_label.add_theme_font_size_override("font_size", 11)
	row.add_child(name_label)
	slot_name_labels[slot_name] = name_label

	var next_btn = Button.new()
	next_btn.text = ">"
	next_btn.custom_minimum_size.x = 30
	next_btn.pressed.connect(_on_slot_next.bind(slot_name))
	row.add_child(next_btn)


func _sync_gui() -> void:
	if not gui_layer:
		return

	# Character selector
	character_select.selected = current_mode

	# Toggle monster vs avatar UI
	var is_monster := current_mode in [CharacterMode.MONSTER, CharacterMode.NPC]
	anim_mode_select.visible = not is_monster
	monster_selector_container.visible = is_monster
	left_panel.visible = not is_monster

	if is_monster:
		# Monster animation dropdown
		animation_select.clear()
		animation_select.disabled = false
		play_pause_btn.disabled = false
		for i in range(monster_anim_names.size()):
			animation_select.add_item(monster_anim_names[i], i)
		if monster_anim_index >= 0 and monster_anim_index < monster_anim_names.size():
			animation_select.selected = monster_anim_index
		play_pause_btn.text = "||" if (monster_anim_player and monster_anim_player.is_playing()) else ">"

		# Monster selector dropdown
		monster_select.clear()
		for i in range(monster_list.size()):
			monster_select.add_item(_monster_display_name(monster_list[i]), i)
		if monster_index >= 0 and monster_index < monster_list.size():
			monster_select.selected = monster_index
		return  # Skip avatar-specific sync below

	# Animation mode selector
	anim_mode_select.selected = animation_mode
	# Disable Equip option when no equipment
	anim_mode_select.set_item_disabled(AnimMode.EQUIP, current_equipment == EquipmentType.NONE)

	# Animation dropdown
	animation_select.clear()
	if animation_mode == AnimMode.TPOSE:
		animation_select.disabled = true
		play_pause_btn.disabled = true
	else:
		animation_select.disabled = false
		play_pause_btn.disabled = false
		for i in range(animation_list.size()):
			animation_select.add_item(animation_list[i], i)
		if animation_index >= 0 and animation_index < animation_list.size():
			animation_select.selected = animation_index

	# Play/pause button text
	play_pause_btn.text = "||" if (animation_mode != AnimMode.TPOSE and not animation_paused) else ">"

	# Part slot labels
	for slot in ["hair", "upper", "lower", "hands", "feet"]:
		if slot_name_labels.has(slot):
			var name = current_part_names.get(slot, "")
			if name == "":
				slot_name_labels[slot].text = "None"
			else:
				# Strip prefix and extension: "male_hair_M0101.glb" -> "hair_M0101"
				slot_name_labels[slot].text = name.get_file().get_basename().trim_prefix(_cfg()["name"] + "_")

	# Face label
	if slot_name_labels.has("face"):
		var face_types = _face_types()
		slot_name_labels["face"].text = "Face " + face_types[current_face_type_index]

	# Equipment labels — only show name for the active equipment type
	var equip_slots = {
		"blade": [EquipmentType.BLADE, blade_variants, blade_variant_index],
		"glorb": [EquipmentType.GLORB, [], 0],  # glorb uses part system
		"mura": [EquipmentType.MURA, mura_variants, mura_variant_index],
		"spirit": [EquipmentType.SPIRIT, spirit_variants, spirit_variant_index],
	}
	for slot in equip_slots:
		if not slot_name_labels.has(slot):
			continue
		var equip_type = equip_slots[slot][0]
		if current_equipment != equip_type:
			slot_name_labels[slot].text = "None"
		elif slot == "glorb":
			var glorb_name = current_part_names.get("glorb", "")
			if glorb_name == "":
				slot_name_labels[slot].text = "None"
			else:
				slot_name_labels[slot].text = glorb_name.get_file().get_basename().trim_prefix(_cfg()["name"] + "_")
		else:
			var variants = equip_slots[slot][1]
			var idx = equip_slots[slot][2]
			if variants.size() > 0:
				# "weapon_blade_A0001.glb" -> "blade_A0001"
				slot_name_labels[slot].text = variants[idx].get_basename().trim_prefix("weapon_")
			else:
				slot_name_labels[slot].text = "None"


func _on_character_selected(index: int) -> void:
	if index == current_mode:
		return
	if index in [CharacterMode.MONSTER, CharacterMode.NPC]:
		_enter_model_viewer(index)
	elif current_mode in [CharacterMode.MONSTER, CharacterMode.NPC]:
		_exit_monster_mode(index)
	else:
		# Switching between MALE and FEMALE
		current_mode = index
		_remove_all_parts()
		_unequip()
		_enter_tpose()
		for slot in variant_index:
			variant_index[slot] = 0
		_initialize_avatar()
		_sync_gui()


func _on_anim_mode_selected(index: int) -> void:
	var target_mode = index  # 0=TPOSE, 1=BASIC, 2=EQUIP
	if target_mode == animation_mode:
		return
	if target_mode == AnimMode.TPOSE:
		_enter_tpose()
	elif target_mode == AnimMode.BASIC:
		animation_mode = AnimMode.BASIC
		animation_paused = false
		_update_available_animations()
		var stand_idx = animation_list.find(_stand_anim())
		animation_index = stand_idx if stand_idx >= 0 else 0
		_play_current_animation()
		print("Animation: BASIC (", animation_list.size(), " animations)")
	elif target_mode == AnimMode.EQUIP:
		if current_equipment == EquipmentType.NONE:
			print("Cannot enter Equip mode without equipment.")
			_sync_gui()
			return
		animation_mode = AnimMode.EQUIP
		animation_paused = false
		_update_available_animations()
		if animation_list.is_empty():
			animation_mode = AnimMode.BASIC
			_update_available_animations()
			print("No equip animations available, staying in BASIC mode.")
		else:
			animation_index = 0
			_play_current_animation()
			var equip_name = EquipmentType.keys()[current_equipment].to_lower()
			print("Animation: EQUIP/", equip_name, " (", animation_list.size(), " animations)")
	_sync_gui()


func _on_animation_selected(index: int) -> void:
	if current_mode in [CharacterMode.MONSTER, CharacterMode.NPC]:
		monster_anim_index = index
		_play_monster_animation()
		_sync_gui()
		return
	if animation_mode == AnimMode.TPOSE:
		return
	animation_index = index
	animation_paused = false
	_play_current_animation()
	_sync_gui()


func _on_play_pause_pressed() -> void:
	if current_mode in [CharacterMode.MONSTER, CharacterMode.NPC]:
		_toggle_monster_pause()
		_sync_gui()
		return
	if animation_mode != AnimMode.TPOSE:
		_toggle_animation_pause()
		_sync_gui()


func _on_monster_selected(index: int) -> void:
	if current_mode in [CharacterMode.MONSTER, CharacterMode.NPC] and index != monster_index:
		_load_monster(index)
		_sync_gui()


func _on_slot_prev(slot_name: String) -> void:
	_gui_cycle_slot(slot_name, -1)


func _on_slot_next(slot_name: String) -> void:
	_gui_cycle_slot(slot_name, 1)


func _gui_cycle_slot(slot_name: String, direction: int) -> void:
	match slot_name:
		"hair", "upper", "lower", "feet":
			if direction > 0:
				_cycle_part(slot_name)
			else:
				_cycle_part_prev(slot_name)
		"hands":
			if current_equipment == EquipmentType.GLORB:
				_unequip()
			if direction > 0:
				_cycle_part("hands")
			else:
				_cycle_part_prev("hands")
		"face":
			if direction > 0:
				_cycle_face_next()
			else:
				_cycle_face_prev()
		"blade":
			_gui_cycle_equipment(EquipmentType.BLADE, direction)
		"glorb":
			_gui_cycle_equipment(EquipmentType.GLORB, direction)
		"mura":
			_gui_cycle_equipment(EquipmentType.MURA, direction)
		"spirit":
			_gui_cycle_equipment(EquipmentType.SPIRIT, direction)
	_sync_gui()


func _gui_cycle_equipment(equip_type: EquipmentType, direction: int) -> void:
	if current_equipment == equip_type:
		# Already this type — cycle variant
		match equip_type:
			EquipmentType.BLADE:
				blade_variant_index = (blade_variant_index + direction) % blade_variants.size()
				if blade_variant_index < 0:
					blade_variant_index += blade_variants.size()
				_attach_weapon(blade_variants[blade_variant_index], WEAPONS_BLADE_PATH, "@Sword")
				print("Blade variant [", blade_variant_index + 1, "/", blade_variants.size(), "]: ", blade_variants[blade_variant_index])
			EquipmentType.GLORB:
				if direction > 0:
					_cycle_part("glorb")
				else:
					_cycle_part_prev("glorb")
				print("Glorb variant [", variant_index["glorb"] + 1, "/", part_variants["glorb"].size(), "]: ", part_variants["glorb"][variant_index["glorb"]])
			EquipmentType.MURA:
				mura_variant_index = (mura_variant_index + direction) % mura_variants.size()
				if mura_variant_index < 0:
					mura_variant_index += mura_variants.size()
				_attach_weapon(mura_variants[mura_variant_index], WEAPONS_MURA_PATH, "@Head")
				print("Mura variant [", mura_variant_index + 1, "/", mura_variants.size(), "]: ", mura_variants[mura_variant_index])
			EquipmentType.SPIRIT:
				spirit_variant_index = (spirit_variant_index + direction) % spirit_variants.size()
				if spirit_variant_index < 0:
					spirit_variant_index += spirit_variants.size()
				_attach_weapon(spirit_variants[spirit_variant_index], WEAPONS_SPIRIT_PATH, "@Spine3")
				print("Spirit variant [", spirit_variant_index + 1, "/", spirit_variants.size(), "]: ", spirit_variants[spirit_variant_index])
	else:
		# Different type or none — equip first variant
		# _set_equipment() handles animation updates internally
		_set_equipment(equip_type)
		# _sync_gui() is called by the caller (_gui_cycle_slot calls _sync_gui after this)
		return

	# Only update animations when cycling variants (not first equip)
	if animation_mode == AnimMode.EQUIP:
		_update_available_animations()
		if animation_list.is_empty():
			animation_mode = AnimMode.BASIC
			_update_available_animations()
		animation_index = 0
		_play_current_animation()


# === INPUT ===

func _unhandled_input(event: InputEvent) -> void:
	# Camera controls only fire for events not consumed by GUI
	if event is InputEventMouseButton:
		if event.button_index == MOUSE_BUTTON_LEFT:
			is_dragging = event.pressed
		elif event.button_index == MOUSE_BUTTON_WHEEL_UP and event.pressed:
			camera_distance = max(1.0, camera_distance - 0.3)
			_update_camera_position()
		elif event.button_index == MOUSE_BUTTON_WHEEL_DOWN and event.pressed:
			var max_zoom := 30.0 if current_mode in [CharacterMode.MONSTER, CharacterMode.NPC] else 10.0
			camera_distance = min(max_zoom, camera_distance + 0.3)
			_update_camera_position()

	if event is InputEventMouseMotion and is_dragging:
		camera_angle_x -= event.relative.x * mouse_sensitivity
		camera_angle_y += event.relative.y * mouse_sensitivity
		camera_angle_y = clamp(camera_angle_y, -80.0, 80.0)
		_update_camera_position()

	if event is InputEventMagnifyGesture:
		var max_zoom := 30.0 if current_mode in [CharacterMode.MONSTER, CharacterMode.NPC] else 10.0
		camera_distance = clamp(camera_distance / event.factor, 1.0, max_zoom)
		_update_camera_position()


func _input(event: InputEvent) -> void:
	if not event is InputEventKey or not event.pressed:
		return

	# Monster/NPC mode keyboard shortcuts — consume event to prevent GUI focus change
	if current_mode in [CharacterMode.MONSTER, CharacterMode.NPC]:
		match event.keycode:
			KEY_LEFT:
				_cycle_monster(-1)
			KEY_RIGHT:
				_cycle_monster(1)
			KEY_TAB:
				_cycle_monster_animation(1)
			KEY_SPACE:
				_toggle_monster_pause()
			KEY_QUOTELEFT:
				_exit_monster_mode(CharacterMode.MALE)
		get_viewport().set_input_as_handled()
		return

	match event.keycode:
		KEY_0:
			_unequip()
			_remove_all_parts()
		KEY_1:
			_cycle_part("hair")
		KEY_2:
			_cycle_part("upper")
		KEY_3:
			_cycle_part("lower")
		KEY_4:
			if current_equipment == EquipmentType.GLORB:
				_unequip()
			_cycle_part("hands")
		KEY_5:
			_cycle_part("feet")
		KEY_Q:
			_cycle_part_prev("hair")
		KEY_W:
			_cycle_part_prev("upper")
		KEY_E:
			_cycle_part_prev("lower")
		KEY_R:
			if current_equipment == EquipmentType.GLORB:
				_unequip()
			_cycle_part_prev("hands")
		KEY_T:
			_cycle_part_prev("feet")
		KEY_F:
			_cycle_face_next()
		KEY_V:
			_cycle_face_prev()
		KEY_6, KEY_Y:
			_set_equipment(EquipmentType.BLADE)
		KEY_7, KEY_U:
			_set_equipment(EquipmentType.GLORB)
		KEY_8, KEY_I:
			_set_equipment(EquipmentType.MURA)
		KEY_9, KEY_O:
			_set_equipment(EquipmentType.SPIRIT)
		KEY_TAB:
			_cycle_animation_mode()
		KEY_SPACE:
			if animation_mode != AnimMode.TPOSE:
				_toggle_animation_pause()
		KEY_LEFT:
			if animation_mode != AnimMode.TPOSE:
				_cycle_animation(-1)
		KEY_RIGHT:
			if animation_mode != AnimMode.TPOSE:
				_cycle_animation(1)
		KEY_P:
			_unequip()
		KEY_QUOTELEFT:
			_switch_gender()
		KEY_H:
			_toggle_parts_visibility()
		KEY_D:
			_print_debug_state()
		KEY_C:
			_debug_color_meshes()
		KEY_G:
			_restore_textures()
		KEY_B:
			_debug_toggle_base_mesh()
		KEY_X:
			_debug_toggle_part_solid()
		KEY_N:
			_debug_cycle_base_material()
	_sync_gui()


func _process(_delta: float) -> void:
	pass
