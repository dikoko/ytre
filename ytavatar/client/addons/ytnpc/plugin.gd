@tool
extends EditorPlugin


func _enter_tree() -> void:
	add_custom_type(
		"NPCCharacter",
		"Node3D",
		preload("npc_character.gd"),
		null
	)


func _exit_tree() -> void:
	remove_custom_type("NPCCharacter")
