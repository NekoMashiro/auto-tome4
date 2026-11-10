# look

日期：2026-11-09。这里记每一种 `look`。总决定仍在 [游玩问题的处理决定](play-issues-decisions.md)。

| 名字 | 看什么 |
| --- | --- |
| `around` | 周围这一眼。不带名字时就是这一种 |
| `map` | 本层全图 |
| `actor` | 一只生物 |
| `prompt` | 当前窗口 |

`map`、`actor`、`prompt` 只读内存，不带日志，也不推动日志游标。每次 `act` 结束自动做一次 `around`，把这份结果和这次行动的结果一起返回。

## 1. `around`

不带名字的 `look` 就是这一种。它看周围这一眼，用来走路和决定打不打。

### 周围的图

已定。一张 41×41，玩家周围各 20 格。玩家在正中，上北下南，`y` 向下。出了地图的格子是空格，窗口大小不变。不是整张已经探索过的地图。

默认视野大约 10 格。自动探索在没有 `sight` 时按 10 算。20 格的外圈多半是记得或没见过。

| 格子 | 字符 |
| --- | --- |
| `seen` | 最上面一层。生物和物品用它们自己的 `display`，地形用下面这套 |
| `remembered` | 地形用下面这套。生物不留下。会记住的物品用物品自己的字符 |
| `unseen` | 空格 |

看得见和记得可能是同一个字符，每格再标 `seen`、`remembered` 或 `unseen`。没见过和地图外都是空格。见过的格子一定有字符。

格子上若是生物或物品，用它自己的 `display`。地形不按名字列，按顺序套下面这张表，先套中的为准：

| 字符 | 规则 |
| --- | --- |
| `+` | 有 `door_opened`。关着的门，封着的宝库门也是 |
| `'` | 开着的门。水下开着的门也用这个，它同时要水下呼吸 |
| `<` | `change_zone` 是世界地图，或 `change_level < 0`。带 `change_level_check` 的格子仍用这个，拒绝发生在使用时 |
| `>` | 其余有 `change_level` 或 `change_zone` 的。水下楼梯也用这个 |
| `&` | 拉杆 |
| `%` | 能走，`on_stand` 会掉血。岩浆地面、毒水。毒水同时要水下呼吸。区域若把 `on_stand` 清掉，就不再是这个 |
| `~` | 能走，不掉血，`air_condition` 是 `water`。深水、海底地板 |
| `:` | 能走，`air_level` 为正。海底气泡，站上去补空气 |
| `;` | 能走，`on_stand` 只上状态、不掉血。冰地板 |
| `=` | 走不进去，不挡视线，`pass_projectile`。熔岩、巨魔炖锅、虚空 `OUTERSPACE`。虚空在游戏里画成空格，这里不能画成空格 |
| `W` | 走不进去，`can_pass` 里有 `pass_water`。世界地图上的海、湖。没有 `air_level` |
| `#` | 其余走不进去、并且挡视线的。墙有 `pass_wall`，树有 `pass_tree`，硬墙和老墙没有。不会穿的人看起来一样 |
| `.` | 其余能走的。地板、草地、沙、路、冻水、沼泽水、浮石、世界地图上的河。带 `grow` 的在长出来之前也是。没有 `does_block_move` 的 `VOID` 也是这个 |
| `@` | 玩家 |
| 字母 | 生物各自的字符 |
| 其他 | 物品各自的字符，盖在地形上面 |

生物或物品盖住楼梯时，字符不再是 `<` 或 `>`。这格仍给出地形的 `change_level`。人站在楼梯上时字符是 `@`，方向仍读这格地形。

### 视野里的生物

和这张图一起给。条件与现在相同：`canSee`，并且那一格在 `seens` 里。`hostile` 换成 `relation`。

| 字段 | 来源 |
| --- | --- |
| `id`，`name`，`x`，`y` | 现有的。瞄准用 `id`，坐标对到图上 |
| `life`，`max_life` | 现有的 |
| `relation` | `player:reactionToward`。大于 0 友军，等于 0 中立，小于 0 敌对。队友和玩家的召唤物都算友军 |
| `level` | `actor.level` |
| `randboss` | `createRandomBoss` 打上的布尔值 |
| `rank` | `TextRank` 的名字：critter、normal、elite、rare、unique、boss、elite boss、god。脚本 boss 没有 `randboss`，靠这个看出阶层 |

