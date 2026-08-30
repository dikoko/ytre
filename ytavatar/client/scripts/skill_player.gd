class_name SkillPlayer
extends Node3D
## Plays one `skills.json` catalog entry against a character: the "core
## four" component kinds (effect models, caster motion, sound, color
## flash) on a single 30 fps clock. `sfx`/`camera`/`sword_trace` TRACKS
## are cataloged but deliberately not played here (deferred to the
## particle/camera phases). There is
## no "path" track kind (catalog track kinds: motion/tmd/sfx/sound/camera/
## sword_trace/color) — path COMMANDS on tmd tracks DO play, since C1.5
## (see _arm_path/_update_paths).
##
## Effect-model wrappers reuse the warp-puff shape from ytlevel's
## warp_effects.gd: a Node3D running prop_lighting.gd (ported verbatim,
## see prop_lighting.gd's ADAPTATION note for the one ytavatar-specific
## change) with `anim_one_shot` meta, wrapping the instantiated GLB.

signal finished(code: String)

const PROP_LIGHTING_SCRIPT: Script = preload("res://scripts/prop_lighting.gd")
const CATALOG_PATH := "res://assets/effects/skills.json"
const MODELS_DIR := "res://assets/effects/models/effects/"
const SOUNDS_DIR := "res://assets/sounds/"
## Track kinds _run_command refuses to play. No track ever has kind "path"
## (catalog track kinds: motion/tmd/sfx/sound/camera/sword_trace/color) —
## a "path" entry here was dead-weight cleanup, not a real deferral; path
## COMMANDS live on tmd tracks and have played since C1.5 (_arm_path/
## _update_paths), so removing "path" changes no behavior.
const DEFERRED_KINDS := ["sfx", "camera", "sword_trace"]
## Result codes for play_ex(): why a play request did or didn't start.
## play() (unchanged signature/behavior for existing callers) is just
## `play_ex(...) == PlayResult.OK`.
enum PlayResult { OK, UNKNOWN, MISSING_ASSETS, NO_CHARACTER }
## Role bits in the high byte of a motion/tmd track's
## character_type / base_character: ACTOR/TARGET/OTHER/WORLD. Non-actor
## roles route to the target dummy set via set_target() (C1.5); with no
## dummy set they skip, as before (see _run_motion_command/_bind_wrapper).
const ROLE_ACTOR := 0x100
## Failsafe teardown for a skill that never satisfies the natural-finish
## condition (an effect model whose AnimationPlayer never reports finished —
## missing clip, import hiccup — or a skill with no wrapper to hang the
## condition on at all). Same constant/pattern as warp_effects.gd's MAX_LIFETIME.
const MAX_LIFETIME := 4.0

var _catalog: Dictionary = {}  # code -> catalog entry
## Bones-lookup view used by _bind_wrapper (bone_name(bone_id)); a
## data-only load of the three skills.json/weapons.json/bones.json files
## alongside SkillPlayer's own catalog read is cheap, and avoids a second
## reader class for just bone names.
var _catalog_view := SkillCatalog.new()

var _playing := false
var _code := ""
var _character: Node3D = null
var _fps := 30.0
var _tracks: Array = []
var _time := 0.0
var _fired: Dictionary = {}  # "track_idx:cmd_idx" -> true
## Monotonic session id, bumped on every play(). Anything that can outlive
## a session (the failsafe SceneTreeTimer today, and any future async
## callback) captures the session id it belongs to and no-ops if the
## current session has since moved on — replaying/chaining skills within
## MAX_LIFETIME of a prior play() must not let that prior session's
## failsafe kill the new one (fix round 1 finding 2).
var _session := 0
## Last frame at which ANY command exists across every track. Natural
## finish waits for max(this, the catalog's own "frames" field) — NOT
## this alone: a skill whose last authored event is a color flash or a
## sound (~50% of the fleet) must hold that state on screen at least until
## the catalog's declared playback length elapses, or _maybe_finish would
## apply-then-instantly-revert the terminal effect in the same tick (fix
## round 1 finding 1). "frames" alone isn't enough either — sk100001's
## commands all fire at frame 0 but its spawned effect has its own
## 30-frame/1s one-shot clip (its .anim.json sidecar) that must finish
## playing before teardown, which _pending_wrappers below still guards.
var _max_command_frame := 0
## Catalog "frames" field for the currently-playing skill (see
## _max_command_frame's note on why both bounds are needed).
var _catalog_frames := 0
## Spawned effect wrappers still mid-animation; natural finish waits for
## both "every command has fired" AND "every spawned effect finished
## playing" (B's warp_effects.gd per-puff animation_finished pattern,
## generalized to the whole skill's wrapper set).
var _pending_wrappers := 0

