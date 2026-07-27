class_name MapHost
extends Node3D
## Hosts exported map scenes: instances scenes/maps/{code}.tscn, strips the
## standalone-viewer parts (embedded fly camera + map_editor script), keeps
## Terrain/Props/Water/lights intact so their loaders run normally.

signal map_loaded(code: String)

var current_code := ""
var current_map: Node3D = null
var _prefetching: Dictionary = {}   # code -> path with load_threaded_request active
var _draining: Dictionary = {}      # code -> path: evicted but still loading; claim when done


func load_map(code: String) -> bool:
	var path := "res://scenes/maps/%s.tscn" % code
	var scene: PackedScene = null
	if _draining.has(code):   # user stepped back to an evicted-but-loading map
		_prefetching[code] = _draining[code]
		_draining.erase(code)
	if _prefetching.has(code):
		scene = ResourceLoader.load_threaded_get(path) as PackedScene
		_prefetching.erase(code)
	elif ResourceLoader.exists(path):
		# Route through the same threaded pipeline as prefetch. Mixing
		# ResourceLoader.load() with in-flight threaded requests whose scenes
		# share subresources (neighbor maps reference the same prop GLBs)
		# exercises the engine's cross-thread resource-cache paths; keeping
		# every scene load on one pipeline avoids that class of race.
		ResourceLoader.load_threaded_request(path)
		scene = ResourceLoader.load_threaded_get(path) as PackedScene
	if scene == null:
		push_warning("map_host: cannot load %s" % path)
		return false

	if current_map != null:
		current_map.queue_free()
		current_map = null

	var inst := scene.instantiate() as Node3D
	inst.set_script(null)   # map_editor.gd: never runs inside the tool
	var cam := inst.get_node_or_null("Camera3D")
	if cam != null:
		inst.remove_child(cam)   # embedded fly_camera would steal input/current
		cam.free()
	add_child(inst)
	current_map = inst
	current_code = code
	map_loaded.emit(code)
	return true


func get_terrain() -> MeshInstance3D:
	if current_map == null:
		return null
	return current_map.get_node_or_null("Terrain") as MeshInstance3D


func prefetch(codes: Array) -> void:
	for code: String in codes:
		if code == current_code or _prefetching.has(code):
			continue
		if _draining.has(code):
			# Reuse the still-in-flight request instead of stacking a second
			# threaded request on the same path.
			_prefetching[code] = _draining[code]
			_draining.erase(code)
			continue
		var path := "res://scenes/maps/%s.tscn" % code
		if ResourceLoader.exists(path):
			ResourceLoader.load_threaded_request(path)
			_prefetching[code] = path


func release_except(codes: Array) -> void:
	# Bound prefetch retention: claim (and discard) any threaded request for
	# a sibling that isn't in the keep set (typically the current ±1 window)
	# and isn't the live map, so unclaimed PackedScenes don't stay resident
	# forever as we step through levels. Requests still loading are parked in
	# _draining and claimed from _process once done — claiming an in-flight
	# request here would block the main thread mid-travel.
	var keep := {}
	for c: String in codes:
		keep[c] = true
	for code: String in _prefetching.keys():
		if code == current_code or keep.has(code):
			continue
		var path: String = _prefetching[code]
		if ResourceLoader.load_threaded_get_status(path) \
				== ResourceLoader.THREAD_LOAD_IN_PROGRESS:
			_draining[code] = path
		else:
			ResourceLoader.load_threaded_get(path)   # claim + discard
		_prefetching.erase(code)


func _process(_delta: float) -> void:
	for code: String in _draining.keys():
		var path: String = _draining[code]
		if ResourceLoader.load_threaded_get_status(path) \
				!= ResourceLoader.THREAD_LOAD_IN_PROGRESS:
			ResourceLoader.load_threaded_get(path)   # claim + discard
			_draining.erase(code)
