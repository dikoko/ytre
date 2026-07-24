extends Node3D
## Test scene for verifying female avatar parts attach to skeleton correctly.
##
## Instructions:
## 1. Open test_avatar_female.tscn in Godot editor
## 2. Add female_base_materials.glb as child node (drag from FileSystem)
## 3. Run the scene
##
## Controls:
## - 0: Remove all parts (show base mesh only)
## - 1-5: Cycle forward  (1=hair, 2=upper, 3=lower, 4=hands, 5=feet)
## - Q-T: Cycle backward (q=hair, w=upper, e=lower, r=hands, t=feet)
## - F/V: Cycle face type forward/backward
## - 6-9: Equip equipment (6=blade, 7=glorb, 8=mura, 9=spirit); press again to cycle variants
## - Y-O: Same as 6-9 (y=blade, u=glorb, i=mura, o=spirit)
## - P: Remove equipment (unequip + detach weapon)
## - Tab: Cycle animation mode (T-pose → basic → equip → basic → ...)
##         Without equipment: T-pose → basic → T-pose → ...
## - Space: Pause/resume animation (animation mode only)
## - Left/Right: Cycle through animations (animation mode only)
## - H: Toggle parts visibility (debug - see which regions are hidden)
## - D: Print debug state (regions, materials, visibility)

# Node references - these will be found dynamically when female_base is added
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

# Animation prefix rules per equipment type
const EQUIPMENT_ANIMATION_PREFIXES: Dictionary = {
	EquipmentType.NONE: ["febasic"],
	EquipmentType.BLADE: ["febasic", "feblade"],
	EquipmentType.GLORB: ["febasic", "feglorb"],
	EquipmentType.MURA: ["febasic", "femura"],
	EquipmentType.SPIRIT: ["febasic", "fespirit"],
}

# Animation mode
enum AnimMode { TPOSE, BASIC, EQUIP }
var animation_mode: int = AnimMode.TPOSE
var all_animations: PackedStringArray = []      # All animations from the model
var animation_list: PackedStringArray = []       # Filtered by current animation mode
var animation_index: int = 0
var animation_paused: bool = false

# Procedural scalp cap to fill gaps behind hair parts
var scalp_cap: MeshInstance3D = null

# Currently attached parts by slot
var current_parts: Dictionary = {
	"hair": null,
	"upper": null,
	"lower": null,
	"hands": null,
	"feet": null,
	"glorb": null,
}

# Part variants for each slot
var part_variants: Dictionary = {
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
}

# Current variant index for each slot
var variant_index: Dictionary = {
	"hair": 0,
	"upper": 0,
	"lower": 0,
	"hands": 0,
	"feet": 0,
	"glorb": 0,
}

# Per-part metadata loaded from JSON (maps part name to hides_materials)
var parts_metadata: Dictionary = {}

# Shared skin material for base mesh fill behind transparent parts
var shared_skin_material: ShaderMaterial

# Debug: neck line investigation
var debug_base_hidden: bool = false
var debug_part_solid: bool = false
var debug_individual_mat: String = ""  # Which material is toggled off

# Track which part file is currently equipped in each slot
var current_part_names: Dictionary = {
	"hair": "",
	"upper": "",
	"lower": "",
	"hands": "",
	"feet": "",
	"glorb": "",
}

# Face state
var current_face_type_index: int = 0
var current_blink_frame: int = 0
var blink_sequence_index: int = 0
var is_blinking: bool = false

# Weapon attachment state (blade = @Sword, mura = @Head)
var weapon_attachment: BoneAttachment3D = null
var current_weapon_node: Node3D = null
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

const PARTS_PATH := "res://assets/avatars/parts/female/"
const METADATA_PATH := "res://assets/avatars/parts/parts_metadata_female.json"
const TEXTURES_BASE_PATH := "res://assets/avatars/textures/base/"
const TEXTURES_PARTS_PATH := "res://assets/avatars/textures/parts/"
const WEAPONS_BLADE_PATH := "res://assets/avatars/weapons/blade/"
const WEAPONS_MURA_PATH := "res://assets/avatars/weapons/mura/"
const WEAPONS_SPIRIT_PATH := "res://assets/avatars/weapons/spirit/"
const TEXTURES_WEAPONS_PATH := "res://assets/avatars/textures/weapons/"

