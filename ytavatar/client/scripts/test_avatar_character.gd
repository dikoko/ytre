extends Node3D
## Test scene for AvatarCharacter component.
##
## Controls:
##   Left/Right: Switch focus between avatars
##   1-5/Q-T: Cycle parts forward/backward (hair, upper, lower, hands, feet)
##   6-9: Equip weapons (blade, glorb, mura, spirit)
##   P: Unequip weapon
##   Tab: Cycle animation
##   Space: Pause/resume animation
##   F/V: Cycle face forward/backward
##   G: Toggle gender of focused avatar
##   C: Change skin color of focused avatar
##   A: Add a third avatar at runtime
##   S: Save/load state test

# Camera orbit
var camera_distance: float = 5.0
var camera_yaw: float = 0.0
var camera_pitch: float = 15.0
var is_dragging: bool = false

const ZOOM_MIN := 1.0
const ZOOM_MAX := 15.0

@onready var camera: Camera3D = $Camera3D

# Avatars
var avatars: Array[Node3D] = []
var focused_index: int = 0

# Animation cycling
var anim_index: int = 0
var anim_list: PackedStringArray = []

# Part cycling state per gender -> slot -> variants
var part_lists_by_gender: Dictionary = {}  # "male" -> { slot -> Array }, "female" -> { ... }
var part_indices: Dictionary = {}  # slot -> int

# Skin color presets
var skin_colors: Array[Color] = [
	Color(0.992, 0.812, 0.635, 1.0),  # Default light
	Color(0.871, 0.663, 0.478, 1.0),  # Tan
	Color(0.698, 0.502, 0.349, 1.0),  # Medium
	Color(0.494, 0.333, 0.231, 1.0),  # Dark
	Color(1.0, 0.9, 0.8, 1.0),        # Pale
]
var skin_color_index: int = 0


func _ready() -> void:
	# Collect the pre-placed avatars
	avatars.append($AvatarLeft)
	avatars.append($AvatarRight)

	# Connect signals on both avatars
	for avatar in avatars:
		avatar.part_changed.connect(_on_part_changed.bind(avatar))
		avatar.equipment_changed.connect(_on_equipment_changed.bind(avatar))
		avatar.animation_started.connect(_on_animation_started.bind(avatar))
		avatar.gender_changed.connect(_on_gender_changed.bind(avatar))

	# Scan available parts for cycling
	_scan_available_parts()

	# Initialize focus indicator
	_update_focus_indicator()

	_update_camera()
	print("=== AvatarCharacter Test Scene ===")
	print("Left/Right: Switch avatar focus")
	print("1-5/Q-T: Cycle parts")
	print("6-9: Equip weapons, P: Unequip")
	print("Tab: Cycle animation, Space: Pause")
	print("F/V: Cycle face, G: Toggle gender")
	print("C: Cycle skin color, A: Add avatar, S: Save/load test")


func _scan_available_parts() -> void:
	# Scan both male and female parts directories (derive from first avatar's assets_path)
	var base_path: String = avatars[0].get_assets_path()
	if not base_path.ends_with("/"):
		base_path += "/"
	var gender_dirs = {
		"male": base_path + "parts/male/",
		"female": base_path + "parts/female/",
	}

	for gender_name in gender_dirs:
		var dir_path: String = gender_dirs[gender_name]
		var dir = DirAccess.open(dir_path)
		if not dir:
			continue

		var slot_map = {"hair": [], "upper": [], "lower": [], "hand": [], "foot": []}
		dir.list_dir_begin()
		var file_name = dir.get_next()
		while file_name != "":
			if file_name.ends_with(".glb"):
				var base = file_name.get_basename()
				var parts = base.split("_")
				if parts.size() >= 3:
					var slot_name = parts[1]
					var variant = parts[parts.size() - 1]
					if slot_map.has(slot_name):
						slot_map[slot_name].append(variant)
			file_name = dir.get_next()

		var gender_parts = {}
		gender_parts["hair"] = slot_map["hair"]
		gender_parts["upper"] = slot_map["upper"]
		gender_parts["lower"] = slot_map["lower"]
		gender_parts["hands"] = slot_map["hand"]
		gender_parts["feet"] = slot_map["foot"]

		for slot in gender_parts:
			gender_parts[slot].sort()

		part_lists_by_gender[gender_name] = gender_parts
		print("Found %s parts: " % gender_name, {
			"hair": gender_parts["hair"].size(),
			"upper": gender_parts["upper"].size(),
			"lower": gender_parts["lower"].size(),
			"hands": gender_parts["hands"].size(),
			"feet": gender_parts["feet"].size(),
		})

	for slot in ["hair", "upper", "lower", "hands", "feet"]:
		part_indices[slot] = 0


