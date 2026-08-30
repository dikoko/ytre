class_name TargetDummy
extends Node3D
## C1.5 target dummy: wraps an AvatarCharacter OR a MonsterCharacter
## behind one hit-reaction surface for SkillPlayer's target-role routing.
## The tool owns placement/lifecycle; SkillPlayer only calls play_hit /
## get_bone_attachment / root.
##
## Idle contract: an avatar dummy idles on basic stand (clear_stance);
## a monster dummy loops "{id}_stand". A finished hit one-shot re-idles
## via the character's animation_finished signal — an avatar with no
## stance would otherwise FREEZE on the hit's last frame
## (avatar_character.gd's _on_animation_finished only auto-returns when
## a stance is set).
##
## Default parts: AvatarCharacter exposes no get_available_parts()/
## default-parts API (verified against avatar_character.gd) — the only
## default-part mechanism lives in avatar_tool.gd's tool-private
## GENDER_CONFIG. Per the task brief, a bare base body is acceptable for
## v1: the dummy skips outfitting entirely and idles on the unclothed
## base mesh.

var kind := ""          # "", "avatar", "monster"
var _char: Node3D = null
var _monster_id := ""


func root() -> Node3D:
	return _char


func clear() -> void:
	if _char != null:
		if _char.has_signal("animation_finished") \
				and _char.animation_finished.is_connected(_on_char_animation_finished):
			_char.animation_finished.disconnect(_on_char_animation_finished)
		_char.queue_free()
	_char = null
	kind = ""
	_monster_id = ""


func setup_avatar(gender: String) -> bool:
	clear()
	var av := AvatarCharacter.new()
	av.gender = gender
	av.default_animation = ""
	add_child(av)
	av.clear_stance()                      # basic stand loop
	av.animation_finished.connect(_on_char_animation_finished)
	_char = av
	kind = "avatar"
	return true


func setup_monster(monster_id: String) -> bool:
	clear()
	var mc := MonsterCharacter.new()
	mc.auto_play = ""
	add_child(mc)
	mc.set_monster(monster_id)
	if mc.get_monster_id() != monster_id:
		mc.queue_free()
		return false
	_monster_id = monster_id
	mc.play_animation("%s_stand" % monster_id, true)
	mc.animation_finished.connect(_on_char_animation_finished)
	_char = mc
	kind = "monster"
	return true


func play_hit(motion_id: int) -> void:
	## Hit reaction. Avatar: by motion id (the catalog's target motions are
	## id 19 fleet-wide, one 60002 outlier — both resolve via the mlib map).
	## Monster: any target motion maps to the model's "{id}_hit1" one-shot
	## (monster GLBs ship stand/walk/run/attack1/hit1/die; there is no
	## per-id monster motion table and the authored tracks all say 19).
	if _char == null:
		return
	if kind == "avatar":
		_char.play_motion_id(motion_id)    # silent false on missing id
	elif kind == "monster":
		var clip := "%s_hit1" % _monster_id
		if _char.get_animation_list().has(clip):
			_char.play_animation(clip, false)


func get_bone_attachment(bone_name: String) -> BoneAttachment3D:
	## Avatar-rig bone names only — a monster dummy returns null and the
	## caller (SkillPlayer._bind_wrapper) falls back to root binding.
	if kind == "avatar" and _char != null:
		return _char.get_bone_attachment(bone_name)
	return null


func _on_char_animation_finished(_name: String) -> void:
	## Re-idle after a one-shot hit (see the idle contract above).
	if _char == null:
		return
	if kind == "avatar":
		if not _char.is_animation_playing():
			_char.clear_stance()
	elif kind == "monster":
		if _char.get_current_animation() != "%s_stand" % _monster_id:
			_char.play_animation("%s_stand" % _monster_id, true)
