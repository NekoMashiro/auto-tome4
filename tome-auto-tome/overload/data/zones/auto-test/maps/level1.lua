-- 40 by 36. Street on y=2, door at x=6, stairs at x=37.
-- A shaft at x=20 leads to a room on y=32 that a normal sight radius cannot see from the street.
-- The pickup pile is placed later on the floor at x=37, y=3.
defineTile("#", "WALL")
defineTile(".", "FLOOR")
defineTile("+", "DOOR")
defineTile(">", "DOWN")
startx, starty = 2, 2
endx, endy = 37, 2

local width, height = 40, 36
local rows = {}
for y = 0, height - 1 do
	local cells = {}
	for x = 0, width - 1 do cells[x + 1] = "#" end
	rows[y + 1] = cells
end
local function put(x, y, char) rows[y + 1][x + 1] = char end
for x = 1, 37 do put(x, 2, ".") end
put(6, 2, "+")
put(37, 2, ">")
for y = 3, 32 do put(20, y, ".") end
for x = 16, 30 do put(x, 32, ".") end
put(37, 3, ".")

local lines = {}
for y = 1, height do lines[y] = table.concat(rows[y]) end
return table.concat(lines, "\n")
