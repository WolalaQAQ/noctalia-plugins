--!nonstrict
-- CC Switch 面板，对应 CC Switch 自己的托盘快捷面板：
--   配置页  每个应用一行（当前供应商 · 模式、额度），点进去是供应商列表（搜索、使用中）
--   用量页  时间范围、四格汇总、趋势图
--   底栏    打开主窗口、退出
--
-- 不做悬停高亮：每次悬停都要整棵树重建，鼠标快速划过时会拖影，还会吃掉点击。
-- 需要悬停反馈的地方用 ui.button，它自带悬停效果。

local common = require("./common.luau")

local snapshot = { loaded = false, running = false, apps = {} }
local usage = { loading = false, ranges = nil }

local tab = "config"          -- config | usage
local openApp = nil           -- 子页里的应用 id
local query = ""
local range = "today"
local metric = "tokens"

local RANGES = { { "today", "今天" }, { "7d", "7 天" }, { "30d", "30 天" }, { "all", "全部" } }
local METRICS = { { "tokens", "Token" }, { "requests", "请求" }, { "cost", "费用" } }
-- 面板 380 - 外边距 24 - 卡片内边距 20 - Y 轴 40 - 滚动条余量
local CHART_WIDTH = 262
local CHART_HEIGHT = 110
local MAX_BARS = 31
local MODE_COLORS = { direct = "primary", route = "secondary", stack = "tertiary" }
local AVATAR_COLORS = { "#cc7e8b", "#7aa2f7", "#9ece6a", "#e0af68", "#bb9af7", "#7dcfff", "#f7768e" }

local render

local function rerender()
  if render ~= nil then
    render()
  end
end

-- 分段切换（配置/用量、时间范围、指标）
local function segmented(key, options, value, onChange, small)
  local buttons = {}
  for _, option in ipairs(options) do
    local id, label = option[1], option[2]
    local selected = id == value
    table.insert(buttons, ui.button({
      key = key .. ":" .. id,
      text = label,
      variant = selected and "secondary" or "ghost",
      controlSize = "sm",
      flexGrow = small and 0 or 1,
      onClick = function()
        if not selected then
          onChange(id)
        end
      end,
    }))
  end
  return ui.row({ gap = 2, padding = 2, radius = small and 8 or 10, fill = "on_surface/0.07" }, buttons)
end

