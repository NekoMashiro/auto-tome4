# 里程碑 1：十七个原子操作打通测试层

日期：2026-11-03。目标版本：Tales of Maj'Eyal 1.7.6。插件版本：0.2.0，作者 NekoMashiro。

这一阶段把关卡内的操作收成 11 条世界命令和 6 种回答。外部程序只调用 `look` 和 `act`，就能把当前角色带过 Auto Test 测试层。操作怎么拆，见 [原子操作](tome-mcp-atomic-actions.md) 和 [覆盖范围](tome-mcp-atomic-actions-coverage.md)。

## 验收

2026-11-03 在一台有图形界面的 Linux 上跑通。`tools/drive_game.py` 打开游戏、读档，并在窗口里移动指针；`tools/play_test.py` 只发 `look` / `act`。整段约 41 秒，退出码 0。结束时角色在 `auto-test` 第 2 层 `(4, 3)`，也就是上楼楼梯。

脚本途中实际做了这些事：走一格、撞上普攻、休息、穿门、定向跑、自动探索、从一堆里捡一件、对测试技能瞄准、使用物品、打开背包后取消、丢弃时填数量、升级加一点并接受、给物品输入一次文字、切换武器组、下楼。

`enter_test` 只在测试里使用。它把已经在关卡中的角色传到测试层，并发放点数、物品和测试技能。它不是第 18 种玩法操作。

这一阶段不做：主战役、建角、存读档、队友、自动战斗策略、人物面板、整层记忆地图。真人模型打一遍只作演示，不算验收。

## 架构

游戏是单线程的。插件在每一帧开头看一次本机端口。外部程序不按帧说话：一条 `act` 发出去之后一直等，直到角色又能做决定，或者屏幕上出现真正要回答的窗口。

```text
MCP 客户端
    |  Content-Length 帧，stdio
    v
server/auto_tome_mcp          工具只有 look、act、status
    |  一行一个 JSON，127.0.0.1:9741
    v
Bridge.poll                   挂在 mod.class.Game:tick 开头
    |-- 世界命令 --> Commands   调用游戏自己的按键处理
    |-- 回答     --> Prompt     只看最上面的窗口
    +-- 快照     --> Observe
```

世界命令走 `mod/class/Game.lua` 的 `setupCommands`，不直接调用穿装备、捡东西或升级结算的内部函数。`step` 调用 `attackOrMoveDir`。`use` 走热键那条路：技能是 `Player:useTalent`，物品是 `Player:playerUseItem`。

回答只看最上面一层。认不出的窗口只要有按钮或列表，就暴露成 `choose`。两边都没有时，这一步停住，交给外面处理。

## 协议

游戏端口只认三个操作：

| 操作 | 何时回复 |
| --- | --- |
| `look` | 立刻。返回当前快照 |
| `status` | 立刻。按 `command_id` 取已经保存的结果，不重新执行 |
| `act` | 执行之后先不回复。角色空闲且有能量，回复 `completed`；出现真正的窗口或索敌，回复 `awaiting_input` |

`act` 必须带唯一的 `command_id`。同一个 id 再发一次，只返回上次的结果。最近 32 条结果留在内存里。

游戏里的失败是 `ok: true`，同时 `result.status == "failed"`，这样失败结果也能按 `command_id` 记下来。请求本身不合法时才是 `ok: false`。

空闲超过 110 秒仍没有新的决定，这条 `act` 以 `still_busy` 失败。Python 客户端的套接字超时是 120 秒。

窗口种类是 `none`、`choose`、`aim`、`quantity`、`adjust`、`text`。休息时游戏自己弹出的 “按回车停止” 不算要回答的窗口。角色正在跑或休息时，快照里的 `activity` 分别是 `run` 和 `rest`；自动探索也记成 `run`。

方向是小键盘，没有 5。y 向下增加，8 是北。

端口只绑定 `127.0.0.1:9741`，没有鉴权。新连接会替换旧连接，并清掉还没答完的命令。不要在设置里打开 “禁用所有网络连接”：引擎会因此卸掉 luasocket，桥就起不来。

MCP 进程：

```bash
PYTHONPATH=server python3 -m auto_tome_mcp
```

它对外的工具也只有 `look`、`act`、`status`。协议版本 `2024-11-05`。

## 代码

插件目录名必须是 `tome-auto-tome`，`short_name` 是 `auto-tome`。引擎用 PhysFS 扫 `game/addons`，指到游戏目录外面的符号链接不会被看见，测试机上要放成真实目录。