var _wrappers: Array = []          # spawned effect-model wrapper nodes
var _track_wrappers: Dictionary = {}  # tmd track idx -> wrapper Node3D
var _track_offsets: Dictionary = {}   # tmd track idx -> {offset, rot, bone, role, inherit_rot}
var _sound_players: Array = []

## Active flight paths: tmd track idx -> {path: SkillPath, t0: float,
## play_time: float}. An active path REPLACES the track wrapper's
## anchoring each frame (the original swaps the whole component matrix
## for the path pose while a path is set) and holds the end pose after
## play_time (dt clamps). Cleared by stop().
var _track_paths: Dictionary = {}
var _skill_paths: Array = []   # catalog "paths" for the playing skill

## Glow-loop state: an independent minimal runner alongside the one-shot
## session above (never a second full session — glow skills are tmd-only,
## frame-0 commands, e.g. sk610011 has 1 track / play+base at frame 0).
## stop()/_finish() (one-shot teardown) must never touch this, and
## stop_loop() must never touch one-shot state — a one-shot playing over
## an active glow must not kill the glow, and vice versa.
var _loop_code := ""
var _loop_character: Node3D = null
var _loop_tracks: Array = []
var _loop_wrappers: Array = []

## C1.5 target dummy (TargetDummy or duck-typed equivalent). Nullable;
## null preserves pre-C1.5 behavior exactly (target/other roles skip).
## Freed-instance safe: every consumer checks is_instance_valid.
var _target: Node = null


func set_target(dummy: Node) -> void:
	_target = dummy


## Bones a `_bind_wrapper` actor-role lookup wanted but the character's
## get_bone_attachment() returned null for — warned once each (spec §6
## "missing bone → root + one warning per bone"), never for bone 11/Local
## or non-actor roles (those never reach the lookup at all).
var _warned_bones: Dictionary = {}

var _color_stash: Array = []       # [{mesh, surface, orig_override, src}]
var _flash_shaders: Dictionary = {}  # source shader RID id -> derived Shader

## Active color-lerp state — a port of the original client's color
## track. A color command's `self` material is the
## LERP START and its `target` material is the LERP END, interpolated over
## `total_frame/fps` seconds — never an instant snap. Ambient.rgb and
## Diffuse.rgba are the only channels the original interpolates (Ambient
## alpha is decoded but dead — the original client explicitly skips it, kept
## dead here too); Diffuse.rgb is white in 100% of the shipped catalog
## (self AND target, all 910 color commands), so in practice only Ambient's
## rgb tint and Diffuse's alpha fade ever move. 401/910 color commands
## across 267 skills fade Diffuse.alpha — this IS the dominant authored
## use (character transparency), not the ambient tint the pre-fix code
## alone applied.
var _color_active := false
var _color_dt := 0.0
var _color_total_time := 0.0
var _color_start_ambient := Color(0.7, 0.7, 0.7, 1.0)
var _color_end_ambient := Color(0.7, 0.7, 0.7, 1.0)
var _color_start_diffuse := Color(1, 1, 1, 1)
var _color_end_diffuse := Color(1, 1, 1, 1)


func load_catalog() -> void:
	var text := FileAccess.get_file_as_string(CATALOG_PATH)
	var parsed: Variant = JSON.parse_string(text)
	if parsed is Dictionary and parsed.get("skills") is Dictionary:
		_catalog = parsed["skills"]
	else:
		_catalog = {}
	_catalog_view.load()


func skill_ids() -> PackedStringArray:
	var ids := PackedStringArray(_catalog.keys())
	ids.sort()
	return ids


func skill_info(code: String) -> Dictionary:
	return _catalog.get(code, {})


func play(code: String, character: Node3D) -> bool:
	return play_ex(code, character) == PlayResult.OK


func play_ex(code: String, character: Node3D) -> int:
	## Same entry as play(), but reports WHY a play request refused instead
	## of a bare bool. Order matters: an unknown/errored catalog entry is
	## UNKNOWN even when character is also null; a resolvable entry with
	## unresolved asset ref(s) is MISSING_ASSETS even against a valid
	## character; only a fully-playable entry checks the character last.
	var info: Dictionary = _catalog.get(code, {})
	if info.is_empty() or info.has("error"):
		return PlayResult.UNKNOWN
	if not (info.get("missing", []) as Array).is_empty():
		return PlayResult.MISSING_ASSETS  # unresolvable asset ref(s) — refuse rather than play a hole
	if character == null:
		return PlayResult.NO_CHARACTER
	stop()
	_session += 1
	var session := _session
	_code = code
	_character = character
	_fps = float(info.get("fps", 30.0))
	if _fps <= 0.0:
		_fps = 30.0
	_tracks = info.get("tracks", [])
	_skill_paths = info.get("paths", [])
	_track_paths.clear()
	_catalog_frames = int(info.get("frames", 0))
	_time = 0.0
	_fired.clear()
	_track_wrappers.clear()
	_track_offsets.clear()
	_pending_wrappers = 0
	_max_command_frame = 0
	for track in _tracks:
		for cmd in (track as Dictionary).get("commands", []):
			_max_command_frame = maxi(_max_command_frame, int((cmd as Dictionary).get("frame", 0)))
	# stop() above already restored/cleared any prior session's color stash;
	# also drop the prior session's lerp STATE so a new skill with no color
	# track at all can't inherit a stale in-flight fade from the last one.
	_color_active = false
	_color_dt = 0.0
	_playing = true
	set_process(true)
	# Frame-0 commands (e.g. the effect-model spawn) fire synchronously here
	# so a caller sees the spawned wrapper immediately after play() returns,
	# not one process tick later.
	_run_due_commands()
	get_tree().create_timer(MAX_LIFETIME).timeout.connect(_on_failsafe_timeout.bind(session))
	return PlayResult.OK


