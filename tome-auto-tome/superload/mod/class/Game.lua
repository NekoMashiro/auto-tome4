-- Check the bridge once per tick, then run the game. A command's reply can stay open across ticks.
local _M = loadPrevious(...)
local tick = _M.tick

function _M:tick(...)
	local ok, err = pcall(function()
		require("mod.auto_tome.Bridge").poll(self)
	end)
	if not ok then print("[auto-tome] poll", err) end
	return tick(self, ...)
end

return _M