| 路径 | 职责 |
| --- | --- |
| `tome-auto-tome/init.lua` | 插件清单。`for_module = "tome"`，版本 `{1,7,6}` |
| `tome-auto-tome/superload/mod/class/Game.lua` | 在原来的 `tick` 之前调用 `Bridge.poll` |
| `tome-auto-tome/overload/mod/auto_tome/Bridge.lua` | 收一行 JSON，推迟 `act` 的回复，记住 `command_id` |
| `tome-auto-tome/overload/mod/auto_tome/Commands.lua` | 11 条世界命令和 `enter_test` |
| `tome-auto-tome/overload/mod/auto_tome/Prompt.lua` | 描述最上面的窗口，并执行 6 种回答 |
| `tome-auto-tome/overload/mod/auto_tome/Observe.lua` | 组装快照 |
| `tome-auto-tome/overload/mod/auto_tome/Json.lua` | 自带的 JSON 编解码。数组要用 `Json.array` 标记 |
| `tome-auto-tome/hooks/load.lua` | 在基础技能加载之后注册测试技能 |
| `tome-auto-tome/data/talents.lua` | `T_AUTO_TOME_BOLT`，命中型，射程 6，无消耗 |
| `tome-auto-tome/overload/data/zones/auto-test/` | 两层静态图 |
| `server/auto_tome_mcp/` | MCP stdio 服务和游戏端口客户端 |
| `tools/play_test.py` | 验收脚本，只调用 `look` 和 `act` |
| `tools/drive_game.py` | 打开游戏、读档或进教程，并保持指针移动 |
| `tools/test_mcp_framing.py` | 不启动游戏也能跑的协议和路线检查 |

`Json.lua` 不使用游戏自带的 `Json2.lua`。空表编码成对象。出站字符串是原始 UTF-8。`\uXXXX` 的解码只适合码点小于 256 的情况，验收流量是 ASCII。

快照包含：是否在关卡中、坐标、生命、能量、未分配属性点、力量、主手名字、活动、能否行动、区域、层数、看得见的生物、已学的主动或持续技能、背包、脚下物品、最近 12 行日志、当前窗口。`log[1]` 是这 12 行里较旧的一条，最后一条最新。脚下物品只含角色站着的那一格。

## 测试层

区域短名 `auto-test`，两层，不持久、不连世界地图。`no_level_connectivity` 让一扇关上的门不会把地图生成卡死。

第 1 层 40×36。角色从 `(2, 2)` 开始，假人在 `(4, 2)`，门在 `(6, 2)`，下楼楼梯在 `(37, 2)`，地上的一堆东西在 `(37, 3)`。一条竖井通向 y≈32 的房间，用来产生还没探索过的区域。第 2 层 10×8，上楼楼梯在 `(4, 3)`，到达时就站在楼梯上。

`enter_test` 使用 `direct_switch`，避免传送箱对话框挡住准备过程。真正的 `change_level` 不用这个开关，所以捐助者角色如果触发传送箱对话框，脚本会停在那一层窗口上。

假人属于单独的敌对阵营，不会动，生命为 1。准备过程还会放入治疗药、三颗可堆叠的石头、主手测试武器和备用武器，并把未分配属性点至少补到 1。生命被设到大约一半，生命回复至少为 1，休息才能走完。同一层上的 `__auto_tome_ready` 会挡住第二次准备，避免重复刷出假人和物品。

升级窗口没有单独的完成按钮。快照里有一个合成选项，文字是 `Finish`，它触发窗口自己的退出。退出后游戏询问是否接受，脚本再 `choose` 肯定的那个按钮。`cancel` 在这个窗口上会先恢复改动再关掉，而不是弹出接受框。

## 怎么跑

不启动游戏：

```bash
python3 tools/test_mcp_framing.py
```

在显示游戏的那台机器上跑完整验收：

```bash
python3 tools/drive_game.py
```

它会启动 `~/tome-test/t-engine4-linux64-1.7.6` 里的 1.7.6，把本仓库的插件复制成 `game/addons` 下的真实目录，点击 Load Game 和存档列表的第一行，再跑 `play_test.py`。`--new tutorial` 改为走教程建角。`--wiggle-only` 只移动指针。`--quit` 在脚本结束时关掉游戏。

游戏已经在关卡里、只想重跑验收时：

```bash
PYTHONPATH=server python3 tools/play_test.py
```

## 引擎的空闲等待

角色空闲时，引擎阻塞在 `SDL_WaitEvent`，主线程不再跑帧。桥只在 `Game:tick` 里读端口，所以一条新请求会一直挂着，直到有一次真正的鼠标或键盘事件。动作开始之后帧会自己继续，休息、奔跑和自动探索都能在一条 `act` 里走完。卡住的是两条命令之间的那一下。

`drive_game.py` 在角色头像上把指针来回挪几个像素，用来产生这个事件，不会点到地图。窗口坐标要用 `xwininfo` 的绝对左上角。`xdotool getwindowgeometry` 给出的位置含有窗框偏移，按它点击会点偏。点击本身用相对游戏窗口的坐标。

## 接着做时不用重复踩的点

- 插件必须是 `game/addons/tome-auto-tome` 这个真实目录。游戏开着的时候替换文件不会重新加载，要重启游戏。
- 音效音量不能是空值。音效关掉但 `effects_volume` 缺失时，点按钮会在播音效的地方出错。
- 背包使用窗口和捡东西窗口在操作之后常常还开着。验收脚本用 `cancel` 关掉剩下的那一层。
- 先丢石头，再给宝石打标签。打过标签的物品不能丢。
- 升级时第一项属性可能已经到顶。脚本会逐个尝试 `stat:` 节点，直到未分配点数下降。
- 假人不要设置不存在的 AI 模块。它靠能量模数为 0 保持不动，生命在放入地图之后再压成 1。
