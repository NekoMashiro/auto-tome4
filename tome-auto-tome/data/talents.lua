-- A single targeted talent so the test can answer a real aiming prompt.
newTalent{
	name = "Test Bolt",
	short_name = "AUTO_TOME_BOLT",
	type = {"misc/objects", 1},
	mode = "activated",
	hide = true,
	no_npc_use = true,
	points = 1,
	cooldown = 1,
	range = 6,
	action = function(self, t)
		local x, y = self:getTarget{type = "hit", range = 6, nowarning = true, nolock = true}
		if not x or not y then return nil end
		local Map = require "engine.Map"
		local target = game.level.map(x, y, Map.ACTOR)
		if target and target ~= self and not target.dead then
			if target.takeHit then target:takeHit(1, self) end
			game.logPlayer(self, "Test bolt hits %s.", target.name or "something")
		else
			game.logPlayer(self, "Test bolt hits the ground.")
		end
		return true
	end,
	info = function(self, t)
		return "A short bolt used by the Auto ToME test."
	end,
}
