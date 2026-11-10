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

正常退出用世界命令 `quit`。它停下休息和奔跑，存档，等写完，把结果送回，然后退出进程。窗口还开着，或角色已经死亡时，这条命令失败。不要用游戏里的退出键，那个键存档后回到主菜单，进程还在，桥会断。崩溃或 `SIGTERM` 不会存档。

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

科纳克狂战士的起始区域是巨魔沼泽，短名 `trollmire`。换种族或职业前，先确认那一组 `race`、`subrace`、`class`、`subclass` 能组成合法角色。

`tools/birth_cornac_berserker.py` 会写好上面这个目录，并删掉同名的旧存档。`tools/drive_game.py` 在不带 `--save` 时会调用它。

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
