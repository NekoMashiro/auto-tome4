-- World commands call the game directly. They do not press the key the player would press.
local Prompt = require "mod.auto_tome.Prompt"
local M = {}

local DIRECTIONS = {[1] = true, [2] = true, [3] = true, [4] = true, [6] = true, [7] = true, [8] = true, [9] = true}

local function direction_ok(direction)
	return DIRECTIONS[direction] == true
end

local function level_before(game)
	return {
		track_level = true,
		zone = game.zone and (game.zone.short_name or game.zone.name or "") or "",
		level = game.level and game.level.level or 0,
	}
end

local function find_item(player, item_id)
	local want = tostring(item_id or "")
	local function scan(inven, inven_id)
		if type(inven) ~= "table" then return nil end
		for slot, object in ipairs(inven) do
			if type(object) == "table" and "item-" .. tostring(object.uid or 0) == want then
				return object, inven_id or inven, slot
			end
		end
	end
	local backpack = player.getInven and player:getInven("INVEN") or nil
	local object, inven, slot = scan(backpack, player.INVEN_INVEN)
	if object then return object, inven, slot end
	for inven_id, inven in pairs(player.inven or {}) do
		object, inven, slot = scan(inven, inven_id)
		if object then return object, inven, slot end
	end
end

function M.use(game, action)
	local player = game.player
	local id = action.id
	if type(id) ~= "string" or id == "" then return false, "invalid_id" end
	if id:sub(1, 2) == "T_" then
		local talent = player.getTalentFromId and player:getTalentFromId(id) or nil
		if type(talent) ~= "table" or not player:knowTalent(id) then return false, "unknown_talent" end
		if talent.mode ~= "activated" and talent.mode ~= "sustained" then return false, "passive_talent" end
		player:useTalent(id)
		return true
	end
	local object, inven, slot = find_item(player, id)
	if not object then return false, "unknown_item" end
	player:playerUseItem(object, slot, inven)
	return true
end

local function make_object(name, fields)
	local Object = require "mod.class.Object"
	local object = Object.new(fields or {
		name = name,
		type = "misc", subtype = "misc",
		display = "?", color_r = 220, color_g = 180, color_b = 40,
		encumber = 0, identified = true, desc = "Placed by the Auto ToME test.",
	})
	object.name = name
	object.identified = true
	if type(object.resolve) == "function" then
		object:resolve()
		object:resolve(nil, true)
	end
	object.name = name
	object.identified = true
	return object
end

local function stack(name, count)
	local object = make_object(name, {
		name = name, type = "misc", subtype = "misc",
		display = "*", color_r = 180, color_g = 180, color_b = 180,
		encumber = 0, identified = true, stacking = true,
		desc = "A stack used by the Auto ToME test.",
	})
	if count > 1 then
		object.stacked = {}
		for _ = 2, count do
			object.stacked[#object.stacked + 1] = make_object(name, {
				name = name, type = "misc", subtype = "misc",
				display = "*", identified = true, stacking = true, encumber = 0,
			})
		end
	end
	return object
end

local function weapon(name)
	return make_object(name, {
		name = name, type = "weapon", subtype = "dagger",
		display = "|", color_r = 200, color_g = 200, color_b = 200,
		encumber = 1, identified = true, slot = "MAINHAND",
		desc = "A weapon used by the Auto ToME test.",
		combat = {dam = 4, atk = 0, apr = 0, physcrit = 0, dammod = {str = 0.4}},
	})
end

local function salve()
	return make_object("test salve", {
		name = "test salve", type = "misc", subtype = "misc",
		display = "!", color_r = 80, color_g = 200, color_b = 80,
		encumber = 0, identified = true,
		desc = "Rub it.",
		use_simple = {
			name = "rub it",
			use = function(self, who)
				game.logPlayer(who, "The test salve is used.")
				return {used = true, destroy = true}
			end,
		},
	})
end