func _focused_avatar():
	if focused_index < avatars.size():
		return avatars[focused_index]
	return null


func _cycle_part(slot: String, direction: int) -> void:
	var avatar = _focused_avatar()
	if not avatar:
		return
	var gender_parts: Dictionary = part_lists_by_gender.get(avatar.gender, {})
	var variants: Array = gender_parts.get(slot, [])
	if variants.is_empty():
		return
	var count = variants.size()
	part_indices[slot] = (part_indices[slot] + direction + count) % count
	var variant = variants[part_indices[slot]]
	avatar.set_part(slot, variant)


func _cycle_face(direction: int) -> void:
	var avatar = _focused_avatar()
	if not avatar:
		return
	var face_count = avatar.get_face_type_count()
	var current = avatar.get_face_type_index()
	avatar.set_face((current + direction + face_count) % face_count)


func _update_focus_indicator() -> void:
	# Print which avatar is focused
	if focused_index < avatars.size():
		var avatar = avatars[focused_index]
		var label = "Left" if focused_index == 0 else ("Right" if focused_index == 1 else "Extra #%d" % (focused_index - 1))
		print("Focus: %s (%s)" % [label, avatar.gender])


func _update_camera() -> void:
	if not camera:
		return
	var yaw_rad = deg_to_rad(camera_yaw)
	var pitch_rad = deg_to_rad(camera_pitch)
	var offset = Vector3(
		camera_distance * cos(pitch_rad) * sin(yaw_rad),
		camera_distance * sin(pitch_rad),
		camera_distance * cos(pitch_rad) * cos(yaw_rad),
	)
	var target = Vector3(0, 1.0, 0)
	camera.position = target + offset
	camera.look_at(target)


func _unhandled_input(event: InputEvent) -> void:
	# Camera orbit
	if event is InputEventMouseButton:
		if event.button_index == MOUSE_BUTTON_LEFT:
			is_dragging = event.pressed
		elif event.button_index == MOUSE_BUTTON_WHEEL_UP and event.pressed:
			camera_distance = max(ZOOM_MIN, camera_distance - 0.3)
			_update_camera()
		elif event.button_index == MOUSE_BUTTON_WHEEL_DOWN and event.pressed:
			camera_distance = min(ZOOM_MAX, camera_distance + 0.3)
			_update_camera()

	if event is InputEventMouseMotion and is_dragging:
		camera_yaw -= event.relative.x * 0.3
		camera_pitch += event.relative.y * 0.3
		camera_pitch = clamp(camera_pitch, -80.0, 80.0)
		_update_camera()

	if event is InputEventMagnifyGesture:
		camera_distance = clamp(camera_distance / event.factor, ZOOM_MIN, ZOOM_MAX)
		_update_camera()

	if not event is InputEventKey or not event.pressed:
		return

	var avatar = _focused_avatar()

	match event.keycode:
		# Focus switching
		KEY_LEFT:
			focused_index = (focused_index - 1 + avatars.size()) % avatars.size()
			_update_focus_indicator()
		KEY_RIGHT:
			focused_index = (focused_index + 1) % avatars.size()
			_update_focus_indicator()

		# Parts forward
		KEY_1:
			_cycle_part("hair", 1)
		KEY_2:
			_cycle_part("upper", 1)
		KEY_3:
			_cycle_part("lower", 1)
		KEY_4:
			if avatar:
				avatar.unequip_weapon()  # Remove glorb if equipped
			_cycle_part("hands", 1)
		KEY_5:
			_cycle_part("feet", 1)

		# Parts backward
		KEY_Q:
			_cycle_part("hair", -1)
		KEY_W:
			_cycle_part("upper", -1)
		KEY_E:
			_cycle_part("lower", -1)
		KEY_R:
			if avatar:
				avatar.unequip_weapon()
			_cycle_part("hands", -1)
		KEY_T:
			_cycle_part("feet", -1)

		# Equipment
		KEY_6:
			if avatar:
				avatar.equip_weapon("blade", "A0001")
		KEY_7:
			if avatar:
				avatar.equip_weapon("glorb", "A0001")
		KEY_8:
			if avatar:
				avatar.equip_weapon("mura", "A0001")
		KEY_9:
			if avatar:
				avatar.equip_weapon("spirit", "A0001")
		KEY_P:
			if avatar:
				avatar.unequip_weapon()

		# Animation
		KEY_TAB:
			if avatar:
				anim_list = avatar.get_animation_list()
				if anim_list.size() > 0:
					anim_index = (anim_index + 1) % anim_list.size()
					avatar.play_animation(anim_list[anim_index])
					print("Animation: ", anim_list[anim_index])
		KEY_SPACE:
			if avatar:
				if avatar.is_animation_playing():
					avatar.pause_animation()
					print("Paused")
				else:
					avatar.resume_animation()
					print("Resumed")

		# Face
		KEY_F:
			_cycle_face(1)
		KEY_V:
			_cycle_face(-1)

		# Gender toggle
		KEY_G:
			if avatar:
				var new_gender = "female" if avatar.gender == "male" else "male"
				avatar.set_gender(new_gender)
				print("Gender -> ", new_gender)

		# Skin color
		KEY_C:
			if avatar:
				skin_color_index = (skin_color_index + 1) % skin_colors.size()
				avatar.set_skin_color(skin_colors[skin_color_index])
				print("Skin color preset: ", skin_color_index + 1)

		# Add avatar at runtime
		KEY_A:
			_add_runtime_avatar()

		# Save/load test
		KEY_S:
			_test_save_load()


