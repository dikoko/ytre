class_name SfxGraph
extends RefCounted
## Value graph of the original particle library (spec §4.3.1): control
## points `[t, v, c1, c2]` over normalized time 0..1. `value()` is the
## piecewise-linear evaluator, `discrete()` the step-function variant used
## for texture frames. The STORED c1/c2 are the contract — the game
## overwrote its own equal-interval recompute with the file's coefficients
## on load, and 73/154 shipped files depend on that (unequal point times).
## A single-point graph therefore evaluates to its stored c2, which the
## original editor always wrote as 0 — not to its value.

var points: Array = []  # Array of [t: float, v: float, c1: float, c2: float]


static func from_points(pts: Array) -> SfxGraph:
	var g := SfxGraph.new()
	for p in pts:
		g.points.append([float(p[0]), float(p[1]), float(p[2]), float(p[3])])
	return g


static func constant(v: float) -> SfxGraph:
	## Test/default convenience: a one-point graph that evaluates to v.
	return from_points([[0.0, v, 0.0, v]])


func _segment(t: float) -> int:
	## Original walk: advance while the NEXT point's time is strictly below t.
	var idx := 0
	while idx + 1 < points.size() and float(points[idx + 1][0]) < t:
		idx += 1
	return idx


func value(t: float) -> float:
	if points.is_empty():
		return 0.0
	t = clampf(t, 0.0, 1.0)
	var p: Array = points[_segment(t)]
	return float(p[2]) * t + float(p[3])


func discrete(t: float) -> float:
	if points.is_empty():
		return 0.0
	t = clampf(t, 0.0, 1.0)
	return float(points[_segment(t)][1])


func max_value() -> float:
	var m := 0.0
	for i in points.size():
		var v := float(points[i][1])
		m = v if i == 0 else maxf(m, v)
	return m


func negated() -> SfxGraph:
	## Z-axis conversion helper (spec §4.4): flips v, c1, c2; keeps t.
	var g := SfxGraph.new()
	for p in points:
		g.points.append([float(p[0]), -float(p[1]), -float(p[2]), -float(p[3])])
	return g
