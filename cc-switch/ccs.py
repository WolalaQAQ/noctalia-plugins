#!/usr/bin/env python3
"""CC Switch 的数据和操作，给 Noctalia 插件用。

  ccs.py state                       应用、供应商、模式、轻量模式（托盘菜单 + 数据库里的图标）
  ccs.py quota [--force]             Codex 官方订阅额度（缓存 5 分钟）
  ccs.py usage <today|7d|30d|all|ranges>  用量汇总和趋势（只读数据库，口径同 CC Switch；ranges 一次给出四个范围）
  ccs.py click <app> <provider>      切换供应商
  ccs.py subitem <app> <label>       点应用子菜单里的普通项（“打开 Claude Code 页面”）
  ccs.py item <label>                点顶层菜单项（可只写开头，如“Grok Build”）

切换和其他操作都是点击 CC Switch 的托盘菜单（DBus com.canonical.dbusmenu），走它自己的逻辑。
菜单 id 每次重建都会变，所以每次重新读取、按文字匹配。
"""
import datetime as dt
import json
import os
import sqlite3
import subprocess
import sys
import time
import urllib.request

HOME = os.path.expanduser("~")
DB = f"{HOME}/.cc-switch/cc-switch.db"
LIVE_STATE = f"{HOME}/.cc-switch/live-state.json"
CODEX_AUTH = f"{HOME}/.codex/auth.json"
CACHE_DIR = f"{HOME}/.cache/noctalia-cc-switch"
QUOTA_TTL = 300
WARN_BELOW = 20.0

WATCHER = ("org.kde.StatusNotifierWatcher", "/StatusNotifierWatcher", "org.kde.StatusNotifierWatcher")

APP_IDS = {
    "Claude Code": "claude", "Claude Desktop": "claude-desktop", "Codex": "codex",
    "Gemini CLI": "gemini", "Grok Build": "grokbuild", "OpenCode": "opencode",
    "OpenClaw": "openclaw", "Hermes": "hermes", "Pi": "pi", "MiniMax Code": "mcode",
    "Kimi Code": "kimi", "DeepSeek Harness": "dsh", "Antigravity": "agy",
    "Oh My Pi": "omp", "Copilot CLI": "copilot",
}
APP_ICONS = {"claude": "claude", "claude-desktop": "claude", "codex": "openai",
             "gemini": "gemini", "grokbuild": "grok"}
APP_BADGES = {"claude": "terminal-2", "claude-desktop": "device-desktop"}
PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))


def out(obj):
    print(json.dumps(obj, ensure_ascii=False))


# ── 托盘菜单 ──────────────────────────────────────────────────────────────────────

def busctl(*args):
    res = subprocess.run(["busctl", "--user", "--json=short", *args],
                         capture_output=True, text=True, timeout=5)
    if res.returncode != 0:
        raise RuntimeError(res.stderr.strip() or "busctl failed")
    return json.loads(res.stdout) if res.stdout.strip() else None


def find_menu():
    items = busctl("get-property", *WATCHER, "RegisteredStatusNotifierItems")["data"]
    for item in items:
        if "cc_switch" in item:
            slash = item.index("/")
            bus, path = item[:slash], item[slash:]
            menu = busctl("get-property", bus, path, "org.kde.StatusNotifierItem", "Menu")["data"]
            return bus, menu
    return None


def layout(bus, menu):
    return busctl("call", bus, menu, "com.canonical.dbusmenu", "GetLayout", "iias",
                  "--", "0", "-1", "0")["data"][1]


def props(node):
    return {k: v["data"] for k, v in node[1].items()}


def children(node):
    return [c["data"] for c in node[2]]


def text(label):
    return label.replace("__", "_")


def click(bus, menu, item_id):
    busctl("call", bus, menu, "com.canonical.dbusmenu", "Event", "isvu",
           str(item_id), "clicked", "s", "", str(int(time.time())))


def provider_meta():
    """(app_type, name) -> {icon, color, official}，只读数据库。"""
    meta = {}
    try:
        con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=2)
        for app, name, icon, color, category in con.execute(
                "SELECT app_type, name, icon, icon_color, category FROM providers"):
            meta[(app, name)] = {"icon": icon, "color": color, "official": category == "official"}
        con.close()
    except sqlite3.Error:
        pass
    return meta


def icon_path(name):
    if not name:
        return None
    path = os.path.join(PLUGIN_DIR, "icons", f"{name}.svg")
    return path if os.path.exists(path) else None


