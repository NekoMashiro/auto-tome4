# 游玩问题的处理决定

日期：2026-11-09。只记方案，代码等全部问题定下来再改。来源是服务器上的 `docs/tome4-play-issues-2026-11-09.md`。

## 1. Look around 与按键

已定。不加重用 Esc，也不做「关掉一切面板」的脱困指令。

MCP 的 `look` 只读内存，不会进入 Look around。那个模式是游戏按键 `l`。进去之后 `game.key` 换成索敌层，世界命令看到 `target_co` 就返回 `player_busy`。退出用已有的 `cancel`，它按索敌层的 `EXIT`。游戏自己的 `EXIT` 在没有窗口时打开主菜单。

要改的是实现：现在用 `press` 的世界命令改成直接调用，`act` 不再按游戏按键。

| 命令 | 调用 |
| --- | --- |
| `run` | `player:runInit(方向)` |
| `rest` | `player:restInit()` |
| `pickup` | `player:playerPickup()` |
| `switch_weapons` | `player:quickSwitchWeapons()` |
| `open_levelup` | `player:playerLevelup(nil, false)` |
| `open_inventory` | `player:showEquipInven`，并带上点物品后打开 `UseItemDialog` 的回调 |
| `change_level` | 没有单独函数。把 `CHANGE_LEVEL` 按键里的检查和 `game:changeLevel` 搬进模组 |

`step`、`wait`、`auto_explore`、`use` 已经是直接调用。`cancel` 和 `aim` 仍调用当前窗口或索敌层自己的退出和确认。查看模式开着时，世界命令依然先返回 `player_busy`。

## 2. 退出与读档

已定。不加单独的存档或读档命令。进程开着时不会一直落盘；正常退出会存档，崩溃或 `SIGTERM` 不会。

新增世界命令 `quit`。不走游戏内退出键，那个键存档后回到主菜单，进程还在，桥会断。也不弹 “Save and exit game?”。直接执行关窗口时选「是」的路径：停下休息和奔跑，`saveGame()`，`savefile_pipe:forceWait()` 等写完，再退出进程。回复先送回 MCP，然后退出。窗口还开着，或角色已死亡时，命令失败。

读档以后写进 `docs/agent-launch.md`，现在还没写。先等 `quit` 退出进程，再在显示游戏的机器上执行 `python3 tools/drive_game.py --save 存档短名 --no-play`。现在的科纳克狂战士短名是 `CornacBerserker`，对应 `./t-engine -Mtome -uCornacBerserker`。进程还开着时运行这条命令会先发 `SIGTERM`，这一下不存档。

## 3. look 看到的太少

已定要大改。`look` 分四种，都记在 [look](look.md)：`around`、`map`、`actor`、`prompt`。不带名字就是 `around`。只加脚下 `stairs` 不够。

现在一次 `look` 有坐标、生命、能量、力量、主手名字、区域、层数、人物等级、视野里的生物、主动和持续技能、背包、脚下一格的物品、最近 12 行日志、最上面的窗口。生物只有 `id`、名字、坐标、生命和是否敌对。没有地形。视野里其他格子上的物品没有。`zone` 和 `mainhand` 几乎不变，每次都重复。

走路是盲的。AI 知道怪在哪个坐标，不知道中间那格是地板、墙、门还是楼梯，只能走一格再看坐标变没变。周围这一眼是 `around`。整层图是 `map`。

## 4. 上下楼

已定。不分上下两个命令，继续用一个 `change_level`。

游戏的 `CHANGE_LEVEL` 就是一个键。脚下地形的 `change_level` 为正往更深层，为负往上层。没有这个字段时人不动，日志是 “There is no way out of this level here”。到达层的那一格往往是反方向的楼梯，再按一次会原路返回。

楼梯往哪边放进 `around` 的那张图，不单独先加 `stairs`。这条命令的返回写明原来的层数、现在的层数，以及这次是上、下、换区域，还是没动。失败时现在仍是 `completed`，不能只靠那行会滚掉的日志。

## 5. 日志

已定。不再固定返回最近 12 行。带日志的返回从上次已经返回的最后一行接着吐，到这次为止有多少行给多少行。没有新行就是空数组。AI 自己把每次的日志接上。

`map`、`actor`、`prompt` 只读内存，不带日志，也不推动游标。`around` 带日志。每次 `act` 结束自动做一次 `around`，连同这次行动的结果一起给 AI，游标跟着这次 `around` 往前走。

12 行是 `Observe.lua` 里 `getLines(12)` 截的。游戏日志区是有上限的环形缓冲。只在返回时去读它，一次长探索仍可能把更早的行冲掉。每一行写进日志时就抄进模组，被某次返回送出后再删。

## 6. 窗口和世界命令

已定。仍是一个 `act`，靠 `type` 分派。`step`、`rest`、`change_level` 这类走世界命令。`choose`、`aim`、`quantity`、`adjust`、`text`、`cancel` 走窗口。不拆成两个工具。

窗口开着时世界命令失败。现在的 `code` 只有 `player_busy`，同一次返回里虽有 `prompt`，工具说明没让 AI 去读。失败时加一句人话，写出当前窗口的标题和正文，指明选项在 `prompt.options`。背包这类长列表不逐项写进这句话。

窗口全文在 `look` 的 `prompt`。`around` 只带 `prompt_kind`，没有窗口是 `none`。不加一个内容相同的 `window`。失败时的人话以上面为准：标题和正文，长列表不逐项写进这句话，选项的 label 放在这次返回的 `options` 里。

`choose` 改为传刚刚返回的 `label` 原文。当前窗口里恰好一项相同才点。没有匹配，或有两项原文一样，就失败并把这些选项再返回，不点第一项。现在的 `option_id` 含 `row1`、`button2` 这种序号，列表重排会点错。`aim`、`quantity`、`adjust`、`text`、`cancel` 仍用原来的参数。

## 7. 自动探索停了

已定。不另报「本层剩余敌人」或「已探索完」。

“There is nowhere left to explore.” 表示自动探索的记忆里没有未走过的格子。一般这时这一层已经清完。视野里的敌人仍看 `around` 的生物。谁死了靠第 5 条的日志。没打开的宝库看 `around` 或 `map` 上的地形。

七个问题都已定。四种 `look` 已写入 [look](look.md)：`around`、`map`、`actor`、`prompt`。代码等讨论完再改。
