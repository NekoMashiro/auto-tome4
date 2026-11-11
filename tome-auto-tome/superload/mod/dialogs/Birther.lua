-- Quickbirth runs when the birth dialog opens. The login reply can still be
-- queued then. Wait up to 6 seconds and read profile events before selecting
-- a mode, so Exploration can see auth.donated. An auth that is already in
-- memory starts the birth immediately.
local _M = loadPrevious(...)

local on_register = _M.on_register
local AUTH_WAIT_MS = 6000

local function wait_for_auth()
	if profile and not profile.auth then
		local start = core.game.getTime()
		print("[auto-tome] waiting up to 6s for profile auth before quickbirth")
		while not profile.auth and core.game.getTime() - start < AUTH_WAIT_MS do
			if game and game.handleEvents then game:handleEvents() end
			if profile.auth then break end
			pcall(core.display.forceRedraw)
			core.game.sleep(50)
		end
	end
	local auth = profile and profile.auth
	print("[auto-tome] quickbirth auth", auth and auth.name or "none", auth and auth.donated or "none")
end

function _M:on_register()
	if __module_extra_info and __module_extra_info.auto_quickbirth then
		wait_for_auth()
	end
	return on_register(self)
end

return _M
