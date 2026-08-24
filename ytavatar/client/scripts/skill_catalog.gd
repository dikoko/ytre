class_name SkillCatalog
extends RefCounted
## Data-only view over skills.json v2 + weapons.json + bones.json.
## SkillPlayer keeps playback; the tool asks this class what to play.

const SKILLS_PATH := "res://assets/effects/skills.json"
const WEAPONS_PATH := "res://assets/effects/weapons.json"
const BONES_PATH := "res://assets/effects/bones.json"

var _skills: Dictionary = {}
var _weapons: Dictionary = {}
var _bones: Dictionary = {}


static func _read_json(path: String) -> Dictionary:
	var f := FileAccess.open(path, FileAccess.READ)
	if f == null:
		return {}
	var doc = JSON.parse_string(f.get_as_text())
	return doc if doc is Dictionary else {}


func load() -> bool:
	_skills = _read_json(SKILLS_PATH).get("skills", {})
	_weapons = _read_json(WEAPONS_PATH).get("weapons", {})
	_bones = _read_json(BONES_PATH).get("bones", {})
	return not _skills.is_empty() and not _weapons.is_empty() and not _bones.is_empty()


func skill_ids() -> PackedStringArray:
	var out := PackedStringArray(_skills.keys())
	out.sort()
	return out


func skill_info(code: String) -> Dictionary:
	return _skills.get(code, {})


func family(code: String) -> String:
	return String(skill_info(code).get("family", ""))


func weapon_keys() -> PackedStringArray:
	var out := PackedStringArray(_weapons.keys())
	out.sort()
	return out


func skill_set_for_weapon(key: String) -> Dictionary:
	return _weapons.get(key, {})


func bone_name(bone_id: int) -> String:
	var v = _bones.get(str(bone_id))
	return String(v) if v is String else ""


static func code_for_id(id: int) -> String:
	return "sk%06d" % id
