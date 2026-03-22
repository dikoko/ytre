extends Control
## Avatar Composer Tool
##
## Interactive tool for composing and previewing avatar configurations.
## Allows swapping body parts, weapons, and testing animations.

# Paths to avatar assets
const AVATAR_PATH := "res://assets/characters/avatars/"
const PARTS_PATH := "res://assets/characters/parts/"

# Current state
var current_gender: String = "male"
var current_parts: Dictionary = {}  # slot -> part_id
var base_skeleton: Skeleton3D
var animation_player: AnimationPlayer

# Part slots
const PART_SLOTS := ["hair", "upper", "lower", "foot", "hand", "glorb", "special"]

# Weapon attachment bones
const ATTACHMENT_BONES := {
	"HandR": 3,   # Primary weapon
	"HandL": 2,   # Offhand
	"Head": 1,    # Hats
	"Spine3": 8,  # Back items
	"Sword": 7,   # Sheathed weapon
}


func _ready() -> void:
	# TODO: Initialize UI components
	# TODO: Load default avatar
	pass


func load_base_avatar(gender: String) -> void:
	"""Load the base avatar skeleton with animations."""
	current_gender = gender
	var base_path := AVATAR_PATH + gender + "_base.glb"

	# TODO: Load GLTF scene
	# TODO: Extract skeleton and animation player
	# TODO: Set up part attachment points
	pass


func swap_part(slot: String, part_id: String) -> void:
	"""Swap a body part on the current avatar."""
	if slot not in PART_SLOTS:
		push_error("Invalid part slot: " + slot)
		return

	# Remove existing part
	if current_parts.has(slot):
		_remove_part(slot)

	if part_id.is_empty():
		return

	# Load new part
	var part_path := PARTS_PATH + current_gender + "/" + slot + "/" + part_id + ".glb"
	# TODO: Load part GLTF
	# TODO: Attach to skeleton
	# TODO: Update current_parts

	current_parts[slot] = part_id


func attach_weapon(bone_name: String, weapon_path: String) -> void:
	"""Attach a weapon to the specified bone."""
	if bone_name not in ATTACHMENT_BONES:
		push_error("Invalid attachment bone: " + bone_name)
		return

	# TODO: Load weapon GLTF
	# TODO: Create BoneAttachment3D
	# TODO: Add as child of skeleton
	pass


func play_animation(anim_name: String) -> void:
	"""Play an animation on the current avatar."""
	if animation_player and animation_player.has_animation(anim_name):
		animation_player.play(anim_name)


func get_animation_list() -> PackedStringArray:
	"""Get list of available animations."""
	if animation_player:
		return animation_player.get_animation_list()
	return PackedStringArray()


func _remove_part(slot: String) -> void:
	"""Remove a part from the specified slot."""
	# TODO: Find and remove mesh instance
	current_parts.erase(slot)


func randomize_parts() -> void:
	"""Randomize all parts for testing."""
	# TODO: Get available parts from filesystem
	# TODO: Randomly select one for each slot
	pass


func reset_to_default() -> void:
	"""Reset avatar to default configuration."""
	for slot in PART_SLOTS:
		_remove_part(slot)
	current_parts.clear()
