extends SceneTree
## Run: "$GODOT_BIN" --headless --path client --script scripts/tests/test_sfx_object.gd
## Deterministic simulation checks for SfxObject (spec §6): billboard
## alignment/color/clock here; emitter particles in the second half.

var _fails := 0


func _check(cond: bool, label: String) -> void:
	if cond:
		print("ok: " + label)
	else:
		printerr("FAIL: " + label)
		_fails += 1


func _near(a: float, b: float, eps := 1e-5) -> bool:
	return absf(a - b) <= eps


func _v_near(a: Vector3, b: Vector3, eps := 1e-4) -> bool:
	return a.distance_to(b) <= eps


func _graphs(overrides: Dictionary) -> Dictionary:
	## Every graph an effect can carry, defaulted flat; overrides win.
	var g := {}
	for k in ["opacity", "color_r", "color_g", "color_b", "life_random", "wind_x",
			"width", "height", "particle_opacity"]:
		g[k] = SfxGraph.constant(1.0)
	for k in ["gravity", "wind_y", "wind_z", "wind_force", "drag", "blackhole_x",
			"blackhole_y", "blackhole_z", "blackhole_force", "dir_x", "dir_y", "dir_z",
			"spread", "init_deg", "init_deg_random", "ang_vel", "ang_vel_random"]:
		g[k] = SfxGraph.constant(0.0)
	g["texture_frame"] = SfxGraph.constant(1.0)
	g["life"] = SfxGraph.constant(2.0)
	g["speed"] = SfxGraph.constant(1.0)
	g["rate"] = SfxGraph.constant(10.0)
	g["scale_t"] = SfxGraph.constant(0.5)
	g["scale_n"] = SfxGraph.constant(0.5)
	for k in overrides:
		g[k] = overrides[k]
	return g


func _config(kind: String, overrides := {}, extra := {}) -> Dictionary:
	var c := {
		"kind": kind, "additive": true, "total_time": 1.0, "texture_direction": 0,
		"alignment": 0, "graphs": _graphs(overrides), "atlas": null,
		"rects": [Rect2(0, 0, 1, 1)], "white_rect": Rect2(0, 0, 1, 1), "name_key": "test",
	}
	for k in extra:
		c[k] = extra[k]
	return c


func _make(cfg: Dictionary) -> SfxObject:
	var o := SfxObject.new()
	root.add_child(o)
	o.setup(cfg)
	return o