# Map material mesh names to texture files
# Material-based splitting preserves correct UV mapping
const MATERIAL_TO_TEXTURE: Dictionary = {
	"upper": "female_upper_F0000.tga",  # Default outfit top
	"arm": "female_arm_F0000.tga",      # Arm skin
	"foot": "female_foot_F0000.tga",    # Foot skin
	"hand": "female_hand_F0000.tga",    # Hand skin
	"leg": "female_leg_F0000.tga",      # Leg skin
	"lower": "female_lower_F0000.tga",  # Default outfit bottom
	"hair_scalp": "female_hair_F0000.tga",  # Scalp - uses same hair texture as strands (both hidden when hair part equipped)
	"hair_strands": "female_hair_F0000.tga",  # Hair strands (hidden when hair part equipped)
	"face": null,                      # Face - uses skin color shader
}


# Face texture configuration
const TEXTURES_FACES_PATH := "res://assets/avatars/textures/faces/"

# Face types available (20 types for female)
const FACE_TYPES: Array[String] = [
	"001", "002", "003", "004", "005",
	"011", "012", "013",
	"021", "022", "023",
	"031", "032", "033",
	"041", "042", "043",
	"051", "052", "053",
]

# Blink animation configuration
const BLINK_INTERVAL_MIN := 2.0  # Minimum seconds between blinks
const BLINK_INTERVAL_MAX := 5.0  # Maximum seconds between blinks
const BLINK_FRAME_DURATION := 0.06  # Seconds per blink frame
const BLINK_SEQUENCE: Array[int] = [0, 1, 2, 1, 0]  # open -> half -> closed -> half -> open


func _load_parts_metadata() -> void:
	"""Load per-part region hiding metadata from JSON file."""
	var file = FileAccess.open(METADATA_PATH, FileAccess.READ)
	if not file:
		push_warning("Could not load parts metadata from: " + METADATA_PATH)
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


func _get_part_hides_materials(part_name: String) -> Array:
	"""Base material meshes replaced by this part (from its .swp slots)."""
	if parts_metadata.has(part_name):
		return parts_metadata[part_name].get("hides_materials", [])
	# Fallback if metadata not found
	push_warning("No metadata for part: " + part_name)
	return []



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

	# Create shared skin material for meshes that are always skin-colored
	shared_skin_material = ShaderMaterial.new()
	shared_skin_material.shader = skin_shader
	shared_skin_material.set_shader_parameter("skin_color", Color(0.992, 0.812, 0.635, 1.0))

	for mat_name in material_meshes:
		# Skin-only materials use shared flat skin color for consistency
		# (these textures are 99%+ transparent - texture adds no visual detail)
		if mat_name in ["arm", "leg", "hand", "foot"]:
			material_meshes[mat_name].material_override = shared_skin_material
			print("  ", mat_name, " -> shared skin material")
			continue

		var texture_file = MATERIAL_TO_TEXTURE.get(mat_name)
		if texture_file == null:
			print("  No texture mapping for: ", mat_name)
			continue  # No texture for this material

		var texture_path = TEXTURES_BASE_PATH + texture_file
		print("  ", mat_name, " -> ", texture_file)
		var use_hair_shader = mat_name in ["hair_scalp", "hair_strands"]
		var use_clothing_shader = mat_name in ["upper", "lower"]
		var material = _create_textured_material(texture_path, use_hair_shader, use_clothing_shader)
		if material:
			material_meshes[mat_name].material_override = material
		else:
			print("    FAILED to load texture: ", texture_path)

	# Debug: print final state of all meshes
	print("\\n=== FINAL MATERIAL STATE ===")
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
	var texture_name = "female_face_F" + face_type + str(blink_frame) + ".tga"
	return TEXTURES_FACES_PATH + texture_name


