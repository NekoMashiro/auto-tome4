#!/usr/bin/env python3
"""Clear Trollmire level 1 with look and act only.

Real choices stop the script. Notes with no buttons are closed. Resume with
--resume and an answer once a choice has been read.

    python3 tools/play_trollmire1.py
    python3 tools/play_trollmire1.py --resume --answer no
    python3 tools/play_trollmire1.py --resume --option '<option_id>'
"""

import argparse
import json
import os
import signal
import sys
import time
import uuid
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from auto_tome_mcp.game import GameClient, GameError

STATE_PATH = Path("/tmp/trollmire_state.json")
LOG_PATH = Path("/tmp/trollmire_play.log")
MAX_ACTIONS = 2500

DELTAS = {
    8: (0, -1),
    2: (0, 1),
    4: (-1, 0),
    6: (1, 0),
    7: (-1, -1),
    9: (1, -1),
    1: (-1, 1),
    3: (1, 1),
}
CARDINALS = (8, 6, 2, 4)
DIR_OF = {delta: direction for direction, delta in DELTAS.items()}


class NeedDecision(Exception):
    def __init__(self, snap, reason):
        self.snap = snap
        self.reason = reason


class StopPlay(Exception):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def log_line(text):
    print(text, flush=True)
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(text + "\n")


def fresh_state():
    return {
        "floor": [],
        "blocked": [],
        "soft": {},
        "stairs_down": [],
        "stairs_up": [],
        "refused": [],
        "prev_log": [],
        "turn": 0,
        "heal_retry": 0,
        "stun_retry": 0,
        "shout_retry": 0,
        "last_attempt": None,
        "levelup_done": False,
    }


def load_state():
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def save_state(state):
    STATE_PATH.write_text(json.dumps(state), encoding="utf-8")


def as_set(pairs):
    return {tuple(pair) for pair in pairs}


def pair_list(points):
    return sorted([list(point) for point in points])