func _add_runtime_avatar() -> void:
	var avatar_scene = load("res://addons/ytavatar/avatar_character.tscn") as PackedScene
	if not avatar_scene:
		push_warning("Could not load avatar_character.tscn")
		return

	var new_avatar = avatar_scene.instantiate()
	new_avatar.position = Vector3(avatars.size() * 2.0 - 2.0, 0, 0)
	new_avatar.gender = "male"
	new_avatar.hair_variant = "M0301"
	new_avatar.upper_variant = "M0011"
	new_avatar.lower_variant = "M0011"
	add_child(new_avatar)
	avatars.append(new_avatar)

	new_avatar.part_changed.connect(_on_part_changed.bind(new_avatar))
	new_avatar.equipment_changed.connect(_on_equipment_changed.bind(new_avatar))
	new_avatar.animation_started.connect(_on_animation_started.bind(new_avatar))
	new_avatar.gender_changed.connect(_on_gender_changed.bind(new_avatar))

	focused_index = avatars.size() - 1
	print("Added avatar #%d at runtime" % avatars.size())
	_update_focus_indicator()


func _test_save_load() -> void:
	var avatar = _focused_avatar()
	if not avatar:
		return

	# Save state
	var state = avatar.get_current_state()
	print("Saved state: ", state)

	# Modify avatar
	avatar.remove_all_parts()
	avatar.unequip_weapon()
	avatar.stop_animation()
	print("Cleared avatar")

	# Restore after a short delay so the change is visible
	await get_tree().create_timer(1.0).timeout
	avatar.load_state(state)
	print("Restored state from save")


# Signal handlers
func _on_part_changed(slot: String, variant: String, avatar: Node3D) -> void:
	var idx = avatars.find(avatar)
	print("[Avatar %d] Part %s -> %s" % [idx, slot, variant if variant != "" else "removed"])

func _on_equipment_changed(type: String, variant: String, avatar: Node3D) -> void:
	var idx = avatars.find(avatar)
	if type == "":
		print("[Avatar %d] Unequipped" % idx)
	else:
		print("[Avatar %d] Equipped %s %s" % [idx, type, variant])

func _on_animation_started(anim_name: String, avatar: Node3D) -> void:
	var idx = avatars.find(avatar)
	print("[Avatar %d] Animation: %s" % [idx, anim_name])

func _on_gender_changed(new_gender: String, avatar: Node3D) -> void:
	var idx = avatars.find(avatar)
	print("[Avatar %d] Gender -> %s" % [idx, new_gender])