func _update_face_texture() -> void:
	"""Apply current face texture to the face material mesh."""
	if not material_meshes.has("face"):
		return

	var face_type = FACE_TYPES[current_face_type_index]
	var texture_path = _get_face_texture_path(face_type, current_blink_frame)

	var texture = load(texture_path) as Texture2D
	if not texture:
		push_warning("Could not load face texture: " + texture_path)
		return

	var material = material_meshes["face"].material_override as ShaderMaterial
	if not material:
		# Simple shader that blends face texture with skin color based on alpha
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




func _setup_blink_timers() -> void:
	"""Create and configure blink timers."""
	# Timer for interval between blinks
	blink_timer = Timer.new()
	blink_timer.one_shot = true
	blink_timer.timeout.connect(_on_blink_timer_timeout)
	add_child(blink_timer)

	# Timer for blink animation frames
	blink_frame_timer = Timer.new()
	blink_frame_timer.one_shot = true
	blink_frame_timer.timeout.connect(_on_blink_frame_timeout)
	add_child(blink_frame_timer)

	# Start the first blink timer
	_start_blink_timer()


func _start_blink_timer() -> void:
	"""Start timer for next blink with random interval."""
	var interval = randf_range(BLINK_INTERVAL_MIN, BLINK_INTERVAL_MAX)
	blink_timer.start(interval)


func _on_blink_timer_timeout() -> void:
	"""Called when it's time to blink."""
	is_blinking = true
	blink_sequence_index = 0
	_play_blink_frame()


func _on_blink_frame_timeout() -> void:
	"""Called to advance to next blink frame."""
	blink_sequence_index += 1

	if blink_sequence_index >= BLINK_SEQUENCE.size():
		# Blink complete, return to open eyes
		is_blinking = false
		current_blink_frame = 0
		_update_face_texture()
		_start_blink_timer()
	else:
		_play_blink_frame()


func _play_blink_frame() -> void:
	"""Play current frame of blink animation."""
	current_blink_frame = BLINK_SEQUENCE[blink_sequence_index]
	_update_face_texture()
	blink_frame_timer.start(BLINK_FRAME_DURATION)


func _select_face_type(index: int) -> void:
	"""Select a face type by index."""
	current_face_type_index = index % FACE_TYPES.size()
	if current_face_type_index < 0:
		current_face_type_index += FACE_TYPES.size()

	# Reset to open eyes when changing face
	current_blink_frame = 0
	_update_face_texture()
	print("Face type: ", FACE_TYPES[current_face_type_index])


func _cycle_face_next() -> void:
	"""Cycle to next face type."""
	_select_face_type(current_face_type_index + 1)


func _cycle_face_prev() -> void:
	"""Cycle to previous face type."""
	_select_face_type(current_face_type_index - 1)


func _ready() -> void:
	# Pre-compile shaders once to avoid recompilation on every part swap
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

	# Load parts metadata
	_load_parts_metadata()

	# Setup orbit camera
	camera = $Camera3D
	_setup_orbit_camera()

	# Find the base avatar node (should be added as child in editor)
	var base_avatar = _find_base_avatar()
	if not base_avatar:
		push_warning("No base avatar found. Add female_base_materials.glb as child node in editor.")
		return

	# Find skeleton and animation player
	skeleton = _find_skeleton(base_avatar)
	animation_player = _find_animation_player(base_avatar)

	if not skeleton:
		push_error("Could not find Skeleton3D in base avatar")
		return

	print("Found skeleton: ", skeleton.get_path())
	print("Skeleton has ", skeleton.get_bone_count(), " bones")

	if animation_player:
		all_animations = animation_player.get_animation_list()
		all_animations.sort()
		_update_available_animations()
		print("Found AnimationPlayer with ", all_animations.size(), " animations (", animation_list.size(), " available for current equipment)")

	# Find material meshes
	_find_material_meshes(base_avatar)
	print("Found ", material_meshes.size(), " material meshes: ", material_meshes.keys())

	# Apply textures to base mesh materials
	_apply_material_textures()

	# Create procedural scalp cap to fill gaps behind hair parts
	_create_scalp_cap()

	# Load the 5 standard parts (special and glorb are not equipped by default)
	for slot in ["hair", "upper", "lower", "hands", "feet"]:
		_swap_part(slot, 0)

	# Initialize face system
	_setup_blink_timers()
	_update_face_texture()
	print("Face system initialized with ", FACE_TYPES.size(), " face types")

	# Start in static T-pose mode (Tab cycles: T-pose → basic → equip → basic → ...)
	print("Animation: T-POSE. Tab=enter animation mode.")