-- 图标：品牌 SVG，没有就用首字母头像
local function avatar(label, icon, color, size)
  if type(icon) == "string" then
    return ui.image({ path = icon, width = size, height = size })
  end
  local first = string.upper(string.sub(label or "?", 1, 1))
  if color == nil then
    local sum = 0
    for i = 1, #(label or "") do
      sum += string.byte(label, i)
    end
    color = AVATAR_COLORS[(sum % #AVATAR_COLORS) + 1]
  end
  return ui.column({
    width = size, height = size, radius = size / 2,
    fill = color .. "33", align = "center", justify = "center",
  }, {
    ui.label({ text = first, fontSize = math.floor(size * 0.55), fontWeight = "bold", color = color }),
  })
end

local function appIcon(app)
  local children = {}
  if type(app.icon) == "string" then
    table.insert(children, ui.image({ path = app.icon, width = 20, height = 20 }))
  else
    table.insert(children, ui.glyph({ name = common.GLYPH, size = 18, color = "on_surface_variant" }))
  end
  return ui.column({
    width = 34, height = 34, radius = 9, fill = "on_surface/0.07",
    align = "center", justify = "center",
  }, children)
end

-- 额度：“每周剩余 99%  ━━━━  6天19小时后重置”，下面是可重置次数
local function quotaBlock(quota)
  local rows = {}
  for _, line in ipairs(quota.lines or {}) do
    local left = tonumber(line.left) or 0
    local color = left <= 0 and "error" or (line.warn and "#e0af68" or "primary")
    local when = common.resetIn(line.resetsAt)
    local children = {
      ui.label({ text = `{line.tier}剩余 {left}%`, fontSize = 11, color = line.warn and "#e0af68" or "on_surface_variant" }),
      ui.progress({ progress = math.max(left, 2) / 100, fill = color, track = "on_surface/0.12", radius = 2, height = 4, width = when ~= nil and 72 or 160 }),
    }
    if when ~= nil then
      table.insert(children, ui.label({ text = when, fontSize = 10, color = "on_surface_variant" }))
    end
    table.insert(rows, ui.row({ gap = 8, align = "center" }, children))
  end
  if type(quota.resetCredits) == "number" and quota.resetCredits > 0 then
    table.insert(rows, ui.label({ text = `可重置 {quota.resetCredits} 次`, fontSize = 11, color = "on_surface_variant" }))
  end
  if #rows == 0 then
    return nil
  end
  return ui.column({ gap = 4, paddingV = 2 }, rows)
end

-- Codex 官方订阅的额度；接口没取到时退回托盘菜单里的“每周剩余 99%”
local function quotaFor(app)
  if app.id ~= "codex" or app.official ~= true then
    return nil
  end
  local q = snapshot.quota and snapshot.quota.codex
  if type(q) == "table" and #(q.lines or {}) > 0 then
    return q
  end
  local tier, left = string.match(app.detail or "", "·%s*(%S+)剩余%s*(%d+)%%")
  if left ~= nil then
    return { lines = { { tier = tier, left = tonumber(left), warn = tonumber(left) < 20 } } }
  end
  return nil
end

-- ── 配置页 ────────────────────────────────────────────────────────────────────────

local function appRow(app)
  local key = "app:" .. app.id
  local title = { ui.label({ text = app.name, fontSize = 13, fontWeight = "bold" }) }
  if app.badge ~= nil then
    table.insert(title, ui.glyph({ name = app.badge, size = 12, color = "on_surface_variant" }))
  end

  local subtitle
  if app.add ~= nil then
    subtitle = ui.label({ text = app.add, fontSize = 11, color = "on_surface_variant" })
  else
    local parts = {}
    if app.current ~= nil then
      table.insert(parts, ui.label({ text = app.current .. " ·", fontSize = 11, color = "on_surface_variant", maxLines = 1 }))
    end
    table.insert(parts, ui.label({ text = app.mode or "直连", fontSize = 11, fontWeight = "bold", color = MODE_COLORS[app.modeKind] or "primary" }))
    subtitle = ui.row({ gap = 4, align = "center" }, parts)
  end

  local body = { ui.row({ gap = 6, align = "center" }, title), subtitle }
  local quota = quotaFor(app)
  local block = quota ~= nil and quotaBlock(quota) or nil

  local main = ui.row({ gap = 12, align = "start" }, {
    appIcon(app),
    ui.column({ gap = 2, flexGrow = 1 }, body),
    ui.column({ height = 34, justify = "center" }, {
      ui.glyph({ name = app.add ~= nil and "plus" or "chevron-right", size = 16, color = "on_surface_variant" }),
    }),
  })
  local rows = { main }
  if block ~= nil then
    table.insert(rows, ui.row({ gap = 0 }, { ui.spacer({ width = 46, flexGrow = 0 }), ui.column({ flexGrow = 1 }, { block }) }))
  end

  return ui.column({
    key = key, gap = 4, padding = 8, radius = 10,
    onClick = function()
      if app.add ~= nil then
        common.request("item", { label = app.name })
        panel.close()
      else
        openApp = app.id
        query = ""
        rerender()
      end
    end,
  }, rows)
end

local function configTab()
  local rows = {}
  for _, app in ipairs(snapshot.apps or {}) do
    table.insert(rows, appRow(app))
  end
  if #rows == 0 then
    table.insert(rows, ui.label({ text = snapshot.loaded and "没有应用" or "读取中…", color = "on_surface_variant", fontSize = 12 }))
  end
  return rows
end

-- ── 供应商子页 ──────────────────────────────────────────────────────────────────

local function providerRow(app, provider)
  local key = "prov:" .. app.id .. ":" .. provider.label
  local current = provider.current == true
  local children = {
    ui.column({ width = 24, height = 24, align = "center", justify = "center" }, {
      current and ui.glyph({ name = "check", size = 18, color = "primary" })
        or avatar(provider.label, provider.icon, provider.color, 20),
    }),
    ui.label({ text = provider.label, fontSize = 13, fontWeight = current and "bold" or "normal", flexGrow = 1, maxLines = 1 }),
  }
  if current then
    table.insert(children, ui.label({ text = "使用中", fontSize = 11, fontWeight = "bold", color = "primary" }))
  end
  return ui.row({
    key = key, gap = 10, paddingH = 10, paddingV = 7, radius = 8, align = "center",
    fill = current and "primary/0.10" or nil,
    opacity = snapshot.busy == true and 0.6 or 1,
    onClick = function()
      if not current and snapshot.busy ~= true then
        common.request("switch", { app = app.name, provider = provider.label })
      end
    end,
  }, children)
end

local function subPage(app)
  local rows = {
    ui.row({ gap = 6, align = "center" }, {
      ui.button({ glyph = "chevron-left", variant = "ghost", tooltip = "返回", onClick = function()
        openApp = nil
        rerender()
      end }),
      appIcon(app),
      ui.column({ gap = 0, flexGrow = 1 }, {
        ui.label({ text = app.name, fontSize = 14, fontWeight = "bold" }),
        ui.label({ text = snapshot.busy == true and "切换中…" or "切换供应商", fontSize = 11, color = snapshot.busy == true and "primary" or "on_surface_variant" }),
      }),
    }),
  }

  local providers = app.providers or {}
  if #providers > 4 then
    table.insert(rows, ui.input({
      key = "search:" .. app.id,
      value = query,
      placeholder = "搜索供应商…",
      controlSize = "sm",
      onChange = function(value)
        query = tostring(value)
        rerender()
      end,
    }))
  end

  local needle = string.lower(noctalia.string.trim(query))
  local list = {}
  if needle == "" and app.mode ~= nil then
    table.insert(list, ui.row({ paddingH = 10 }, { ui.label({ text = app.mode, fontSize = 11, color = "on_surface_variant" }) }))
  end
  for _, provider in ipairs(providers) do
    if needle == "" or string.find(string.lower(provider.label), needle, 1, true) then
      table.insert(list, providerRow(app, provider))
    end
  end
  if needle ~= "" and #list == 0 then
    table.insert(list, ui.row({ paddingH = 10 }, { ui.label({ text = "没有匹配的供应商", fontSize = 12, color = "on_surface_variant" }) }))
  end
  if needle == "" and #(app.extras or {}) > 0 then
    table.insert(list, ui.separator({}))
    for _, extra in ipairs(app.extras) do
      table.insert(list, ui.button({
        key = "extra:" .. app.id .. ":" .. extra,
        text = extra,
        glyph = "external-link",
        variant = "ghost",
        contentAlign = "start",
        onClick = function()
          common.request("subitem", { app = app.name, label = extra })
          panel.close()
        end,
      }))
    end
  end
  table.insert(rows, ui.column({ gap = 2 }, list))
  return rows
end

-- ── 用量页 ────────────────────────────────────────────────────────────────────────

local function stat(label, value, detail)
  local children = {
    ui.label({ text = label, fontSize = 11, color = "on_surface_variant" }),
    ui.label({ text = value, fontSize = 17, fontWeight = "bold" }),
  }
  if detail ~= nil then
    table.insert(children, ui.label({ text = detail, fontSize = 10, color = "on_surface_variant", maxLines = 1 }))
  end
  return ui.column({ flexGrow = 1, flexBasis = 0, gap = 1, paddingH = 10, paddingV = 8, radius = 10, fill = "on_surface/0.06" }, children)
end

local function loadUsage()
  common.request("usage")
end

local function usageTab()
  local rows = {
    segmented("range", RANGES, range, function(id)
      range = id
      rerender()
    end, false),
  }

  local data = usage.ranges and usage.ranges[range] or nil
  local summary = data and data.summary
  if summary == nil then
    local text = data == nil and "读取中…" or "这段时间没有用量记录"
    if usage.error ~= nil and not usage.loading then
      text = usage.error
    end
    table.insert(rows, ui.column({ height = 120, align = "center", justify = "center" }, {
      ui.label({ text = text, fontSize = 12, color = "on_surface_variant" }),
    }))
    return rows
  end

  table.insert(rows, ui.row({ gap = 6 }, {
    stat("总费用", common.money(summary.cost, 2)),
    stat("请求数", common.int(summary.requests)),
  }))
  table.insert(rows, ui.row({ gap = 6 }, {
    stat("总 Token", common.tokens(summary.total), `输入 {common.tokens(summary.input)} · 输出 {common.tokens(summary.output)}`),
    stat("缓存命中率", common.percent(summary.hitRate), `写入 {common.tokens(summary.cacheWrite)} · 读取 {common.tokens(summary.cacheRead)}`),
  }))

  -- 柱状图，照 CC Switch 托盘面板：Y 轴 3 个刻度、X 轴首中尾、柱子最宽 18、超过 31 根就把相邻几根并成一根。
  -- 悬停信息用控件自带的 tooltip，不触发重绘。
  local points = {}
  local trend = data.trend or {}
  local size = math.max(1, math.ceil(#trend / MAX_BARS))
  for i = 1, #trend, size do
    local first, last = trend[i], trend[math.min(i + size - 1, #trend)]
    local sum = 0
    for j = i, math.min(i + size - 1, #trend) do
      sum += tonumber(trend[j][metric]) or 0
    end
    table.insert(points, {
      value = sum,
      label = first.label,
      tip = size > 1 and `{first.tip or first.label} – {last.tip or last.label}` or (first.tip or first.label),
    })
  end

  local function fmt(v)
    if metric == "cost" then
      return common.money(v, v < 1 and 4 or 2)
    elseif metric == "requests" then
      return common.int(v)
    end
    return common.tokens(v)
  end
  local function tick(v)
    if metric == "cost" then
      return "$" .. common.compact(v)
    end
    return common.compact(v)
  end

  local peak = 0
  for _, point in ipairs(points) do
    peak = math.max(peak, point.value)
  end
  local top = common.niceCeil(peak)

  local rangeLabel = ""
  for _, r in ipairs(RANGES) do
    if r[1] == range then
      rangeLabel = r[2]
    end
  end

  local chart = {
    ui.row({ gap = 8, align = "center", width = CHART_WIDTH + 40 }, {
      ui.label({ text = rangeLabel .. "趋势", fontSize = 11, fontWeight = "bold", color = "on_surface_variant" }),
      ui.spacer({ flexGrow = 1 }),
      segmented("metric", METRICS, metric, function(id)
        metric = id
        rerender()
      end, true),
    }),
  }

  if peak > 0 then
    local slotWidth = CHART_WIDTH / #points
    local barWidth = math.max(2, math.min(18, math.floor(slotWidth * 0.7)))
    local slots = {}
    for i, point in ipairs(points) do
      local h = point.value > 0 and math.max(2, math.floor(point.value / top * CHART_HEIGHT + 0.5)) or 0
      local bar = {}
      if h > 0 then
        table.insert(bar, ui.box({ width = barWidth, height = h, radius = math.min(3, barWidth / 2), fill = "primary" }))
      end
      table.insert(slots, ui.column({
        key = `bar:{range}:{metric}:{i}`,
        flexGrow = 1, flexBasis = 0, height = CHART_HEIGHT,
        align = "center", justify = "end",
        tooltip = `{point.tip}\n{fmt(point.value)}`,
      }, bar))
    end

    local yAxis = ui.column({ width = 34, height = CHART_HEIGHT, justify = "space_between" }, {
      ui.label({ text = tick(top), fontSize = 10, color = "on_surface_variant", textAlign = "right" }),
      ui.label({ text = tick(top / 2), fontSize = 10, color = "on_surface_variant", textAlign = "right" }),
      ui.label({ text = "0", fontSize = 10, color = "on_surface_variant", textAlign = "right" }),
    })
    local xLabels = { ui.label({ text = points[1].label, fontSize = 10, color = "on_surface_variant" }), ui.spacer({ flexGrow = 1 }) }
    if #points >= 3 then
      table.insert(xLabels, ui.label({ text = points[math.floor((#points + 1) / 2)].label, fontSize = 10, color = "on_surface_variant" }))
      table.insert(xLabels, ui.spacer({ flexGrow = 1 }))
    end
    if #points >= 2 then
      table.insert(xLabels, ui.label({ text = points[#points].label, fontSize = 10, color = "on_surface_variant" }))
    end
    table.insert(chart, ui.row({ gap = 6, align = "start" }, {
      yAxis,
      ui.column({ flexGrow = 1, gap = 4 }, {
        ui.row({ width = CHART_WIDTH, height = CHART_HEIGHT, gap = 0, align = "end" }, slots),
        ui.box({ width = CHART_WIDTH, height = 1, fill = "on_surface/0.18" }),
        ui.row({ width = CHART_WIDTH }, xLabels),
      }),
    }))
  else
    table.insert(chart, ui.column({ height = CHART_HEIGHT + 16, align = "center", justify = "center" }, {
      ui.label({ text = "这段时间没有数据", fontSize = 11, color = "on_surface_variant" }),
    }))
  end
  table.insert(rows, ui.column({ gap = 6, padding = 10, radius = 10, fill = "on_surface/0.06" }, chart))
  return rows
end

-- ── 底栏 ──────────────────────────────────────────────────────────────────────────

local function footer()
  local function button(key, glyph, text, onClick)
    return ui.button({ key = key, text = text, glyph = glyph, variant = "ghost", contentAlign = "start", flexGrow = 1, onClick = onClick })
  end
  return ui.column({ gap = 4 }, {
    ui.separator({}),
    ui.row({ gap = 4 }, {
      button("foot:main", "external-link", "打开主窗口", function()
        common.request("item", { label = "打开 CC Switch" })
        panel.close()
      end),
      button("foot:quit", "power", "退出", function()
        common.request("item", { label = "退出 CC Switch" })
        panel.close()
      end),
    }),
  })
end

-- ── 整体 ──────────────────────────────────────────────────────────────────────────

function render()
  local header = ui.row({ align = "center", gap = 8, paddingH = 4 }, {
    ui.glyph({ name = common.GLYPH, size = 18, color = "primary" }),
    ui.label({ text = "CC Switch", fontSize = 15, fontWeight = "bold", flexGrow = 1 }),
    ui.button({ glyph = "refresh", variant = "ghost", tooltip = "刷新", onClick = function()
      common.request("refresh", { quota = true, force = true })
      if tab == "usage" then
        loadUsage()
      end
    end }),
    ui.button({ glyph = "settings", variant = "ghost", tooltip = "打开 CC Switch 设置", enabled = snapshot.running == true, onClick = function()
      common.request("item", { label = "打开 CC Switch" })
      panel.close()
    end }),
  })

  if snapshot.loaded == true and snapshot.running ~= true then
    panel.render(ui.column({ flexGrow = 1, gap = 12, padding = 12 }, {
      header,
      ui.column({ flexGrow = 1, gap = 12, align = "center", justify = "center" }, {
        ui.glyph({ name = common.GLYPH, size = 40, color = "on_surface_variant" }),
        ui.label({ text = "CC Switch 没有在运行", fontSize = 13, color = "on_surface_variant" }),
        ui.button({ text = "启动 CC Switch", glyph = "player-play", variant = "primary", onClick = function() common.request("launch") end }),
      }),
    }))
    return
  end

  local app = openApp and common.findApp(snapshot, openApp) or nil
  if openApp ~= nil and app == nil then
    openApp = nil
  end

  local content
  if app ~= nil then
    content = subPage(app)
  else
    content = tab == "usage" and usageTab() or configTab()
  end
  if type(snapshot.error) == "string" then
    table.insert(content, 1, ui.label({ text = snapshot.error, color = "error", fontSize = 11 }))
  end

  local children = { header }
  if app == nil then
    table.insert(children, segmented("tab", { { "config", "配置" }, { "usage", "用量" } }, tab, function(id)
      tab = id
      if id == "usage" then
        loadUsage()
      end
      rerender()
    end, false))
  end
  table.insert(children, ui.scroll({ flexGrow = 1, gap = 6 }, content))
  table.insert(children, footer())
  panel.render(ui.column({ flexGrow = 1, gap = 10, padding = 12 }, children))
end

function onOpen(_context)
  snapshot = noctalia.state.get("ccs.state") or snapshot
  usage = noctalia.state.get("ccs.usage") or usage
  openApp = nil
  query = ""
  common.request("refresh", { quota = true })
  if tab == "usage" then
    loadUsage()
  end
  render()
end

noctalia.state.watch("ccs.state", function(value)
  if type(value) == "table" then
    snapshot = value
    render()
  end
end)

noctalia.state.watch("ccs.usage", function(value)
  if type(value) == "table" then
    usage = value
    render()
  end
end)