func current_frame() -> int:
	return int(floor(_fps * _time)) if _playing else -1


func _on_failsafe_timeout(session: int) -> void:
	if session != _session:
		return  # a later play() has since started a new session — not ours to kill
	_finish()


func stop() -> void:
	## Immediate teardown: frees every spawned wrapper/sound and restores
	## character materials bit-exact, whether or not the skill finished.
	_playing = false
	set_process(false)
	for w in _wrappers:
		if is_instance_valid(w):
			w.queue_free()
	_wrappers.clear()
	_track_wrappers.clear()
	_track_paths.clear()
	for s in _sound_players:
		if is_instance_valid(s):
			s.queue_free()
	_sound_players.clear()
	_restore_colors()
	_code = ""
	_character = null


func play_loop(code: String, character: Node3D) -> bool:
	## Glow loop: an independent minimal runner alongside the one-shot
	## session, deliberately NOT a second full session — glow skills are
	## tmd-only, frame-0 commands (sk610011: 1 track / play+base at frame
	## 0). Spawns its own wrapper(s) once and leaves them to force-loop via
	## their own AnimationPlayer/PropAnimator (no anim_one_shot meta —
	## see _spawn_effect_wrapper/_spawn_loop_wrappers).
	stop_loop()
	var info: Dictionary = _catalog.get(code, {})
	if info.is_empty() or info.has("error") or character == null:
		return false
	if not (info.get("missing", []) as Array).is_empty():
		return false
	_loop_code = code
	_loop_character = character
	_loop_tracks = info.get("tracks", [])
	_spawn_loop_wrappers()
	return true


func stop_loop() -> void:
	## Loop-only teardown — must NOT touch one-shot state (_playing, _code,
	## _character, _wrappers, ...), symmetric to stop() not touching loop
	## state.
	for w in _loop_wrappers:
		if is_instance_valid(w):
			w.queue_free()
	_loop_wrappers.clear()
	_loop_tracks = []
	_loop_code = ""
	_loop_character = null


func is_looping() -> bool:
	return not _loop_code.is_empty()


func _spawn_loop_wrappers() -> void:
	## Reuses the tmd spawn path (_spawn_effect_wrapper), but records
	## wrappers in _loop_wrappers instead of _wrappers/_track_wrappers, and
	## skips the anim_one_shot meta + animation_finished bookkeeping
	## entirely — a loop has no pending-wrapper/finish concept, and OMITTING
	## anim_one_shot (rather than setting it false) is what makes the
	## effect's own rangeless timeline force-loop (prop_animator's
	## rangeless-loop rule).
	for track_v in _loop_tracks:
		var track: Dictionary = track_v
		if String(track.get("kind", "")) != "tmd":
			continue
		var has_play := false
		var off: Dictionary = {"offset": Vector3.ZERO, "rot": Vector3.ZERO,
				"bone": 11, "role": ROLE_ACTOR, "inherit_rot": true}
		for cmd_v in (track.get("commands", []) as Array):
			var cmd: Dictionary = cmd_v
			var cmd_kind := String(cmd.get("kind", ""))
			if cmd_kind == "play":
				has_play = true
			elif cmd_kind == "base":
				# sk610011's base command runs at spawn time (frame 0):
				# apply it before "play" spawns rather than waiting for a
				# per-frame clock the loop doesn't run.
				var params: Dictionary = cmd.get("params", {})
				off = {
					"offset": _vec3_from(params.get("offset", [])),
					"rot": _vec3_from(params.get("rot", [])),
					"bone": int(params.get("base_bone", 11)),
					"role": int(params.get("base_character", ROLE_ACTOR)),
					"inherit_rot": bool(params.get("inherit_rot", true)),
				}
		if not has_play:
			continue
		var wrapper := _spawn_effect_wrapper(String(track.get("name", "")))
		if wrapper == null:
			continue
		add_child(wrapper)
		_loop_wrappers.append(wrapper)
		_bind_wrapper(wrapper, off, _loop_character)


