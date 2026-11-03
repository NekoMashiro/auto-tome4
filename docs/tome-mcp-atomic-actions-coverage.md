# 原子操作能不能覆盖整个游戏

日期：2026-11-02。依据：Steam 安装的 Tales of Maj'Eyal 1.7.6。原子操作的定义见 [按游戏原生命令拆开的原子操作](tome-mcp-atomic-actions.md)。

这是覆盖结论，不是说现在的 MCP 已经能这样调用。当前 `tome.act` 仍把装备、学技能等拆成各自的动词；认不出的窗口会停成 `needs_input`。

## 结论

关卡里、由当前控制的这个角色来玩，那 11 个世界命令加 6 种回答够用。主菜单、读档，以及切换队友、给队友下命令，还缺入口。回答层本身不用再加新种类。

前提是：游戏弹出的每一层窗口，都被收成 `choose`、`aim`、`quantity`、`adjust`、`text`、`cancel` 之一。桥接如果把某个窗口留成 `needs_input`，这一步就停住，即使词汇表里已经有对应的回答。

## 关卡内已经能串起来的操作

| 玩家要做的事 | 输入顺序 | 游戏里的依据 |
| --- | --- | --- |
| 走、普攻、开门、进店、撞上 NPC 开始对话 | `step(方向)` | `Player:move` 撞上商店陷阱会走地形逻辑；`attackOrMoveDir` 先允许撞击再 `moveDir`。空地移动，敌人格普攻 |
| 沿直线跑、自动探索、休息、上下楼、等待 | `run` / `auto_explore` / `rest` / `change_level` / `wait` | `Game:setupCommands` 里的同名按键 |
| 放技能、开关持续技能、用物品或热键 | `use(id)`，然后零次或多次 `aim` / `choose` | 热键只是记住技能或物品 id（`Player:activateHotkey`）。问两次目标就 `aim` 两次 |
| 镶嵌或替换纹身 | `use(符文)` → `choose(槽位、买新槽或取消)` | `data/chats/player-inscription.lua` |
| 只扩纹身槽 | `open_levelup` → `choose(Inscriptions)` → `choose(是)` | `LevelupDialog` 的 Inscriptions 按钮 |
| 买、卖 | `step` 进店 → `choose(那一件)` → `quantity` → `choose(确认)` | 引擎 `Store:interact` 先 `GetQuantity`，再 `yesnoPopup` |
| 捡起 | 一件：`pickup`。一堆：`pickup` → `choose` | `Player:playerPickup` |
| 装备、卸下、丢弃、幻化、标签、鉴定、转交、装配件 | `open_inventory` → `choose(那一件)` → `choose(菜单项)`，堆叠再 `quantity` | `UseItemDialog` 的 Use / Wield / Take off / Drop / Identify / Tag / Transfer / Attach |
| 加属性、学技能、解锁或提升类别、退回本次点过的一点 | `open_levelup` → `adjust(节点, +1 或 -1)` → `choose(完成)` → `choose(接受)` | `LevelupDialog` 左键加、右键退；结束时是接受 / 取消 |
| 学觉醒 | `open_levelup` → `choose(Prodigies)` → `choose(哪一个)` → 完成并接受 | `UberTalent`，真正学会发生在 `LevelupDialog:finish` |
| 升级时额外弹出的确认、进化、选奖励 | 仍是 `choose` | 挂在同一次升级窗口上的列表或是否框 |
| 换掉第二枚戒指 | 先 `choose(Take off)` 再 `choose(Wield/Wear)` | `wearObject` 不询问槽位：有空位就放进第一个空位，都满了就替换第一格 |
| 切换武器组 | `switch_weapons` | `QUICK_SWITCH_WEAPON` |

点地图上的「走到那里」可以用多次 `step` 或 `run` 走到同一格，不必再做一个寻路动词。移动模式开关只决定撞上敌人时打不打；`step` 按 `attackOrMoveDir` 实现时，撞上就会打，和玩家默认的攻击移动键一致。

任务日志、人物面板、大地图、消息日志是查看。现有的 `observe`、`inspect`、`map` 已经能读，不必再做成输入。

## 还缺的入口

这些是游戏里真有的操作。缺的是「怎么开始」，不是一种新的回答。

| 游戏里的操作 | 现在这套输入的情况 | 依据 |
| --- | --- | --- |
| 切换控制队友（F1–F8） | 没有 `control(谁)`。切过去之后，同一套 `step` / `use` / `open_levelup` 就能操作他 | `Game:setupCommands` 的 `SWITCH_PARTY_*`，`Party:select` |
| 给队友下命令 | 内容已经是现成回答：行为是 `choose`，目标和锚点是 `aim`，活动半径和技能权重是 `quantity`，改名是 `text`，解散是 `choose`。缺的是「对谁下命令」 | `Party:giveOrder`；`orders/Behavior.lua`、`orders/Talents.lua` |
| 存档、退出 | 游戏有独立按键，不在那 11 个世界命令里 | `SAVE_GAME`、`QUIT_GAME` |
| 读档、主菜单、新开一局 | 建角本身是一串 `choose`（种族、职业、难度等）再加 `text(名字)`。主菜单和读档会换成另一局，关卡输入进不去 | `mod/dialogs/Birther.lua` |
| 纸娃娃、自定义头像 | 图片列表或拖拽，不是这 6 种回答 | `Birther:selectTile`、`customizeOptions` |
| 在线聊天、改键、调试、付费道具 | 不改变这局的角色和地图 | `USERCHAT_*`、`LUA_CONSOLE`、`DEBUG_MODE`、`MTXN_*` |

## 和现在 MCP 的差别

| 现在的 MCP | 按这次核对 |
| --- | --- |
| `move`、`wait`、`rest`、`auto_explore`、`change_level`、`pickup` | 与对应原子操作一致 |
| `attack` | 是 `step(敌人方向)` 的明确写法，可以留着 |
| `use_talent`、`set_sustain`、`use_item` | 都是 `use(id)` |
| `equip`、`unequip` | 物品菜单里的 Wear / Take off |
| `spend_stat`、`learn_talent`、`learn_category`、`unlearn_talent` | 升级窗口里的 `adjust`。游戏只允许退本次窗口里点过的点 |
| `tome.respond`、`tome.dismiss` | 已经是 `choose` / `aim` / `cancel` 的一部分 |
| 丢弃、买卖、纹身、觉醒、数量、升级窗口本身 | 不必再各做一个动词。要补的是 `open_inventory`、`open_levelup`、`quantity`、`adjust`、`text`，并让这些窗口走 `choose` |
| 队友控制、队友命令、存档、退出、读档 | 原子集合里还没有入口 |
