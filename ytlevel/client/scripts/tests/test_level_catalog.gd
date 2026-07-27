extends SceneTree
## Headless test: GODOT_BIN --headless --path client --script scripts/tests/test_level_catalog.gd


func _init() -> void:
	var failures := 0
	var cat := LevelCatalog.new()
	failures += _check(cat.load_catalog(), "catalog loads")
	failures += _check(cat.get_groups("schools").size() == 2, "two schools")
	failures += _check(cat.get_groups("episodes").size() > 100, "100+ episode groups")
	var lv := cat.get_level("SF001001")
	failures += _check(lv.get("name", "") == "에스티바 운동장", "SF001001 name")
	failures += _check(lv.get("portals", []).size() == 4, "SF001001 portals")
	failures += _check(cat.display_name("SF001001").contains("SF001001"), "display name")
	failures += _check(cat.is_available("SF001001"), "SF001001 available")
	failures += _check(not cat.is_available("XX999999"), "bogus unavailable")
	print("FAILED: %d" % failures if failures else "ALL OK")
	quit(1 if failures else 0)


func _check(cond: bool, label: String) -> int:
	if not cond:
		printerr("FAIL: " + label)
		return 1
	return 0
