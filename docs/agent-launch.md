# 给 agent：用启动参数进入游戏

日期：2026-11-04。目标版本：Tales of Maj'Eyal 1.7.6。

主菜单和建角画面没有桥。插件只在 `tome` 模块里加载，主菜单属于另一个模块，`look` 连不上。进入游戏用进程参数完成：选模块、新游戏或读档，以及一份预先写好的角色说明。参数把战役、难度、死亡模式、种族、职业和名字定下来，建角窗口不会留给人工去点。

操作进关卡之后的角色，见 [操作](agent-play.md)。

## 在哪台机器上启动

在显示游戏的那台机器上启动。测试机的地址、显示器和游戏目录写在本机的 `docs/server-connection.md`，这个文件不进仓库。

游戏进程需要：

```text
DISPLAY=:10.0
XAUTHORITY=/home/ubuntu/.Xauthority
LIBGL_ALWAYS_SOFTWARE=1
SDL_VIDEODRIVER=x11
```

工作目录是游戏根目录，里面有 `./t-engine`。测试机上是 `~/tome-test/t-engine4-linux64-1.7.6`。

插件必须是 `game/addons/tome-auto-tome` 这个真实目录，不能是指到仓库外的符号链接。`tools/drive_game.py` 启动时会从本仓库把插件复制过去。游戏开着的时候替换文件不会重新加载，改完插件要重启进程。

不要打开游戏里的 “禁用所有网络连接”。luasocket 会被卸掉，`127.0.0.1:9741` 就没有了。

角色空闲时引擎堵在 `SDL_WaitEvent`，主线程不跑帧。桥只在 `Game:tick` 里读端口，没有鼠标或键盘事件时 `look` 会一直挂到超时。`python3 tools/drive_game.py --no-play` 会完成下面的启动，并一直在头像上移动指针。游戏已经开着时，用 `--wiggle-only`。指针只在头像上晃，不点地图。

## 参数是前缀

这四个参数各自占一个 argv，值和标志连在一起，中间没有空格：

| argv | 作用 |
| --- | --- |
| `-Mtome` | 直接进入 Tales of Maj'Eyal，不停留在主菜单 |
| `-n` | 新游戏 |
| `-u名字` | 读取这个存档。和 `-n` 不要同时用 |
| `-E` 后面紧跟一段 Lua | 放进 `__module_extra_info`。整段 Lua 是这一个参数的剩余部分 |

读已有存档：

```bash
./t-engine -Mtome -u存档短名
```

没有 `save` 命令。正常退出用世界命令 `quit`，由它存档并退出。它停下休息和奔跑，存档，等写完，把结果送回，然后退出进程。窗口还开着，或角色已经死亡时，这条命令失败。不要用游戏里的退出键，那个键存档后回到主菜单，进程还在，桥会断。崩溃或 `SIGTERM` 不会存档。

`quit` 退出之后，在显示游戏的机器上再执行：

```bash
python3 tools/drive_game.py --save 存档短名 --no-play
```

现在的科纳克狂战士短名是 `CornacBerserker`，对应 `./t-engine -Mtome -uCornacBerserker`。进程还开着时运行这条命令会先发 `SIGTERM`，这一下不存档。

新游戏还需要 `-E` 里的 `auto_quickbirth`。

## 新角色写在 vault 里

`-E` 只负责指出用哪一份角色说明。说明本身是一个目录：

```text
~/.t-engine/4.0/tome/vault/<短名>/desc.lua
~/.t-engine/4.0/tome/vault/<短名>/character.teac
```

`character.teac` 可以是空文件。目录列表只检查它存在。`desc.lua` 里要有 `force_fallback = true`，这样游戏按描述新建角色，而不是把 `character.teac` 里的旧人物读回来。

已经验证过的科纳克狂战士是：

```lua
module = "tome"
module_version = {1,7,6}
name = "Cornac Berserker"
short_name = "CornacBerserker"
force_fallback = true
descriptors = {
	["difficulty"] = "Normal",
	["permadeath"] = "Adventure",
	["race"] = "Human",
	["subrace"] = "Cornac",
	["class"] = "Warrior",
	["subclass"] = "Berserker",
	["base"] = "base",
}
```