func _process(delta: float) -> void:
	if not _playing:
		return
	_time += delta
	_run_due_commands()
	_update_paths()
	_update_color(delta)
	_maybe_finish()


func _maybe_finish() -> void:
	if not _playing:
		return
	var frame := int(floor(_fps * _time))
	var hold_until := maxi(_max_command_frame, _catalog_frames)
	if frame >= hold_until and _pending_wrappers <= 0:
		_finish()


func _on_wrapper_animation_finished(_anim_name: StringName, session: int) -> void:
	if session != _session:
		return  # a stale signal from a queue_free()'d prior-session wrapper
	_pending_wrappers = maxi(0, _pending_wrappers - 1)
	_maybe_finish()


func _finish() -> void:
	if not _playing:
		return  # already torn down (natural finish beat the failsafe timer)
	var code := _code
	stop()
	finished.emit(code)


func _run_due_commands() -> void:
	## One 30 fps clock per playing skill: fire each command whose frame has
	## been crossed exactly once (tracked in _fired by track/command index,
	## not by frame number, so out-of-order or duplicate frames stay exact).
	var frame := int(floor(_fps * _time))
	for ti in range(_tracks.size()):
		var track: Dictionary = _tracks[ti]
		var commands: Array = track.get("commands", [])
		for ci in range(commands.size()):
			var cmd: Dictionary = commands[ci]
			if int(cmd.get("frame", 0)) > frame:
				continue
			var key := "%d:%d" % [ti, ci]
			if _fired.has(key):
				continue
			_fired[key] = true
			_run_command(ti, track, cmd)


func _run_command(ti: int, track: Dictionary, cmd: Dictionary) -> void:
	var kind: String = track.get("kind", "")
	if kind in DEFERRED_KINDS:
		# sfx/camera/sword_trace: cataloged, not played (C2/C3). This also
		# drops any "path" COMMAND riding an sfx track (80/102 shipped path
		# commands do) — behaviorally correct today since sfx tracks spawn
		# no wrapper until C2, so there is nothing to fly yet. When C2 adds
		# sfx wrappers, they get path flight for free through this same
		# tmd-track machinery (_arm_path/_update_paths) — no new code needed.
		return
	match kind:
		"tmd":
			_run_tmd_command(ti, track, cmd)
		"sound":
			_run_sound_command(track, cmd)
		"motion":
			_run_motion_command(track, cmd)
		"color":
			_run_color_command(cmd)
		_:
			pass  # unknown/future kind — never crash


# === tmd track: effect-model spawn + bind ===

func _run_tmd_command(ti: int, track: Dictionary, cmd: Dictionary) -> void:
	var cmd_kind: String = cmd.get("kind", "")
	if cmd_kind == "base":
		# base command: {offset, rot, base_bone, base_character, inherit_pos,
		# inherit_rot} — base_bone/base_character select the anchor
		# (_bind_wrapper's ROLE_ACTOR + real-bone rule); inherit_pos is not
		# consulted (glyph coverage TODO, no shipped skill needs it yet).
		var params: Dictionary = cmd.get("params", {})
		var offset := _vec3_from(params.get("offset", []))
		var rot := _vec3_from(params.get("rot", []))
		var bone_id := int(params.get("base_bone", 11))
		var role := int(params.get("base_character", ROLE_ACTOR))
		var inherit_rot := bool(params.get("inherit_rot", true))
		_track_offsets[ti] = {"offset": offset, "rot": rot, "bone": bone_id,
				"role": role, "inherit_rot": inherit_rot}
		if _track_wrappers.has(ti):
			_bind_wrapper(_track_wrappers[ti], _track_offsets[ti])
		return
	if cmd_kind == "path":
		_arm_path(ti, cmd)
		return
	if cmd_kind != "play":
		return  # unrecognized tmd command — ignore, never crash

	var wrapper := _spawn_effect_wrapper(String(track.get("name", "")))
	if wrapper == null:
		return
	wrapper.set_meta("anim_one_shot", true)
	add_child(wrapper)

	_wrappers.append(wrapper)
	_track_wrappers[ti] = wrapper
	var off: Dictionary = _track_offsets.get(ti, {"offset": Vector3.ZERO, "rot": Vector3.ZERO,
			"bone": 11, "role": ROLE_ACTOR, "inherit_rot": true})
	_bind_wrapper(wrapper, off)

	# prop_lighting.gd's _ready() (material swap + PropAnimator spawn) has
	# already run synchronously by this point — add_child() calls _ready()
	# immediately for a child added under a node already inside the tree
	# (same assumption warp_effects.gd's _spawn makes right after its own
	# add_child(wrapper)) — so the AnimationPlayer, if any, is findable now.
	var player: AnimationPlayer = null
	for c in wrapper.find_children("*", "AnimationPlayer", true, false):
		player = c as AnimationPlayer
		break
	if player != null:
		_pending_wrappers += 1
		player.animation_finished.connect(_on_wrapper_animation_finished.bind(_session))


