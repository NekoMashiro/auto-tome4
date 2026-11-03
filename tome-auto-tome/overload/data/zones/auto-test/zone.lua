-- Fixed two-level map. Creatures and items are placed by enter_test, not the generator.
return {
	name = "Auto Test",
	level_range = {1, 100},
	max_level = 2,
	width = 40,
	height = 36,
	all_remembered = false,
	all_lited = false,
	persistent = false,
	no_level_connectivity = true,
	no_worldmap = true,
	generator = {
		map = {
			class = "engine.generator.map.Static",
			map = "!level1",
		},
	},
	levels = {
		[1] = {
			generator = {map = {class = "engine.generator.map.Static", map = "!level1"}},
		},
		[2] = {
			width = 10, height = 8,
			generator = {map = {class = "engine.generator.map.Static", map = "!level2"}},
		},
	},
}
