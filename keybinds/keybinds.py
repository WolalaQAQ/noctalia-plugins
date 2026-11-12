#!/usr/bin/env python3
"""读取 Umbriel 快捷键和输入法热键，输出给速查表面板的 JSON。

Umbriel 的 [keybinds] 不能写说明，这里按动作名翻译成中文；没翻译到的动作用
`umbriel msg --help` 里的英文说明兜底，所以配置里新加的快捷键也会出现。
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tomllib

HOME = os.path.expanduser("~")
UMBRIEL_CONFIG = os.path.join(HOME, ".config/umbriel/config.toml")
FCITX_CONFIG = os.path.join(HOME, ".config/fcitx5/config")
RIME_BUILD = os.path.join(HOME, ".local/share/fcitx5/rime/build/default.yaml")

GROUPS = ["常用", "窗口", "焦点", "平铺布局", "工作区", "暂存区", "系统", "输入法",
          "Kitty 标签页", "Kitty 分屏", "Kitty 复制与滚动", "Kitty 其他", "硬件按键"]

# Umbriel 自己的分组 → 这里的分组（没翻译到的动作用）
UMBRIEL_GROUPS = {
    "Apps": "常用", "Focus": "焦点", "Move & size": "平铺布局", "Windows": "窗口",
    "Scratchpad": "暂存区", "Workspaces": "工作区", "Overview": "工作区",
    "System": "系统", "Screencasting": "系统",
}

# 动作 → (分组, 说明, 备注)
ACTIONS = {
    "window-close": ("常用", "关闭窗口", None),
    "window-kill": ("窗口", "强制结束窗口的程序", None),
    "window-minimize": ("窗口", "最小化", None),
    "window-restore-minimized": ("窗口", "恢复最近最小化的窗口", None),
    "window-toggle-fullscreen": ("窗口", "全屏 / 退出全屏", None),
    "window-toggle-maximize-to-edges": ("窗口", "贴边最大化 / 还原", "不留间距，去掉边框、圆角和标题栏"),
    "window-toggle-maximize": ("窗口", "最大化 / 还原", "保留间距和圆角；滚动平铺里是当前列占满宽度"),
    "window-toggle-floating": ("窗口", "切换浮动 / 平铺", "滚动平铺工作区里用"),
    "window-toggle-pinned": ("窗口", "窗口置顶 / 取消置顶", None),
    "window-clear-region": ("窗口", "取消贴靠，恢复原来的位置和大小", None),
    "window-center": ("窗口", "浮动窗口居中", None),
    "window-focus-left": ("焦点", "切到左边的窗口", None),
    "window-focus-right": ("焦点", "切到右边的窗口", None),
    "window-focus-up": ("焦点", "切到上面的窗口", None),
    "window-focus-down": ("焦点", "切到下面的窗口", None),
    "window-focus-next": ("焦点", "切到下一个窗口", None),
    "window-focus-previous": ("焦点", "切到上一个窗口", None),
    "window-focus-last": ("焦点", "切回上一次用的窗口", None),
    "window-focus-switch-floating": ("焦点", "在浮动和平铺窗口之间切换焦点", None),
    "column-move-left": ("平铺布局", "整列左移", None),
    "column-move-right": ("平铺布局", "整列右移", None),
    "window-move-up": ("平铺布局", "窗口在列内上移", "浮动窗口：贴到上边"),
    "window-move-down": ("平铺布局", "窗口在列内下移", "浮动窗口：贴到下边"),
    "window-move-left": ("平铺布局", "窗口左移", "浮动窗口：贴到左边"),
    "window-move-right": ("平铺布局", "窗口右移", "浮动窗口：贴到右边"),
    "window-cycle-primary-extent": ("平铺布局", "循环切换窗口宽度预设", None),
    "window-cycle-primary-extent-back": ("平铺布局", "反向循环切换窗口宽度", None),
    "window-consume-left": ("平铺布局", "把窗口并入左边那列", None),
    "window-consume-right": ("平铺布局", "把窗口并入右边那列", None),
    "window-consume-from-left": ("平铺布局", "把左边那列的窗口拉进当前列", None),
    "window-consume-from-right": ("平铺布局", "把右边那列的窗口拉进当前列", None),
    "column-toggle-tabbed": ("平铺布局", "当前列切换成标签页 / 改回上下排列", None),
    "column-focus-tab-next": ("平铺布局", "下一个标签页", None),
    "column-focus-tab-previous": ("平铺布局", "上一个标签页", None),
    "column-center": ("平铺布局", "当前列居中", None),
    "layout-toggle-split": ("平铺布局", "切换分割方向", "dwindle 布局"),
    "overview-toggle": ("工作区", "工作区概览", None),
    "workspace-next": ("工作区", "下一个工作区", None),
    "workspace-previous": ("工作区", "上一个工作区", None),
    "workspace-focus-last": ("工作区", "切回上一个工作区", None),
    "workspace-toggle-show-desktop": ("常用", "显示桌面 / 恢复窗口", "恢复时之前手动最小化的窗口也会一起出来"),
    "window-move-to-scratchpad": ("暂存区", "把窗口收进暂存区", "暂存区：随叫随到的隐藏窗口"),
    "scratchpad-toggle": ("暂存区", "显示 / 隐藏暂存区窗口", None),
    "window-restore-from-scratchpad": ("暂存区", "把暂存区窗口放回原工作区", None),
    "scratchpad-focus-next": ("暂存区", "切到下一个暂存区窗口", None),
    "window-toggle-scratchpad": ("暂存区", "窗口收进 / 移出暂存区", None),
    "session-quit": ("系统", "退出登录", "会先弹确认"),
    "shortcuts-inhibit-toggle": ("系统", "暂停 / 恢复所有快捷键", "远程桌面、虚拟机里用，再按一次恢复"),
    "cheatsheet-toggle": ("系统", "Umbriel 自带的英文速查表", None),
    "config-reload": ("系统", "重新加载 Umbriel 配置", None),
    "keyboard-layout-next": ("系统", "切换键盘布局", None),
}

# spawn 命令 → (分组, 说明)，按顺序匹配第一条
SPAWNS = [
    (r"panel-toggle wolala/keybinds:panel", "常用", "快捷键速查表（就是这个面板）"),
    (r"panel-toggle launcher", "常用", "应用启动器"),
    (r"panel-toggle control-center", "常用", "控制中心"),
    (r"settings-toggle", "常用", "Noctalia 设置"),
    (r"window-switcher hold reverse", "常用", "反向切换窗口"),
    (r"window-switcher hold", "常用", "切换窗口（按住 Alt 连按 Tab）"),
    (r"screenshot-annotate", "常用", "截图并标注"),
    (r"screenshot", "常用", "截图"),
    (r"volume-up", "硬件按键", "音量加"),
    (r"volume-down", "硬件按键", "音量减"),
    (r"volume-mute", "硬件按键", "静音"),
    (r"media toggle", "硬件按键", "播放 / 暂停"),
    (r"media next", "硬件按键", "下一首"),
    (r"media previous", "硬件按键", "上一首"),
    (r"brightness-up", "硬件按键", "屏幕亮度加"),
    (r"brightness-down", "硬件按键", "屏幕亮度减"),
    (r"^konsole\b", "常用", "打开终端（Konsole）"),
    (r"^kitty\b", "常用", "打开终端（Kitty）"),
    (r"session lock", "常用", "锁屏"),
    (r"panel-toggle clipboard", "常用", "剪贴板历史"),
    (r"^dolphin\b", "常用", "打开文件管理器（Dolphin）"),
]

KEY_NAMES = {
    "Mod": "Super", "Ctrl": "Ctrl", "Control": "Ctrl", "Shift": "Shift", "Alt": "Alt",
    "Return": "Enter", "Escape": "Esc", "Space": "空格", "Tab": "Tab",
    "Left": "←", "Right": "→", "Up": "↑", "Down": "↓",
    "Comma": ",", "Period": ".", "Minus": "-", "Equal": "=", "Grave": "`", "grave": "`",
    "Slash": "/", "Backslash": "\\", "Semicolon": ";", "Apostrophe": "'",
    "BracketLeft": "[", "BracketRight": "]", "Print": "PrtSc",
    "Page_Up": "PgUp", "Page_Down": "PgDn", "Delete": "Del", "BackSpace": "退格",
    "WheelUp": "滚轮↑", "WheelDown": "滚轮↓", "WheelLeft": "滚轮←", "WheelRight": "滚轮→",
    "XF86AudioRaiseVolume": "音量+", "XF86AudioLowerVolume": "音量-", "XF86AudioMute": "静音键",
    "XF86AudioPlay": "播放键", "XF86AudioNext": "下一首键", "XF86AudioPrev": "上一首键",
    "XF86MonBrightnessUp": "亮度+", "XF86MonBrightnessDown": "亮度-",
}


def keycaps(combo):
    return [KEY_NAMES.get(p, p) for p in combo.split("+")]


def umbriel_help():
    """动作名 → (Umbriel 分组, 英文说明)"""
    try:
        text = subprocess.run(["umbriel", "msg", "--help"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    table, group = {}, None
    for line in text.splitlines():
        if line and not line.startswith(" ") and not line.startswith(("Usage", "Send", "Arguments", "Available")):
            group = line.strip()
        m = re.match(r"^  (\S+)(?: [<\[].*?)?\s{2,}(\S.*)$", line)
        if m and group:
            table[m.group(1)] = (group, m.group(2).strip())
    return table


def describe(action, help_table):
    """返回 (分组, 说明, 备注)"""
    action = action.strip()
    if action.startswith("spawn "):
        cmd = action[6:].strip()
        for pattern, group, desc in SPAWNS:
            if re.search(pattern, cmd):
                return group, desc, None
        return "常用", f"运行 {cmd}", None

    name, _, arg = action.partition(" ")
    arg = arg.strip()
    if name == "workspace-switch":
        return "工作区", f"切换到工作区 {arg}", None
    if name in ("window-move-to-workspace", "column-move-to-workspace"):
        return "工作区", f"把窗口移到工作区 {arg}", None
    if name == "window-move-to-workspace-silent":
        return "工作区", f"把窗口移到工作区 {arg}（不跟过去）", None
    if name == "workspace-set-layout":
        label = {"scrolling": "滚动平铺", "stacking": "浮动（传统桌面）", "dwindle": "dwindle 平铺",
                 "master": "主从平铺"}.get(arg, arg)
        return "工作区", f"当前工作区改成{label}", None
    if name == "window-set-region":
        region = {"left": "左半屏", "right": "右半屏", "top": "上半屏", "bottom": "下半屏",
                  "top_left": "左上 1/4", "top_right": "右上 1/4",
                  "bottom_left": "左下 1/4", "bottom_right": "右下 1/4"}.get(arg, arg)
        return "窗口", f"窗口贴到{region}", None
    if name in ("window-modify-primary-extent", "window-modify-secondary-extent"):
        what = "宽度" if "primary" in name else "高度"
        try:
            pct = float(arg) * 100
            change = f"{'加' if pct > 0 else '减'} {abs(pct):g}%"
        except ValueError:
            change = arg
        return "平铺布局", f"窗口{what}{change}", None
    if name in ACTIONS:
        return ACTIONS[name]
    if name in help_table:
        ugroup, english = help_table[name]
        return UMBRIEL_GROUPS.get(ugroup, "系统"), english, action
    return "系统", action, None


def merge_numbered(rows):
    """Super+1 … Super+9 这种只差一个数字、说明里也是这个数字的，合成一行。"""
    buckets, out = {}, []
    for row in rows:
        m = re.search(r"(?<=\+)(\d)$", row["combo"])
        if m and m.group(1) in row["desc"]:
            n = m.group(1)
            key = (row["combo"][:-1], row["desc"].replace(n, "{n}"), row["group"])
            if key not in buckets:
                buckets[key] = {**row, "desc": key[1], "_nums": []}
                out.append(buckets[key])
            buckets[key]["_nums"].append(int(n))
        else:
            out.append(row)
    for row in out:
        nums = row.pop("_nums", None)
        if nums is None:
            continue
        if len(nums) == 1:
            row["desc"] = row["desc"].replace("{n}", str(nums[0]))
            row["combo"] = row["combo"][:-1] + str(nums[0])
        else:
            row["combo"] = row["combo"][:-1] + f"{min(nums)}…{max(nums)}"
            row["desc"] = row["desc"].replace("{n}", f"{min(nums)}–{max(nums)}")
    return out


def umbriel_rows():
    with open(UMBRIEL_CONFIG, "rb") as f:
        config = tomllib.load(f)
    help_table = umbriel_help()
    rows = []
    for combo, value in (config.get("keybinds") or {}).items():
        action = value.get("action") if isinstance(value, dict) else value
        if not isinstance(action, str):
            continue
        group, desc, note = describe(action, help_table)
        rows.append({"combo": combo, "group": group, "desc": desc, "note": note, "action": action})
    rows = merge_numbered(rows)
    # Umbriel 内置的鼠标操作，不在 [keybinds] 里
    rows.append({"combo": "Mod+左键拖动", "group": "窗口", "desc": "移动窗口", "note": "在窗口任意位置按住，没有标题栏的窗口也能拖"})
    rows.append({"combo": "Mod+右键拖动", "group": "窗口", "desc": "调整窗口大小", "note": None})
    return rows


def input_method_rows():
    rows = []
    try:
        text = open(FCITX_CONFIG, encoding="utf-8").read()
    except OSError:
        return rows
    m = re.search(r"^\[Hotkey/TriggerKeys\]\n((?:\d+=.*\n?)+)", text, re.M)
    for line in (m.group(1).splitlines() if m else []):
        key = line.split("=", 1)[1].strip()
        if key in ("Zenkaku_Hankaku", "Hangul"):
            continue
        if key == "Alt+Shift+Shift_L":
            key = "Alt+Shift"
        rows.append({"combo": key.replace("space", "Space"), "group": "输入法", "desc": "切换输入法", "note": "fcitx5"})
    try:
        rime = open(RIME_BUILD, encoding="utf-8").read()
    except OSError:
        return rows
    if re.search(r"^\s+Shift_L:\s*commit_code", rime, re.M):
        rows.append({"combo": "Shift", "group": "输入法", "desc": "中 / 英切换",
                     "note": "单按左 Shift，已打的字母直接上屏"})
    sw = re.search(r"^switcher:.*?^  hotkeys:\n((?:    - [^\n]*\n)+)", rime, re.M | re.S)
    if sw:
        keys = [k.strip()[2:].strip().strip('"').replace("Control", "Ctrl") for k in sw.group(1).splitlines()]
        if keys:
            rows.append({"combo": keys[0], "alts": keys[1:], "group": "输入法",
                         "desc": "Rime 方案选单", "note": "简繁、全半角、中英标点"})
    return rows


KITTY_CONFIG = os.path.expanduser("~/.config/kitty/kitty.conf")

# Kitty 自带的默认键（kitty_mod = ctrl+shift）；只列常用的。kitty.conf 里的 map 会覆盖同一个键
KITTY_DEFAULTS = [
    ("ctrl+shift+t", "new_tab"),
    ("ctrl+shift+q", "close_tab"),
    ("ctrl+shift+right", "next_tab"), ("ctrl+tab", "next_tab"),
    ("ctrl+shift+left", "previous_tab"), ("ctrl+shift+tab", "previous_tab"),
    ("ctrl+shift+period", "move_tab_forward"),
    ("ctrl+shift+comma", "move_tab_backward"),
    ("ctrl+shift+alt+t", "set_tab_title"),
    ("ctrl+shift+enter", "new_window"),
    ("ctrl+shift+w", "close_window"),
    ("ctrl+shift+]", "next_window"),
    ("ctrl+shift+[", "previous_window"),
    ("ctrl+shift+1", "first_window"),
    ("ctrl+shift+f", "move_window_forward"),
    ("ctrl+shift+b", "move_window_backward"),
    ("ctrl+shift+r", "start_resizing_window"),
    ("ctrl+shift+l", "next_layout"),
    ("ctrl+shift+c", "copy_to_clipboard"),
    ("ctrl+shift+v", "paste_from_clipboard"),
    ("ctrl+shift+up", "scroll_line_up"),
    ("ctrl+shift+down", "scroll_line_down"),
    ("ctrl+shift+page_up", "scroll_page_up"),
    ("ctrl+shift+page_down", "scroll_page_down"),
    ("ctrl+shift+h", "show_scrollback"),
    ("ctrl+shift+g", "show_last_command_output"),
    ("ctrl+shift+z", "scroll_to_prompt -1"),
    ("ctrl+shift+x", "scroll_to_prompt 1"),
    ("ctrl+shift+e", "open_url_with_hints"),
    ("ctrl+shift+equal", "increase_font_size"),
    ("ctrl+shift+minus", "decrease_font_size"),
    ("ctrl+shift+backspace", "restore_font_size"),
    ("ctrl+shift+n", "new_os_window"),
    ("ctrl+shift+f11", "toggle_fullscreen"),
    ("ctrl+shift+f2", "edit_config_file"),
    ("ctrl+shift+f5", "load_config_file"),
]

KITTY_ACTIONS = {
    "new_tab": ("Kitty 标签页", "新建标签页", None),
    "new_tab_with_cwd": ("Kitty 标签页", "新建标签页", "在当前目录打开"),
    "close_tab": ("Kitty 标签页", "关闭标签页", None),
    "next_tab": ("Kitty 标签页", "下一个标签页", None),
    "previous_tab": ("Kitty 标签页", "上一个标签页", None),
    "move_tab_forward": ("Kitty 标签页", "标签页右移", None),
    "move_tab_backward": ("Kitty 标签页", "标签页左移", None),
    "set_tab_title": ("Kitty 标签页", "重命名标签页", None),
    "new_window": ("Kitty 分屏", "新建窗格", "按当前布局自动排列"),
    "new_window_with_cwd": ("Kitty 分屏", "新建窗格", "在当前目录打开"),
    "close_window": ("Kitty 分屏", "关闭窗格", None),
    "next_window": ("Kitty 分屏", "下一个窗格", None),
    "previous_window": ("Kitty 分屏", "上一个窗格", None),
    "first_window": ("Kitty 分屏", "跳到第 N 个窗格", "Ctrl+Shift+1 到 0"),
    "move_window_forward": ("Kitty 分屏", "窗格前移", "不是搜索（Konsole 的 Ctrl+Shift+F）"),
    "move_window_backward": ("Kitty 分屏", "窗格后移", None),
    "start_resizing_window": ("Kitty 分屏", "调整窗格大小", "按下后按提示操作"),
    "next_layout": ("Kitty 分屏", "切换布局", "横排、竖排、网格、单窗格放大…"),
    "copy_to_clipboard": ("Kitty 复制与滚动", "复制", None),
    "paste_from_clipboard": ("Kitty 复制与滚动", "粘贴", None),
    "scroll_line_up": ("Kitty 复制与滚动", "向上滚一行", None),
    "scroll_line_down": ("Kitty 复制与滚动", "向下滚一行", None),
    "scroll_page_up": ("Kitty 复制与滚动", "向上翻页", None),
    "scroll_page_down": ("Kitty 复制与滚动", "向下翻页", None),
    "show_scrollback": ("Kitty 复制与滚动", "查看全部历史输出", "在里面按 / 搜索"),
    "show_last_command_output": ("Kitty 复制与滚动", "只看上一条命令的输出", None),
    "scroll_to_prompt -1": ("Kitty 复制与滚动", "跳到上一个命令提示符", None),
    "scroll_to_prompt 1": ("Kitty 复制与滚动", "跳到下一个命令提示符", None),
    "open_url_with_hints": ("Kitty 复制与滚动", "选中屏幕上的链接并打开", None),
    "increase_font_size": ("Kitty 其他", "字号变大", None),
    "decrease_font_size": ("Kitty 其他", "字号变小", None),
    "restore_font_size": ("Kitty 其他", "字号还原", None),
    "new_os_window": ("Kitty 其他", "新开 Kitty 窗口", None),
    "new_os_window_with_cwd": ("Kitty 其他", "新开 Kitty 窗口", "在当前目录打开"),
    "toggle_fullscreen": ("Kitty 其他", "全屏", None),
    "edit_config_file": ("Kitty 其他", "编辑配置", None),
    "load_config_file": ("Kitty 其他", "重新加载配置", None),
}

KITTY_KEYS = {
    "enter": "Return", "return": "Return", "tab": "Tab", "escape": "Escape", "space": "Space",
    "backspace": "BackSpace", "delete": "Delete", "page_up": "Page_Up", "page_down": "Page_Down",
    "left": "Left", "right": "Right", "up": "Up", "down": "Down", "home": "Home", "end": "End",
    "period": "Period", "comma": "Comma", "equal": "Equal", "minus": "Minus", "plus": "+",
    "left_bracket": "[", "right_bracket": "]", "slash": "Slash", "backslash": "Backslash",
    "ctrl": "Ctrl", "control": "Ctrl", "shift": "Shift", "alt": "Alt", "opt": "Alt",
    "super": "Mod", "cmd": "Mod",
}


def kitty_combo(key, kitty_mod):
    parts = []
    for p in key.replace("kitty_mod", kitty_mod).split("+"):
        if p in KITTY_KEYS:
            parts.append(KITTY_KEYS[p])
        elif re.fullmatch(r"f\d+", p):
            parts.append(p.upper())
        else:
            parts.append(p.upper() if len(p) == 1 else p)
    return "+".join(parts)


def kitty_rows():
    if not shutil.which("kitty"):
        return []
    binds = dict(KITTY_DEFAULTS)
    order = [k for k, _ in KITTY_DEFAULTS]
    kitty_mod = "ctrl+shift"
    try:
        lines = open(KITTY_CONFIG, encoding="utf-8").read().splitlines()
    except OSError:
        lines = []
    for line in lines:
        f = line.split(None, 1)
        if len(f) == 2 and f[0] == "kitty_mod":
            kitty_mod = f[1].strip()
    for line in lines:
        f = line.split(None, 2)
        if len(f) == 3 and f[0] == "map":
            key = f[1].replace("kitty_mod", kitty_mod)
            if key not in binds:
                order.append(key)
            binds[key] = f[2].strip()
    rows = []
    for key in order:
        label = KITTY_ACTIONS.get(binds[key])
        if label:
            group, desc, note = label
            rows.append({"combo": kitty_combo(key, kitty_mod), "group": group, "desc": desc, "note": note,
                         "action": binds[key]})
    return rows


def build():
    rows = umbriel_rows() + input_method_rows() + kitty_rows()
    # 同一个动作绑了几个键（比如单按 Super 和 Super+空格）合成一行
    merged, seen = [], {}
    for row in rows:
        key = (row["group"], row["desc"])
        if key in seen:
            seen[key]["combos"].append(row["combo"])
            continue
        row["combos"] = [row["combo"]] + row.pop("alts", [])
        seen[key] = row
        merged.append(row)
    groups = []
    for name in GROUPS:
        items = []
        for row in merged:
            if row["group"] != name:
                continue
            combos = [{"caps": keycaps(c), "tap": c in ("Mod", "Shift")} for c in row["combos"]]
            search = " ".join([name, row["desc"], row.get("note") or "", row.get("action") or "", *row["combos"],
                               *("+".join(c["caps"]) for c in combos)]).lower()
            items.append({"combos": combos, "desc": row["desc"], "note": row.get("note"), "search": search})
        if items:
            groups.append({"name": name, "items": items})
    return {"groups": groups}


def main():
    try:
        data = build()
    except Exception as exc:  # noqa: BLE001 — 面板要显示原因
        print(json.dumps({"groups": [], "error": f"读取快捷键失败：{exc}"}, ensure_ascii=False))
        return 1
    print(json.dumps(data, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
