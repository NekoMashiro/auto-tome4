-- Stop an auto-explore that never reaches the game's own end.
-- Rest and an ordinary run are not counted. The cap covers both the command's
-- loop and Player:act, including runStep calling itself.
local _M = loadPrevious(...)

local runStep = _M.runStep
local EXPLORE_STEP_CAP = 5000

function _M:runStep()
	local running = self.running
	if type(running) == "table" and running.explore then
		local steps = (running.__auto_tome_steps or 0) + 1
		running.__auto_tome_steps = steps
		if steps > EXPLORE_STEP_CAP then
			game.logPlayer(self, "Auto-explore stopped after %d steps.", EXPLORE_STEP_CAP)
			if self.runStop then self:runStop() end
			return false
		end
	end
	return runStep(self)
end

return _M
