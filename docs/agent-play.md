# 给 agent：用 look 和 act 操作游戏

日期：2026-11-04。目标版本：Tales of Maj'Eyal 1.7.6。插件 `auto-tome` 0.2.0。

角色已经在关卡里之后，只使用两个工具：`look` 看局面，`act` 做一件事。启动游戏、跳过建角的方法在 [启动](agent-launch.md)。

`act` 的 `action.type` 只有两类。世界命令让角色行动。回答只处理当前最上面的窗口。窗口开着时，世界命令会失败，代码是 `player_busy`。同一次返回里的 `message` 写出窗口标题和正文，选项在 `options`。先回答，再行动。

## 怎么调用

MCP 工具：

| 工具 | 参数 | 作用 |
| --- | --- | --- |
| `look` | `kind` 可选：`around`（默认）、`map`、`actor`、`prompt`。`actor` 再带 `id`，不带就是自己 | 立刻返回。`map`、`actor`、`prompt` 不带日志，也不推动日志 |
| `act` | `command_id`，`action` | 执行一条世界命令或一种回答 |
| `status` | `command_id` | 取这条命令已经记下的结果，不重新执行 |

`command_id` 每次尝试用一个新字符串。同一个 id 再发一次，只会拿到上一次的结果。游戏记住最近 32 条。

直接连游戏端口时，向 `127.0.0.1:9741` 发送一行 JSON。`look` 是 `{"id":"1","op":"look"}`。`act` 是 `{"id":"2","op":"act","command_id":"...","action":{...}}`。端口只绑定本机，没有鉴权。新连接会替换旧连接，并清掉还没答完的命令。

返回 `ok: true` 时，`result` 就是一份快照，并多三个字段：

| 字段 | 含义 |
| --- | --- |
| `status` | `completed`：角色又能决定。`awaiting_input`：窗口或索敌还开着。`failed`：这步在游戏里没做成 |
| `command_id` | 你传入的 id |
| `code` | 只在 `failed` 时出现，例如 `player_busy`、`invalid_direction`、`still_busy` |

游戏里的失败仍然是 `ok: true`。请求格式不对才是 `ok: false`。一条 `act` 会一直等到角色空闲，或者出现真正要回答的窗口。空闲超过 110 秒仍无结果时，`code` 为 `still_busy`。

角色空闲时引擎堵在 `SDL_WaitEvent`，主线程不跑帧。桥只在 `Game:tick` 里读端口，所以没有鼠标或键盘事件时，`look` 和 `act` 会一直挂到超时。游戏已经开着时，在显示游戏的那台机器上保持：

```bash
python3 tools/drive_game.py --wiggle-only
```

它把指针在角色头像上晃几个像素，用来产生这个事件，不会点到地图。动作开始之后帧会自己继续。卡住的是两条命令之间的那一下。

## 先看快照

`look` 不带 `kind` 时是 `around`。角色还没有坐标时只返回 `in_game: false`、`prompt_kind: "none"` 和这次新出现的 `log`。出生流程把人放进关卡之后，快照才完整。

| 字段 | 含义 |
| --- | --- |
| `in_game` | 角色是否已经在关卡中 |
| `x`，`y` | 坐标。y 向下增加 |
| `life`，`max_life` | 当前生命和上限 |
| `energy` | 当前能量 |
| `unused_stats` | 还没花掉的属性点 |
| `str` | 力量 |
| `mainhand` | 主手武器的名字 |
| `zone`，`zone_name` | 区域短名和显示名。巨魔沼泽的短名是 `trollmire` |
| `level` | 当前地图第几层，不是人物等级 |
| `character_level` | 人物等级 |
| `prompt_kind` | 窗口种类。没有要回答的窗口是 `none`。正文和选项用 `look` 的 `prompt` |
| `view` | 玩家周围 41×41。`rows` 是字符，`sight` 里 `S` 看得见、`R` 记得、空格没见过。`stairs` 给出地形的 `change_level` |
| `actors` | 看得见的生物。`relation` 大于 0 友军，等于 0 中立，小于 0 敌对 |
| `items` | 这张图里看得见的物品，以及记得、游戏还留在格子上的物品 |
| `floor` | 只脚下一格，带一段 `desc` |
| `resources` | 游戏已经登记的资源。学会了对应池才列出 |
| `log` | 从上次 `around` 之后新出现的行。没有新行就是空数组 |

`map` 是整层，迷雾规则和 `view` 一样。顶层的 `x`、`y` 仍是玩家。整层图在 `view` 里，`view.x`、`view.y` 是左上角，从 `(0, 0)` 画起。`actor` 不带 `id` 就是自己，带上 `around` 里那只的 `id` 才查别人；看不见的查不到。技能、抗性、豁免和伤害加成都在 `actor` 里。窗口全文在 `prompt`。四种的字段见 [look](look.md)。

