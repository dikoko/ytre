extends Node3D
## Unified avatar tool viewer — uses YTAvatar, YTMonster, YTNPC addons.
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

# === ADDON INSTANCES ===
var _avatar: AvatarCharacter = null
var _model_char: Node3D = null  # MonsterCharacter or NPCCharacter

# === CAMERA ===
var camera: Camera3D
var camera_pivot: Node3D
var camera_distance: float = 3.0
var camera_angle_x: float = 0.0
var camera_angle_y: float = 15.0
var is_dragging: bool = false
var mouse_sensitivity: float = 0.3

# === MODE ===
enum CharacterMode { MALE, FEMALE, MONSTER, NPC }
var current_mode: int = CharacterMode.MALE

# === EQUIPMENT ===
enum EquipmentType { NONE, BLADE, GLORB, MURA, SPIRIT }
var current_equipment: EquipmentType = EquipmentType.NONE

# === ANIMATION ===
enum AnimMode { TPOSE, BASIC, EQUIP }
var animation_mode: int = AnimMode.TPOSE
var all_animations: PackedStringArray = []
var animation_list: PackedStringArray = []
var animation_index: int = 0
var animation_paused: bool = false

# === PARTS (for UI cycling) ===
var part_variants: Dictionary = {}
var variant_index: Dictionary = {
	"hair": 0, "upper": 0, "lower": 0,
	"hands": 0, "feet": 0, "glorb": 0,
}
var current_part_names: Dictionary = {
	"hair": "", "upper": "", "lower": "",
	"hands": "", "feet": "", "glorb": "",
}

# === WEAPON VARIANTS ===
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

# === MONSTER/NPC VIEWER STATE ===
var monster_root: Node3D
var monster_list: Array[String] = []
var monster_names: Dictionary = {}
var monster_zooms: Dictionary = {}
var monster_index: int = 0
var monster_anim_names: Array[String] = []
var monster_anim_index: int = 0
var monster_cache: Dictionary = {}
const MONSTER_CACHE_RADIUS := 5
const MONSTER_DEFAULT_ZOOM := 4.0

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

# === GUI REFS ===
var gui_layer: CanvasLayer
var character_select: OptionButton
var anim_mode_select: OptionButton
var animation_select: OptionButton
var play_pause_btn: Button
var monster_prev_btn: Button
var monster_select: OptionButton
var monster_next_btn: Button
var monster_selector_container: HBoxContainer
var left_panel: PanelContainer
var slot_name_labels: Dictionary = {}

# === GENDER CONFIG (UI cycling data only) ===