func _test_billboard() -> void:
	# Camera at (0,0,5) looking down -z at the origin; billboard at origin.
	var cam := Transform3D(Basis.IDENTITY, Vector3(0, 0, 5))
	var bb := _make(_config("billboard", {
		"width": SfxGraph.constant(2.0), "height": SfxGraph.constant(4.0),
		"color_r": SfxGraph.from_points([[0.0, 1.0, -1.0, 1.0], [1.0, 0.0, 0.0, 0.0]]),
		"opacity": SfxGraph.constant(0.5),
	}, {"texture_direction": 1}))
	bb.play()
	_check(bb.playing and _near(bb.relative_time, 0.0), "billboard play resets clock")
	bb.tick(0.25, cam)
	_check(_near(bb.relative_time, 0.25), "clock advances dt/total_time")
	var xf := bb.billboard_transform()
	_check(_v_near(xf.basis.x, Vector3(1, 0, 0)) and _v_near(xf.basis.y, Vector3(0, 2, 0)),
			"VIEWPLANE: local U = cam right * half width, V = cam up * half height")
	# Spec §4.4: the D3D forward N is -basis.z of the Godot camera; a
	# straight-ahead VIEWPOINT billboard must agree with it (checked below).
	_check(_v_near(xf.basis.z, Vector3(0, 0, -1)), "VIEWPLANE: N = camera forward (D3D N = -basis.z)")
	_check(_v_near(xf.origin, Vector3.ZERO), "no camera offset by default")
	var col := bb.billboard_color()
	_check(_near(col.r, floor(0.75 * 255.0) / 255.0, 1e-6), "color r sampled at t=0.25 with 8-bit truncation")
	_check(_near(col.a, floor(0.5 * 255.0) / 255.0, 1e-6), "opacity -> alpha, truncated")
	_check(bb.drawn_instances() == 1, "billboard draws one instance")

	bb.cam_offset = 1.0
	bb.tick(0.0, cam)
	_check(_v_near(bb.billboard_transform().origin, Vector3(0, 0, 1)), "VIEWPLANE offset moves toward the camera")

	# clock clamps and holds at 1
	bb.tick(5.0, cam)
	_check(_near(bb.relative_time, 1.0), "relative time clamps at 1")
	bb.set_total_time(4.0)
	bb.set_time(1.0)
	_check(_near(bb.relative_time, 0.25), "set_time = seconds / total_time")
	bb.set_total_time(0.0)
	bb.tick(1.0, cam)
	_check(_near(bb.relative_time, 0.25), "total_time 0 freezes the clock (original guard)")

	# VIEWPOINT: billboard straight ahead -> identical to viewplane; offset flips sign along n
	var vp := _make(_config("billboard", {}, {"alignment": 1}))
	vp.cam_offset = 1.0
	vp.play()
	vp.tick(0.0, cam)
	var vxf := vp.billboard_transform()
	_check(_v_near(vxf.basis.x.normalized(), Vector3(1, 0, 0)) and _v_near(vxf.basis.z, Vector3(0, 0, -1)),
			"VIEWPOINT straight ahead: U = cam right, N = (pos - cam) normalized")
	_check(_v_near(vxf.origin, Vector3(0, 0, 1)), "VIEWPOINT offset = -cam_offset * n (toward camera)")
	# off-axis: n tilts, U/V follow the verbatim (non-unit, doubled-angle) quaternion
	vp.global_position = Vector3(3, 0, 0)
	vp.tick(0.0, cam)
	var n := (Vector3(3, 0, 0) - cam.origin).normalized()
	var cam_n := Vector3(0, 0, -1)
	var axis := cam_n.cross(n)
	var c := cam_n.dot(n)
	var s := sqrt(1.0 - c * c)
	var q := Quaternion(axis.x * s, axis.y * s, axis.z * s, c)
	# conj spelled out: Quaternion.inverse() asserts normalization in 4.7 and
	# returns identity for this deliberately non-unit q.
	var qu := q * Quaternion(1, 0, 0, 0) * Quaternion(-q.x, -q.y, -q.z, q.w)
	# basis.x is U * half width, and this object's width graph is 1.0.
	var expected_u := Vector3(qu.x, qu.y, qu.z) * 0.5
	_check(_v_near(vp.billboard_transform().basis.x, expected_u, 1e-4), "VIEWPOINT off-axis U follows the verbatim quaternion rotate")
	_check(_v_near(vp.billboard_transform().basis.z, n), "VIEWPOINT N = n")

	bb.stop()
	_check(not bb.playing and _near(bb.relative_time, 0.0), "stop clears clock")
	bb.queue_free()
	vp.queue_free()