### 地面上的物品

和这张图一起给。物品用自己的 `display` 画在格子上，会和地形符号相同：光源是 `~`，戒指是 `=`。有物品的格子另列出来。

范围是这张 41×41 里看得见的，以及记得、物品还留在格子上的。生物站在物品上时，图上是生物的字母，物品仍列在这里。一格叠了几件就列几件。

| 字段 | 来源 |
| --- | --- |
| `id`，`name`，`x`，`y`，`number` | 和现在脚下物品一样。`id` 是 `item-` 加 uid |
| `display` | 这件物品画在图上的字符 |
| `terrain` | 这格地形按上面那张表套出来的字符 |

脚下那格的长说明仍在 `floor`。

### 同时带上的状态

`can_act`、`activity`、`talents`、`inventory` 不在这里。休息、自动探索、奔跑结束才把结果返回，进行中不必另报。窗口全文不在这里。

| 字段 | 为什么留 |
| --- | --- |
| `in_game` | 还没进关卡时快照里几乎只有它 |
| `name` | 角色名，也是存档目录名。验收脚本只接受 `auto_test` |
| `x`，`y` | 图以玩家为中心，绝对坐标仍给命令和日志对位置 |
| `life`，`max_life` | 自己还剩多少血 |
| `energy` | 回合能量，`player.energy.value`。够不够行动看它 |
| `level` | 地图第几层 |
| `character_level` | 和生物的 `level` 比 |
| `unused_stats` | 大于 0 就该去加点 |
| `prompt_kind` | 窗口开着时给出种类，没有窗口是 `none`。正文和选项用 `prompt` |
| `floor` | 只脚下一格，带一段 `desc`。这一格的物品也在地面物品列表里 |
| `log` | 从上次返回之后新出现的行全部给出，没有新行就是空。固定 12 行会在长探索里把更早的行冲掉。写入时就抄进模组，送出后再删，见游玩决定第 5 条 |

资源不在模组里重算，直接读游戏已经登记的那张表 `ActorResource.resources_def`。资源条也是按这张表画的。一项带了池天赋时，学会了才列出：魔战士的魔力和体力都在，星月术士的正能量和负能量都在，没学会的不补 0。玩家在界面里藏起某条（`_hide_resource_*`）不影响这里。

每一项给短名、当前值、上限（有 `getMax` 才给）、回复（定义里有 `regen_prop` 才给）。定义上若有 `status_text`，把它的返回原文放进 `text`，失衡的失败率、紊乱的异常率，以及以后新资源加上的字，都在这句里。没有 `status_text` 时，百分比对齐资源条的画法，不另写公式。失衡条上的百分比是 `100` 减去 `equilibriumChance` 的第二个返回值，那个返回值是成功率，相减之后才是失败率。紊乱条上的百分比就是 `paradoxFailChance` 的返回值。

空气不是池天赋，资源条只在 `air < max_air` 时显示，这里同样。堡垒能量在 `player.is_fortress` 时读任务 `shertul-fortress` 的 `shertul_energy`。

每次都在、对走路帮助不大，这一次先留着：`str`（只有力量）、`mainhand`（几乎不变）、`zone` 和 `zone_name`（换区才变，短名够认区域）。

## 2. `map`

已定。另一种 `look`。作用和游戏里弹出的整张地图一样。极简界面的 `SHOW_MAP` 轮到第三档会打开 `ShowMap`，它用 `map:minimapDisplay` 画当前层。窗口装不下时游戏会滚动，这里一次给出整层，宽是 `map.w`，高是 `map.h`。

顶层的 `x`、`y` 是玩家的世界坐标，和 `around` 一样。`zone`、`zone_name`、`level` 也在顶层。整张图在 `view` 里。`view.x`、`view.y` 是 `view.rows[0]` 最左边那一格的世界坐标。整层从地图的 `(0, 0)` 画起，所以这两个数是 `0, 0`。第 `r` 行第 `c` 列的世界坐标是 `(view.x + c, view.y + r)`。玩家的 `@` 应在第 `y - view.y` 行、第 `x - view.x` 列。