class Player:
    def __init__(self, client, state):
        self.client = client
        self.state = state
        self.floor = as_set(state["floor"])
        self.blocked = as_set(state["blocked"])
        self.stairs_down = as_set(state["stairs_down"])
        self.stairs_up = as_set(state["stairs_up"])
        self.refused = as_set(state["refused"])
        self.soft = {tuple(int(part) for part in key.split(",")): count for key, count in state["soft"].items()}

    def persist(self):
        self.state["floor"] = pair_list(self.floor)
        self.state["blocked"] = pair_list(self.blocked)
        self.state["stairs_down"] = pair_list(self.stairs_down)
        self.state["stairs_up"] = pair_list(self.stairs_up)
        self.state["refused"] = pair_list(self.refused)
        self.state["soft"] = {"%s,%s" % key: value for key, value in self.soft.items()}
        save_state(self.state)

    def new_lines(self, snap):
        previous = self.state.get("prev_log") or []
        current = snap.get("log") or []
        start = 0
        for index in range(len(previous) + 1):
            if previous[index:] == current[: len(previous) - index]:
                start = len(previous) - index
                break
        else:
            start = 0
        fresh = current[start:]
        self.state["prev_log"] = current
        return fresh

    def note_terrain(self, lines, x, y):
        here = (x, y)
        for line in lines:
            low = line.lower()
            if "stair" not in low and "ladder" not in low and "楼梯" not in line and "there is a" not in low:
                continue
            log_line("terrain %s,%s: %s" % (x, y, line))
            if here in self.refused:
                continue
            downward = ("down" in low or "向下" in line or "下层" in line or "next level" in low)
            upward = ("up" in low or "向上" in line or "上层" in line or "previous level" in low)
            if downward and not (upward and "down" not in low):
                self.stairs_down.add(here)
            elif upward:
                self.stairs_up.add(here)

    def raw_act(self, action):
        self.state["turn"] += 1
        try:
            snap = self.client.act(action, str(uuid.uuid4()))
        except GameError as error:
            raise StopPlay(1, "bridge rejected %s: %s" % (action.get("type"), error))
        self.last_lines = []
        snap = self.fill_prompt(snap)
        if snap.get("in_game") and snap.get("x") is not None:
            self.floor.add((snap["x"], snap["y"]))
            self.last_lines = self.new_lines(snap)
            for line in self.last_lines:
                if line.strip():
                    log_line("log: %s" % line)
            self.note_terrain(self.last_lines, snap["x"], snap["y"])
            self.note_view(snap)
            self.note_floor(snap)
            self.note_foes(snap)
        if (snap.get("life") or 0) <= 0 or any("you die" in line.lower() or "你死" in line for line in snap.get("log") or []):
            raise StopPlay(1, "died at %s,%s" % (snap.get("x"), snap.get("y")))
        return snap

    def fill_prompt(self, snap):
        if not isinstance(snap, dict) or snap.get("prompt"):
            return snap
        kind = snap.get("prompt_kind") or "none"
        if kind == "none":
            snap["prompt"] = {"kind": "none", "options": []}
            return snap
        try:
            snap["prompt"] = self.client.look("prompt")
        except GameError:
            snap["prompt"] = {"kind": kind, "options": snap.get("options") or []}
        return snap

    def note_view(self, snap):
        view = snap.get("view") or {}
        rows = view.get("rows") or []
        sight = view.get("sight") or []
        origin_x, origin_y = view.get("x"), view.get("y")
        if origin_x is None or origin_y is None:
            return
        blocked = set("#=W")
        open_ground = set(".'<:>~%;&@")
        for y, row in enumerate(rows):
            fog = sight[y] if y < len(sight) else ""
            for x, glyph in enumerate(row):
                if x >= len(fog) or fog[x] == " ":
                    continue
                point = (origin_x + x, origin_y + y)
                if glyph in blocked:
                    self.blocked.add(point)
                elif glyph in open_ground:
                    self.blocked.discard(point)
        for stair in view.get("stairs") or []:
            point = (stair.get("x"), stair.get("y"))
            change = stair.get("change_level")
            if stair.get("change_zone") or (isinstance(change, (int, float)) and change < 0):
                self.stairs_up.add(point)
                self.stairs_down.discard(point)
            elif isinstance(change, (int, float)) and change > 0:
                self.stairs_down.add(point)
                self.stairs_up.discard(point)

    def note_floor(self, snap):
        names = tuple(item.get("name") or "" for item in snap.get("floor") or [])
        if not names or names == getattr(self, "_floor_names", None):
            return
        self._floor_names = names
        for item in snap.get("floor") or []:
            log_line("FLOOR %s" % (item.get("name") or ""))
            for line in (item.get("desc") or "").splitlines():
                log_line("  %s" % line)

    def note_foes(self, snap):
        foes = []
        for actor in snap.get("actors") or []:
            if not is_hostile(actor):
                continue
            foes.append("%s@%s,%s %s/%s" % (
                actor.get("name"), actor.get("x"), actor.get("y"), actor.get("life"), actor.get("max_life"),
            ))
        key = tuple(foes)
        if key == getattr(self, "_foes", None):
            return
        self._foes = key
        if foes:
            log_line("see %s" % "; ".join(foes))

    def log_window(self, snap):
        prompt = snap.get("prompt") or {}
        kind = prompt.get("kind")
        if kind in (None, "none"):
            return
        nodes = tuple((node.get("node"), node.get("label"), node.get("desc")) for node in prompt.get("nodes") or [])
        buttons = tuple(option.get("label") for option in prompt.get("options") or [])
        marker = (kind, prompt.get("title"), prompt.get("text"), buttons, nodes)
        if marker == getattr(self, "_window", None):
            return
        self._window = marker
        log_line("WINDOW kind=%s title=%s" % (kind, prompt.get("title") or ""))
        text = prompt.get("text") or ""
        if text:
            log_line("TEXT:")
            for line in text.splitlines():
                log_line("  %s" % line)
        for label in buttons:
            log_line("  button: %s" % label)
        for node, label, desc in nodes:
            log_line("  point: %s | %s" % (node, label))
            if desc:
                for line in desc.splitlines():
                    log_line("    %s" % line)

    def dismiss_or_decide(self, snap, allow):
        for _ in range(8):
            self.log_window(snap)
            kind, options = prompt_parts(snap)
            if kind in (None, "none") or kind in allow:
                return snap
            if kind == "adjust" and "adjust" not in allow:
                snap = self.finish_levelup(snap)
                continue
            if kind == "choose" and not options:
                title = (snap.get("prompt") or {}).get("title") or "(untitled)"
                log_line("close note: %s" % title)
                for line in snap.get("log") or []:
                    log_line("  log: %s" % line)
                snap = self.raw_act({"type": "cancel"})
                continue
            self.persist()
            raise NeedDecision(snap, "choice")
        self.persist()
        raise NeedDecision(snap, "too many notes")

    def act(self, action, allow=()):
        snap = self.raw_act(action)
        if snap.get("code") == "still_busy":
            snap = self.wait_idle(snap)
        return self.dismiss_or_decide(snap, allow)

    def wait_idle(self, snap):
        deadline = time.time() + 90
        stable = 0
        while time.time() < deadline:
            kind, _options = prompt_parts(snap)
            if kind not in (None, "none"):
                return snap
            time.sleep(0.4)
            previous = (snap.get("x"), snap.get("y"), snap.get("life"))
            snap = self.fill_prompt(self.client.look())
            if snap.get("x") is not None:
                self.floor.add((snap["x"], snap["y"]))
                lines = self.new_lines(snap)
                self.note_view(snap)
                self.note_terrain(lines, snap["x"], snap["y"])
            else:
                lines = []
            current = (snap.get("x"), snap.get("y"), snap.get("life"))
            energy = snap.get("energy") or 0
            if current == previous and not lines and energy >= 1000:
                stable += 1
                if stable >= 3:
                    return snap
            else:
                stable = 0
        return snap

    def cooled_down(self):
        text = " ".join(self.last_lines).lower()
        return any(word in text for word in ("not ready", "cooldown", "冷却", "cannot use", "还没准备"))

    def finish_levelup(self, snap):
        node = find_node(snap, "stat:", ("strength", "力量"))
        if node is None and (snap.get("unused_stats") or 0) > 0:
            self.persist()
            raise NeedDecision(snap, "no strength node")
        for _ in range(8):
            node = find_node(snap, "stat:", ("strength", "力量"))
            if node is None or (snap.get("unused_stats") or 0) <= 0:
                break
            before = snap.get("unused_stats") or 0
            snap = self.act({"type": "adjust", "node": node, "delta": 1}, allow=("adjust",))
            if (snap.get("unused_stats") or 0) >= before:
                break
        node = find_node(snap, "talent:", ("stunning blow", "stunning_blow", "震慑", "晕眩"))
        if node is not None:
            trial = self.act({"type": "adjust", "node": node, "delta": 1}, allow=("adjust",))
            if prompt_parts(trial)[0] == "adjust":
                snap = trial
        finish = find_option(snap, ("finish", "完成", "结束"))
        if finish is None:
            self.persist()
            raise NeedDecision(snap, "levelup has no finish")
        snap = self.act({"type": "choose", "label": finish.get("label") or ""}, allow=("choose", "adjust"))
        yes = find_option(snap, ("yes", "是"))
        labels = {(option.get("label") or "").strip().lower() for option in (snap.get("prompt") or {}).get("options") or []}
        if yes is None or not labels <= {"yes", "no", "cancel", "是", "否", "取消"}:
            self.persist()
            raise NeedDecision(snap, "levelup confirm")
        snap = self.act({"type": "choose", "label": yes.get("label") or ""})
        self.state["levelup_done"] = True
        log_line("levelup accepted, unused stats %s" % snap.get("unused_stats"))
        return snap

    def ensure_levelup(self, snap):
        if self.state.get("levelup_done"):
            return snap
        if prompt_parts(snap)[0] == "adjust":
            return self.finish_levelup(snap)
        opened = self.act({"type": "open_levelup"}, allow=("adjust",))
        if prompt_parts(opened)[0] != "adjust":
            self.state["levelup_done"] = True
            return opened
        return self.finish_levelup(opened)

    def talent(self, snap, part):
        try:
            sheet = self.client.look("actor")
        except GameError:
            return None
        for talent in sheet.get("talents") or []:
            if part in (talent.get("id") or "") and not talent.get("cooldown"):
                return talent["id"]
        return None

    def try_use(self, snap, talent_id, allow):
        if not talent_id:
            return snap, False
        updated = self.act({"type": "use", "id": talent_id}, allow=allow)
        return updated, updated.get("status") != "failed"

    def fight(self, snap):
        hostiles = [actor for actor in snap.get("actors") or [] if is_hostile(actor)]
        if not hostiles:
            return None
        x, y = snap["x"], snap["y"]
        turn = self.state["turn"]
        ratio = (snap.get("life") or 0) / max(snap.get("max_life") or 1, 1)
        if ratio < 0.6 and turn >= self.state.get("heal_retry", 0):
            before = snap.get("life") or 0
            healing = self.talent(snap, "HEALING") or self.talent(snap, "REGENERATION")
            updated, used = self.try_use(snap, healing, allow=())
            if used and not self.cooled_down() and (updated.get("life") or 0) > before + 0.5:
                log_line("heal %s -> %s" % (round(before, 1), round(updated.get("life") or 0, 1)))
                return updated
            self.state["heal_retry"] = turn + 8
            snap = updated
            hostiles = [actor for actor in snap.get("actors") or [] if is_hostile(actor)]
            if not hostiles:
                return snap
        adjacent = [actor for actor in hostiles if chebyshev(x, y, actor["x"], actor["y"]) <= 1]
        if len(adjacent) >= 2 and turn >= self.state.get("shout_retry", 0):
            updated, used = self.try_use(snap, self.talent(snap, "WARSHOUT"), allow=("aim",))
            if used and prompt_parts(updated)[0] == "aim":
                target = min(hostiles, key=lambda actor: chebyshev(x, y, actor["x"], actor["y"]))
                updated = self.act({"type": "aim", "direction": facing(x, y, target["x"], target["y"])})
                log_line("warshout toward %s" % target.get("name"))
                return updated
            self.state["shout_retry"] = self.state["turn"] + 6
            if used and not self.cooled_down():
                log_line("warshout at %s hostiles" % len(adjacent))
                return updated
            snap = updated
        if adjacent and turn >= self.state.get("stun_retry", 0):
            target = min(adjacent, key=lambda actor: actor.get("life") or 0)
            updated, used = self.try_use(snap, self.talent(snap, "STUNNING"), allow=("aim",))
            if used and prompt_parts(updated)[0] == "aim":
                updated = self.act({"type": "aim", "target_id": target["id"]})
                log_line("stun %s" % target.get("name"))
                return updated
            if used and not self.cooled_down():
                log_line("stun without aim on %s" % target.get("name"))
                return updated
            self.state["stun_retry"] = turn + 6
            snap = updated
        if adjacent:
            target = min(adjacent, key=lambda actor: actor.get("life") or 0)
            return self.step_onto(snap, target["x"], target["y"], attack=True)
        target = min(hostiles, key=lambda actor: chebyshev(x, y, actor["x"], actor["y"]))
        direction = toward(x, y, target["x"], target["y"], self.blocked)
        if direction is None:
            return None
        destination = (x + DELTAS[direction][0], y + DELTAS[direction][1])
        return self.step_onto(snap, destination[0], destination[1], attack=destination == (target["x"], target["y"]))

    def step_onto(self, snap, tx, ty, attack):
        direction = DIR_OF.get((tx - snap["x"], ty - snap["y"]))
        if direction is None:
            return None
        self.state["last_attempt"] = [tx, ty]
        moved_from = (snap["x"], snap["y"])
        updated = self.act({"type": "step", "direction": direction})
        arrived = (updated.get("x"), updated.get("y"))
        if arrived != moved_from:
            self.soft.pop((tx, ty), None)
            return updated
        if attack:
            names = ", ".join(actor.get("name") or "?" for actor in updated.get("actors") or [] if is_hostile(actor))
            log_line("attack %s,%s still %s/%s foes=%s" % (tx, ty, round(updated.get("life") or 0, 1), round(updated.get("max_life") or 0, 1), names))
            return updated
        lines = " ".join(self.last_lines).lower()
        if "door" in lines or "门" in lines:
            log_line("opened a door toward %s,%s" % (tx, ty))
            self.soft.pop((tx, ty), None)
            return updated
        count = self.soft.get((tx, ty), 0) + 1
        self.soft[(tx, ty)] = count
        if count >= 2:
            self.blocked.add((tx, ty))
            log_line("blocked %s,%s" % (tx, ty))
        return updated

    def explore(self, snap):
        x, y = snap["x"], snap["y"]
        if (x, y) in self.stairs_down and not adjacent_hostile(snap):
            self.state["last_attempt"] = [x, y]
            updated = self.act({"type": "change_level"}, allow=("choose",))
            if updated.get("zone") == "trollmire" and updated.get("level") == 2:
                raise StopPlay(0, "entered trollmire level 2 at %s,%s life %s/%s" % (
                    updated.get("x"), updated.get("y"), round(updated.get("life") or 0, 1), round(updated.get("max_life") or 0, 1),
                ))
            kind, _options = prompt_parts(updated)
            if kind not in (None, "none"):
                self.persist()
                raise NeedDecision(updated, "stairs")
            log_line("change_level did not leave level 1 at %s,%s" % (x, y))
            self.stairs_down.discard((x, y))
            return updated
        direction = self.frontier_direction(snap)
        if direction is None:
            self.persist()
            raise StopPlay(4, "no route left. down=%s up=%s floor=%s blocked=%s" % (
                pair_list(self.stairs_down), pair_list(self.stairs_up), len(self.floor), len(self.blocked),
            ))
        dx, dy = DELTAS[direction]
        return self.step_onto(snap, x + dx, y + dy, attack=False)

    def frontier_direction(self, snap):
        start = (snap["x"], snap["y"])
        occupied = {(actor["x"], actor["y"]) for actor in snap.get("actors") or []}
        previous = {start: None}
        queue = deque([start])
        while queue:
            cx, cy = queue.popleft()
            for direction in CARDINALS:
                dx, dy = DELTAS[direction]
                nxt = (cx + dx, cy + dy)
                if nxt in self.blocked or nxt in occupied or nxt in self.refused:
                    continue
                if nxt not in self.floor:
                    return self.first_direction(previous, start, (cx, cy), direction)
                if nxt not in previous:
                    previous[nxt] = (cx, cy)
                    queue.append(nxt)
        return None

    def first_direction(self, previous, start, floor_cell, into_unknown):
        if floor_cell == start:
            return into_unknown
        current = floor_cell
        parent = previous[current]
        while parent != start:
            current = parent
            parent = previous[current]
        return DIR_OF[(current[0] - start[0], current[1] - start[1])]

    def rest_if_hurt(self, snap):
        life = snap.get("life") or 0
        maximum = snap.get("max_life") or 1
        if life >= maximum * 0.85:
            return snap
        if any(is_hostile(actor) for actor in snap.get("actors") or []):
            return snap
        log_line("rest at %s/%s" % (round(life, 1), round(maximum, 1)))
        updated = self.act({"type": "rest"})
        self.state["heal_retry"] = 0
        return updated

    def play(self, snap, note_initial):
        snap = self.dismiss_or_decide(snap, allow=("aim",))
        if prompt_parts(snap)[0] == "aim":
            foes = [actor for actor in snap.get("actors") or [] if is_hostile(actor)]
            if foes:
                target = min(foes, key=lambda actor: chebyshev(snap["x"], snap["y"], actor["x"], actor["y"]))
                direction = facing(snap["x"], snap["y"], target["x"], target["y"])
                snap = self.act({"type": "aim", "direction": direction})
                log_line("aim %s toward %s" % (direction, target.get("name")))
            else:
                snap = self.act({"type": "cancel"})
        if snap.get("zone") != "trollmire" or snap.get("level") not in (1, 2):
            raise StopPlay(1, "expected trollmire level 1, got %s level %s" % (snap.get("zone"), snap.get("level")))
        if snap.get("level") == 2:
            raise StopPlay(0, "already on level 2")
        self.floor.add((snap["x"], snap["y"]))
        if note_initial:
            self.note_terrain(snap.get("log") or [], snap["x"], snap["y"])
        self.state["prev_log"] = snap.get("log") or []
        try:
            sheet = self.client.look("actor")
        except GameError:
            sheet = {}
        talents = ", ".join(talent.get("id", "") for talent in sheet.get("talents") or [])
        log_line(
            "start %s,%s life %s/%s char_level=%s hand=%s talents=%s"
            % (snap.get("x"), snap.get("y"), round(snap.get("life") or 0, 1), round(snap.get("max_life") or 0, 1), snap.get("character_level"), snap.get("mainhand"), talents)
        )
        snap = self.ensure_levelup(snap)
        while self.state["turn"] < MAX_ACTIONS:
            if snap.get("zone") == "trollmire" and snap.get("level") == 2:
                raise StopPlay(0, "entered level 2")
            snap = self.dismiss_or_decide(snap, allow=())
            fought = self.fight(snap)
            if fought is not None:
                snap = fought
            else:
                rested = self.rest_if_hurt(snap)
                if rested is not snap:
                    snap = rested
                else:
                    snap = self.explore(snap)
            if self.state["turn"] % 25 == 0:
                hostiles = [actor.get("name") for actor in snap.get("actors") or [] if is_hostile(actor)]
                log_line(
                    "t=%s pos=%s,%s life=%s/%s char_level=%s floor=%s down=%s foes=%s"
                    % (
                        self.state["turn"], snap.get("x"), snap.get("y"),
                        round(snap.get("life") or 0, 1), round(snap.get("max_life") or 0, 1),
                        snap.get("character_level"),
                        len(self.floor), pair_list(self.stairs_down), ",".join(hostiles),
                    )
                )
            self.persist()
        raise StopPlay(4, "stopped after %s actions at %s,%s" % (MAX_ACTIONS, snap.get("x"), snap.get("y")))

    def apply_answer(self, snap, answer, option_id):
        title = ((snap.get("prompt") or {}).get("title") or "").strip().lower()
        if title == "finish":
            self.state["levelup_done"] = True
        if answer == "cancel":
            self.block_attempt()
            return self.act({"type": "cancel"})
        if option_id:
            chosen = self.act({"type": "choose", "label": option_id})
            label = ""
            return chosen if label else chosen
        if answer == "no":
            option = find_option(snap, ("no", "否", "cancel", "leave", "不", "离开"))
            if option is None:
                self.persist()
                raise NeedDecision(snap, "no matching refuse button")
            self.block_attempt()
            return self.act({"type": "choose", "label": option.get("label") or ""})
        if answer == "yes":
            option = find_option(snap, ("yes", "是", "accept", "确定"))
            if option is None:
                self.persist()
                raise NeedDecision(snap, "no matching accept button")
            return self.act({"type": "choose", "label": option.get("label") or ""})
        return snap

    def block_attempt(self):
        attempt = self.state.get("last_attempt")
        if not attempt:
            return
        point = (attempt[0], attempt[1])
        self.blocked.add(point)
        self.refused.add(point)
        self.stairs_down.discard(point)
        log_line("refused %s,%s" % point)


