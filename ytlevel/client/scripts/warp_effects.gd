class_name WarpEffects
extends Node3D
## Portal warp effects: the vanish puff + sound on depart, the materialize
## puff + sound on arrival — a port of the sk100001-04 warp skill family
## (depart = sfx_mon_dead1_small, arrive = sfx_ava_spwan1_small; indoor vs
## outdoor changes only the sound). The effect plays ONCE at the avatar's
## transform on its own 30 fps timeline, all surfaces additive — exactly the
## machinery the animated-prop runtime already provides, so each puff is the
## GLB wrapped in a prop_lighting node with anim_one_shot set.

## PRELOADED, not load()-ed at play time: puffs spawn exactly when
## load_level has threaded neighbor prefetches in flight, and a sync load()
## concurrent with those is the documented engine cache race (map_host
## hardening 2026-07-26) — it can deadlock the main thread, which reads as
## "the screen froze at the portal" (2026-08-12 report). preload resolves
## while level_tool loads at startup, before any threaded map op exists.
const DEPART_SCENE: PackedScene = preload("res://assets/props/models/skillfx/sfx_mon_dead1_small.glb")
const ARRIVE_SCENE: PackedScene = preload("res://assets/props/models/skillfx/sfx_ava_spwan1_small.glb")
const SND_INDOOR: AudioStream = preload("res://assets/sounds/etc_warp_indoor.wav")
const SND_OUTDOOR: AudioStream = preload("res://assets/sounds/etc_warp_outdoor.wav")
const PROP_LIGHTING: Script = preload("res://scripts/prop_lighting.gd")
## Failsafe teardown for a puff whose AnimationPlayer never reports finished
## (missing clip, import hiccup) — comfortably past the longest timeline (2 s).
const MAX_LIFETIME := 4.0

var _sun: Dictionary = {}


func clear() -> void:
	## Kill in-flight puffs — called on map swap so a depart puff cannot
	## linger at stale coordinates inside the destination map.
	for c in get_children():
		c.queue_free()


func set_sun(sun: Dictionary) -> void:
	## Same sun dictionary the portal markers receive; the puff is additive
	## everywhere so the sun barely shows, but the wrapper still wants it.
	_sun = sun


func play_depart(at: Transform3D, map_code: String) -> void:
	_spawn(DEPART_SCENE, at, map_code)


func play_arrive(at: Transform3D, map_code: String) -> void:
	_spawn(ARRIVE_SCENE, at, map_code)


static func is_indoor(map_code: String) -> bool:
	## VIEWER HEURISTIC, not a port: the original picks indoor/outdoor
	## server-side. School grounds (SF*/LW*) read as outdoor, field/dungeon
	## interiors (FD* and everything else) as indoor.
	return not (map_code.begins_with("SF") or map_code.begins_with("LW"))


func _spawn(packed: PackedScene, at: Transform3D, map_code: String) -> void:
	if packed == null:
		return
	var wrapper := Node3D.new()
	wrapper.name = "WarpPuff"
	wrapper.set_meta("sun_direction", _sun.get("direction", Vector3(0, -1, 0)))
	wrapper.set_meta("sun_diffuse", _sun.get("diffuse", Color(1, 1, 1)))
	wrapper.set_meta("sun_ambient", _sun.get("ambient", Color(1, 1, 1)))
	wrapper.set_meta("anim_one_shot", true)
	wrapper.set_script(PROP_LIGHTING)
	wrapper.add_child(packed.instantiate())
	add_child(wrapper)
	# The effect inherits the character's frame (the original client binds
	# skill effects to the caster with zero offsets) — position AND yaw.
	wrapper.global_transform = at

	var sound := AudioStreamPlayer3D.new()
	sound.stream = SND_INDOOR if is_indoor(map_code) else SND_OUTDOOR
	sound.max_distance = 40.0
	wrapper.add_child(sound)
	sound.play()

	# Free when the clip ends; belt-and-braces timer for a puff that never
	# starts (the tween below survives wrapper-freeing safely).
	var player: AnimationPlayer = null
	for c in wrapper.find_children("*", "AnimationPlayer", true, false):
		player = c
	if player != null:
		player.animation_finished.connect(
				func(_n): if is_instance_valid(wrapper): wrapper.queue_free())
	get_tree().create_timer(MAX_LIFETIME).timeout.connect(
			func(): if is_instance_valid(wrapper): wrapper.queue_free())