def cmd_state():
    found = find_menu()
    if found is None:
        return out({"running": False, "apps": [], "lightweight": False})
    root = layout(*found)
    meta = provider_meta()
    try:
        modes = json.load(open(LIVE_STATE)).get("apps", {})
    except (OSError, ValueError):
        modes = {}

    apps, lightweight = [], False
    for node in children(root):
        p = props(node)
        label = text(p.get("label", ""))
        if p.get("toggle-type") == "checkmark" and label == "轻量模式":
            lightweight = p.get("toggle-state") == 1
            continue
        name, _, detail = label.partition(" · ")
        app_id = APP_IDS.get(name)
        if app_id is None:
            continue
        app = {
            "id": app_id, "name": name, "detail": detail,
            "icon": icon_path(APP_ICONS.get(app_id)), "badge": APP_BADGES.get(app_id),
            "current": None, "mode": None,
            "modeKind": (modes.get(app_id) or {}).get("mode", "direct"),
            "providers": [], "extras": [], "add": None, "official": False,
        }
        if p.get("children-display") != "submenu":
            app["add"] = detail or "添加供应商…"
            apps.append(app)
            continue
        for child in children(node):
            c = props(child)
            clabel = text(c.get("label", ""))
            if c.get("type") == "separator":
                continue
            if c.get("toggle-type") == "checkmark":
                m = meta.get((app_id, clabel), {})
                current = c.get("toggle-state") == 1
                app["providers"].append({
                    "label": clabel, "current": current,
                    "icon": icon_path(m.get("icon")), "color": m.get("color"),
                })
                if current:
                    app["current"] = clabel
                    app["official"] = m.get("official", False)
            elif c.get("enabled") is False and app["mode"] is None:
                app["mode"] = clabel
            elif clabel:
                app["extras"].append(clabel)
        apps.append(app)
    out({"running": True, "apps": apps, "lightweight": lightweight})


def cmd_click(app, provider):
    found = find_menu()
    if found is None:
        raise RuntimeError("CC Switch 没有运行")
    for node in children(layout(*found)):
        if text(props(node).get("label", "")).partition(" · ")[0] != app:
            continue
        for child in children(node):
            c = props(child)
            if text(c.get("label", "")) == provider:
                click(*found, child[0])
                return
    raise RuntimeError(f"找不到：{app} / {provider}")


def cmd_item(label):
    found = find_menu()
    if found is None:
        raise RuntimeError("CC Switch 没有运行")
    nodes = children(layout(*found))
    for exact in (True, False):
        for node in nodes:
            t = text(props(node).get("label", ""))
            if (t == label) if exact else t.startswith(label):
                click(*found, node[0])
                return
    raise RuntimeError(f"找不到菜单项：{label}")


# ── Codex 额度 ──────────────────────────────────────────────────────────────────────

TIER_NAMES = {18000: "5 小时", 604800: "每周", 2592000: "每月"}


def chatgpt_get(url, token, account, extra=None):
    headers = {"Authorization": f"Bearer {token}", "User-Agent": "codex-cli", "Accept": "application/json"}
    if account:
        headers["ChatGPT-Account-Id"] = account
    headers.update(extra or {})
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=10) as res:
        return json.loads(res.read())


def fetch_codex_quota():
    auth = json.load(open(CODEX_AUTH))
    if auth.get("auth_mode") != "chatgpt":
        return None
    tokens = auth.get("tokens") or {}
    token, account = tokens.get("access_token"), tokens.get("account_id")
    if not token:
        return None
    usage = chatgpt_get("https://chatgpt.com/backend-api/wham/usage", token, account)
    lines = []
    rate = usage.get("rate_limit") or {}
    for window in (rate.get("primary_window"), rate.get("secondary_window")):
        if not window or window.get("used_percent") is None:
            continue
        used = float(window["used_percent"])
        secs = window.get("limit_window_seconds")
        tier = TIER_NAMES.get(secs) or (f"{secs // 86400} 天" if secs and secs >= 86400 else f"{(secs or 0) // 3600} 小时")
        left = max(0.0, 100.0 - used)
        lines.append({
            "tier": tier, "left": round(left),
            "resetsAt": window.get("reset_at") if used > 0 else None,
            "warn": left < WARN_BELOW,
        })
    credits = None
    try:
        body = chatgpt_get("https://chatgpt.com/backend-api/wham/rate-limit-reset-credits",
                           token, account, {"OpenAI-Beta": "codex-1"})
        now = dt.datetime.now(dt.timezone.utc)
        credits = 0
        for credit in body.get("credits") or []:
            if credit.get("status") != "available":
                continue
            exp = credit.get("expires_at")
            try:
                if exp and dt.datetime.fromisoformat(exp.replace("Z", "+00:00")) <= now:
                    continue
            except ValueError:
                pass
            credits += 1
    except Exception:  # noqa: BLE001  重置次数只是附带信息
        credits = None
    return {"lines": lines, "resetCredits": credits}