def is_hostile(actor):
    if "relation" in actor:
        return (actor.get("relation") or 0) < 0
    return bool(actor.get("hostile"))


def prompt_parts(snap):
    prompt = snap.get("prompt") or {}
    kind = prompt.get("kind") or snap.get("prompt_kind")
    return kind, prompt.get("options") or snap.get("options") or []


def find_option(snap, names):
    wanted = {name.lower() for name in names}
    for option in (snap.get("prompt") or {}).get("options") or []:
        label = (option.get("label") or "").strip().lower()
        if label in wanted or any(name in label for name in wanted if len(name) > 3):
            return option
    return None


def find_node(snap, prefix, names):
    for node in (snap.get("prompt") or {}).get("nodes") or []:
        identity = node.get("node") or ""
        label = (node.get("label") or "").lower()
        if not identity.startswith(prefix):
            continue
        if any(name.lower() in identity.lower() or name.lower() in label for name in names):
            return identity
    return None


def adjacent_hostile(snap):
    for actor in snap.get("actors") or []:
        if actor.get("hostile") and chebyshev(snap["x"], snap["y"], actor["x"], actor["y"]) <= 1:
            return True
    return False


def chebyshev(x1, y1, x2, y2):
    return max(abs(x1 - x2), abs(y1 - y2))