func _spawn_effect_wrapper(name: String) -> Node3D:
	## Shared effect-model instantiate for both the one-shot tmd path above
	## and the glow loop path (_spawn_loop_wrappers): GLB load + prop_lighting
	## wrap + sun meta. Returns an UNPARENTED wrapper — the caller sets any
	## extra meta (anim_one_shot for one-shots; loops set none, so the
	## effect's own rangeless timeline force-loops) and calls add_child()
	## itself, since prop_lighting.gd reads meta synchronously in _ready(),
	## which only fires once the wrapper is added under a node already in
	## the tree.
	if name.is_empty():
		return null
	var glb_path := "%s%s.glb" % [MODELS_DIR, name.get_basename()]
	if not ResourceLoader.exists(glb_path):
		return null  # missing/broken effect model ref — skip, do not crash

	# PLAIN load(), not preload/threaded — safe ONLY because the avatar
	# tool loads everything synchronously today (no threaded neighbor
	# prefetch like ytlevel's map_host). ytlevel hit a main-thread deadlock
	# mixing sync load() with an in-flight ResourceLoader.load_threaded_*
	# request for a shared subresource (map_host hardening 2026-07-26;
	# warp_effects.gd's 2026-08-12 "screen froze at the portal" report is
	# the same class of bug at play time). If this tool ever grows threaded
	# scene loading, revisit this load() via
	# ResourceLoader.load_threaded_request/get exactly as that fix did.
	var packed := load(glb_path) as PackedScene
	if packed == null:
		return null

	var wrapper := Node3D.new()
	wrapper.name = "SkillFx_%s" % name.get_basename()
	wrapper.set_meta("sun_direction", Vector3(0, -1, 0))
	wrapper.set_meta("sun_diffuse", Color(1, 1, 1))
	wrapper.set_meta("sun_ambient", Color(1, 1, 1))
	wrapper.set_script(PROP_LIGHTING_SCRIPT)
	wrapper.add_child(packed.instantiate())
	return wrapper


func _bind_wrapper(wrapper: Node3D, off: Dictionary, target_character: Node3D = null) -> void:
	## Anchor rule (the original client's base-command handling): actor-role commands with a
	## real bone (id != 11 Local) ride the skeleton bone; inherit_rot=false
	## keeps the wrapper world-aligned at the bone's position. Non-actor
	## roles with a target dummy set (C1.5) ride the DUMMY's bone the same
	## way, resolved through the dummy's own get_bone_attachment() (one
	## interface — a monster dummy's null/no-skeleton case falls back to
	## its root exactly like a boneless character does today). Local/no-
	## dummy/no-bones cases stay character-root-relative as before.
	##
	## target_character lets a caller bind against a character OTHER than
	## the one-shot session's own _character — used by the glow-loop path
	## (_spawn_loop_wrappers passes _loop_character): a loop and a one-shot
	## can run concurrently against different characters (or no one-shot at
	## all, leaving _character null), so reading _character unconditionally
	## here would either bind the loop to the wrong node or drop it
	## whenever no one-shot happens to be active. Defaults to _character so
	## both existing one-shot call sites are unchanged two-argument calls.
	var character: Node3D = target_character if target_character != null else _character
	var role := int(off.get("role", ROLE_ACTOR))
	# An explicitly passed target_character (the glow-loop path's
	# _loop_character) always wins over the dummy — the dummy override
	# below only applies to the one-shot session's own _character, so a
	# future non-actor-role loop/glow base command can never have its
	# explicit loop character silently discarded in favor of the dummy
	# (fix round 1, code review finding).
	var use_dummy := target_character == null and role & ROLE_ACTOR == 0 \
			and _target != null and is_instance_valid(_target) \
			and _target.has_method("root") and _target.root() != null
	if use_dummy:
		# Non-actor base command with a dummy set: anchor on the dummy
		# (C1.5). All non-actor roles (0x200/0x400/0x800) share the one
		# dummy — deliberate single-dummy simplification (spec §4).
		character = _target.root()
	if character == null or not is_instance_valid(character):
		return
	var offset: Vector3 = off.get("offset", Vector3.ZERO)
	var rot: Vector3 = off.get("rot", Vector3.ZERO)
	var bone_id := int(off.get("bone", 11))
	var bone_name := _catalog_view.bone_name(bone_id)
	if use_dummy and not bone_name.is_empty() and _target.has_method("get_bone_attachment"):
		var att: BoneAttachment3D = _target.get_bone_attachment(bone_name)
		if att != null:
			if wrapper.get_parent() != att:
				wrapper.get_parent().remove_child(wrapper)
				att.add_child(wrapper)
			if bool(off.get("inherit_rot", true)):
				wrapper.transform = Transform3D(Basis.from_euler(rot), offset)
			else:
				wrapper.position = offset
				wrapper.global_transform.basis = Basis.from_euler(rot)
			return
		elif not _warned_bones.has(bone_name):
			_warned_bones[bone_name] = true
			push_warning("SkillPlayer: missing bone attachment '%s' — falling back to character root" % bone_name)
	elif role & ROLE_ACTOR != 0 and not bone_name.is_empty() \
			and character.has_method("get_bone_attachment"):
		var att: BoneAttachment3D = character.get_bone_attachment(bone_name)
		if att != null:
			if wrapper.get_parent() != att:
				wrapper.get_parent().remove_child(wrapper)
				att.add_child(wrapper)
			if bool(off.get("inherit_rot", true)):
				wrapper.transform = Transform3D(Basis.from_euler(rot), offset)
			else:
				wrapper.position = offset
				wrapper.global_transform.basis = Basis.from_euler(rot)
			return
		elif not _warned_bones.has(bone_name):
			_warned_bones[bone_name] = true
			push_warning("SkillPlayer: missing bone attachment '%s' — falling back to character root" % bone_name)
	# fallback: character-root binding (pre-C1 behavior)
	var char_xform: Transform3D = character.global_transform
	wrapper.global_transform = Transform3D(
			char_xform.basis * Basis.from_euler(rot),
			char_xform.origin + char_xform.basis * offset)


