--!nonstrict
-- 顶栏组件：可用订阅的剩余额度，订阅商图标 + 圆环 + 百分比（目前是 ChatGPT/Codex 订阅）。
-- 没有额度数据时只显示切换图标。点击打开面板。

local common = require("./common.luau")

local snapshot = { loaded = false, running = false, apps = {} }
local RING_SIZE = 16

local ringDir = (function()
  local dir = noctalia.pluginDataDir()
  return dir and (dir .. "/rings") or nil
end)()

-- Noctalia 的 ui 没有圆弧，圆环用小 SVG 画；每个（百分比, 颜色）只写一次。
local function ringImage(percent, fillRole)
  local fill = noctalia.getColor(fillRole) or fillRole
  local track = noctalia.getColor("on_surface")
  if ringDir == nil or type(fill) ~= "string" or type(track) ~= "string" then
    return nil
  end
  local pct = math.max(0, math.min(100, math.floor(percent + 0.5)))
  local path = `{ringDir}/ring-{pct}-{(fill:gsub("#", ""))}-{(track:gsub("#", ""))}.svg`
  if not noctalia.fileExists(path) then
    noctalia.mkdirAll(ringDir)
    local r = 14
    local c = 2 * math.pi * r
    local arc = ""
    if pct > 0 then
      arc = string.format(
        '<circle cx="18" cy="18" r="%d" fill="none" stroke="%s" stroke-width="6" stroke-linecap="round" stroke-dasharray="%.2f %.2f" transform="rotate(-90 18 18)"/>',
        r, fill, c * pct / 100, c)
    end
    noctalia.writeFile(path, string.format(
      '<svg xmlns="http://www.w3.org/2000/svg" width="36" height="36" viewBox="0 0 36 36"><circle cx="18" cy="18" r="%d" fill="none" stroke="%s" stroke-opacity="0.22" stroke-width="6"/>%s</svg>',
      r, track, arc))
  end
  return path
end

-- 每个订阅取剩余最少的那一档（比如 5 小时和每周都有时，哪个快用完显示哪个）。
local function subscriptions()
  local list = {}
  local codex = snapshot.quota and snapshot.quota.codex
  if type(codex) == "table" and #(codex.lines or {}) > 0 then
    local worst = nil
    for _, line in ipairs(codex.lines) do
      if worst == nil or (tonumber(line.left) or 0) < (tonumber(worst.left) or 0) then
        worst = line
      end
    end
    table.insert(list, {
      name = "ChatGPT", app = "Codex", icon = noctalia.pluginDir() .. "/icons/openai.svg",
      worst = worst, lines = codex.lines, resetCredits = codex.resetCredits,
    })
  end
  return list
end

local function tooltip(subs)
  local rows = {}
  for _, sub in ipairs(subs) do
    for _, line in ipairs(sub.lines) do
      local when = common.resetIn(line.resetsAt)
      local value = `剩余 {line.left}%`
      if when ~= nil then
        value = value .. "，" .. when
      end
      table.insert(rows, { key = `{sub.name} {line.tier}`, value = value })
    end
    if type(sub.resetCredits) == "number" and sub.resetCredits > 0 then
      table.insert(rows, { key = `{sub.name} 可重置`, value = `{sub.resetCredits} 次` })
    end
  end
  for _, row in ipairs(common.tooltipRows(snapshot)) do
    table.insert(rows, row)
  end
  return rows
end

local function render()
  if snapshot.loaded == true and snapshot.running ~= true then
    barWidget.render(ui.row({ gap = 4, align = "center" }, {
      ui.glyph({ name = common.GLYPH, size = 16, color = "on_surface_variant" }),
    }))
    barWidget.setTooltip("CC Switch 未运行，点击启动")
    return
  end

  local subs = subscriptions()
  local children = {}
  for _, sub in ipairs(subs) do
    local left = tonumber(sub.worst.left) or 0
    local role = left <= 0 and "error" or (sub.worst.warn and "#e0af68" or "primary")
    if #children > 0 then
      table.insert(children, ui.spacer({ width = 4, flexGrow = 0 }))
    end
    table.insert(children, ui.image({ path = sub.icon, width = 14, height = 14 }))
    local img = ringImage(left, role)
    if img ~= nil then
      table.insert(children, ui.image({ path = img, width = RING_SIZE, height = RING_SIZE }))
    end
    table.insert(children, ui.label({ text = `{left}%`, color = left < 20 and role or "on_surface" }))
  end
  if #children == 0 then
    table.insert(children, ui.glyph({ name = common.GLYPH, size = 16, color = "primary" }))
  end
  barWidget.render(ui.row({ gap = 5, align = "center" }, children))

  local rows = tooltip(subs)
  if #rows > 0 then
    barWidget.setTooltip(rows)
  else
    barWidget.setTooltip("CC Switch")
  end
end

function update()
  render()
end

function onClick()
  if snapshot.loaded == true and snapshot.running ~= true then
    common.request("launch")
    return
  end
  noctalia.togglePanel(common.PANEL)
end

noctalia.state.watch("ccs.state", function(value)
  if type(value) == "table" then
    snapshot = value
    render()
  end
end)

snapshot = noctalia.state.get("ccs.state") or snapshot
render()
common.request("refresh", { quota = true })
