--!nonstrict
-- 快捷键服务：唯一调用 keybinds.py 的地方。
--
--   "kb.data"     分组后的快捷键（面板按它渲染）
--   "kb.request"  面板打开时发来的刷新请求（带 nonce）

local SCRIPT = noctalia.pluginDir() .. "/keybinds.py"

local inFlight = false

local function refresh()
  if inFlight then
    return
  end
  inFlight = true
  noctalia.runAsync({ "python3", SCRIPT }, function(result)
    inFlight = false
    local decoded = noctalia.json.decode(result.stdout or "")
    if type(decoded) ~= "table" then
      local err = noctalia.string.trim(result.stderr or "")
      decoded = { groups = {}, error = err ~= "" and err or "读取快捷键失败" }
    end
    decoded.at = noctalia.nowMs()
    noctalia.state.set("kb.data", decoded)
  end, 10000)
end

noctalia.state.watch("kb.request", function(req)
  if type(req) == "table" then
    refresh()
  end
end)

refresh()
