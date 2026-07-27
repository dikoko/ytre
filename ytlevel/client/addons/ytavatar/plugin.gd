@tool
extends EditorPlugin


func _enter_tree() -> void:
	add_custom_type(
		"AvatarCharacter",
		"Node3D",
		preload("avatar_character.gd"),
		null
	)


func _exit_tree() -> void:
	remove_custom_type("AvatarCharacter")