func _setup_orbit_camera() -> void:
	"""Setup camera for orbit controls around the avatar."""
	if not camera:
		return
	# Create pivot point at avatar center (waist height)
	camera_pivot = Node3D.new()
	camera_pivot.name = "CameraPivot"
	add_child(camera_pivot)
	camera_pivot.position = Vector3(0, 1.0, 0)  # Waist height
	_update_camera_position()
	print("Camera controls: Left-drag to rotate, Scroll to zoom")


func _update_camera_position() -> void:
	"""Update camera position based on orbit angles and distance."""
	if not camera:
		return
	var angle_y_rad = deg_to_rad(camera_angle_y)
	var angle_x_rad = deg_to_rad(camera_angle_x)

	# Calculate camera position on sphere around pivot
	var offset = Vector3(
		sin(angle_x_rad) * cos(angle_y_rad),
		sin(angle_y_rad),
		cos(angle_x_rad) * cos(angle_y_rad)
	) * camera_distance

	camera.position = camera_pivot.position + offset
	camera.look_at(camera_pivot.position, Vector3.UP)


func _find_base_avatar() -> Node:
	"""Find the imported base avatar node."""
	for child in get_children():
		# Look for node that contains Armature/Skeleton3D structure
		if _find_skeleton(child):
			return child
	return null


func _find_skeleton(node: Node) -> Skeleton3D:
	"""Recursively find Skeleton3D in node hierarchy."""
	if node is Skeleton3D:
		return node
	for child in node.get_children():
		var result = _find_skeleton(child)
		if result:
			return result
	return null


func _find_animation_player(node: Node) -> AnimationPlayer:
	"""Recursively find AnimationPlayer in node hierarchy."""
	if node is AnimationPlayer:
		return node
	for child in node.get_children():
		var result = _find_animation_player(child)
		if result:
			return result
	return null


func _find_material_meshes(node: Node) -> void:
	"""Find all material mesh nodes and store references."""
	if node is MeshInstance3D:
		var mesh_name = node.name as String
		var current_mat = node.material_override
		var surface_mat = node.get_surface_override_material(0) if node.mesh else null
		print("  MeshInstance3D: ", mesh_name, " | override=", current_mat, " | surface=", surface_mat)

		# Material meshes are named "mesh_<material>" (e.g., "mesh_upper", "mesh_arm")
		if mesh_name.begins_with("mesh_"):
			var mat_name = mesh_name.substr(5)  # Remove "mesh_" prefix
			material_meshes[mat_name] = node
			print("    -> Added as material: ", mat_name)

	for child in node.get_children():
		_find_material_meshes(child)


func _find_mesh_in_part(node: Node) -> MeshInstance3D:
	"""Recursively find MeshInstance3D in a part scene."""
	if node is MeshInstance3D:
		return node
	for child in node.get_children():
		var result = _find_mesh_in_part(child)
		if result:
			return result
	return null


func _update_material_visibility() -> void:
	"""Update material mesh visibility based on currently equipped parts."""
	# Start with all materials visible
	for mat_name in material_meshes:
		material_meshes[mat_name].visible = true

	# Hide exactly the base material meshes each equipped part replaces
	var hidden_list: Array[String] = []
	for slot in current_parts:
		if current_parts[slot] != null:
			var part_name = current_part_names[slot]
			for mat_name in _get_part_hides_materials(part_name):
				if material_meshes.has(mat_name) and material_meshes[mat_name].visible:
					material_meshes[mat_name].visible = false
					hidden_list.append(mat_name)

	if hidden_list.size() > 0:
		print("Hidden materials: ", hidden_list)