def facing(x, y, tx, ty):
    return DIR_OF.get(((tx > x) - (tx < x), (ty > y) - (ty < y)), 6)


def toward(x, y, tx, ty, blocked):
    best = None
    best_distance = chebyshev(x, y, tx, ty)
    for direction in CARDINALS:
        dx, dy = DELTAS[direction]
        nxt = (x + dx, y + dy)
        if nxt in blocked:
            continue
        distance = chebyshev(nxt[0], nxt[1], tx, ty)
        if distance < best_distance and (best is None or distance < best[0]):
            best = (distance, direction)
    return None if best is None else best[1]


def describe(snap, reason):
    prompt = snap.get("prompt") or {}
    lines = [
        "DECISION %s" % reason,
        "pos=%s,%s zone=%s level=%s life=%s/%s" % (
            snap.get("x"), snap.get("y"), snap.get("zone"), snap.get("level"),
            round(snap.get("life") or 0, 1), round(snap.get("max_life") or 0, 1),
        ),
        "title: %s" % (prompt.get("title") or ""),
        "kind: %s" % prompt.get("kind"),
        "text: %s" % (prompt.get("text") or ""),
    ]
    for option in prompt.get("options") or []:
        lines.append("option: %s id=%s" % (option.get("label"), option.get("option_id")))
    for node in prompt.get("nodes") or []:
        lines.append("node: %s %s" % (node.get("node"), node.get("label")))
        if node.get("desc"):
            lines.append("  %s" % node.get("desc"))
    foes = []
    for actor in snap.get("actors") or []:
        if is_hostile(actor):
            foes.append("%s@%s,%s %s/%s" % (actor.get("name"), actor.get("x"), actor.get("y"), actor.get("life"), actor.get("max_life")))
    lines.append("foes: %s" % "; ".join(foes))
    lines.append("log:")
    for line in snap.get("log") or []:
        lines.append("  %s" % line)
    return "\n".join(lines)