进游戏后的名字是 `short_name`，也就是 `CornacBerserker`。`name` 只是这份说明自己的标题。`-u` 改不了这个新角色的名字。

`descriptors` 用游戏内部的 id，不是界面上的中文：

| 字段 | 已验证的值 | 结果 |
| --- | --- | --- |
| `difficulty` | `Normal` | 普通难度 |
| `permadeath` | `Adventure` | 冒险模式 |
| `race`，`subrace` | `Human`，`Cornac` | 人类，科纳克人 |
| `class`，`subclass` | `Warrior`，`Berserker` | 战士，狂战士 |
| `base` | `base` | 固定填这个 |

不要写 `world`。建角对话框一开始已经把战役设成 Maj'Eyal，显示名是 “Maj'Eyal: The Age of Ascendancy”。自动确认只接受刚好四项匹配：难度、死亡模式、种族、职业。表里再写世界就会变成五项，Play 不会被按下，人就停在建角画面。因此 `difficulty`、`permadeath`、`race`、`class` 都要留在表里，`subrace`、`subclass` 和 `base` 也要留着。

不要写 `sex`。省略时角色是女性。表里只要出现 `sex`，不管值写什么，角色都会变成男性。

科纳克狂战士的起始区域是巨魔沼泽，短名 `trollmire`。其它组合用下面的 id。子职业必须属于它那一列的大类。档案还没解锁的项，自动确认对不上，人会停在建角画面。

## 游戏模式

`permadeath` 就是死亡模式。探索、冒险、一命对应这三个 id。界面中文来自游戏自己的翻译。三种都能用 `quit` 存档。区别在命数，不在能不能存。

| 写入的 id | 界面 | 规则 |
| --- | --- | --- |
| `Exploration` | 探索模式 | 无限命，城镇里可以随时洗点。测试机上要登录返回的 `donated` 至少为 1，桌面 Steam 版会直接当作捐助者。没达到时这一项是锁住的，自动确认不会选中它。等待方式见下面「选模式之前」 |
| `Adventure` | 冒险模式 | 有限的额外命。1、2、5、7、14、24、35 级各给一条命，死亡后在本层起点复活。新档案默认就是这个 |
| `Roguelike` | 永久死亡模式 | 一命。只有游戏里找到的复活办法才能再起来 |

## 难度

`difficulty` 必须写。简单难度的 id 是 `Easy`，不是界面上的 Easier。

| 写入的 id | 界面 | 新档案 |
| --- | --- | --- |
| `Easy` | 简单 | 可选。玩家受伤减少，治疗增加，负面状态更短。不给成就 |
| `Normal` | 普通 | 可选。默认难度。击杀后 2 回合不能上楼梯 |
| `Nightmare` | 梦魇 | 可选。区域等级、怪物技能和稀有怪都提高 |
| `Insane` | 疯狂 | 要先解锁 |
| `Madness` | 绝望 | 要先解锁 |

不要写 `Tutorial`。它不出现在正常建角里。

## 种族

`race` 是大类，`subrace` 是具体种族。出生地是没被职业改掉时的第一张地图，`look` 里的 `zone` 用短名。

| `race` | `subrace` | 界面 | 新档案 | 出生地 |
| --- | --- | --- | --- | --- |
| `Human` | `Cornac` | 人类，科纳克人 | 可选 | `trollmire`，巨魔沼泽 |
| `Human` | `Higher` | 人类，高等人类 | 可选 | `trollmire`，巨魔沼泽 |
| `Elf` | `Shalore` | 精灵，永恒精灵 | 可选 | `scintillating-caves`，闪光洞穴 |
| `Elf` | `Thalore` | 精灵，自然精灵 | 可选 | `norgos-lair`，诺尔格斯巢穴 |
| `Halfling` | `Halfling` | 半身人 | 可选 | `trollmire`，巨魔沼泽 |
| `Dwarf` | `Dwarf` | 矮人 | 可选 | `reknor-escape`，从瑞库纳逃亡 |
| `Yeek` | `Yeek` | 夺心魔 | 要先解锁 | `town-irkkk`，伊尔克 |
| `Giant` | `Ogre` | 巨人，食人魔 | 要先解锁 | `scintillating-caves`，闪光洞穴 |
| `Undead` | `Ghoul` | 不死族，食尸鬼 | 要先解锁 | `blighted-ruins`，荒芜废墟 |
| `Undead` | `Skeleton` | 不死族，骷髅 | 要先解锁 | `blighted-ruins`，荒芜废墟 |
| `Construct` | `Runic Golem` | 构装生物，符文傀儡 | 要先解锁，没解锁时界面里不显示 | `ruins-kor-pul`，卡·普尔废墟 |