func _swap_part(slot: String, variant_idx: int) -> void:
	"""Remove old part and load new part for the given slot."""
	if not skeleton:
		push_error("No skeleton available")
		return

	# Remove old part if present
	if current_parts[slot]:
		current_parts[slot].queue_free()
		current_parts[slot] = null
		current_part_names[slot] = ""

	# Update variant index
	variant_index[slot] = variant_idx

	# Load new part
	var part_file = part_variants[slot][variant_idx]
	var part_path = PARTS_PATH + part_file
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

	# Parts now come with their own skeleton and skin.
	# We need to reparent the mesh to use our shared skeleton.
	# The skin resource should work because it has matching bone names.

	# Get the skin from the part (should have one now)
	var part_skin = mesh_instance.skin
	print("  Part skin: ", part_skin)

	# Reparent mesh to our skeleton
	mesh_instance.get_parent().remove_child(mesh_instance)
	skeleton.add_child(mesh_instance)

	# Restore the skeleton reference and skin
	mesh_instance.skeleton = skeleton.get_path()
	if part_skin:
		mesh_instance.skin = part_skin
		print("  Skin applied from part")

	# Debug info
	print("  Skeleton path: ", mesh_instance.skeleton)

	# Clean up the rest of the part scene (including its skeleton)
	part_instance.queue_free()

	current_parts[slot] = mesh_instance
	# Store part name (without .glb extension) for metadata lookup
	var part_name = part_file.replace(".glb", "")
	current_part_names[slot] = part_name
	print("Attached ", slot, ": ", part_file)

	# Apply texture to part
	var texture_path = _get_part_texture_path(part_name)
	if texture_path != "":
		var use_hair_shader = slot == "hair"
		# Clothing parts use alpha_scissor to discard transparent pixels
		# (textures have alpha=0 skin-tone pixels at boundaries like neck/armholes)
		var use_alpha = slot in ["upper", "lower", "hands", "feet", "special", "glorb"]
		var material = _create_textured_material(texture_path, use_hair_shader, use_alpha)
		if material:
			mesh_instance.material_override = material
			print("  Applied texture: ", texture_path.get_file(), " (hair_shader: ", use_hair_shader, ", alpha_scissor: ", use_alpha, ")")

	# Update material visibility based on all equipped parts
	_update_material_visibility()


func _cycle_part(slot: String) -> void:
	"""Cycle to the next variant for the given slot."""
	var next_idx = (variant_index[slot] + 1) % part_variants[slot].size()
	_swap_part(slot, next_idx)


func _cycle_part_prev(slot: String) -> void:
	"""Cycle to the previous variant for the given slot."""
	var count = part_variants[slot].size()
	var prev_idx = (variant_index[slot] - 1 + count) % count
	_swap_part(slot, prev_idx)


func _remove_all_parts() -> void:
	"""Remove all equipped parts to show base mesh only."""
	print("Removing all parts...")
	for slot in current_parts:
		if current_parts[slot]:
			current_parts[slot].queue_free()
			current_parts[slot] = null
			current_part_names[slot] = ""
	_update_material_visibility()
	print("All materials now visible:")
	for mat_name in material_meshes:
		print("  ", mat_name, ": visible=", material_meshes[mat_name].visible)


func _toggle_parts_visibility() -> void:
	"""Toggle parts visibility to see which base materials are hidden."""
	parts_visible = not parts_visible
	for slot in current_parts:
		if current_parts[slot]:
			current_parts[slot].visible = parts_visible

	if parts_visible:
		print("Parts VISIBLE - normal view")
	else:
		print("Parts HIDDEN - showing base mesh materials only")
		print("Hidden materials (holes in base mesh):")
		for mat_name in material_meshes:
			if not material_meshes[mat_name].visible:
				print("  ", mat_name, " (hidden by equipped part)")