const GENDER_CONFIG: Dictionary = {
	CharacterMode.MALE: {
		"name": "male",
		"anim_prefix": "basic",
		"anim_prefixes": {
			EquipmentType.NONE: ["basic"],
			EquipmentType.BLADE: ["basic", "blade"],
			EquipmentType.GLORB: ["basic", "glorb"],
			EquipmentType.MURA: ["basic", "mura"],
			EquipmentType.SPIRIT: ["basic", "spirit"],
		},
		"stand_anim": "basic_stand",
		"face_types": ["001", "002", "003", "011", "012", "021", "031", "041", "051", "052"],
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
		"anim_prefix": "febasic",
		"anim_prefixes": {
			EquipmentType.NONE: ["febasic"],
			EquipmentType.BLADE: ["febasic", "feblade"],
			EquipmentType.GLORB: ["febasic", "feglorb"],
			EquipmentType.MURA: ["febasic", "femura"],
			EquipmentType.SPIRIT: ["febasic", "fespirit"],
		},
		"stand_anim": "febasic_stand",
		"face_types": [
			"001", "002", "003", "004", "005",
			"011", "012", "013", "021", "022", "023",
			"031", "032", "033", "041", "042", "043",
			"051", "052", "053",
		],
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


# === HELPERS ===

func _cfg() -> Dictionary:
	return GENDER_CONFIG[current_mode]

func _anim_prefixes() -> Dictionary:
	return _cfg()["anim_prefixes"]

func _basic_prefix() -> String:
	return _cfg()["anim_prefix"]

func _stand_anim() -> String:
	return _cfg()["stand_anim"]

func _face_types() -> Array:
	return _cfg()["face_types"]

func _extract_variant_code(filename: String) -> String:
	"""Extract variant code from filename: 'male_hair_M0101.glb' -> 'M0101'"""
	var base = filename.get_basename()
	var parts = base.split("_")
	return parts[parts.size() - 1]


# === METADATA ===

func _load_model_viewer_config(mode: int) -> void:
	var cfg = MODEL_VIEWER_CONFIG[mode]
	_viewer_models_path = cfg["models_path"]
	_viewer_config_key = cfg["config_key"]

	var file = FileAccess.open(cfg["config_path"], FileAccess.READ)
	if not file:
		push_warning("Could not load config: " + cfg["config_path"])
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
	return monster_names.get(monster_id, monster_id)

func _monster_zoom(monster_id: String) -> float:
	return monster_zooms.get(monster_id, MONSTER_DEFAULT_ZOOM)


# === MONSTER CACHE ===

func _monster_cache_update() -> void:
	if monster_list.is_empty():
		return
	var lo := maxi(0, monster_index - MONSTER_CACHE_RADIUS)
	var hi := mini(monster_list.size() - 1, monster_index + MONSTER_CACHE_RADIUS)

	var to_evict: Array[int] = []
	for idx in monster_cache:
		if idx < lo or idx > hi:
			to_evict.append(idx)
	for idx in to_evict:
		monster_cache.erase(idx)

	for idx in range(lo, hi + 1):
		if not monster_cache.has(idx):
			var path := _viewer_models_path + monster_list[idx] + ".glb"
			var scene := load(path) as PackedScene
			if scene:
				monster_cache[idx] = scene


# === CAMERA ===

func _setup_orbit_camera() -> void:
	if not camera:
		return
	camera_pivot = Node3D.new()
	camera_pivot.name = "CameraPivot"
	add_child(camera_pivot)
	camera_pivot.position = Vector3(0, 1.0, 0)
	_update_camera_position()

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
	if not _model_char or not camera:
		return
	var aabb := _compute_aabb(_model_char)
	if aabb.size == Vector3.ZERO:
		return
	camera_pivot.position.y = aabb.get_center().y
	var mid := monster_list[monster_index]
	camera_distance = _monster_zoom(mid)
	_update_camera_position()

func _compute_aabb(node: Node) -> AABB:
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


# === INITIALIZATION ===

func _ready() -> void:
	camera = $Camera3D
	monster_root = $MonsterRoot
	_setup_orbit_camera()
	_initialize_avatar()
	_build_gui()
	_sync_gui()


func _initialize_avatar() -> void:
	var cfg = _cfg()
	var gender_name = cfg["name"]
	print("\n=== Initializing ", gender_name.to_upper(), " avatar ===")

	# Create AvatarCharacter addon instance
	if _avatar:
		_avatar.queue_free()
	_avatar = AvatarCharacter.new()
	_avatar.gender = gender_name
	_avatar.default_animation = ""  # We manage animation
	add_child(_avatar)

	# Load part variants for cycling UI
	part_variants = cfg["part_variants"]

	# Get full animation list from addon
	all_animations = _avatar.get_animation_list()
	_update_available_animations()

	# Apply default parts (index 0 for each slot)
	for slot in ["hair", "upper", "lower", "hands", "feet"]:
		_swap_part(slot, 0)

	# Initialize face
	_avatar.set_face(0)

	# Enter T-pose
	animation_mode = AnimMode.TPOSE
	animation_paused = false
	_avatar.stop_animation()

	print("Avatar: ", gender_name.to_upper(), ". Animation: T-POSE. Press ` to switch gender, Tab for animation mode.")


func _switch_gender() -> void:
	_unequip()
	_enter_tpose()

	if current_mode == CharacterMode.MALE:
		current_mode = CharacterMode.FEMALE
	else:
		current_mode = CharacterMode.MALE

	for slot in variant_index:
		variant_index[slot] = 0

	_initialize_avatar()
	_sync_gui()


func _enter_model_viewer(mode: int) -> void:
	# Clean up previous model viewer state
	if _model_char:
		_model_char.queue_free()
		_model_char = null
	monster_anim_names.clear()
	monster_cache.clear()

	# Remove avatar
	if _avatar:
		_avatar.queue_free()
		_avatar = null

	animation_mode = AnimMode.TPOSE
	animation_paused = false

	# Set mode and load config
	current_mode = mode
	_load_model_viewer_config(mode)

	# Create appropriate addon instance
	if mode == CharacterMode.MONSTER:
		var mc = MonsterCharacter.new()
		mc.auto_play = ""
		_model_char = mc
	else:
		var nc = NPCCharacter.new()
		nc.auto_play = ""
		_model_char = nc
	monster_root.add_child(_model_char)

	# Load first model
	if monster_list.size() > 0:
		_load_monster(0)

	var label: String = MODEL_VIEWER_CONFIG[mode]["label"]
	_sync_gui()
	print("%s mode. %d models available." % [label, monster_list.size()])


func _exit_monster_mode(target_mode: int) -> void:
	if _model_char:
		_model_char.queue_free()
		_model_char = null
	monster_anim_names.clear()
	monster_cache.clear()

	# Reset camera for avatar
	camera_pivot.position.y = 1.0
	camera_distance = 3.0
	camera_angle_x = 0.0
	camera_angle_y = 15.0
	_update_camera_position()

	current_mode = target_mode
	_initialize_avatar()
	_sync_gui()


# === PARTS (delegates to addon) ===

func _swap_part(slot: String, variant_idx: int) -> void:
	if not _avatar:
		return
	variant_index[slot] = variant_idx
	var part_file = part_variants[slot][variant_idx]
	var variant_code = _extract_variant_code(part_file)
	_avatar.set_part(slot, variant_code)
	current_part_names[slot] = part_file.get_basename()
	print("Attached ", slot, ": ", part_file)

func _cycle_part(slot: String) -> void:
	var next_idx = (variant_index[slot] + 1) % part_variants[slot].size()
	_swap_part(slot, next_idx)

func _cycle_part_prev(slot: String) -> void:
	var count = part_variants[slot].size()
	var prev_idx = (variant_index[slot] - 1 + count) % count
	_swap_part(slot, prev_idx)

func _remove_all_parts() -> void:
	if _avatar:
		_avatar.remove_all_parts()
	for slot in current_part_names:
		current_part_names[slot] = ""


# === EQUIPMENT (delegates to addon) ===

func _set_equipment(equip_type: EquipmentType) -> void:
	if current_equipment == equip_type:
		# Cycle variant
		match equip_type:
			EquipmentType.BLADE:
				blade_variant_index = (blade_variant_index + 1) % blade_variants.size()
			EquipmentType.GLORB:
				variant_index["glorb"] = (variant_index["glorb"] + 1) % part_variants["glorb"].size()
			EquipmentType.MURA:
				mura_variant_index = (mura_variant_index + 1) % mura_variants.size()
			EquipmentType.SPIRIT:
				spirit_variant_index = (spirit_variant_index + 1) % spirit_variants.size()
	else:
		current_equipment = equip_type
		if equip_type == EquipmentType.GLORB:
			current_part_names["hands"] = ""

	_apply_equipment()

	if animation_mode == AnimMode.EQUIP:
		_update_available_animations()
		if animation_list.is_empty():
			animation_mode = AnimMode.BASIC
			_update_available_animations()
		animation_index = 0
		_play_current_animation()
	_sync_gui()


func _apply_equipment() -> void:
	if not _avatar:
		return
	match current_equipment:
		EquipmentType.BLADE:
			_avatar.equip_weapon("blade", _extract_variant_code(blade_variants[blade_variant_index]))
		EquipmentType.GLORB:
			_avatar.equip_weapon("glorb", _extract_variant_code(part_variants["glorb"][variant_index["glorb"]]))
		EquipmentType.MURA:
			_avatar.equip_weapon("mura", _extract_variant_code(mura_variants[mura_variant_index]))
		EquipmentType.SPIRIT:
			_avatar.equip_weapon("spirit", _extract_variant_code(spirit_variants[spirit_variant_index]))
		EquipmentType.NONE:
			_avatar.unequip_weapon()


func _unequip() -> void:
	if current_equipment == EquipmentType.NONE:
		return
	var was_glorb = current_equipment == EquipmentType.GLORB
	current_equipment = EquipmentType.NONE
	if _avatar:
		_avatar.unequip_weapon()
	if was_glorb:
		current_part_names["glorb"] = ""
	print("Unequipped.")
	if animation_mode == AnimMode.EQUIP:
		animation_mode = AnimMode.BASIC
		animation_paused = false
		_update_available_animations()
		var stand_idx = animation_list.find(_stand_anim())
		animation_index = stand_idx if stand_idx >= 0 else 0
		_play_current_animation()
	_sync_gui()


# === FACE (delegates to addon) ===

func _cycle_face_next() -> void:
	if _avatar:
		var count = _avatar.get_face_type_count()
		var current = _avatar.get_face_type_index()
		_avatar.set_face((current + 1) % count)
		print("Face type: ", _face_types()[_avatar.get_face_type_index()])

func _cycle_face_prev() -> void:
	if _avatar:
		var count = _avatar.get_face_type_count()
		var current = _avatar.get_face_type_index()
		_avatar.set_face((current - 1 + count) % count)
		print("Face type: ", _face_types()[_avatar.get_face_type_index()])


# === ANIMATION ===

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
	if _avatar:
		_avatar.stop_animation()
	print("Animation: T-POSE. Tab=enter animation mode.")
	_sync_gui()

func _play_current_animation() -> void:
	if not _avatar or animation_list.is_empty():
		return
	var anim_name = animation_list[animation_index]
	_avatar.play_animation(anim_name)
	print("Playing [", animation_index + 1, "/", animation_list.size(), "]: ", anim_name)
	_sync_gui()

func _toggle_animation_pause() -> void:
	if not _avatar:
		return
	animation_paused = not animation_paused
	if animation_paused:
		_avatar.pause_animation()
		print("Paused")
	else:
		_avatar.resume_animation()
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


# === MONSTER/NPC OPERATIONS ===

func _load_monster(index: int) -> void:
	monster_index = index
	_monster_cache_update()

	var mid := monster_list[index]
	if _model_char is MonsterCharacter:
		(_model_char as MonsterCharacter).set_monster(mid)
	elif _model_char is NPCCharacter:
		(_model_char as NPCCharacter).set_npc(mid)

	# Get animation info from addon
	monster_anim_names.clear()
	var anim_list: PackedStringArray
	if _model_char is MonsterCharacter:
		anim_list = (_model_char as MonsterCharacter).get_animation_list()
	else:
		anim_list = (_model_char as NPCCharacter).get_animation_list()
	for anim_name in anim_list:
		monster_anim_names.append(anim_name)

	# Find and play stand animation
	monster_anim_index = 0
	for i in range(monster_anim_names.size()):
		if "stand" in monster_anim_names[i]:
			monster_anim_index = i
			break
	_play_monster_animation()

	# Camera auto-fit
	_camera_auto_fit()

	var display := _monster_display_name(mid)
	var label := display if display == mid else "%s (%s)" % [display, mid]
	print("Monster: %s (%d/%d) - %d anims, zoom=%.1f" % [
		label, index + 1, monster_list.size(), monster_anim_names.size(), _monster_zoom(mid)
	])

func _play_monster_animation() -> void:
	if monster_anim_names.is_empty():
		return
	var anim_name := monster_anim_names[monster_anim_index]
	if _model_char is MonsterCharacter:
		(_model_char as MonsterCharacter).play_animation(anim_name)
	elif _model_char is NPCCharacter:
		(_model_char as NPCCharacter).play_animation(anim_name)
	print("  Animation: %s (%d/%d)" % [
		anim_name, monster_anim_index + 1, monster_anim_names.size()
	])

func _cycle_monster(direction: int) -> void:
	if monster_list.is_empty():
		return
	var new_index := (monster_index + direction + monster_list.size()) % monster_list.size()
	_load_monster(new_index)
	_sync_gui()

func _cycle_monster_animation(direction: int) -> void:
	if monster_anim_names.is_empty():
		return
	monster_anim_index = (monster_anim_index + direction + monster_anim_names.size()) % monster_anim_names.size()
	_play_monster_animation()
	_sync_gui()

func _toggle_monster_pause() -> void:
	if _model_char is MonsterCharacter:
		var mc = _model_char as MonsterCharacter
		if mc.is_animation_playing():
			mc.pause_animation()
		else:
			mc.resume_animation()
	elif _model_char is NPCCharacter:
		var nc = _model_char as NPCCharacter
		if nc.is_animation_playing():
			nc.pause_animation()
		else:
			nc.resume_animation()
	_sync_gui()


# === GUI ===

func _build_gui() -> void:
	gui_layer = CanvasLayer.new()
	gui_layer.layer = 10
	add_child(gui_layer)

	var root = VBoxContainer.new()
	root.set_anchors_preset(Control.PRESET_FULL_RECT)
	root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	gui_layer.add_child(root)

	# Top bar
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

	# Monster selector
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

	# Animation selector
	animation_select = OptionButton.new()
	animation_select.custom_minimum_size.x = 200
	animation_select.disabled = true
	animation_select.item_selected.connect(_on_animation_selected)
	top_layout.add_child(animation_select)

	# Play/pause button
	play_pause_btn = Button.new()
	play_pause_btn.text = ">"
	play_pause_btn.custom_minimum_size.x = 40
	play_pause_btn.disabled = true
	play_pause_btn.pressed.connect(_on_play_pause_pressed)
	top_layout.add_child(play_pause_btn)

	# Content area
	var content = HBoxContainer.new()
	content.size_flags_vertical = Control.SIZE_EXPAND_FILL
	content.mouse_filter = Control.MOUSE_FILTER_IGNORE
	root.add_child(content)

	# Left panel
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

	_build_slot_row(left_layout, "hair", "Hair")
	_build_slot_row(left_layout, "upper", "Upper")
	_build_slot_row(left_layout, "lower", "Lower")
	_build_slot_row(left_layout, "hands", "Hands")
	_build_slot_row(left_layout, "feet", "Feet")
	_build_slot_row(left_layout, "face", "Face")

	var separator = HSeparator.new()
	left_layout.add_child(separator)

	_build_slot_row(left_layout, "blade", "Blade")
	_build_slot_row(left_layout, "glorb", "Glorb")
	_build_slot_row(left_layout, "mura", "Mura")
	_build_slot_row(left_layout, "spirit", "Spirit")

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

	character_select.selected = current_mode

	var is_monster := current_mode in [CharacterMode.MONSTER, CharacterMode.NPC]
	anim_mode_select.visible = not is_monster
	monster_selector_container.visible = is_monster
	left_panel.visible = not is_monster

	if is_monster:
		animation_select.clear()
		animation_select.disabled = false
		play_pause_btn.disabled = false
		for i in range(monster_anim_names.size()):
			animation_select.add_item(monster_anim_names[i], i)
		if monster_anim_index >= 0 and monster_anim_index < monster_anim_names.size():
			animation_select.selected = monster_anim_index

		var is_playing := false
		if _model_char is MonsterCharacter:
			is_playing = (_model_char as MonsterCharacter).is_animation_playing()
		elif _model_char is NPCCharacter:
			is_playing = (_model_char as NPCCharacter).is_animation_playing()
		play_pause_btn.text = "||" if is_playing else ">"

		monster_select.clear()
		for i in range(monster_list.size()):
			monster_select.add_item(_monster_display_name(monster_list[i]), i)
		if monster_index >= 0 and monster_index < monster_list.size():
			monster_select.selected = monster_index
		return

	# Avatar mode
	anim_mode_select.selected = animation_mode
	anim_mode_select.set_item_disabled(AnimMode.EQUIP, current_equipment == EquipmentType.NONE)

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

	play_pause_btn.text = "||" if (animation_mode != AnimMode.TPOSE and not animation_paused) else ">"

	# Part slot labels
	for slot in ["hair", "upper", "lower", "hands", "feet"]:
		if slot_name_labels.has(slot):
			var name_str = current_part_names.get(slot, "")
			if name_str == "":
				slot_name_labels[slot].text = "None"
			else:
				slot_name_labels[slot].text = name_str.trim_prefix(_cfg()["name"] + "_")

	# Face label
	if slot_name_labels.has("face") and _avatar:
		slot_name_labels["face"].text = "Face " + _face_types()[_avatar.get_face_type_index()]

	# Equipment labels
	var equip_slots = {
		"blade": [EquipmentType.BLADE, blade_variants, blade_variant_index],
		"glorb": [EquipmentType.GLORB, [], 0],
		"mura": [EquipmentType.MURA, mura_variants, mura_variant_index],
		"spirit": [EquipmentType.SPIRIT, spirit_variants, spirit_variant_index],
	}
	for slot in equip_slots:
		if not slot_name_labels.has(slot):
			continue
		var equip_type_val = equip_slots[slot][0]
		if current_equipment != equip_type_val:
			slot_name_labels[slot].text = "None"
		elif slot == "glorb":
			var glorb_name = current_part_names.get("glorb", "")
			if glorb_name == "":
				slot_name_labels[slot].text = "None"
			else:
				slot_name_labels[slot].text = glorb_name.trim_prefix(_cfg()["name"] + "_")
		else:
			var variants = equip_slots[slot][1]
			var idx = equip_slots[slot][2]
			if variants.size() > 0:
				slot_name_labels[slot].text = variants[idx].get_basename().trim_prefix("weapon_")
			else:
				slot_name_labels[slot].text = "None"


# === GUI CALLBACKS ===

func _on_character_selected(index: int) -> void:
	if index == current_mode:
		return
	if index in [CharacterMode.MONSTER, CharacterMode.NPC]:
		_enter_model_viewer(index)
	elif current_mode in [CharacterMode.MONSTER, CharacterMode.NPC]:
		_exit_monster_mode(index)
	else:
		current_mode = index
		for slot in variant_index:
			variant_index[slot] = 0
		_initialize_avatar()
		_sync_gui()

func _on_anim_mode_selected(index: int) -> void:
	if index == animation_mode:
		return
	if index == AnimMode.TPOSE:
		_enter_tpose()
	elif index == AnimMode.BASIC:
		animation_mode = AnimMode.BASIC
		animation_paused = false
		_update_available_animations()
		var stand_idx = animation_list.find(_stand_anim())
		animation_index = stand_idx if stand_idx >= 0 else 0
		_play_current_animation()
	elif index == AnimMode.EQUIP:
		if current_equipment == EquipmentType.NONE:
			_sync_gui()
			return
		animation_mode = AnimMode.EQUIP
		animation_paused = false
		_update_available_animations()
		if animation_list.is_empty():
			animation_mode = AnimMode.BASIC
			_update_available_animations()
		else:
			animation_index = 0
			_play_current_animation()
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
		match equip_type:
			EquipmentType.BLADE:
				blade_variant_index = (blade_variant_index + direction) % blade_variants.size()
				if blade_variant_index < 0:
					blade_variant_index += blade_variants.size()
			EquipmentType.GLORB:
				var count = part_variants["glorb"].size()
				variant_index["glorb"] = (variant_index["glorb"] + direction + count) % count
			EquipmentType.MURA:
				mura_variant_index = (mura_variant_index + direction) % mura_variants.size()
				if mura_variant_index < 0:
					mura_variant_index += mura_variants.size()
			EquipmentType.SPIRIT:
				spirit_variant_index = (spirit_variant_index + direction) % spirit_variants.size()
				if spirit_variant_index < 0:
					spirit_variant_index += spirit_variants.size()
		_apply_equipment()
		if animation_mode == AnimMode.EQUIP:
			_update_available_animations()
			if animation_list.is_empty():
				animation_mode = AnimMode.BASIC
				_update_available_animations()
			animation_index = 0
			_play_current_animation()
	else:
		_set_equipment(equip_type)


# === INPUT ===

func _unhandled_input(event: InputEvent) -> void:
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

	# Monster/NPC mode
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

	# Avatar mode
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
		KEY_D:
			_print_debug_state()
	_sync_gui()


func _print_debug_state() -> void:
	print("\n=== DEBUG STATE ===")
	print("Mode: ", CharacterMode.keys()[current_mode])
	if _avatar:
		print("Gender: ", _avatar.gender)
		print("Parts: ", current_part_names)
		print("Equipment: ", EquipmentType.keys()[current_equipment])
		print("Animation mode: ", AnimMode.keys()[animation_mode])
		if animation_list.size() > 0 and animation_index < animation_list.size():
			print("Animation: ", animation_list[animation_index])
		print("Face: ", _face_types()[_avatar.get_face_type_index()])
	print("===================\n")
