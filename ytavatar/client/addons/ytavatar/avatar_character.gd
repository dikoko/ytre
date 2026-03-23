@tool
class_name AvatarCharacter
extends Node3D
## Reusable avatar character component.
##
## Drop into any scene as a "prefab". Configure via @export properties in the
## inspector or via method calls at runtime. Visual-only — parent node handles
## physics/movement.
##
## Asset path structure (under assets_path):
##   base/           - male_base_materials.glb, female_base_materials.glb
##   parts/male/     - male part GLBs
##   parts/female/   - female part GLBs
##   parts/          - parts_metadata.json, parts_metadata_female.json
##   textures/base/  - base body textures
##   textures/parts/ - part textures
##   textures/weapons/ - weapon textures
##   textures/faces/ - face textures
##   weapons/blade/  - blade weapon GLBs
##   weapons/mura/   - mura weapon GLBs
##   weapons/spirit/ - spirit weapon GLBs

# === SIGNALS ===

signal part_changed(slot: String, variant: String)
signal equipment_changed(type: String, variant: String)
signal animation_started(name: String)
signal animation_finished(name: String)
signal gender_changed(new_gender: String)

# === EXPORTS ===

@export_group("Assets")
@export_dir var assets_path: String = "res://assets/avatars/"

@export_group("Character")
@export_enum("male", "female") var gender: String = "male"
@export var skin_color: Color = Color(0.992, 0.812, 0.635, 1.0)

@export_group("Parts")
@export var hair_variant: String = ""
@export var upper_variant: String = ""
@export var lower_variant: String = ""
@export var hands_variant: String = ""
@export var feet_variant: String = ""

@export_group("Face")
@export var face_type: int = 0
@export var blink_enabled: bool = true

@export_group("Equipment")
@export var equipment_type: String = ""
@export var equipment_variant: String = ""

@export_group("Animation")
@export var default_animation: String = ""

# === CONSTANTS ===

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

const BLINK_INTERVAL_MIN := 2.0
const BLINK_INTERVAL_MAX := 5.0
const BLINK_FRAME_DURATION := 0.06
const BLINK_SEQUENCE: Array[int] = [0, 1, 2, 1, 0]

# Weapon attachment bones
const WEAPON_BONES: Dictionary = {
	"blade": "@Sword",
	"mura": "@Head",
	"spirit": "@Spine3",
}