func _print_debug_state() -> void:
	"""Print detailed debug state for troubleshooting."""
	print("\n=== DEBUG STATE ===")
	print("\nEquipped parts:")
	for slot in current_parts:
		if current_parts[slot]:
			var part_name = current_part_names[slot]
			var hidden_materials = _get_part_hides_materials(part_name)
			print("  ", slot, ": ", part_name)
			print("    hides materials: ", hidden_materials)
		else:
			print("  ", slot, ": (none)")

	print("\nFace:")
	print("  Type: ", FACE_TYPES[current_face_type_index], " (index ", current_face_type_index, ")")
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
	"""Color each mesh with a unique solid color to identify which mesh is which."""
	var colors = {
		"upper": Color.RED,
		"arm": Color.GREEN,
		"foot": Color.BLUE,
		"hand": Color.YELLOW,
		"leg": Color.CYAN,
		"lower": Color.MAGENTA,
		"hair_scalp": Color.ORANGE,
		"hair_strands": Color.PURPLE,
		"face": Color.WHITE,
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
	"""Restore normal textures after debug coloring."""
	_apply_material_textures()
	_update_face_texture()
	print("Textures restored")


# === NECK LINE DIAGNOSTIC EXPERIMENTS ===

func _debug_toggle_base_mesh() -> void:
	"""Experiment A: Toggle ALL base mesh materials hidden/visible.
	If the neck line disappears when base is hidden, the base mesh causes it."""
	debug_base_hidden = not debug_base_hidden
	for mat_name in material_meshes:
		material_meshes[mat_name].visible = not debug_base_hidden
	if debug_base_hidden:
		print("[DIAG] Base mesh HIDDEN - only parts visible. Does the neck line disappear?")
	else:
		print("[DIAG] Base mesh VISIBLE - restored")
		_update_material_visibility()


func _debug_toggle_part_solid() -> void:
	"""Experiment B: Toggle alpha scissor + skin fill on upper part.
	Enables alpha transparency on M0009 and keeps UPPER base mesh visible
	with skin color to fill the transparent areas."""
	debug_part_solid = not debug_part_solid
	var upper_mesh = current_parts.get("upper")
	if not upper_mesh:
		print("[DIAG] No upper part equipped!")
		return
	if debug_part_solid:
		# Replace part with solid green to test if line is UV/texture related
		var mat = StandardMaterial3D.new()
		mat.albedo_color = Color(0.0, 0.8, 0.0)
		upper_mesh.material_override = mat
		print("[DIAG] Upper part -> SOLID GREEN. Does the neck line disappear?")
	else:
		# Restore part texture
		var part_name = current_part_names["upper"]
		var texture_path = _get_part_texture_path(part_name)
		if texture_path != "":
			var material = _create_textured_material(texture_path)
			if material:
				upper_mesh.material_override = material
		# Restore base mesh visibility
		_apply_material_textures()
		_update_material_visibility()
		print("[DIAG] Upper part + base mesh RESTORED")


func _debug_cycle_base_material() -> void:
	"""Experiment C: Cycle through hiding individual base materials (arm, face, upper).
	Identifies which specific base material contributes to the neck line."""
	var neck_materials = ["arm", "face", "upper", ""]  # empty = all visible
	var current_idx = neck_materials.find(debug_individual_mat)
	var next_idx = (current_idx + 1) % neck_materials.size()
	debug_individual_mat = neck_materials[next_idx]

	# First restore all
	for mat_name in material_meshes:
		material_meshes[mat_name].visible = true
	_update_material_visibility()

	if debug_individual_mat != "":
		if material_meshes.has(debug_individual_mat):
			material_meshes[debug_individual_mat].visible = false
			print("[DIAG] Hiding base '", debug_individual_mat, "' only. Does the neck line change?")
		else:
			print("[DIAG] Material '", debug_individual_mat, "' not found")
	else:
		print("[DIAG] All base materials RESTORED (normal visibility)")


func _update_available_animations() -> void:
	"""Filter animations based on current animation mode."""
	var prefixes: Array
	if animation_mode == AnimMode.EQUIP:
		# Equip mode: only weapon-specific animations (exclude basic)
		var equip_prefixes = EQUIPMENT_ANIMATION_PREFIXES.get(current_equipment, [])
		prefixes = equip_prefixes.filter(func(p): return p != "febasic")
	else:
		# Basic mode: only basic animations
		prefixes = ["febasic"]
	var filtered: PackedStringArray = []
	for anim_name in all_animations:
		for prefix in prefixes:
			if anim_name.begins_with(prefix):
				filtered.append(anim_name)
				break
	animation_list = filtered


func _attach_weapon(glb_filename: String, weapons_path: String, bone: String) -> void:
	"""Load and attach a weapon GLB to a bone via BoneAttachment3D."""
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

	# Apply texture to weapon meshes, hide trail anchors
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
	"""Remove currently attached weapon."""
	if weapon_attachment:
		weapon_attachment.queue_free()
		weapon_attachment = null
		current_weapon_node = null


func _get_weapon_texture_path(weapon_name: String) -> String:
	"""Get the texture path for a weapon, trying BMP then TGA."""
	var bmp_path = TEXTURES_WEAPONS_PATH + weapon_name + ".bmp"
	if ResourceLoader.exists(bmp_path):
		return bmp_path

	var tga_path = TEXTURES_WEAPONS_PATH + weapon_name + ".tga"
	if ResourceLoader.exists(tga_path):
		return tga_path

	return ""


func _set_equipment(equip_type: EquipmentType) -> void:
	"""Toggle equipment type on/off. Updates available animations and weapon visuals."""
	var was_blade = current_equipment == EquipmentType.BLADE
	var was_glorb = current_equipment == EquipmentType.GLORB
	var was_mura = current_equipment == EquipmentType.MURA
	var was_spirit = current_equipment == EquipmentType.SPIRIT
	if current_equipment == equip_type:
		# Same type pressed again: cycle variant
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

	# Attach/detach weapon visual
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

	# Equip/remove glorb part (mutually exclusive with hands)
	if current_equipment == EquipmentType.GLORB:
		if not was_glorb:
			# Remove hands part when equipping glorb
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
		# Re-filter equip animations for new equipment
		_update_available_animations()
		if animation_list.is_empty():
			# No equip animations for new weapon, fall back to basic
			animation_mode = AnimMode.BASIC
			_update_available_animations()
		animation_index = 0
		_play_current_animation()
		print("  Animations updated: ", animation_list.size(), " available")


func _unequip() -> void:
	"""Force unequip current equipment."""
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
		# Was in equip mode, fall back to basic since no equipment now
		animation_mode = AnimMode.BASIC
		animation_paused = false
		_update_available_animations()
		var stand_idx = animation_list.find("febasic_stand")
		animation_index = stand_idx if stand_idx >= 0 else 0
		_play_current_animation()
		print("  Fell back to BASIC mode (no equipment).")


func _cycle_animation_mode() -> void:
	"""Cycle animation mode: T-pose → basic → equip → basic → ..."""
	match animation_mode:
		AnimMode.TPOSE:
			# Enter basic animation mode
			animation_mode = AnimMode.BASIC
			animation_paused = false
			_update_available_animations()
			var stand_idx = animation_list.find("febasic_stand")
			animation_index = stand_idx if stand_idx >= 0 else 0
			_play_current_animation()
			print("Animation: BASIC (", animation_list.size(), " animations). Tab=next mode, Left/Right=cycle, Space=pause.")
		AnimMode.BASIC:
			# Try to enter equip mode if weapon equipped
			if current_equipment != EquipmentType.NONE:
				animation_mode = AnimMode.EQUIP
				animation_paused = false
				_update_available_animations()
				if animation_list.is_empty():
					# No equip-specific animations, stay in basic
					animation_mode = AnimMode.BASIC
					_update_available_animations()
					print("No equip animations available, staying in BASIC mode.")
				else:
					animation_index = 0
					_play_current_animation()
					var equip_name = EquipmentType.keys()[current_equipment].to_lower()
					print("Animation: EQUIP/", equip_name, " (", animation_list.size(), " animations). Tab=back to basic.")
			else:
				# No equipment, return to T-pose
				_enter_tpose()
		AnimMode.EQUIP:
			# Return to T-pose
			_enter_tpose()


func _enter_tpose() -> void:
	"""Return to static T-pose."""
	animation_mode = AnimMode.TPOSE
	animation_paused = false
	if animation_player:
		animation_player.stop()
	if skeleton:
		skeleton.reset_bone_poses()
	print("Animation: T-POSE. Tab=enter animation mode.")


func _play_current_animation() -> void:
	"""Play the animation at current index."""
	if not animation_player or animation_list.is_empty():
		return
	var anim_name = animation_list[animation_index]
	var anim = animation_player.get_animation(anim_name)
	if anim:
		anim.loop_mode = Animation.LOOP_LINEAR
	animation_player.play(anim_name)
	print("Playing [", animation_index + 1, "/", animation_list.size(), "]: ", anim_name)


func _toggle_animation_pause() -> void:
	"""Pause or resume current animation."""
	if not animation_player:
		return
	animation_paused = not animation_paused
	if animation_paused:
		animation_player.pause()
		print("Paused")
	else:
		animation_player.play()
		print("Resumed")


func _cycle_animation(direction: int) -> void:
	"""Cycle to next/previous animation."""
	if animation_list.is_empty():
		return
	animation_index = (animation_index + direction) % animation_list.size()
	if animation_index < 0:
		animation_index += animation_list.size()
	animation_paused = false
	_play_current_animation()


func _input(event: InputEvent) -> void:
	# Handle mouse input for camera orbit
	if event is InputEventMouseButton:
		if event.button_index == MOUSE_BUTTON_LEFT:
			is_dragging = event.pressed
		elif event.button_index == MOUSE_BUTTON_WHEEL_UP and event.pressed:
			camera_distance = max(1.0, camera_distance - 0.3)
			_update_camera_position()
		elif event.button_index == MOUSE_BUTTON_WHEEL_DOWN and event.pressed:
			camera_distance = min(10.0, camera_distance + 0.3)
			_update_camera_position()

	if event is InputEventMouseMotion and is_dragging:
		camera_angle_x -= event.relative.x * mouse_sensitivity
		camera_angle_y += event.relative.y * mouse_sensitivity
		camera_angle_y = clamp(camera_angle_y, -80.0, 80.0)
		_update_camera_position()

	# Trackpad pinch zoom
	if event is InputEventMagnifyGesture:
		camera_distance = clamp(camera_distance / event.factor, 1.0, 10.0)
		_update_camera_position()

	# Handle keyboard input
	if not event is InputEventKey or not event.pressed:
		return

	match event.keycode:
		# Number keys 1-5: cycle parts forward
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
			# Hands and glorbs are mutually exclusive
			if current_equipment == EquipmentType.GLORB:
				_unequip()
			_cycle_part("hands")
		KEY_5:
			_cycle_part("feet")
		# Letter keys Q-T: cycle parts backward
		KEY_Q:
			_cycle_part_prev("hair")
		KEY_W:
			_cycle_part_prev("upper")
		KEY_E:
			_cycle_part_prev("lower")
		KEY_R:
			# Hands and glorbs are mutually exclusive
			if current_equipment == EquipmentType.GLORB:
				_unequip()
			_cycle_part_prev("hands")
		KEY_T:
			_cycle_part_prev("feet")
		# Face cycling
		KEY_F:
			_cycle_face_next()
		KEY_V:
			_cycle_face_prev()
		# Equipment type selection (6-9 / Y-O)
		KEY_6, KEY_Y:
			_set_equipment(EquipmentType.BLADE)
		KEY_7, KEY_U:
			_set_equipment(EquipmentType.GLORB)
		KEY_8, KEY_I:
			_set_equipment(EquipmentType.MURA)
		KEY_9, KEY_O:
			_set_equipment(EquipmentType.SPIRIT)
		# Animation mode
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
		# Remove equipment
		KEY_P:
			_unequip()
		# Debug keys
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


func _process(_delta: float) -> void:
	pass
