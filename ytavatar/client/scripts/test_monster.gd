extends Node3D
## Model viewer for monsters and NPCs.
##
## Controls: Left/Right=cycle model, Tab=cycle anim, Space=pause
## Camera: Mouse drag=orbit, Scroll/Pinch=zoom

# -- Model management --
# Each entry: { "id": "ct0001", "path": "res://assets/monsters/models/ct0001.glb" }
var model_entries: Array[Dictionary] = []
var current_model_index: int = 0
var current_instance: Node3D = null
var animation_player: AnimationPlayer = null

# -- Animation --
var animation_names: Array[String] = []
var current_anim_index: int = 0
var is_paused: bool = false

# -- Camera orbit --
var camera_distance: float = 4.0
var camera_yaw: float = 0.0
var camera_pitch: float = -15.0
var camera_target: Vector3 = Vector3(0, 0.8, 0)
var is_dragging: bool = false

const ZOOM_MIN := 0.5
const ZOOM_MAX := 30.0
const ZOOM_STEP := 0.5
const PITCH_MIN := -80.0
const PITCH_MAX := 80.0

const MODEL_DIRS := [
	"res://assets/npcs/models/",
]

# Only load model IDs starting with this prefix (empty = load all)
const MODEL_PREFIX_FILTER := "cn0047"

@onready var camera: Camera3D = $Camera3D
@onready var model_root: Node3D = $MonsterRoot


func _ready() -> void:
	_discover_models()
	if model_entries.size() > 0:
		_load_model(0)
	_update_camera()
	print("Model Viewer Ready")
	print("  Models found: %d" % model_entries.size())
	print("  Controls: Left/Right=cycle model, Tab=cycle anim, Space=pause")
	print("  Camera: Mouse drag=orbit, Scroll=zoom")


func _discover_models() -> void:
	"""Scan model directories for GLB files."""
	for dir_path in MODEL_DIRS:
		var dir := DirAccess.open(dir_path)
		if dir == null:
			continue
		dir.list_dir_begin()
		var file_name := dir.get_next()
		while file_name != "":
			if file_name.ends_with(".glb"):
				var model_id := file_name.get_basename()
				# Apply prefix filter if set
				if MODEL_PREFIX_FILTER != "" and not model_id.begins_with(MODEL_PREFIX_FILTER):
					file_name = dir.get_next()
					continue
				model_entries.append({
					"id": model_id,
					"path": dir_path + file_name,
				})
			file_name = dir.get_next()
	model_entries.sort_custom(func(a, b): return a["id"] < b["id"])


func _load_model(index: int) -> void:
	"""Load a model GLB and set up its AnimationPlayer."""
	if current_instance:
		current_instance.queue_free()
		current_instance = null
		animation_player = null
		animation_names.clear()

	current_model_index = index
	var entry := model_entries[index]
	var path: String = entry["path"]

	var scene := load(path) as PackedScene
	if scene == null:
		print("ERROR: Failed to load %s" % path)
		return

	current_instance = scene.instantiate()
	model_root.add_child(current_instance)

	animation_player = _find_animation_player(current_instance)
	if animation_player:
		animation_names.clear()
		for anim_name in animation_player.get_animation_list():
			animation_names.append(anim_name)
		animation_names.sort()
		current_anim_index = 0
		_play_current_animation()

	print("Loaded: %s (%d/%d) - %d animations" % [
		entry["id"], index + 1, model_entries.size(), animation_names.size()
	])


func _find_animation_player(node: Node) -> AnimationPlayer:
	"""Recursively find AnimationPlayer in node tree."""
	if node is AnimationPlayer:
		return node as AnimationPlayer
	for child in node.get_children():
		var found := _find_animation_player(child)
		if found:
			return found
	return null



func _play_current_animation() -> void:
	if animation_player and animation_names.size() > 0:
		var anim_name := animation_names[current_anim_index]
		animation_player.play(anim_name)
		is_paused = false
		print("  Animation: %s (%d/%d)" % [
			anim_name, current_anim_index + 1, animation_names.size()
		])


func _unhandled_input(event: InputEvent) -> void:
	# Camera orbit
	if event is InputEventMouseButton:
		var mb := event as InputEventMouseButton
		if mb.button_index == MOUSE_BUTTON_LEFT:
			is_dragging = mb.pressed
		elif mb.button_index == MOUSE_BUTTON_WHEEL_UP:
			camera_distance = max(ZOOM_MIN, camera_distance - ZOOM_STEP)
			_update_camera()
		elif mb.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			camera_distance = min(ZOOM_MAX, camera_distance + ZOOM_STEP)
			_update_camera()

	elif event is InputEventMouseMotion and is_dragging:
		var mm := event as InputEventMouseMotion
		camera_yaw -= mm.relative.x * 0.3
		camera_pitch = clamp(camera_pitch - mm.relative.y * 0.3, PITCH_MIN, PITCH_MAX)
		_update_camera()

	elif event is InputEventMagnifyGesture:
		camera_distance = clamp(camera_distance / event.factor, ZOOM_MIN, ZOOM_MAX)
		_update_camera()

	elif event is InputEventKey and event.pressed:
		var key := event as InputEventKey
		match key.keycode:
			KEY_LEFT:
				if model_entries.size() > 0:
					_load_model((current_model_index - 1 + model_entries.size()) % model_entries.size())
			KEY_RIGHT:
				if model_entries.size() > 0:
					_load_model((current_model_index + 1) % model_entries.size())
			KEY_TAB:
				if animation_names.size() > 0:
					current_anim_index = (current_anim_index + 1) % animation_names.size()
					_play_current_animation()
			KEY_SPACE:
				if animation_player:
					if animation_player.is_playing():
						animation_player.pause()
					else:
						animation_player.play()
					is_paused = not animation_player.is_playing()
			KEY_D:
				_print_debug()


func _update_camera() -> void:
	if not camera:
		return
	var yaw_rad := deg_to_rad(camera_yaw)
	var pitch_rad := deg_to_rad(camera_pitch)
	var offset := Vector3(
		camera_distance * cos(pitch_rad) * sin(yaw_rad),
		camera_distance * -sin(pitch_rad),
		camera_distance * cos(pitch_rad) * cos(yaw_rad),
	)
	camera.position = camera_target + offset
	camera.look_at(camera_target)


func _print_debug() -> void:
	if model_entries.size() == 0:
		print("No models loaded")
		return
	var entry := model_entries[current_model_index]
	print("--- Debug ---")
	print("  Model: %s (%d/%d)" % [entry["id"], current_model_index + 1, model_entries.size()])
	if animation_names.size() > 0:
		print("  Animation: %s (%d/%d)" % [
			animation_names[current_anim_index],
			current_anim_index + 1,
			animation_names.size()
		])
	print("  Paused: %s" % str(is_paused))
