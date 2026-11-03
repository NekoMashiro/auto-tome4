-- Eleven world commands, each one the game's own key or the hotkey it remembers.
local Prompt = require "mod.auto_tome.Prompt"
local M = {}

local RUN_KEYS = {
	[1] = "RUN_LEFT_DOWN", [2] = "RUN_DOWN", [3] = "RUN_RIGHT_DOWN",
	[4] = "RUN_LEFT", [6] = "RUN_RIGHT",
	[7] = "RUN_LEFT_UP", [8] = "RUN_UP", [9] = "RUN_RIGHT_UP",
}

local function direction_ok(direction)
	return RUN_KEYS[direction] ~= nil
end

local function press(game, name)
	local fn = game.key and game.key.virtuals and game.key.virtuals[name]
	if type(fn) ~= "function" then return false, "key_unavailable" end
	fn()
	return true
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
		return press(game, RUN_KEYS[action.direction])
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
		return press(game, "REST")
	elseif kind == "change_level" then
		return press(game, "CHANGE_LEVEL")
	elseif kind == "pickup" then
		return press(game, "PICKUP_FLOOR")
	elseif kind == "switch_weapons" then
		return press(game, "QUICK_SWITCH_WEAPON")
	elseif kind == "open_inventory" then
		return press(game, "SHOW_INVENTORY")
	elseif kind == "open_levelup" then
		return press(game, "LEVELUP")
	elseif kind == "use" then
		return M.use(game, action)
	end
	return false, "unknown_action"
end

return M