背包不在 `around` 里。打开背包之后，物品名字在 `prompt` 的 `options[].label`。

## 窗口

`prompt.kind`：

| kind | 手里有什么 | 回答 |
| --- | --- | --- |
| `none` | 没有要回答的窗口 | 可以发世界命令 |
| `choose` | `options` 里每一项有 `label` | `choose` 传这个 `label` 原文，或用 `cancel` 关掉 |
| `aim` | 技能或战吼正在索敌 | `aim`，或 `cancel` |
| `quantity` | 要一个整数，`maximum` 可能给出上限 | `quantity` |
| `adjust` | 加点页。`nodes` 是可加减的项 | `adjust`，点完用 `choose` |
| `text` | 要一段文字 | `text` |

每个窗口尽量带上 `title` 和 `text`。`text` 是屏幕上的正文：欢迎词、确认句、任务提示、纸条打开后的内容。加点页的 `nodes` 还有 `desc`，是这项属性或技能的说明。

`choose` 传刚刚返回的 `label` 原文。当前窗口里恰好一项相同才点。没有匹配，或有两项原文一样，命令失败，并把这些选项再放进 `options`，不会点第一项。

没有按钮、也没有列表的窗口仍然是 `choose`，只是 `options` 为空。欢迎词、羊皮纸纸条、任务横幅都是这种。先读 `title` 和 `text`，再用 `cancel` 关掉。`cancel` 会按这个窗口自己的退出键，欢迎词关掉后出生流程会继续。

有按钮的确认框也是 `choose`。问题在 `text`，按钮文字在 `options[].label`。`choose` 传这个 `label`。

加点页是 `adjust`。`nodes[].node` 形如 `stat:1`、`talent:T_STUNNING_BLOW_ASSAULT`、`category:technique/2hweapon-assault`。`label` 是屏幕上的名字，`desc` 是说明。按钮里会有 `Finish`、剩余点数、`Prodigies`、`Inscriptions`。

休息时那条 “按回车停止” 不会出现在 `prompt` 里。休息结束前，这一条 `act` 不会返回。

## 回答

```json
{"type": "choose", "label": "刚才 look 到的原文"}
{"type": "cancel"}
{"type": "aim", "target_id": "actor-123"}
{"type": "aim", "direction": 6}
{"type": "aim", "x": 12, "y": 8}
{"type": "quantity", "quantity": 1}
{"type": "adjust", "node": "stat:1", "delta": 1}
{"type": "text", "text": "要输入的文字"}
```

`delta` 只能是 `1` 或 `-1`。`quantity` 必须是整数。`aim` 三种写法用一种即可：`target_id` 指向一个还活着的生物，`direction` 是小键盘方向，`x` 和 `y` 是地图坐标。

加点的顺序：

1. 读 `nodes` 的 `label` 和 `desc`，决定加哪一项。
2. `adjust` 一次加一点或减一点。
3. `choose` 标签为 `Finish` 的那一项。
4. 下一扇窗口的正文是 “Do you accept changes?”，按钮是 Yes、No、Cancel。`choose` Yes 才保存。

在加点页上直接 `cancel` 会撤销刚才的改动并关掉，不会问是否接受。

## 世界命令

`direction` 只能是数字，不能写 `"east"` 这种名字。合法值是 `1`、`2`、`3`、`4`、`6`、`7`、`8`、`9`，没有 `5`。写成字符串会得到 `invalid_direction`。8 北，2 南，4 西，6 东，7 西北，9 东北，1 西南，3 东南。`step`、`run` 和 `aim` 都用这套数字。

| type | 其他字段 | 做什么 |
| --- | --- | --- |
| `step` | `direction` | 朝该方向走一格。那一格是敌人时改为攻击，人留在原地 |
| `wait` | 无 | 空过一回合 |
| `run` | `direction` | 朝该方向一直跑，直到被挡住 |
| `auto_explore` | 无 | 用游戏自己的自动探索，直到它停下 |
| `rest` | 无 | 休息到回复满、被打断，或游戏自己停 |
| `change_level` | 无 | 使用脚上的楼梯。返回 `from_level`、`from_zone`、`level_move`：`up`、`down`、`zone` 或 `none`。没动是失败，不能只看日志 |
| `quit` | 无 | 存档并退出进程。窗口开着或角色已死亡时失败 |
| `pickup` | 无 | 捡起脚下的东西。一堆物品时会变成 `choose` |
| `switch_weapons` | 无 | 切换武器组 |
| `open_inventory` | 无 | 打开背包，随后用 `choose` 或 `cancel` |
| `open_levelup` | 无 | 打开加点页 |
| `use` | `id` | 用一个技能或背包里的一件物品 |