def cmd_quota(force):
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache = os.path.join(CACHE_DIR, "codex-quota.json")
    try:
        cached = json.load(open(cache))
    except (OSError, ValueError):
        cached = None
    if cached and not force and time.time() - cached.get("at", 0) < QUOTA_TTL:
        return out(cached)
    try:
        result = {"at": time.time(), "codex": fetch_codex_quota(), "error": None}
    except Exception as exc:  # noqa: BLE001
        result = {"at": time.time(), "codex": (cached or {}).get("codex"), "error": str(exc)}
    json.dump(result, open(cache, "w"))
    out(result)


# ── 用量统计（口径照搬 CC Switch services/usage_stats.rs）─────────────────────────────

CACHE_INCLUSIVE = "('codex', 'gemini', 'grokbuild')"
SESSION_SOURCES = "('session_log', 'codex_session', 'gemini_session', 'opencode_session')"
DEDUP_WINDOW = 600


def fresh_input(a):
    return (f"CASE WHEN {a}.input_token_semantics = 2 THEN {a}.input_tokens "
            f"WHEN {a}.app_type IN {CACHE_INCLUSIVE} AND {a}.input_token_semantics = 1 "
            f"AND {a}.input_tokens >= ({a}.cache_read_tokens + {a}.cache_creation_tokens) "
            f"THEN ({a}.input_tokens - {a}.cache_read_tokens - {a}.cache_creation_tokens) "
            f"WHEN {a}.app_type IN {CACHE_INCLUSIVE} AND {a}.input_token_semantics = 0 "
            f"AND {a}.input_tokens >= {a}.cache_read_tokens "
            f"THEN ({a}.input_tokens - {a}.cache_read_tokens) ELSE {a}.input_tokens END")


def dedup_filter(con, start, end):
    """代理日志和会话日志都有时，去掉和代理记录重复的会话记录。"""
    proxy, session = con.execute(
        f"SELECT COALESCE(SUM(CASE WHEN COALESCE(data_source,'proxy')='proxy' "
        f"AND status_code BETWEEN 200 AND 299 THEN 1 ELSE 0 END),0), "
        f"COALESCE(SUM(CASE WHEN COALESCE(data_source,'proxy') IN {SESSION_SOURCES} THEN 1 ELSE 0 END),0) "
        f"FROM proxy_request_logs WHERE created_at BETWEEN ? AND ?",
        (start - DEDUP_WINDOW, end + DEDUP_WINDOW)).fetchone()
    if proxy == 0 or session == 0:
        return "1 = 1"
    return (f"l.rowid NOT IN (SELECT s.rowid FROM proxy_request_logs p JOIN proxy_request_logs s "
            f"ON s.app_type IN (p.app_type, CASE WHEN p.app_type='claude-desktop' THEN 'claude' ELSE p.app_type END) "
            f"AND COALESCE(s.data_source,'proxy') IN {SESSION_SOURCES} "
            f"AND s.input_tokens = p.input_tokens AND s.output_tokens = p.output_tokens "
            f"AND s.cache_read_tokens = p.cache_read_tokens "
            f"AND s.created_at BETWEEN p.created_at - {DEDUP_WINDOW} AND p.created_at + {DEDUP_WINDOW} "
            f"WHERE COALESCE(p.data_source,'proxy') = 'proxy')")


def local_day(ts):
    return dt.datetime.fromtimestamp(ts).date()


def rollup_bounds(start, end):
    """只数被范围完整覆盖的自然日的汇总行。"""
    s, e = dt.datetime.fromtimestamp(start), dt.datetime.fromtimestamp(end)
    first = s.date() if (s.hour, s.minute, s.second) == (0, 0, 0) else s.date() + dt.timedelta(days=1)
    last = e.date() if (e.hour, e.minute) == (23, 59) else e.date() - dt.timedelta(days=1)
    return first.isoformat(), last.isoformat()