func _arm_path(ti: int, cmd: Dictionary) -> void:
	## Path command: bake the flight frame at
	## COMMAND time from the live caster/dummy poses, then drive the
	## track's wrapper from _process. Base frame quirk ported: root
	## ORIENTATION with base-BONE position.
	var params: Dictionary = cmd.get("params", {})
	var pid := int(params.get("path_id", -1))
	if pid < 0 or pid >= _skill_paths.size():
		return  # dangling path id — no-op (spec §7)
	var pd: Dictionary = _skill_paths[pid]
	var path := SkillPath.from_catalog(pd)
	if path == null:
		return
	if _character == null or not is_instance_valid(_character):
		return
	var base_pos := _anchor_pos(_character, int(pd.get("base_bone", 11)))
	var base_basis: Basis = _character.global_transform.basis
	var target_pos: Variant = null
	var tchar := int(pd.get("target_character", 0))
	if tchar != 0 and _target != null and is_instance_valid(_target) \
			and _target.has_method("root") and _target.root() != null:
		target_pos = _anchor_pos(_target.root(), int(pd.get("target_bone", 11)))
	path.bake(base_pos, base_basis, target_pos)
	_track_paths[ti] = {"path": path, "t0": _time,
			"play_time": maxf(0.0, float(params.get("play_time", 0.0)))}


func _anchor_pos(character: Node3D, bone_id: int) -> Vector3:
	## Bone position for the path frame (orientation always comes from the
	## character root — the original's non-Local-bone quirk).
	var bone_name := _catalog_view.bone_name(bone_id)
	if bone_id != 11 and not bone_name.is_empty() \
			and character.has_method("get_bone_attachment"):
		var att: BoneAttachment3D = character.get_bone_attachment(bone_name)
		if att != null:
			return att.global_position
	return character.global_position


func _update_paths() -> void:
	for ti in _track_paths:
		var wrapper: Node3D = _track_wrappers.get(ti)
		if wrapper == null or not is_instance_valid(wrapper):
			continue
		var st: Dictionary = _track_paths[ti]
		var play_time: float = st["play_time"]
		var dt: float = _time - float(st["t0"])
		var t := 1.0 if play_time <= 0.0 else clampf(dt / play_time, 0.0, 1.0)
		wrapper.global_transform = (st["path"] as SkillPath).sample(t)


func _vec3_from(arr: Variant) -> Vector3:
	if arr is Array and arr.size() >= 3:
		return Vector3(float(arr[0]), float(arr[1]), float(arr[2]))
	return Vector3.ZERO


# === sound track ===

func _run_sound_command(track: Dictionary, cmd: Dictionary) -> void:
	if String(cmd.get("kind", "")) != "play":
		return
	var name: String = track.get("name", "")
	if name.is_empty():
		return
	var snd_path := "%s%s" % [SOUNDS_DIR, name]
	if not ResourceLoader.exists(snd_path):
		return  # missing sound ref — skip, do not crash
	var stream := load(snd_path) as AudioStream
	if stream == null:
		return
	var player := AudioStreamPlayer3D.new()
	player.stream = stream
	add_child(player)
	if _character != null and is_instance_valid(_character):
		player.global_position = _character.global_position
	_sound_players.append(player)
	player.play()