# Gender-specific config (paths computed at runtime from assets_path)
const _GENDER_DATA: Dictionary = {
	"male": {
		"base_glb": "base/male_base_materials.glb",
		"parts_dir": "parts/male/",
		"metadata_file": "parts/parts_metadata.json",
		"anim_prefix": "basic",
		"anim_prefixes": {
			"": ["basic"],
			"blade": ["basic", "blade"],
			"glorb": ["basic", "glorb"],
			"mura": ["basic", "mura"],
			"spirit": ["basic", "spirit"],
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
		"part_prefix": "male",
		"glorb_prefix": "male",
	},
	"female": {
		"base_glb": "base/female_base_materials.glb",
		"parts_dir": "parts/female/",
		"metadata_file": "parts/parts_metadata_female.json",
		"anim_prefix": "febasic",
		"anim_prefixes": {
			"": ["febasic"],
			"blade": ["febasic", "feblade"],
			"glorb": ["febasic", "feglorb"],
			"mura": ["febasic", "femura"],
			"spirit": ["febasic", "fespirit"],
		},
		"stand_anim": "febasic_stand",
		"face_prefix": "female_face_F",
		"face_types": [
			"001", "002", "003", "004", "005",
			"011", "012", "013", "021", "022", "023",
			"031", "032", "033", "041", "042", "043",
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
		"part_prefix": "female",
		"glorb_prefix": "female",
	},
}

# === INTERNAL STATE ===

var _skeleton: Skeleton3D
var _animation_player: AnimationPlayer
var _material_meshes: Dictionary = {}
var _base_instance: Node = null
var _parts_metadata: Dictionary = {}

# Shaders (compiled once)
var _hair_shader: Shader
var _clothing_shader: Shader
var _skin_shader: Shader
var _shared_skin_material: ShaderMaterial

# Parts state
var _current_parts: Dictionary = {
	"hair": null, "upper": null, "lower": null,
	"hands": null, "feet": null, "glorb": null,
}
var _current_part_names: Dictionary = {
	"hair": "", "upper": "", "lower": "",
	"hands": "", "feet": "", "glorb": "",
}

# Equipment state
var _current_equipment_type: String = ""
var _current_equipment_variant: String = ""
var _weapon_attachment: BoneAttachment3D = null
var _current_weapon_node: Node3D = null

# Face state
var _current_face_type_index: int = 0
var _current_blink_frame: int = 0
var _blink_sequence_index: int = 0
var _is_blinking: bool = false

# Blink timers
var _blink_timer: Timer
var _blink_frame_timer: Timer

# Animation state
var _all_animations: PackedStringArray = []
var _current_anim_name: String = ""


# === LIFECYCLE ===

func _ready() -> void:
	if Engine.is_editor_hint():
		return
	_compile_shaders()
	if blink_enabled:
		_setup_blink_timers()
	_build_avatar()


# === INTERNAL: Path helpers ===

func _asset(relative_path: String) -> String:
	var base = assets_path
	if not base.ends_with("/"):
		base += "/"
	return base + relative_path


func _cfg() -> Dictionary:
	return _GENDER_DATA[gender]


# === PUBLIC API: Gender ===

func set_gender(new_gender: String) -> void:
	if new_gender != "male" and new_gender != "female":
		push_warning("Invalid gender: " + new_gender)
		return
	if new_gender == gender:
		return
	_teardown_avatar()
	gender = new_gender
	_build_avatar()
	gender_changed.emit(new_gender)


# === PUBLIC API: Parts ===

func set_part(slot: String, variant: String) -> void:
	if not _skeleton:
		push_warning("Avatar not initialized")
		return
	if slot == "glorb":
		push_warning("Use equip_weapon('glorb', variant) for glorb")
		return
	_swap_part_by_variant(slot, variant)
	part_changed.emit(slot, variant)


func remove_part(slot: String) -> void:
	if _current_parts.has(slot) and _current_parts[slot]:
		_current_parts[slot].queue_free()
		_current_parts[slot] = null
		_current_part_names[slot] = ""
		_update_material_visibility()
		part_changed.emit(slot, "")


func remove_all_parts() -> void:
	for slot in _current_parts:
		if _current_parts[slot]:
			_current_parts[slot].queue_free()
			_current_parts[slot] = null
			_current_part_names[slot] = ""
	_update_material_visibility()


# === PUBLIC API: Equipment ===

func equip_weapon(type: String, variant: String) -> void:
	if not _skeleton:
		push_warning("Avatar not initialized")
		return

	_unequip_internal()

	_current_equipment_type = type
	_current_equipment_variant = variant

	if type == "glorb":
		if _current_parts["hands"]:
			_current_parts["hands"].queue_free()
			_current_parts["hands"] = null
			_current_part_names["hands"] = ""
		var cfg = _cfg()
		var glb_name = cfg["glorb_prefix"] + "_glorb_" + variant + ".glb"
		var glb_path = _asset(cfg["parts_dir"] + glb_name)
		var part_name = glb_name.replace(".glb", "")
		_load_and_attach_part("glorb", glb_path, part_name)
	else:
		var bone: String = WEAPON_BONES.get(type, "")
		if bone == "":
			push_warning("Unknown weapon type: " + type)
			return
		var weapons_path = _asset("weapons/" + type + "/")
		var glb_name = "weapon_" + type + "_" + variant + ".glb"
		_attach_weapon(glb_name, weapons_path, bone)

	equipment_changed.emit(type, variant)


func unequip_weapon() -> void:
	if _current_equipment_type == "":
		return
	_unequip_internal()
	equipment_changed.emit("", "")


# === PUBLIC API: Face ===

func set_face(type_index: int) -> void:
	var face_types: Array = _cfg()["face_types"]
	_current_face_type_index = type_index % face_types.size()
	if _current_face_type_index < 0:
		_current_face_type_index += face_types.size()
	_current_blink_frame = 0
	_update_face_texture()


func set_skin_color(color: Color) -> void:
	skin_color = color
	_apply_skin_color_to_all()


# === PUBLIC API: Animation ===

func play_animation(anim_name: String) -> void:
	if not _animation_player:
		return
	if not _animation_player.has_animation(anim_name):
		push_warning("Animation not found: " + anim_name)
		return
	var anim = _animation_player.get_animation(anim_name)
	if anim:
		anim.loop_mode = Animation.LOOP_LINEAR
	_animation_player.play(anim_name)
	_current_anim_name = anim_name
	animation_started.emit(anim_name)


func stop_animation() -> void:
	if _animation_player:
		_animation_player.stop()
	if _skeleton:
		_skeleton.reset_bone_poses()
	_current_anim_name = ""


func pause_animation() -> void:
	if _animation_player:
		_animation_player.pause()


func resume_animation() -> void:
	if _animation_player:
		_animation_player.play()


func is_animation_playing() -> bool:
	return _animation_player != null and _animation_player.is_playing()


func get_face_type_index() -> int:
	return _current_face_type_index


func get_face_type_count() -> int:
	return _cfg()["face_types"].size()


func get_animation_list(filter_prefix: String = "") -> PackedStringArray:
	if filter_prefix == "":
		return _all_animations
	var filtered: PackedStringArray = []
	for anim_name in _all_animations:
		if anim_name.begins_with(filter_prefix):
			filtered.append(anim_name)
	return filtered


# === PUBLIC API: State ===

func get_current_state() -> Dictionary:
	return {
		"gender": gender,
		"skin_color": skin_color,
		"hair": _variant_from_part_name("hair"),
		"upper": _variant_from_part_name("upper"),
		"lower": _variant_from_part_name("lower"),
		"hands": _variant_from_part_name("hands"),
		"feet": _variant_from_part_name("feet"),
		"face_type": _current_face_type_index,
		"equipment_type": _current_equipment_type,
		"equipment_variant": _current_equipment_variant,
		"animation": _current_anim_name,
	}


func load_state(state: Dictionary) -> void:
	var new_gender: String = state.get("gender", gender)
	if new_gender != gender:
		_teardown_avatar()
		gender = new_gender
		_build_avatar()
		gender_changed.emit(new_gender)

	var color = state.get("skin_color", skin_color)
	if color is Color:
		set_skin_color(color)

	for slot in ["hair", "upper", "lower", "hands", "feet"]:
		var variant: String = state.get(slot, "")
		if variant != "":
			set_part(slot, variant)
		else:
			remove_part(slot)

	set_face(state.get("face_type", 0))

	var eq_type: String = state.get("equipment_type", "")
	var eq_variant: String = state.get("equipment_variant", "")
	if eq_type != "" and eq_variant != "":
		equip_weapon(eq_type, eq_variant)
	else:
		unequip_weapon()

	var anim: String = state.get("animation", "")
	if anim != "":
		play_animation(anim)


# === PUBLIC API: Assets path ===

func get_assets_path() -> String:
	return assets_path


func get_parts_path() -> String:
	return _asset(_cfg()["parts_dir"])


# === INTERNAL: Shader compilation ===

func _compile_shaders() -> void:
	_hair_shader = Shader.new()
	_hair_shader.code = """
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

	_clothing_shader = Shader.new()
	_clothing_shader.code = """
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

	_skin_shader = Shader.new()
	_skin_shader.code = """
shader_type spatial;

uniform vec4 skin_color : source_color = vec4(0.992, 0.812, 0.635, 1.0);

void fragment() {
	ALBEDO = skin_color.rgb;
	ROUGHNESS = 1.0;
	SPECULAR = 0.0;
}
"""


# === INTERNAL: Blink system ===

func _setup_blink_timers() -> void:
	_blink_timer = Timer.new()
	_blink_timer.one_shot = true
	_blink_timer.timeout.connect(_on_blink_timer_timeout)
	add_child(_blink_timer)

	_blink_frame_timer = Timer.new()
	_blink_frame_timer.one_shot = true
	_blink_frame_timer.timeout.connect(_on_blink_frame_timeout)
	add_child(_blink_frame_timer)

	_start_blink_timer()


func _start_blink_timer() -> void:
	if _blink_timer:
		_blink_timer.start(randf_range(BLINK_INTERVAL_MIN, BLINK_INTERVAL_MAX))


func _on_blink_timer_timeout() -> void:
	_is_blinking = true
	_blink_sequence_index = 0
	_play_blink_frame()


func _on_blink_frame_timeout() -> void:
	_blink_sequence_index += 1
	if _blink_sequence_index >= BLINK_SEQUENCE.size():
		_is_blinking = false
		_current_blink_frame = 0
		_update_face_texture()
		_start_blink_timer()
	else:
		_play_blink_frame()


func _play_blink_frame() -> void:
	_current_blink_frame = BLINK_SEQUENCE[_blink_sequence_index]
	_update_face_texture()
	_blink_frame_timer.start(BLINK_FRAME_DURATION)


# === INTERNAL: Avatar build/teardown ===

func _build_avatar() -> void:
	var cfg = _cfg()

	var base_path = _asset(cfg["base_glb"])
	var base_scene = load(base_path) as PackedScene
	if not base_scene:
		push_error("Failed to load base avatar: " + base_path)
		return

	_base_instance = base_scene.instantiate()
	add_child(_base_instance)

	_skeleton = _find_skeleton(_base_instance)
	_animation_player = _find_animation_player(_base_instance)

	if not _skeleton:
		push_error("No Skeleton3D found in base avatar")
		return

	if _animation_player:
		_all_animations = _animation_player.get_animation_list()
		_all_animations.sort()
		_animation_player.animation_finished.connect(_on_animation_finished)

	_material_meshes.clear()
	_find_material_meshes(_base_instance)

	_load_parts_metadata()
	_apply_material_textures()

	_current_face_type_index = face_type
	_update_face_texture()

	if blink_enabled:
		_start_blink_timer()

	_apply_initial_parts()

	if equipment_type != "" and equipment_variant != "":
		equip_weapon(equipment_type, equipment_variant)

	if default_animation != "":
		play_animation(default_animation)
	elif _animation_player:
		var stand = cfg["stand_anim"]
		if _animation_player.has_animation(stand):
			play_animation(stand)


func _teardown_avatar() -> void:
	for slot in _current_parts:
		if _current_parts[slot]:
			_current_parts[slot].queue_free()
			_current_parts[slot] = null
			_current_part_names[slot] = ""

	_unequip_internal()

	if _blink_timer:
		_blink_timer.stop()
	if _blink_frame_timer:
		_blink_frame_timer.stop()

	if _animation_player:
		if _animation_player.animation_finished.is_connected(_on_animation_finished):
			_animation_player.animation_finished.disconnect(_on_animation_finished)
		_animation_player.stop()

	if _base_instance:
		_base_instance.queue_free()
		_base_instance = null

	_skeleton = null
	_animation_player = null
	_material_meshes.clear()
	_all_animations = PackedStringArray()
	_current_anim_name = ""


func _apply_initial_parts() -> void:
	var slots = {
		"hair": hair_variant,
		"upper": upper_variant,
		"lower": lower_variant,
		"hands": hands_variant,
		"feet": feet_variant,
	}
	for slot in slots:
		var variant: String = slots[slot]
		if variant != "":
			_swap_part_by_variant(slot, variant)


# === INTERNAL: Node finding ===

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
			_material_meshes[mat_name] = node
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


# === INTERNAL: Parts metadata ===

func _load_parts_metadata() -> void:
	var metadata_path = _asset(_cfg()["metadata_file"])
	var file = FileAccess.open(metadata_path, FileAccess.READ)
	if not file:
		push_warning("Could not load parts metadata: " + metadata_path)
		return
	var json_text = file.get_as_text()
	file.close()
	var json = JSON.new()
	if json.parse(json_text) != OK:
		push_error("Failed to parse parts metadata: " + json.get_error_message())
		return
	var data = json.get_data()
	if data.has("parts"):
		_parts_metadata = data["parts"]


func _get_part_hides_regions(part_name: String) -> Array:
	if _parts_metadata.has(part_name):
		return _parts_metadata[part_name].get("hides_regions", [])
	return []


# === INTERNAL: Materials ===

func _create_textured_material(texture_path: String, use_hair_shader: bool = false, use_alpha_scissor: bool = false) -> Material:
	var texture = load(texture_path) as Texture2D
	if not texture:
		push_warning("Could not load texture: " + texture_path)
		return null

	if use_hair_shader:
		var mat = ShaderMaterial.new()
		mat.shader = _hair_shader
		mat.set_shader_parameter("hair_texture", texture)
		mat.set_shader_parameter("skin_color", skin_color)
		mat.set_shader_parameter("alpha_threshold", 0.3)
		return mat

	if use_alpha_scissor:
		var mat = ShaderMaterial.new()
		mat.shader = _clothing_shader
		mat.set_shader_parameter("clothing_texture", texture)
		mat.set_shader_parameter("skin_color", skin_color)
		mat.set_shader_parameter("alpha_threshold", 0.5)
		return mat

	var material = StandardMaterial3D.new()
	material.albedo_texture = texture
	material.roughness = 1.0
	material.specular_mode = BaseMaterial3D.SPECULAR_DISABLED
	return material


func _apply_material_textures() -> void:
	_shared_skin_material = ShaderMaterial.new()
	_shared_skin_material.shader = _skin_shader
	_shared_skin_material.set_shader_parameter("skin_color", skin_color)

	var mat_to_tex: Dictionary = _cfg()["material_to_texture"]
	for mat_name in _material_meshes:
		if mat_name in ["arm", "leg", "hand", "foot"]:
			_material_meshes[mat_name].material_override = _shared_skin_material
			continue

		var texture_file = mat_to_tex.get(mat_name)
		if texture_file == null:
			continue

		var texture_path = _asset("textures/base/" + texture_file)
		var use_hair = mat_name in ["hair_scalp", "hair_strands"]
		var use_clothing = mat_name in ["upper", "lower"]
		var material = _create_textured_material(texture_path, use_hair, use_clothing)
		if material:
			_material_meshes[mat_name].material_override = material


# === INTERNAL: Face ===

func _update_face_texture() -> void:
	if not _material_meshes.has("face"):
		return

	var cfg = _cfg()
	var face_types: Array = cfg["face_types"]
	if _current_face_type_index >= face_types.size():
		_current_face_type_index = 0
	var face_type_code: String = face_types[_current_face_type_index]
	var texture_name = cfg["face_prefix"] + face_type_code + str(_current_blink_frame) + ".tga"
	var texture_path = _asset("textures/faces/" + texture_name)

	var texture = load(texture_path) as Texture2D
	if not texture:
		return

	var material = _material_meshes["face"].material_override as ShaderMaterial
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
		material.set_shader_parameter("skin_color", skin_color)
		_material_meshes["face"].material_override = material

	material.set_shader_parameter("face_texture", texture)


# === INTERNAL: Part swapping ===

func _swap_part_by_variant(slot: String, variant: String) -> void:
	if not _skeleton:
		return

	if _current_parts[slot]:
		_current_parts[slot].queue_free()
		_current_parts[slot] = null
		_current_part_names[slot] = ""

	if variant == "":
		_update_material_visibility()
		return

	var cfg = _cfg()
	var actual_slot = slot
	if slot == "hands":
		actual_slot = "hand"
	elif slot == "feet":
		actual_slot = "foot"
	var glb_name = cfg["part_prefix"] + "_" + actual_slot + "_" + variant + ".glb"
	var glb_path = _asset(cfg["parts_dir"] + glb_name)
	var part_name = glb_name.replace(".glb", "")

	_load_and_attach_part(slot, glb_path, part_name)


func _load_and_attach_part(slot: String, glb_path: String, part_name: String) -> void:
	var part_scene = load(glb_path) as PackedScene
	if not part_scene:
		push_warning("Failed to load part: " + glb_path)
		return

	var part_instance = part_scene.instantiate()
	var mesh_instance: MeshInstance3D = _find_mesh_in_part(part_instance)

	if not mesh_instance:
		push_warning("No MeshInstance3D in part: " + glb_path)
		part_instance.queue_free()
		return

	var part_skin = mesh_instance.skin
	mesh_instance.get_parent().remove_child(mesh_instance)
	_skeleton.add_child(mesh_instance)
	mesh_instance.skeleton = _skeleton.get_path()
	if part_skin:
		mesh_instance.skin = part_skin
	part_instance.queue_free()

	_current_parts[slot] = mesh_instance
	_current_part_names[slot] = part_name

	var texture_path = _get_part_texture_path(part_name)
	if texture_path != "":
		var use_hair = slot == "hair"
		var use_alpha = slot in ["upper", "lower", "hands", "feet", "glorb"]
		var material = _create_textured_material(texture_path, use_hair, use_alpha)
		if material:
			mesh_instance.material_override = material

	_update_material_visibility()


func _get_part_texture_path(part_name: String) -> String:
	var tga_path = _asset("textures/parts/" + part_name + ".tga")
	if ResourceLoader.exists(tga_path):
		return tga_path
	var bmp_path = _asset("textures/parts/" + part_name + ".bmp")
	if ResourceLoader.exists(bmp_path):
		return bmp_path
	return ""


# === INTERNAL: Material visibility ===

func _update_material_visibility() -> void:
	for mat_name in _material_meshes:
		_material_meshes[mat_name].visible = true

	var all_hidden_regions: Array[String] = []
	for slot in _current_parts:
		if _current_parts[slot] != null:
			var part_name = _current_part_names[slot]
			var hidden_regions = _get_part_hides_regions(part_name)
			for region_name in hidden_regions:
				if not all_hidden_regions.has(region_name):
					all_hidden_regions.append(region_name)

	for mat_name in MATERIAL_REQUIRED_REGIONS:
		var required_regions = MATERIAL_REQUIRED_REGIONS[mat_name]
		var all_required_hidden = true
		for region_name in required_regions:
			if not all_hidden_regions.has(region_name):
				all_required_hidden = false
				break
		if all_required_hidden and _material_meshes.has(mat_name):
			_material_meshes[mat_name].visible = false


# === INTERNAL: Skin color ===

func _apply_skin_color_to_all() -> void:
	if _shared_skin_material:
		_shared_skin_material.set_shader_parameter("skin_color", skin_color)

	for mat_name in _material_meshes:
		var mat = _material_meshes[mat_name].material_override
		if mat is ShaderMaterial:
			if mat.shader == _hair_shader or mat.shader == _clothing_shader or mat.shader == _skin_shader:
				mat.set_shader_parameter("skin_color", skin_color)

	for slot in _current_parts:
		if _current_parts[slot]:
			var mat = _current_parts[slot].material_override
			if mat is ShaderMaterial:
				mat.set_shader_parameter("skin_color", skin_color)

	if _material_meshes.has("face"):
		var face_mat = _material_meshes["face"].material_override
		if face_mat is ShaderMaterial:
			face_mat.set_shader_parameter("skin_color", skin_color)


# === INTERNAL: Weapons ===

func _attach_weapon(glb_filename: String, weapons_path: String, bone: String) -> void:
	_detach_weapon()

	var weapon_path = weapons_path + glb_filename
	var weapon_scene = load(weapon_path) as PackedScene
	if not weapon_scene:
		push_warning("Failed to load weapon: " + weapon_path)
		return

	_weapon_attachment = BoneAttachment3D.new()
	_weapon_attachment.bone_name = bone
	_skeleton.add_child(_weapon_attachment)

	_current_weapon_node = weapon_scene.instantiate()
	_weapon_attachment.add_child(_current_weapon_node)

	var weapon_name = glb_filename.replace(".glb", "")
	for child in _current_weapon_node.get_children():
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


func _detach_weapon() -> void:
	if _weapon_attachment:
		_weapon_attachment.queue_free()
		_weapon_attachment = null
		_current_weapon_node = null


func _get_weapon_texture_path(weapon_name: String) -> String:
	var bmp_path = _asset("textures/weapons/" + weapon_name + ".bmp")
	if ResourceLoader.exists(bmp_path):
		return bmp_path
	var tga_path = _asset("textures/weapons/" + weapon_name + ".tga")
	if ResourceLoader.exists(tga_path):
		return tga_path
	return ""


func _unequip_internal() -> void:
	var was_glorb = _current_equipment_type == "glorb"
	_current_equipment_type = ""
	_current_equipment_variant = ""
	_detach_weapon()
	if was_glorb and _current_parts["glorb"]:
		_current_parts["glorb"].queue_free()
		_current_parts["glorb"] = null
		_current_part_names["glorb"] = ""
		_update_material_visibility()


# === INTERNAL: Animation callback ===

func _on_animation_finished(anim_name: StringName) -> void:
	animation_finished.emit(String(anim_name))


# === INTERNAL: Variant extraction ===

func _variant_from_part_name(slot: String) -> String:
	var part_name: String = _current_part_names.get(slot, "")
	if part_name == "":
		return ""
	var parts = part_name.split("_")
	if parts.size() >= 3:
		return parts[parts.size() - 1]
	return part_name
