extends SceneTree
## Run: "$GODOT_BIN" --headless --path client --script scripts/tests/test_sfx_graph.gd
## Pins the value-graph evaluation rules of spec §4.3.1: stored c1/c2 are
## the contract, strict `<` walk, last point never selected, single-point
## graph evaluates to its stored c2.

var _fails := 0


func _check(cond: bool, label: String) -> void:
	if cond:
		print("ok: " + label)
	else:
		printerr("FAIL: " + label)
		_fails += 1


func _near(a: float, b: float, eps := 1e-6) -> bool:
	return absf(a - b) <= eps


func _init() -> void:
	# Unequal intervals, DELIBERATELY wrong stored slopes: the evaluator must
	# use c1/c2 verbatim, not the values.
	var g := SfxGraph.from_points([
		[0.0, 10.0, 5.0, 10.0],     # segment 0: 5t + 10
		[0.3, 99.0, -1.0, 2.0],     # segment 1: -t + 2  (value 99 is a decoy)
		[1.0, 7.0, 0.0, 0.0],
	])
	_check(_near(g.value(0.0), 10.0), "t=0 uses segment 0 (c2)")
	_check(_near(g.value(0.2), 11.0), "t=0.2 -> 5*0.2+10")
	_check(_near(g.value(0.3), 11.5), "t exactly on an interior point stays on the PREVIOUS segment (strict <)")
	_check(_near(g.value(0.5), 1.5), "t=0.5 -> -0.5+2 from stored coefficients, value 99 ignored")
	_check(_near(g.value(1.0), 1.0), "t=1 -> segment n-2 (-1+2), last point's zero coefficients never selected")
	_check(_near(g.value(-3.0), 10.0), "t clamps below to 0")
	_check(_near(g.value(7.0), 1.0), "t clamps above to 1")
	_check(_near(g.discrete(0.5), 99.0), "discrete returns the segment start VALUE")
	_check(_near(g.discrete(0.3), 10.0), "discrete boundary is strict too")
	_check(_near(g.max_value(), 99.0), "max_value over stored values")

	var single := SfxGraph.from_points([[0.0, 4.0, 0.0, 0.0]])
	_check(_near(single.value(0.5), 0.0), "single-point graph evaluates to stored c2 (0), NOT its value")
	_check(_near(single.discrete(0.5), 4.0), "single-point discrete returns the value")
	var empty := SfxGraph.from_points([])
	_check(_near(empty.value(0.5), 0.0) and _near(empty.discrete(0.5), 0.0), "empty graph is 0")

	# Real shipped data has graphs whose last point sits BEFORE t=1.0: the
	# strict walk then reaches the last point, whose stored coefficients are
	# 0, so the graph evaluates to 0 past its end.
	var short := SfxGraph.from_points([[0.0, 1.0, 0.0, 1.0], [0.5, 1.0, 0.0, 0.0]])
	_check(_near(short.value(0.25), 1.0), "graph ending before t=1: on-segment value")
	_check(_near(short.value(0.75), 0.0), "graph ending before t=1 evaluates to 0 past its last point (walk reaches the zero-coefficient last point)")

	var neg := g.negated()
	_check(_near(neg.value(0.2), -11.0), "negated flips v, c1 and c2")
	_check(_near(neg.points[1][1], -99.0) and _near(neg.points[1][0], 0.3), "negated keeps time")
	_check(_near(g.value(0.2), 11.0), "negated() does not mutate the source")
	_check(_near(SfxGraph.constant(3.0).value(0.7), 3.0), "constant() convenience")

	print("FAILED: %d" % _fails if _fails else "ALL OK")
	quit(1 if _fails else 0)