local function place_actor(game, x, y)
	local NPC = require "mod.class.NPC"
	local player = game.player
	local actor = NPC.new{
		name = "test dummy",
		type = "humanoid", subtype = "human",
		display = "e", color_r = 255, color_g = 40, color_b = 40,
		faction = "enemies",
		level_range = {1, 1},
		max_life = 1, life = 1, life_regen = 0,
		combat = {dam = 1, atk = 0, apr = 0, dammod = {str = 0}},
		combat_armor = 0,
		never_move = 1,
		exp_worth = 0,
		sight = 1,
	}
	if type(actor.resolve) == "function" then
		actor:resolve()
		actor:resolve(nil, true)
	end
	actor.name = "test dummy"
	actor.max_life = 1
	actor.life = 1
	actor.never_move = 1
	actor.exp_worth = 0
	actor.energy = actor.energy or {}
	actor.energy.mod = 0
	actor.energy.value = 0
	pcall(function()
		local Faction = require "engine.Faction"
		local hostile = "auto-tome-hostile"
		if not Faction.factions[hostile] then
			Faction:add{name = "Auto Tome Hostile", short_name = hostile, reaction = {}}
		end
		actor.faction = hostile
		if player.faction then Faction:setFactionReaction(player.faction, hostile, -100, true) end
	end)
	game.zone:addEntity(game.level, actor, "actor", x, y)
	actor.max_life = 1
	actor.life = 1
	actor.energy.mod = 0
	actor.energy.value = 0
	return actor
end

local function setup_level(game)
	local level = game.level
	local player = game.player
	if level.__auto_tome_ready then return true end
	local talent = player.T_AUTO_TOME_BOLT
	if not talent then return false, "test_talent_missing" end
	player:move(2, 2, true)
	place_actor(game, 4, 2)
	local map = level.map
	map:addObject(37, 3, make_object("test gem", {
		name = "test gem", type = "gem", subtype = "white",
		display = "*", color_r = 120, color_g = 220, color_b = 255,
		encumber = 0, identified = true, desc = "A gem used by the Auto ToME test.",
	}))
	map:addObject(37, 3, make_object("test shard", {
		name = "test shard", type = "gem", subtype = "white",
		display = "*", color_r = 180, color_g = 180, color_b = 255,
		encumber = 0, identified = true, desc = "A shard used by the Auto ToME test.",
	}))
	local inven = player:getInven("INVEN")
	player:addObject(inven, salve())
	player:addObject(inven, stack("test pebble", 3))
	local function stash(name)
		local worn = player:getInven(name)
		if type(worn) ~= "table" then return end
		for slot = #worn, 1, -1 do
			local worn_object = player:removeObject(worn, slot)
			if worn_object then player:addObject(inven, worn_object) end
		end
	end
	stash("MAINHAND")
	stash("QS_MAINHAND")
	local blade = weapon("test blade")
	local spare = weapon("test spare")
	local main = player:getInven("MAINHAND")
	local quick = player:getInven("QS_MAINHAND")
	if main then player:addObject(main, blade) end
	if quick then player:addObject(quick, spare) end
	if player.sortInven then player:sortInven(inven) end
	player:learnTalent(talent, true)
	if not player:knowTalent(talent) then return false, "test_talent_missing" end
	player.unused_stats = math.max(player.unused_stats or 0, 1)
	if (player.life_regen or 0) <= 0 then player.life_regen = 1 end
	player.life = math.max(1, math.floor((player.max_life or 1) * 0.5))
	level.__auto_tome_ready = true
	game.logPlayer(player, "Auto ToME test level is ready.")
	return true
end

function M.enter_test(game)
	if not game.player or not game.level then return false, "no_player" end
	if Prompt.blocking(game) then return false, "player_busy" end
	if not game.zone or game.zone.short_name ~= "auto-test" or not game.level or game.level.level ~= 1 then
		game:changeLevel(1, "auto-test", {direct_switch = true})
	end
	if not game.zone or game.zone.short_name ~= "auto-test" or not game.level or game.level.level ~= 1 then
		return false, "level_change_failed"
	end
	return setup_level(game)
end