def launch_birth():
    import drive_game
    from birth_cornac_berserker import NAME, prepare_vault

    me = os.getpid()
    proc = Path("/proc")
    if proc.is_dir():
        for entry in proc.iterdir():
            if not entry.name.isdigit():
                continue
            pid = int(entry.name)
            if pid == me:
                continue
            try:
                command = (entry / "cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", "replace")
            except OSError:
                continue
            if "drive_game.py" in command:
                os.kill(pid, signal.SIGTERM)
                print("stopped driver %s" % pid, flush=True)
    display = drive_game.Desktop(
        os.environ.get("DISPLAY", ":10.0"),
        os.environ.get("XAUTHORITY", str(Path.home() / ".Xauthority")),
    )
    game_dir = Path.home() / "tome-test" / "t-engine4-linux64-1.7.6"
    addon = Path(__file__).resolve().parents[1] / "tome-auto-tome"
    drive_game.install_addon(addon, game_dir / "game" / "addons" / "tome-auto-tome")
    drive_game.stop_game()
    prepare_vault()
    # Leave the birth level-up and the welcome note on screen so look can read them.
    extra = 'auto_quickbirth="%s" birth_done_script=[==[game.paused = false]==]' % NAME
    drive_game.launch_game(
        game_dir,
        Path.home() / "tome-test" / "tome.log",
        display,
        ["./t-engine", "-Mtome", "-n", "-E" + extra],
    )
    display.start_wiggle()
    return display