func _test_emitter() -> void:
	var cam := Transform3D(Basis.IDENTITY, Vector3(0, 0, 5))
	SfxRandom.load_tables()

	# 1) Rate accumulator: rate 10/s, dt 0.05 -> int(10*0.05)=0 then int(10*0.10)=1:
	#    one particle every second tick; spread 0 and random 0 keep it deterministic.
	SfxRandom.reset()
	var e := _make(_config("emitter_polygon", {
		"rate": SfxGraph.constant(10.0), "dir_y": SfxGraph.constant(1.0),
		"speed": SfxGraph.constant(2.0), "spread": SfxGraph.constant(0.0),
		"life_random": SfxGraph.constant(0.0), "life": SfxGraph.constant(2.0),
		"gravity": SfxGraph.constant(0.0),
	}))
	e.play()
	e.tick(0.05, cam)
	_check(e.particle_count() == 0, "rate: int(10*0.05) = 0 particles, accumulator kept")
	e.tick(0.05, cam)
	_check(e.particle_count() == 1, "rate: accumulator 0.10 -> 1 particle, accumulator reset")
	for i in 18:
		e.tick(0.05, cam)
	_check(e.particle_count() == 10, "rate: 10 particles after 1.0 s at 10/s")
	_check(e.drawn_instances() == 10, "every live particle is drawn")
	var p0: SfxObject.Particle = e.particles()[0]
	_check(_v_near(p0.velocity, Vector3(0, 2, 0)), "spread 0: velocity = dir * speed, unrotated by identity emitter")
	_check(_near(p0.total_life, 2.0), "life_random 0: life = life graph")
	_check(p0.deg == 0 and p0.ang_vel == 0, "no spin by default")
	_check(_near(p0.base_opacity, 255.0) and _near(p0.opacity, 255.0), "opacity = base(255) * particle_opacity(1)")
	_check(p0.texture_id == 0, "texture frame 1 -> id 0")
	e.queue_free()

	# 2) Gravity-only Euler integration: v += g*dt; p += v*dt (in that order).
	SfxRandom.reset()
	var g := _make(_config("emitter_polygon", {
		"rate": SfxGraph.constant(20.0), "dir_y": SfxGraph.constant(0.0),
		"speed": SfxGraph.constant(0.0), "spread": SfxGraph.constant(0.0),
		"life_random": SfxGraph.constant(0.0), "gravity": SfxGraph.constant(10.0),
	}))
	g.play()
	g.tick(0.05, cam)   # spawns 1 particle at the origin (velocity 0)
	_check(g.particle_count() == 1, "gravity case: one particle")
	g.tick(0.1, cam)
	g.tick(0.1, cam)
	var gp: SfxObject.Particle = g.particles()[0]
	# step1: v=(0,-1,0) p=(0,-0.1,0); step2: v=(0,-2,0) p=(0,-0.3,0)
	_check(_v_near(gp.velocity, Vector3(0, -2, 0)) and _v_near(gp.position, Vector3(0, -0.3, 0)),
			"Euler order: velocity first, then position (p=-0.3 after two 0.1 s steps)")
	g.queue_free()

	# 3) Spin: ang_vel 90 deg/s = 16380 units/s; dt 0.5 -> +8190 per tick, wraps at 65536.
	#    A NEGATIVE rate wraps at the float-to-angle conversion into a fast
	#    positive spin (spec §3.4).
	SfxRandom.reset()
	var s := _make(_config("emitter_polygon", {
		"rate": SfxGraph.constant(20.0), "speed": SfxGraph.constant(0.0),
		"spread": SfxGraph.constant(0.0), "life_random": SfxGraph.constant(0.0),
		"ang_vel": SfxGraph.constant(90.0), "init_deg": SfxGraph.constant(350.0),
	}))
	s.play()
	s.tick(0.05, cam)
	var sp: SfxObject.Particle = s.particles()[0]
	_check(sp.ang_vel == 16380 and sp.deg == SfxRandom.deg_units(350.0), "spin units at spawn")
	s.tick(0.5, cam)
	_check(sp.deg == (SfxRandom.deg_units(350.0) + 8190) & 0xFFFF, "deg advances by u16(ang_vel*dt) mod 65536")
	s.queue_free()
	SfxRandom.reset()
	var sn := _make(_config("emitter_polygon", {
		"rate": SfxGraph.constant(20.0), "speed": SfxGraph.constant(0.0),
		"spread": SfxGraph.constant(0.0), "life_random": SfxGraph.constant(0.0),
		"ang_vel": SfxGraph.constant(-90.0),
	}))
	sn.play()
	sn.tick(0.05, cam)
	_check((sn.particles()[0] as SfxObject.Particle).ang_vel == 49156, "negative ang_vel wraps to 49156 (fast positive spin)")
	sn.queue_free()

	# 4) Opacity wrap: opacity graph 1.2 -> base 306 -> int & 0xFF = 50 -> alpha 50/255.
	SfxRandom.reset()
	var o := _make(_config("emitter_polygon", {
		"rate": SfxGraph.constant(20.0), "speed": SfxGraph.constant(0.0),
		"spread": SfxGraph.constant(0.0), "life_random": SfxGraph.constant(0.0),
		"opacity": SfxGraph.constant(1.2),
	}))
	o.play()
	o.tick(0.05, cam)
	var oc := o.instance_color(0)
	_check(_near(oc.a, 50.0 / 255.0, 1e-6), "alpha byte wraps (306 & 0xFF = 50)")
	o.queue_free()

	# 5) Retirement, stop, and the emitter basis rotating spawn velocities.
	SfxRandom.reset()
	var r := _make(_config("emitter_polygon", {
		"rate": SfxGraph.constant(20.0), "dir_x": SfxGraph.constant(1.0),
		"dir_y": SfxGraph.constant(0.0), "speed": SfxGraph.constant(1.0),
		"spread": SfxGraph.constant(0.0), "life_random": SfxGraph.constant(0.0),
		"life": SfxGraph.constant(0.2), "gravity": SfxGraph.constant(0.0),
	}))
	r.global_transform = Transform3D(Basis(Vector3.UP, PI / 2.0), Vector3(1, 2, 3))
	r.play()
	r.tick(0.05, cam)
	var rp: SfxObject.Particle = r.particles()[0]
	_check(_v_near(rp.velocity, Vector3(0, 0, -1)), "spawn velocity rotated by the emitter basis (+x -> -z under 90 deg yaw)")
	_check(_v_near(rp.position, Vector3(1, 2, 3)),
			"first-tick spawn sits at the emitter origin (prev = cur; spawned AFTER aging, so not yet moved)")
	r.tick(0.1, cam)
	r.tick(0.1, cam)
	_check(r.particle_count() >= 1, "particles alive within life")
	r.tick(0.1, cam)  # the first particle is now past 0.2 s
	_check(not r.particles().has(rp), "particle retired when life > total_life")
	r.stop()
	_check(r.particle_count() == 0 and r.drawn_instances() == 0, "stop clears particles")
	r.queue_free()

	# 6) Trail interpolation: a moving emitter spreads a burst between prev and cur.
	SfxRandom.reset()
	var tr := _make(_config("emitter_polygon", {
		"rate": SfxGraph.constant(100.0), "speed": SfxGraph.constant(0.0),
		"spread": SfxGraph.constant(0.0), "life_random": SfxGraph.constant(0.0),
	}))
	tr.play()
	tr.tick(0.05, cam)           # first tick: prev = cur = origin, 5 particles at origin
	tr.global_position = Vector3(10, 0, 0)
	tr.tick(0.05, cam)           # 5 more, spread over 0..10 at i/5
	var xs := []
	for p in tr.particles():
		xs.append(snappedf((p as SfxObject.Particle).position.x, 0.01))
	_check(xs.count(0.0) == 6 and xs.has(2.0) and xs.has(8.0) and not xs.has(10.0),
			"burst spread over prev->cur at i/n (never reaching cur): %s" % [xs])
	tr.queue_free()

	# 7) Non-additive: instances sorted back-to-front (farther from camera first).
	SfxRandom.reset()
	var na := _make(_config("emitter_polygon", {
		"rate": SfxGraph.constant(40.0), "dir_z": SfxGraph.constant(1.0),
		"speed": SfxGraph.constant(1.0), "spread": SfxGraph.constant(0.0),
		"life_random": SfxGraph.constant(0.0), "gravity": SfxGraph.constant(0.0),
	}, {"additive": false}))
	na.play()
	na.tick(0.05, cam)
	na.tick(0.5, cam)
	na.tick(0.05, cam)
	var z_first := na.instance_transform(0).origin.z
	var z_last := na.instance_transform(na.drawn_instances() - 1).origin.z
	_check(z_first < z_last, "non-additive draw order is back-to-front (camera at +z: smallest z drawn first)")
	na.queue_free()

	# 8) Velocity-aligned quads when texture_direction != NONE.
	SfxRandom.reset()
	var va := _make(_config("emitter_polygon", {
		"rate": SfxGraph.constant(20.0), "dir_x": SfxGraph.constant(0.0),
		"dir_y": SfxGraph.constant(1.0), "speed": SfxGraph.constant(3.0),
		"spread": SfxGraph.constant(0.0), "life_random": SfxGraph.constant(0.0),
		"gravity": SfxGraph.constant(0.0), "scale_t": SfxGraph.constant(0.5), "scale_n": SfxGraph.constant(0.25),
	}, {"texture_direction": 1}))
	va.play()
	va.tick(0.05, cam)
	var vb := va.instance_transform(0).basis
	_check(_v_near(vb.x, Vector3(0, 0.5, 0)) and _v_near(vb.y, Vector3(-0.25, 0, 0)),
			"TOP direction: U aligns with the velocity's screen projection (up), V = perpendicular")
	va.queue_free()


func _init() -> void:
	await process_frame
	_test_billboard()
	_test_emitter()
	print("FAILED: %d" % _fails if _fails else "ALL OK")
	quit(1 if _fails else 0)
