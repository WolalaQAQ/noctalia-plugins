--!nonstrict
-- CC Switch 服务：唯一调用 ccs.py 的地方。
--
--   "ccs.state"    应用、供应商、轻量模式、Codex 额度（顶栏、控制中心、面板按它渲染）
--   "ccs.usage"    用量页的数据，按需读取
--   "ccs.request"  各入口发来的动作（带 nonce，重复请求也会触发）

local SCRIPT = noctalia.pluginDir() .. "/ccs.py"
local POLL_MS = 8000
local QUOTA_EVERY_MS = 60000
local TIMEOUT_MS = 10000

local state = { loaded = false, running = false, apps = {}, lightweight = false, busy = false, error = nil, quota = nil }
local inFlight = false
local quotaInFlight = false
local lastQuotaAt = -QUOTA_EVERY_MS

local function publish()
  noctalia.state.set("ccs.state", {
    loaded = state.loaded,
    running = state.running,
    apps = state.apps,
    lightweight = state.lightweight,
    busy = state.busy,
    error = state.error,
    quota = state.quota,
    at = noctalia.nowMs(),
  })
end

local function stderrOf(result)
  local text = noctalia.string.trim(result.stderr or "")
  return text ~= "" and text or nil
end

local function refresh()
  if inFlight then
    return
  end
  inFlight = true
  noctalia.runAsync({ "python3", SCRIPT, "state" }, function(result)
    inFlight = false
    state.loaded = true
    if result.exitCode ~= 0 or result.timedOut then
      state.error = stderrOf(result) or "读取 CC Switch 状态失败"
      publish()
      return
    end
    local decoded = noctalia.json.decode(result.stdout)
    if type(decoded) == "table" then
      state.running = decoded.running == true
      state.apps = decoded.apps or {}
      state.lightweight = decoded.lightweight == true
      state.error = nil
    end
    publish()
  end, TIMEOUT_MS)
end

local function refreshQuota(force)
  if quotaInFlight then
    return
  end
  quotaInFlight = true
  lastQuotaAt = noctalia.nowMs()
  local argv = { "python3", SCRIPT, "quota" }
  if force then
    table.insert(argv, "--force")
  end
  noctalia.runAsync(argv, function(result)
    quotaInFlight = false
    local decoded = result.exitCode == 0 and noctalia.json.decode(result.stdout) or nil
    if type(decoded) == "table" then
      state.quota = decoded
      publish()
    end
  end, 25000)
end

-- 四个时间范围一次算完（约 0.7 秒），面板切换范围时直接取，不会先显示别的范围的旧数据。
local usageInFlight = false
local function loadUsage()
  if usageInFlight then
    return
  end
  usageInFlight = true
  local previous = noctalia.state.get("ccs.usage") or {}
  noctalia.state.set("ccs.usage", { loading = true, ranges = previous.ranges })
  noctalia.runAsync({ "python3", SCRIPT, "usage", "ranges" }, function(result)
    usageInFlight = false
    local decoded = result.exitCode == 0 and noctalia.json.decode(result.stdout) or nil
    noctalia.state.set("ccs.usage", {
      loading = false,
      ranges = decoded or previous.ranges,
      error = decoded == nil and (stderrOf(result) or "读取用量失败") or nil,
    })
  end, 30000)
end

-- 点击后 CC Switch 需要一点时间重建菜单，等一下再读，面板才能立刻显示新的勾选。
local function runThenRefresh(argv, failTitle)
  state.busy = true
  publish()
  noctalia.runAsync(argv, function(result)
    if result.exitCode ~= 0 or result.timedOut then
      noctalia.notifyError(failTitle, stderrOf(result))
    end
    noctalia.runAsync({ "sleep", "0.6" }, function()
      state.busy = false
      inFlight = false
      refresh()
    end, 2000)
  end, TIMEOUT_MS)
end

noctalia.state.watch("ccs.request", function(req)
  if type(req) ~= "table" then
    return
  end
  local action = req.action
  if action == "refresh" then
    refresh()
    if req.quota == true then
      refreshQuota(req.force == true)
    end
  elseif action == "switch" and type(req.app) == "string" and type(req.provider) == "string" then
    runThenRefresh({ "python3", SCRIPT, "click", req.app, req.provider }, "CC Switch 切换失败")
  elseif action == "subitem" and type(req.app) == "string" and type(req.label) == "string" then
    runThenRefresh({ "python3", SCRIPT, "subitem", req.app, req.label }, "CC Switch 操作失败")
  elseif action == "item" and type(req.label) == "string" then
    runThenRefresh({ "python3", SCRIPT, "item", req.label }, "CC Switch 操作失败")
  elseif action == "usage" then
    loadUsage()
  elseif action == "launch" then
    -- CC Switch 启动后要几秒才注册托盘，交给下一轮轮询发现
    noctalia.runAsync({ "sh", "-c", "setsid -f cc-switch >/dev/null 2>&1" }, function() end, 3000)
  end
end)

function update()
  refresh()
  if noctalia.nowMs() - lastQuotaAt >= QUOTA_EVERY_MS then
    refreshQuota(false)
  end
end

noctalia.setUpdateInterval(POLL_MS)
refresh()
refreshQuota(false)