def usage_for(rng):
    now = int(time.time())
    today = dt.datetime.combine(dt.date.today(), dt.time())
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=5)
    if rng == "today":
        start = int(today.timestamp())
    elif rng in ("7d", "30d"):
        start = int((today - dt.timedelta(days=int(rng[:-1]) - 1)).timestamp())
    else:
        firsts = [r[0] for r in con.execute(
            "SELECT MIN(date(created_at,'unixepoch','localtime')) FROM proxy_request_logs "
            "UNION ALL SELECT MIN(date) FROM usage_daily_rollups") if r[0]]
        if not firsts:
            return {"range": rng, "summary": None, "trend": []}
        start = int(dt.datetime.fromisoformat(min(firsts)).timestamp())
        start = min(start, now - 86400 - 1)
    end = now

    dedup = dedup_filter(con, start, end)
    fi_l, fi_r = fresh_input("l"), fresh_input("r")
    d = con.execute(
        f"SELECT COUNT(*), COALESCE(SUM(CAST(l.total_cost_usd AS REAL)),0), COALESCE(SUM({fi_l}),0), "
        f"COALESCE(SUM(l.output_tokens),0), COALESCE(SUM(l.cache_creation_tokens),0), "
        f"COALESCE(SUM(l.cache_read_tokens),0) FROM proxy_request_logs l "
        f"WHERE {dedup} AND l.created_at >= ? AND l.created_at <= ?", (start, end)).fetchone()
    rfirst, rlast = rollup_bounds(start, end)
    r = con.execute(
        f"SELECT COALESCE(SUM(r.request_count),0), COALESCE(SUM(CAST(r.total_cost_usd AS REAL)),0), "
        f"COALESCE(SUM({fi_r}),0), COALESCE(SUM(r.output_tokens),0), "
        f"COALESCE(SUM(r.cache_creation_tokens),0), COALESCE(SUM(r.cache_read_tokens),0) "
        f"FROM usage_daily_rollups r WHERE r.date >= ? AND r.date <= ?", (rfirst, rlast)).fetchone()
    req, cost, inp, outp, cw, cr = (a + b for a, b in zip(d, r))
    cacheable = inp + cw + cr
    summary = {
        "requests": req, "cost": cost, "input": inp, "output": outp,
        "cacheWrite": cw, "cacheRead": cr, "total": inp + outp + cw + cr,
        "hitRate": (cr / cacheable) if cacheable else 0.0,
    }

    trend = []
    if end - start <= 86400:
        buckets = max(1, (end - start + 3599) // 3600)
        rows = dict((int(b), (n, c, t)) for b, n, c, t in con.execute(
            f"SELECT CAST((l.created_at - ?) / 3600 AS INTEGER) b, COUNT(*), "
            f"COALESCE(SUM(CAST(l.total_cost_usd AS REAL)),0), COALESCE(SUM({fi_l} + l.output_tokens),0) "
            f"FROM proxy_request_logs l WHERE l.created_at >= ? AND l.created_at <= ? AND {dedup} GROUP BY b",
            (start, start, end)))
        for i in range(buckets):
            n, c, t = rows.get(i, (0, 0.0, 0))
            at = dt.datetime.fromtimestamp(start + i * 3600)
            trend.append({"label": at.strftime("%H:00"), "tip": f"{at.month}月{at.day}日 {at:%H}:00",
                          "requests": n, "cost": c, "tokens": t})
    else:
        rows = {}
        for day, n, c, t in con.execute(
                f"SELECT date(l.created_at,'unixepoch','localtime') d, COUNT(*), "
                f"COALESCE(SUM(CAST(l.total_cost_usd AS REAL)),0), COALESCE(SUM({fi_l} + l.output_tokens),0) "
                f"FROM proxy_request_logs l WHERE l.created_at >= ? AND l.created_at <= ? AND {dedup} GROUP BY d",
                (start, end)):
            rows[day] = [n, c, t]
        for day, n, c, t in con.execute(
                f"SELECT r.date, SUM(r.request_count), COALESCE(SUM(CAST(r.total_cost_usd AS REAL)),0), "
                f"COALESCE(SUM({fi_r} + r.output_tokens),0) FROM usage_daily_rollups r "
                f"WHERE r.date >= ? AND r.date <= ? GROUP BY r.date", (rfirst, rlast)):
            acc = rows.setdefault(day, [0, 0.0, 0])
            acc[0] += n
            acc[1] += c
            acc[2] += t
        day, last = local_day(start), local_day(end)
        while day <= last:
            n, c, t = rows.get(day.isoformat(), (0, 0.0, 0))
            trend.append({"label": f"{day.month}/{day.day}", "tip": f"{day.year}年{day.month}月{day.day}日",
                          "requests": n, "cost": c, "tokens": t})
            day += dt.timedelta(days=1)
    con.close()
    return {"range": rng, "summary": summary if req else None, "trend": trend}


RANGES = ("today", "7d", "30d", "all")


def cmd_usage(rng):
    if rng == "ranges":
        return out({r: usage_for(r) for r in RANGES})
    out(usage_for(rng))


def main():
    args = sys.argv[1:] or ["state"]
    cmd = args[0]
    if cmd == "state":
        cmd_state()
    elif cmd == "quota":
        cmd_quota("--force" in args)
    elif cmd == "usage" and len(args) == 2:
        cmd_usage(args[1])
    elif cmd == "click" and len(args) == 3:
        cmd_click(args[1], args[2])
    elif cmd == "subitem" and len(args) == 3:
        cmd_click(args[1], args[2])
    elif cmd == "item" and len(args) == 2:
        cmd_item(args[1])
    else:
        print(__doc__, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print(str(exc), file=sys.stderr)
        sys.exit(1)