function M.execute(game, action)
	if type(action) ~= "table" or type(action.type) ~= "string" then return false, "invalid_action" end
	local kind = action.type
	if kind == "enter_test" then return M.enter_test(game) end
	if kind == "quit" then return M.quit(game) end
	if not game.player or not game.level then return false, "no_player" end
	if Prompt.blocking(game) then return false, "player_busy" end
	if kind == "step" then
		if not direction_ok(action.direction) then return false, "invalid_direction" end
		game.player:attackOrMoveDir(action.direction)
		return true
	elseif kind == "wait" then
		game.player:waitTurn()
		return true
	elseif kind == "run" then
		if not direction_ok(action.direction) then return false, "invalid_direction" end
		game.player:runInit(action.direction)
		return true
	elseif kind == "move_to" then
		-- Same walk as a left click on the map, even when the mouse-move option is off.
		local x, y = action.x, action.y
		if type(x) ~= "number" or type(y) ~= "number" or x % 1 ~= 0 or y % 1 ~= 0 then
			return false, "invalid_coordinate"
		end
		local player = game.player
		if type(player.mouseMove) ~= "function" then return false, "move_unavailable" end
		player:mouseMove(x, y, true)
		return true
	elseif kind == "auto_explore" then
		-- Same native explore the key runs, without the optional rest-first setting.
		local player = game.player
		if (game.zone and game.zone.no_autoexplore) or (game.level and game.level.no_autoexplore) then
			return false, "explore_forbidden"
		end
		if not player.autoExplore or not player:autoExplore() then
			game.logPlayer(player, "There is nowhere left to explore.")
			return true
		end
		while player:enoughEnergy() and player:runStep() do end
		return true
	elseif kind == "rest" then
		game.player:restInit()
		return true
	elseif kind == "change_level" then
		return M.change_level(game)
	elseif kind == "pickup" then
		if game.player.no_inventory_access then return false, "no_inventory" end
		game.player:playerPickup()
		return true
	elseif kind == "switch_weapons" then
		if game.player.no_inventory_access then return false, "no_inventory" end
		game.player:quickSwitchWeapons()
		return true
	elseif kind == "open_inventory" then
		return M.open_inventory(game)
	elseif kind == "open_levelup" then
		return M.open_levelup(game)
	elseif kind == "use" then
		return M.use(game, action)
	end
	return false, "unknown_action"
end

function M.change_level(game)
	local player = game.player
	local before = level_before(game)
	local terrain = game.level.map(player.x, player.y, game.level.map.TERRAIN)
	if not (player.enoughEnergy and player:enoughEnergy() and terrain and terrain.change_level) then
		game.log("There is no way out of this level here.")
		return false, "level_unchanged", before
	end
	if player:attr("never_move") then
		game.log("You cannot currently leave the level.")
		return false, "level_unchanged", before
	end
	local stop = {}
	for eff_id, _ in pairs(player.tmp or {}) do
		local effect = player.tempeffect_def[eff_id]
		if effect and effect.status == "detrimental" and not effect.no_stop_enter_worlmap then
			stop[#stop + 1] = type(effect.desc) == "string" and effect.desc or tostring(effect.desc or "")
		end
	end
	if terrain.change_zone and #stop > 0 and tostring(terrain.change_zone):find("^wilderness") then
		game.log("You cannot go into the wilds with the following effects: %s", table.concat(stop, ", "))
		return false, "level_unchanged", before
	end
	if terrain.change_level_check and terrain:change_level_check(player) then
		return false, "level_unchanged", before
	end
	local destination = (terrain.change_zone or terrain.change_level_abs) and terrain.change_level or game.level.level + terrain.change_level
	game:changeLevel(destination, terrain.change_zone, {
		keep_old_lev = terrain.keep_old_lev,
		force_down = terrain.force_down,
		auto_zone_stair = terrain.change_zone_auto_stairs,
		auto_level_stair = terrain.change_level_auto_stairs,
		temporary_zone_shift_back = terrain.change_level_shift_back,
	})
	return true, nil, before
end

function M.open_inventory(game)
	local player = game.player
	if player.no_inventory_access then return false, "no_inventory" end
	local dialog
	local title = type(_t) == "function" and _t"Inventory" or "Inventory"
	local titleupdator = player:getEncumberTitleUpdator(title)
	dialog = player:showEquipInven(titleupdator(), nil, function(object, inven, item, button, event)
		if not object then return end
		local UseItemDialog = require("mod.dialogs.UseItemDialog")
		local menu = UseItemDialog.new(event == "button", player, object, item, inven, function(_, _, _, stop)
			dialog:generate()
			dialog:generateList()
			dialog:updateTitle(titleupdator())
			if stop then game:unregisterDialog(dialog) end
		end)
		game:registerDialog(menu)
	end)
	if not dialog then return false, "inventory_unavailable" end
	return true
end

function M.open_levelup(game)
	local player = game.player
	if player:attr("no_levelup_access") then
		if type(player.no_levelup_access_log) == "string" then game.log(player.no_levelup_access_log) end
		return false, "no_levelup"
	end
	player:playerLevelup(nil, false)
	return true
end

function M.quit(game)
	local player = game.player
	if not player then return false, "no_player" end
	if player.dead then return false, "player_dead" end
	if player.runStop then player:runStop("quitting") end
	if player.restStop then player:restStop("quitting") end
	if game.target_co or (game.hasDialogUp and game:hasDialogUp()) then return false, "player_busy" end
	game:saveGame()
	if savefile_pipe and type(savefile_pipe.forceWait) == "function" then savefile_pipe:forceWait() end
	return true, "quit"
end

return M