不死族不能选野性系。巫妖、教程人类不要写。

## 职业

`class` 是大类，`subclass` 是具体职业。同一格里的子职业才能配这个大类。

| `class` | `subclass` | 界面 | 新档案 |
| --- | --- | --- | --- |
| `Warrior` | `Berserker` | 战士系，狂战士 | 可选 |
| `Warrior` | `Bulwark` | 战士系，盾战士 | 可选 |
| `Warrior` | `Archer` | 战士系，弓箭手 | 可选 |
| `Warrior` | `Arcane Blade` | 战士系，奥术之刃 | 可选 |
| `Warrior` | `Brawler` | 战士系，格斗家 | 要先解锁 |
| `Rogue` | `Rogue` | 盗贼 | 可选。大类和子职业的 id 都是 `Rogue` |
| `Rogue` | `Shadowblade` | 盗贼，影舞者 | 可选 |
| `Rogue` | `Marauder` | 盗贼，掠夺者 | 要先解锁 |
| `Rogue` | `Skirmisher` | 盗贼，散兵 | 要先解锁 |
| `Mage` | `Alchemist` | 法师系，炼金术师 | 可选 |
| `Mage` | `Archmage` | 法师系，元素法师 | 要先解锁 |
| `Mage` | `Necromancer` | 法师系，死灵法师 | 要先解锁 |
| `Wilder` | `Summoner` | 野性系，召唤师 | 要先解锁 |
| `Wilder` | `Wyrmic` | 野性系，龙战士 | 要先解锁 |
| `Wilder` | `Stone Warden` | 野性系，岩石守卫 | 要先解锁 |
| `Wilder` | `Oozemancer` | 野性系，软泥使 | 要先解锁。野性系这一大类要召唤师、龙战士、岩石守卫里至少解锁一个才会出现 |
| `Celestial` | `Sun Paladin` | 天空系，太阳骑士 | 要先解锁 |
| `Celestial` | `Anorithil` | 天空系，星月术士 | 要先解锁 |
| `Chronomancer` | `Paradox Mage` | 时空系，时空法师 | 要先解锁 |
| `Chronomancer` | `Temporal Warden` | 时空系，时空守卫 | 要先解锁 |
| `Defiler` | `Reaver` | 堕落系，收割者 | 要先解锁 |
| `Defiler` | `Corruptor` | 堕落系，腐化者 | 要先解锁 |
| `Afflicted` | `Cursed` | 痛苦系，被诅咒者 | 要先解锁 |
| `Afflicted` | `Doomed` | 痛苦系，末日使者 | 要先解锁 |
| `Psionic` | `Mindslayer` | 灵能系，心灵杀手 | 要先解锁 |
| `Psionic` | `Solipsist` | 灵能系，织梦者 | 要先解锁 |
| `Adventurer` | `Adventurer` | 冒险家 | 要先解锁，没解锁时不显示 |
| `Adventurer` | `Wanderer` | 流浪者 | 要先解锁，没解锁时不显示 |

这些职业会改掉种族的出生地，只在 Maj'Eyal 战役里生效：

| 职业 | 条件 | 出生地 |
| --- | --- | --- |
| 太阳骑士、星月术士 | 人类或精灵 | `town-gates-of-morning`，晨曦之门 |
| 元素法师 | 人类、精灵、半身人或食人魔 | `town-angolwen`，安格利文 |
| 时空法师、时空守卫 | 不是不死族、矮人、夺心魔 | `town-point-zero`，零点圣域 |

不要写 `None` 和教程职业。

`tools/birth_cornac_berserker.py` 会写好上面这个目录，并删掉同名的旧存档。`tools/drive_game.py --no-play` 在不带 `--save` 时会调用它。