迷雾和默认 `look` 的那张图用同一套规则。游戏里看得见是亮的，记得但现在看不见是暗的，没见过不画。文本里用标记分开：

| 格子 | 字符 |
| --- | --- |
| `seen` | 和 `around` 同一套。有生物就是生物的字母，有物品就是物品的字符 |
| `remembered` | 地形用 `around` 那套。生物不留下。会记住的物品可以留在字符上 |
| `unseen` | 空格。真实地形不填出来 |

每格再标 `seen`、`remembered` 或 `unseen`。楼梯被盖住时，这格仍给出地形的 `change_level`。字符和 `around` 用同一套。

这一次只给这张带迷雾的整图。默认 `look` 里的资源、日志、生物详情不在这里。看得见的生物只出现在它所站的那一格上。

## 3. `actor`

已定。另一种 `look`。指定一只生物，返回它的完整信息。不带 `id` 就是查自己。其他生物用 `around` 里看得见的那只的 `id`。看不见的生物不留在地图上，查不到。

数字都走人物页已经在调用的函数，不另写公式。提示框里的抗性只显示绝对值到了 20% 的，这里不照那个砍。

身份沿用默认 `look` 里生物的那几项：`id`、`name`、`x`、`y`、`life`、`max_life`、`relation`、`level`、`randboss`、`rank`。查自己时没有 `relation`。

伤害抗性按人物页。`DamageType.dam_def` 里 `resists` 不为 0 的才列。数值用 `combatGetResist`，上限是该类型的 `resists_cap` 加上 `resists_cap.all`。另有全体抗性 `resists.all`，以及对某一类生物的 `resists_actor_type`。

状态抗性是人物页那一列免疫。有这个属性才列，百分比是 `bound(attr * 100, 0, 100)`：`poison_immune`、`disease_immune`、`cut_immune`、`confusion_immune`、`blind_immune`、`silence_immune`、`disarm_immune`、`pin_immune`、`stun_immune`、`sleep_immune`、`fear_immune`、`knockback_immune`、`stone_immune`、`instakill_immune`、`teleport_immune`，以及全体 `negative_status_effect_immune`。100% 就是该状态落不上。不到 100% 时，落不落还看豁免：`combatPhysicalResist`、`combatSpellResist`、`combatMentalResist`。

伤害加成按人物页。`combatGetDamageIncrease` 列出有加成的伤害类型，另有 `inc_damage.all`，以及对某一类生物的 `inc_damage_actor_type`。查自己时用这个看输出。

技能是学会的全部，被动也在内。每项给 `id`、名字、`mode`、`getTalentLevelRaw` 的等级、是否持续中、剩余冷却。不附整段说明。

## 4. `prompt`

已定。另一种 `look`。只看当前最上面的窗口。没有窗口时 `kind` 为 `none`。

悬停不收。鼠标停上去才出现的说明不在这里。加点页不调用 `getTalentDesc`，所以需求、当前级和下一级的差别、能不能退点都不给。停在「属性点」「职业点」「通用点」「类别点」「觉醒」「纹身」上的那段说明也不给。其他窗口的物品对比、技能悬停同样不收。

屏幕上已经写出来的字都给，不再截断。现在 `dialog_body` 单段超过 4000、列表项超过 1000、整段超过 8000 会截掉，加点页的 `desc` 超过 2500 也会截掉。

| 字段 | 屏幕上是什么 |
| --- | --- |
| `title` | 窗口标题 |
| `text` | 窗口自己的正文，以及控件上的字 |
| `options[].label` | 按钮和列表行上的字。`choose` 用这个原文 |
| `nodes[].label` | 加点页每一项的名字 |
| `nodes[].desc` | 该项现在就能直接读到的说明：技能用 `getTalentFullDescription`，属性用属性定义里的说明 |
| `maximum` | 数量窗口的上限 |

`kind` 仍是 `none`、`choose`、`aim`、`quantity`、`adjust`、`text`。索敌时没有窗口，`kind` 为 `aim`。休息时那条「按回车停止」不是要回答的窗口，不放进来。