def wait_for_window(client):
    deadline = time.time() + 120
    last = None
    while time.time() < deadline:
        try:
            client.connect()
            last = client.look()
        except (OSError, TimeoutError, GameError):
            client.close()
            time.sleep(0.4)
            continue
        kind = last.get("prompt_kind") or (last.get("prompt") or {}).get("kind")
        if last.get("in_game") and kind not in (None, "none"):
            return last
        time.sleep(0.3)
    return last


def main():
    parser = argparse.ArgumentParser(description="Play Trollmire level 1 through look and act.")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--answer", choices=("cancel", "no", "yes"))
    parser.add_argument("--option", default="")
    parser.add_argument("--birth", action="store_true", help="Restart as a new Cornac Berserker and read the birth windows.")
    args = parser.parse_args()

    holder = None
    if args.birth:
        holder = launch_birth()
    if args.resume:
        state = load_state()
    else:
        if LOG_PATH.exists():
            LOG_PATH.unlink()
        state = fresh_state()
        save_state(state)

    client = GameClient()
    player = Player(client, state)
    try:
        if holder is not None:
            snap = wait_for_window(client)
            if not snap or not snap.get("in_game"):
                log_line("birth did not reach a level")
                return 2
        else:
            client.connect()
            snap = client.look()
        if args.resume and (args.answer or args.option):
            snap = player.apply_answer(snap, args.answer, args.option)
        player.play(snap, note_initial=not args.resume)
    except NeedDecision as decision:
        player.persist()
        log_line(describe(decision.snap, decision.reason))
        return 3
    except StopPlay as stop:
        player.persist()
        log_line(str(stop))
        return stop.code
    except (OSError, TimeoutError) as error:
        log_line("bridge unavailable: %s" % error)
        return 2
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