验收不走这个角色。`python3 tools/drive_game.py` 只新建名为 `auto_test` 的科纳克狂战士，并且只删除 `~/.t-engine/4.0/tome/save/auto_test`。已经开着的游戏会被停掉且不存档，避免把验收跑进别的存档。`--save` 不能和验收一起用。

## 两条启动命令

两条都在游戏根目录执行。`-E` 后面的整段必须是同一个参数。

要自己处理开局加点页和欢迎词：

```bash
./t-engine -Mtome -n -Eauto_quickbirth="CornacBerserker"
```

角色进入巨魔沼泽第一层，加点页开着。`look` 能看到 `prompt.kind` 为 `adjust`，以及每项的 `label` 和 `desc`。按 [操作](agent-play.md) 加完点并选择 Yes。接着是欢迎词，`prompt.text` 里是全文，`options` 为空，`cancel` 关掉它，游戏才解除暂停。

要直接拿到一个能行动的角色，跳过加点页和欢迎词：

```bash
./t-engine -Mtome -n -Eauto_quickbirth="CornacBerserker" no_birth_popup=true birth_done_script=[==[game.paused = false]==]
```

`no_birth_popup=true` 让游戏自己关掉出生时的加点页和欢迎词，属性点先留着。`birth_done_script` 把暂停解开。进关卡后再 `open_levelup`，窗口和出生时是同一个。`tools/drive_game.py` 用的就是这一条。

`tools/play_trollmire1.py --birth` 用的是第一条：窗口留着，脚本先读正文再回答。

## 选模式之前

vault 的写法和上面两条命令都没有变。`-E` 里仍然只写 `auto_quickbirth="短名"`。

建角窗口一打开，插件先看登录结果在不在内存里。不在的话，最多再等 6 秒，并把这段时间里到达的登录回复读进来，然后再做难度、死亡模式、种族、职业这四项匹配。已经登录则马上建角。

日志有一行：

```text
[auto-tome] quickbirth auth 名字 donated
```

`donated` 是数字。探索模式只在它大于等于 1 时被选中。测试机跑的是独立的 `t-engine`，账号登录成功本身不够。桌面 Steam 版会直接把玩家当作捐助者，所以那边能选探索模式，不代表测试机这次返回里已经有这个数字。

游戏自己在启动时也会等登录，但一次断线就会取消这次等待，即便稍后档案线程打出 `logged in`。插件这 6 秒补的是这个空档。`explore_test` 就是这样建成的：等待被取消之后，补等读到 `Haroldyhli` 和 `donated` 24，存档里的模式是 `Exploration`。

6 秒后这个数字仍然没有，或者小于 1，四项对不齐，Play 不会被按下。窗口留在默认的冒险模式，并没有建成一个冒险模式角色。

## 启动之后

`look` 返回 `in_game: true` 并且 `zone` 是 `trollmire` 时，角色已经在巨魔沼泽。`level` 是地图层数。出生加点页还开着时，`prompt_kind` 为 `adjust`。

指针没有在动时，下一条 `look` 会一直停着。先确认 `drive_game.py` 的指针循环还在。

## 启动之后的第一眼

留着加点页的那条命令，第一次 `look` 类似：

```json
{
  "in_game": true,
  "zone": "trollmire",
  "level": 1,
  "character_level": 1,
  "prompt_kind": "adjust",
  "prompt": {"kind": "adjust", "title": "Levelup: CornacBerserker, level 1"}
}
```

`prompt.nodes` 里有力量、敏捷等属性和已经学会的技能。按 [操作](agent-play.md) 里的加点示例处理，再 `cancel` 掉欢迎词。欢迎词关掉之后，`prompt_kind` 变为 `none`。

跳过加点页和欢迎词的那条命令，第一次能行动的 `look` 类似：

```json
{
  "in_game": true,
  "zone": "trollmire",
  "zone_name": "Trollmire",
  "level": 1,
  "character_level": 1,
  "mainhand": "iron greatsword (18-29 power, 1 apr)",
  "prompt_kind": "none"
}
```

这时可以直接 `auto_explore` 或 `rest`。属性点还在 `unused_stats` 里，需要时再 `open_levelup`。