# === motion track ===

func _run_motion_command(track: Dictionary, cmd: Dictionary) -> void:
	## Actor motion by INTEGER motion id (the original's only in-game path —
	## the lib-name string is editor-only, dropped by the game's bridge).
	## Target/other-role motion tracks (monster hit reactions) route to the
	## target dummy via `_target.play_hit()` when one is set (C1.5); with
	## no dummy set they skip, same as pre-C1.5.
	if String(cmd.get("kind", "")) != "play":
		return
	if _character == null or not is_instance_valid(_character):
		return
	var ctype := int((track.get("params", {}) as Dictionary).get("character_type", 0))
	if ctype & ROLE_ACTOR == 0:
		# Target/other role: route the hit reaction to the dummy if one is
		# set (C1.5); without a dummy, skip — pre-C1.5 behavior.
		if _target != null and is_instance_valid(_target) and _target.has_method("play_hit"):
			var tmid := int((track.get("params", {}) as Dictionary).get("motion_id", -1))
			if tmid >= 0:
				_target.play_hit(tmid)
		return
	if not _character.has_method("play_motion_id"):
		return  # no motion-id API (test stub) — also the missing-motion fallback
	var mid := int((track.get("params", {}) as Dictionary).get("motion_id", -1))
	if mid < 0:
		return
	_character.play_motion_id(mid)  # silent false on missing id = original behavior


# === color track: character material flash (original-client port) ===

func _run_color_command(cmd: Dictionary) -> void:
	## Ports the original client's color-command handling: arms a fresh
	## lerp from THIS command's own `self` (start) to `target` (end) over
	## `total_frame/fps` seconds. A skill with several color commands back
	## to back (e.g. sk200012's fade-out-then-hold: frame 0 no-op, frame 20
	## alpha 1->0 over 16 frames, frame 36 a 0-frame no-op hold) restarts
	## the lerp from EACH command's own self/target — never from whatever
	## the previous command left interpolated to.
	if String(cmd.get("kind", "")) != "color":
		return
	var params: Dictionary = cmd.get("params", {})
	var self_mat: Dictionary = params.get("self", {})
	var target_mat: Dictionary = params.get("target", {})
	_color_start_ambient = _color_from(self_mat.get("ambient", []), Color(0.7, 0.7, 0.7, 1.0))
	_color_end_ambient = _color_from(target_mat.get("ambient", []), Color(0.7, 0.7, 0.7, 1.0))
	_color_start_diffuse = _color_from(self_mat.get("diffuse", []), Color(1, 1, 1, 1))
	_color_end_diffuse = _color_from(target_mat.get("diffuse", []), Color(1, 1, 1, 1))
	_color_dt = 0.0
	var total_frame := float(params.get("total_frame", 0))
	_color_total_time = total_frame / _fps if _fps > 0.0 else 0.0
	_color_active = true


func _color_from(arr: Variant, fallback: Color = Color(1, 1, 1, 1)) -> Color:
	if arr is Array and arr.size() >= 4:
		return Color(float(arr[0]), float(arr[1]), float(arr[2]), float(arr[3]))
	if arr is Array and arr.size() >= 3:
		return Color(float(arr[0]), float(arr[1]), float(arr[2]), fallback.a)
	return fallback


func _update_color(delta: float) -> void:
	## Ports the original client's per-frame color update: advance the
	## elapsed timer by this frame's delta, clamp to total_time, derive
	## delta/total_time (or an instant 1.0 when total_time is 0, e.g.
	## sk200012's frame-36 0-frame command).
	## The guard mirrors the original's elapsed<=total check exactly:
	## once dt reaches total_time the branch keeps re-applying the SAME
	## target values every frame — a deliberate hold, not a bug — until a
	## new color command re-arms it or stop() clears the stash.
	if not _color_active or _color_dt > _color_total_time:
		return
	_color_dt += delta
	if _color_dt > _color_total_time:
		_color_dt = _color_total_time
	var t := 1.0
	if _color_total_time > 0.0:
		t = _color_dt / _color_total_time
	var ambient := Color(
			lerpf(_color_start_ambient.r, _color_end_ambient.r, t),
			lerpf(_color_start_ambient.g, _color_end_ambient.g, t),
			lerpf(_color_start_ambient.b, _color_end_ambient.b, t),
			1.0)
	var alpha := lerpf(_color_start_diffuse.a, _color_end_diffuse.a, t)
	_apply_color(ambient, alpha)


func _apply_color(ambient: Color, alpha: float) -> void:
	if _color_stash.is_empty():
		_build_color_stash()
	for entry in _color_stash:
		var mesh: MeshInstance3D = entry["mesh"]
		if not is_instance_valid(mesh):
			continue
		var derived := _color_variant(entry["src"], ambient, alpha)
		if entry["surface"] == -1:
			mesh.material_override = derived
		else:
			mesh.set_surface_override_material(entry["surface"], derived)


