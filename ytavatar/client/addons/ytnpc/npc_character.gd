@tool
class_name NPCCharacter
extends Node3D
## Reusable NPC character component.
##
## Each instance represents a single NPC. Set npc_id in the inspector
## or call set_npc() at runtime. Visual-only — parent node handles
## physics/movement.
##
## Asset path structure (under assets_path):
##   models/   - cn0001.glb, cn0002.glb, etc. (self-contained GLBs)

# === SIGNALS ===

signal npc_loaded(npc_id: String)
signal npc_cleared()
signal animation_started(name: String)
signal animation_finished(name: String)

# === EXPORTS ===

@export_group("Assets")
@export_dir var assets_path: String = "res://assets/npcs/"

@export_group("NPC")
@export var npc_id: String = ""
@export var auto_play: String = "stand"

# === INTERNAL STATE ===

var _instance: Node3D = null
var _skeleton: Skeleton3D = null
var _animation_player: AnimationPlayer = null
var _animation_list: PackedStringArray = []
var _current_anim_name: String = ""
var _current_npc_id: String = ""


# === LIFECYCLE ===

func _ready() -> void:
	if Engine.is_editor_hint():
		return
	if npc_id != "":
		_load_npc()


# === PUBLIC API: NPC lifecycle ===

func set_npc(id: String) -> void:
	if id == "":
		clear_npc()
		return
	npc_id = id
	_load_npc()


func clear_npc() -> void:
	if _animation_player:
		if _animation_player.animation_finished.is_connected(_on_animation_finished):
			_animation_player.animation_finished.disconnect(_on_animation_finished)

	if _instance:
		_instance.queue_free()
		_instance = null

	_skeleton = null
	_animation_player = null
	_animation_list = PackedStringArray()
	_current_anim_name = ""
	_current_npc_id = ""
	npc_cleared.emit()


func get_npc_id() -> String:
	return _current_npc_id


# === PUBLIC API: Animation ===

func play_animation(anim_name: String, loop: bool = true) -> void:
	if not _animation_player:
		return
	if not _animation_player.has_animation(anim_name):
		push_warning("Animation not found: " + anim_name)
		return
	var anim = _animation_player.get_animation(anim_name)
	if anim:
		anim.loop_mode = Animation.LOOP_LINEAR if loop else Animation.LOOP_NONE
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
	if _animation_player and _animation_player.is_playing():
		_animation_player.pause()


func resume_animation() -> void:
	if _animation_player and not _animation_player.is_playing() and _current_anim_name != "":
		_animation_player.play()


func is_animation_playing() -> bool:
	return _animation_player != null and _animation_player.is_playing()


func get_animation_list() -> PackedStringArray:
	return _animation_list


func get_current_animation() -> String:
	return _current_anim_name


# === PUBLIC API: Access ===

func get_skeleton() -> Skeleton3D:
	return _skeleton


# === INTERNAL ===

func _load_npc() -> void:
	clear_npc()

	var base = assets_path
	if not base.ends_with("/"):
		base += "/"
	var path = base + "models/" + npc_id + ".glb"

	if not ResourceLoader.exists(path):
		push_warning("NPC GLB not found: " + path)
		return

	var scene = load(path) as PackedScene
	if not scene:
		push_warning("Failed to load NPC: " + path)
		return

	_instance = scene.instantiate()
	add_child(_instance)

	_skeleton = _find_node_of_type(_instance, "Skeleton3D") as Skeleton3D
	_animation_player = _find_node_of_type(_instance, "AnimationPlayer") as AnimationPlayer

	if _animation_player:
		var names: Array[String] = []
		for anim_name in _animation_player.get_animation_list():
			names.append(anim_name)
		names.sort()
		_animation_list = PackedStringArray(names)
		_animation_player.animation_finished.connect(_on_animation_finished)

	_current_npc_id = npc_id

	if auto_play != "" and _animation_list.size() > 0:
		for anim_name in _animation_list:
			if anim_name.contains(auto_play):
				play_animation(anim_name)
				break

	npc_loaded.emit(npc_id)


func _find_node_of_type(node: Node, type_name: String) -> Node:
	if node.get_class() == type_name:
		return node
	for child in node.get_children():
		var result = _find_node_of_type(child, type_name)
		if result:
			return result
	return null


func _on_animation_finished(anim_name: StringName) -> void:
	animation_finished.emit(String(anim_name))
