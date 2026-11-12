--!nonstrict
-- 控制中心按钮：显示 ChatGPT 订阅剩余额度，点击打开 CC Switch 面板。

local common = require("./common.luau")

local snapshot = { loaded = false, running = false, apps = {} }

local function render()
  shortcut.setIcon(common.GLYPH)
  -- 插件按钮都会被当成开关渲染，这里只是面板入口，不点亮
  shortcut.setActive(false)
  shortcut.setEnabled(true)
  if snapshot.loaded == true and snapshot.running ~= true then
    shortcut.setLabel("CC Switch 未运行")
    return
  end
  -- 有订阅额度就显示剩余最少的那档；空标签会被替换成条目 id，所以没有数据时显示名字
  local codex = snapshot.quota and snapshot.quota.codex
  local left = nil
  for _, line in ipairs((type(codex) == "table" and codex.lines) or {}) do
    local value = tonumber(line.left)
    if value ~= nil and (left == nil or value < left) then
      left = value
    end
  end
  shortcut.setLabel(left ~= nil and `ChatGPT {left}%` or "CC Switch")
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