func _build_color_stash() -> void:
	## Stash-and-restore is exact: every entry records the SOURCE material
	## (to derive the flash variant from, always the same source, never a
	## previous flash) and the ORIGINAL override slot value to restore to
	## (which may itself be null — restoring clears back to the mesh's own
	## material, same as prop_lighting's stash/restore contract).
	if _character == null or not is_instance_valid(_character):
		return
	for m in _find_mesh_instances(_character):
		var mesh := m as MeshInstance3D
		if mesh == null:
			continue
		if mesh.material_override != null:
			_color_stash.append({
				"mesh": mesh, "surface": -1,
				"orig_override": mesh.material_override,
				"src": mesh.material_override,
			})
			continue
		if mesh.mesh == null:
			continue
		for s in range(mesh.mesh.get_surface_count()):
			var src: Material = mesh.get_active_material(s)
			if src == null:
				continue
			_color_stash.append({
				"mesh": mesh, "surface": s,
				"orig_override": mesh.get_surface_override_material(s),
				"src": src,
			})


func _find_mesh_instances(node: Node) -> Array:
	var out: Array = []
	if node is MeshInstance3D:
		out.append(node)
	for c in node.get_children():
		out.append_array(_find_mesh_instances(c))
	return out


func _restore_colors() -> void:
	for entry in _color_stash:
		var mesh: MeshInstance3D = entry["mesh"]
		if is_instance_valid(mesh):
			if entry["surface"] == -1:
				mesh.material_override = entry["orig_override"]
			else:
				mesh.set_surface_override_material(entry["surface"], entry["orig_override"])
	_color_stash.clear()
	_color_active = false
	_color_dt = 0.0


func _color_variant(src: Material, ambient: Color, alpha: float) -> Material:
	if src is StandardMaterial3D:
		var orig := src as StandardMaterial3D
		var dup := orig.duplicate() as StandardMaterial3D
		dup.albedo_color = Color(orig.albedo_color.r * ambient.r, orig.albedo_color.g * ambient.g,
				orig.albedo_color.b * ambient.b, orig.albedo_color.a * alpha)
		if alpha < 1.0:
			dup.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		return dup
	if src is ShaderMaterial:
		var sm := src as ShaderMaterial
		var dup := sm.duplicate() as ShaderMaterial
		dup.shader = _flash_shader_variant(sm.shader)
		# flash_color packs both lerp outputs into the one vec4 uniform:
		# .rgb is the ambient tint (pre-existing mechanism), .a is the
		# diffuse-alpha fade — the catalog's DOMINANT authored use
		# (401/910 color commands across 267 skills fade diffuse alpha;
		# target diffuse rgb is white fleet-wide, so an rgb-only tint never
		# rendered it).
		dup.set_shader_parameter("flash_color", Color(ambient.r, ambient.g, ambient.b, alpha))
		return dup
	return src  # unknown material type — leave it alone, never crash


func _flash_shader_variant(src: Shader) -> Shader:
	## Derive a flash-carrying variant of a character shader, exactly the
	## prop_animator.gd `_fade_variant` pattern: never write
	## ALPHA_SCISSOR_THRESHOLD in the derived code (standing pitfall — a
	## scissor write forces the opaque pass), and compute rfind("}") AFTER
	## the uniform-declaration replace() since that replace lengthens the
	## string (a stale index lands mid-token). Writing ALPHA at all (even
	## with no explicit blend render_mode) is sufficient: Godot's spatial
	## shader compiler auto-promotes a material that writes ALPHA into the
	## transparent pass unless ALPHA_SCISSOR_THRESHOLD forces it opaque
	## (which this derived code never sets) — so the avatar shader's
	## authored "no transparency, alpha means skin-mask" opaque pass
	## (avatar_character.gd:452-453) only ever gains real blending on this
	## derived variant, only while a color command is actively fading it.
	if src == null:
		return src
	var key := src.get_rid().get_id()
	if _flash_shaders.has(key):
		return _flash_shaders[key]
	var code := src.code
	if code.contains("uniform vec4 flash_color"):
		_flash_shaders[key] = src
		return src  # already a flash variant — deriving again would redefine it
	code = code.replace("shader_type spatial;",
			"shader_type spatial;\nuniform vec4 flash_color : source_color = vec4(1.0);")
	var idx := code.rfind("}")
	if idx == -1:
		_flash_shaders[key] = src
		return src
	code = code.substr(0, idx) + "\tALBEDO *= flash_color.rgb;\n\tALPHA *= flash_color.a;\n" + code.substr(idx)
	var variant := Shader.new()
	variant.code = code
	_flash_shaders[key] = variant
	return variant