`use` 的技能 `id` 来自 `look` 的 `actor`（不带 `id` 就是自己）里的 `talents[].id`。物品先 `open_inventory`，再按窗口里的 `label` 选。技能可能接着要求 `aim`。用完如果还开着窗口，继续回答，直到 `prompt_kind` 回到 `none`。

没有 `open`。`{"type":"open","x":52,"y":22}` 会得到 `unknown_action`。关着的门在图上是 `+`。朝它 `step`，游戏自己开门，人通常还停在原地，下一回合再走进去。`open_inventory` 和 `open_levelup` 只打开背包和加点页。

`step` 没有移动时，看 `log` 和 `actors`。目标格有敌人，这是一次攻击。连续两次走不进去，那一格是墙或别的障碍。

上下楼只看日志和结果里的 `level`。日志出现 “There is a way to the next level here” 时，人站在向下的楼梯上，`change_level` 进入下一层。出现 “previous level” 时，同一命令回到上一层。换层之后重新 `look`，坐标和 `level` 都会变。

`enter_test` 会把角色传送到 Auto Test 测试层。打主战役时不要用它。

## 一轮怎么走

1. `look`。
2. `prompt.kind` 不是 `none`：读 `title`、`text`、`options`、`nodes`，发一种回答。
3. 否则根据 `life`、`actors`、`floor`、`log` 发一条世界命令。
4. 用返回的 `around` 做下一次决定。`log` 只有这次新出现的行，自己把每次的接上。窗口开着时再 `look`，`kind` 用 `prompt`。

脚下出现纸条时，`floor[].desc` 只是这件物品的短说明。正文在打开之后的窗口 `prompt.text` 里。先 `pickup` 或 `use`，读完再用 `cancel` 关掉。

## 示例

下面的 `action` 就是 `act` 的参数。`command_id` 每次换一个新字符串。返回里的快照只留和这步有关的字段。`label` 必须用这一次窗口里的原文，不能沿用示例里的占位符。

空闲时向东走一格：

```json
{"type": "step", "direction": 6}
```

返回里 `x` 比原来大 1，`prompt.kind` 仍是 `none`。那一格站着敌人时坐标不变，`log` 里会出现命中或未命中。

一段路用一次自动探索。没有敌人、没有窗口时：

```json
{"type": "auto_explore"}
```

这一条会自己走很多格，直到探索停下。停下来之后读 `actors` 和 `log`。看见敌人就改去战斗，不要接着探索。日志里出现 “There is nowhere left to explore.” 时，这层能走的地方已经走完。

血量不满、视野里没有敌人时，一次休息回到满血：

```json
{"type": "rest"}
```

返回前游戏会休息很多回合。`log` 里能看到 “Rested for 23 turns” 这类句子。休息被敌人打断时，`actors` 里会出现它。

相邻的森林巨魔用震慑打击。先看技能 id，再使用：

```json
{"type": "use", "id": "T_STUNNING_BLOW_ASSAULT"}
```

返回 `prompt.kind` 为 `aim` 时，朝那只巨魔确认：

```json
{"type": "aim", "target_id": "actor-41"}
```

`log` 里会出现 “uses Stunning Blow” 和 “is stunned”。技能还在冷却时，`log` 里是 “still on cooldown”，这回合改成朝它的方向 `step`，也就是普通攻击。战吼同样可能先要 `aim`，朝敌人的方向给出 `direction` 即可。

开局加点页 `prompt.kind` 为 `adjust`。先读 `nodes` 里力量的 `desc`，再加一点：

```json
{"type": "adjust", "node": "stat:1", "delta": 1}
```

`unused_stats` 会减少。点完后在 `options` 里找标签 `Finish`：

```json
{"type": "choose", "label": "Finish"}
```

下一扇窗口的 `text` 是 “Do you accept changes?”，`options` 是 Yes、No、Cancel。对 Yes 再发一次 `choose`。

欢迎词没有按钮。`title` 是 “Welcome to Tales of Maj'Eyal”，正文在 `text`，`options` 是空数组。读完后：

```json
{"type": "cancel"}
```

任务横幅也是这样。第二层弹出的 `text` 里有 “Quest: Escort: lost warrior”，同样 `cancel` 关掉。

脚下是纸条时，`floor` 里先只有短说明 “A paper scrap, left by an adventurer.” 捡起来：

```json
{"type": "pickup"}
```

纸条窗口打开后，全文在新的 `prompt.text` 里。读完 `cancel`。

站在楼梯上时，`log` 有 “There is a way to the next level here”。下楼：

```json
{"type": "change_level"}
```

成功时 `zone` 仍是 `trollmire`，`level` 从 1 变成 2，坐标换成下一层的落点。日志若是 “previous level”，同一条命令回到上一层。
