--!nonstrict
-- 顶栏、控制中心、面板共用的小工具。

local M = {}

M.PANEL = "wolala/cc-switch:panel"
M.GLYPH = "arrows-exchange"

function M.request(action, fields)
  local req = fields or {}
  req.action = action
  req.nonce = noctalia.nowMs()
  noctalia.state.set("ccs.request", req)
end

function M.findApp(snapshot, id)
  for _, app in ipairs(snapshot.apps or {}) do
    if app.id == id or app.name == id then
      return app
    end
  end
  return nil
end

-- 提示里每个应用一行：应用名 → 当前供应商。
function M.tooltipRows(snapshot)
  local rows = {}
  for _, app in ipairs(snapshot.apps or {}) do
    if app.add == nil then
      table.insert(rows, { key = app.name, value = app.current or "未选择" })
    end
  end
  return rows
end

-- 还有多久重置：最多两级（天+小时、小时+分、分），不足一分钟按一分钟，已经过了返回 nil。
function M.resetIn(resetsAt)
  if type(resetsAt) ~= "number" then
    return nil
  end
  local seconds = resetsAt - os.time()
  if seconds <= 0 then
    return nil
  end
  local minutes = math.max(1, math.floor(seconds / 60))
  local days = math.floor(minutes / 1440)
  local hours = math.floor((minutes % 1440) / 60)
  local mins = minutes % 60
  local parts = {}
  if days > 0 then
    table.insert(parts, days .. "天")
    if hours > 0 then
      table.insert(parts, hours .. "小时")
    end
  elseif hours > 0 then
    table.insert(parts, hours .. "小时")
    if mins > 0 then
      table.insert(parts, mins .. "分钟")
    end
  else
    table.insert(parts, mins .. "分钟")
  end
  return table.concat(parts) .. "后重置"
end

local function trimZeros(text)
  return (string.gsub(text, "%.?0+$", ""))
end

function M.tokens(n)
  n = tonumber(n) or 0
  if n >= 1e8 then
    return trimZeros(string.format("%.2f", n / 1e8)) .. "亿"
  elseif n >= 1e7 then
    return string.format("%d", math.floor(n / 1e4 + 0.5)) .. "万"
  elseif n >= 1e4 then
    return trimZeros(string.format("%.1f", n / 1e4)) .. "万"
  end
  return tostring(math.floor(n))
end

-- 坐标刻度用的紧凑写法：1.2K、24万、1.5亿
function M.compact(n)
  n = tonumber(n) or 0
  if n >= 1e8 then
    return trimZeros(string.format("%.1f", n / 1e8)) .. "亿"
  elseif n >= 1e4 then
    return trimZeros(string.format("%.1f", n / 1e4)) .. "万"
  elseif n >= 1000 then
    return trimZeros(string.format("%.1f", n / 1000)) .. "K"
  elseif n >= 10 or n == 0 then
    return tostring(math.floor(n + 0.5))
  end
  return trimZeros(string.format("%.2f", n))
end

-- 坐标轴顶端：向上取到 1/2/2.5/5 × 10^k，刻度才整齐
function M.niceCeil(v)
  if v <= 0 then
    return 1
  end
  local exp = 10 ^ math.floor(math.log10(v))
  for _, m in ipairs({ 1, 2, 2.5, 5, 10 }) do
    if v <= m * exp then
      return m * exp
    end
  end
  return 10 * exp
end

function M.int(n)
  local s = tostring(math.floor(tonumber(n) or 0))
  local out = s:reverse():gsub("(%d%d%d)", "%1,"):reverse()
  return (out:gsub("^,", ""))
end

function M.money(usd, digits)
  return "$" .. string.format("%." .. (digits or 2) .. "f", tonumber(usd) or 0)
end

function M.percent(ratio)
  return trimZeros(string.format("%.1f", (tonumber(ratio) or 0) * 100)) .. "%"
end

return M
