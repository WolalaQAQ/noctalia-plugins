--!nonstrict
-- 快捷键速查表面板：两栏分组，左边键帽、右边中文说明；搜索时只显示匹配的行。
-- 数据来自服务发布的 "kb.data"，每次打开面板都让服务重读一遍配置。

local KEY_WIDTH = 168

local data = nil
local query = ""
local opened = 0 -- 每次打开换一个输入框 key，上次的搜索词不会留在框里

local function keycap(text)
  return ui.row({ paddingH = 6, paddingV = 1, radius = 5, fill = "on_surface/0.10" }, {
    ui.label({ text = text, fontSize = 11, fontWeight = "bold", color = "on_surface" }),
  })
end

local function combo(c)
  local caps = {}
  for _, cap in ipairs(c.caps or {}) do
    table.insert(caps, keycap(cap))
  end
  if c.tap == true then
    table.insert(caps, ui.label({ text = "单按", fontSize = 10, color = "on_surface_variant" }))
  end
  return ui.row({ gap = 3, align = "center" }, caps)
end

local function item(it)
  local combos = {}
  for _, c in ipairs(it.combos or {}) do
    table.insert(combos, combo(c))
  end
  local text = { ui.label({ text = it.desc, fontSize = 12, color = "on_surface" }) }
  if type(it.note) == "string" and it.note ~= "" then
    table.insert(text, ui.label({ text = it.note, fontSize = 10, color = "on_surface_variant" }))
  end
  return ui.row({ gap = 10, align = "start", paddingV = 3 }, {
    ui.column({ width = KEY_WIDTH, gap = 3 }, combos),
    ui.column({ flexGrow = 1, flexBasis = 0, gap = 1, paddingV = 1 }, text),
  })
end

local function group(name, items)
  local rows = {
    ui.label({ text = name, fontSize = 12, fontWeight = "bold", color = "primary" }),
  }
  for _, it in ipairs(items) do
    table.insert(rows, item(it))
  end
  return ui.column({ gap = 2, padding = 10, radius = 10, fill = "on_surface/0.05" }, rows)
end

-- 按组排进两栏：每组放进当前较短的那一栏，组的顺序不变
local function columns(groups)
  local cols, heights = { {}, {} }, { 0, 0 }
  for _, g in ipairs(groups) do
    local i = heights[1] <= heights[2] and 1 or 2
    table.insert(cols[i], group(g.name, g.items))
    heights[i] += #g.items + 2
  end
  return ui.row({ gap = 10, align = "start" }, {
    ui.column({ flexGrow = 1, flexBasis = 0, gap = 10 }, cols[1]),
    ui.column({ flexGrow = 1, flexBasis = 0, gap = 10 }, cols[2]),
  })
end

-- 空格分开的几个词都要出现（"super shift" 找同时有这两个键的）
local function matches(text, words)
  for _, word in ipairs(words) do
    if not string.find(text, word, 1, true) then
      return false
    end
  end
  return true
end

local function filtered()
  local words = {}
  for word in string.gmatch(string.lower(query), "%S+") do
    table.insert(words, word)
  end
  if #words == 0 then
    return data.groups or {}
  end
  local out = {}
  for _, g in ipairs(data.groups or {}) do
    local items = {}
    for _, it in ipairs(g.items or {}) do
      if matches((it.search or "") .. " " .. string.lower(g.name), words) then
        table.insert(items, it)
      end
    end
    if #items > 0 then
      table.insert(out, { name = g.name, items = items })
    end
  end
  return out
end

function render()
  local header = ui.row({ align = "center", gap = 10, paddingH = 4 }, {
    ui.glyph({ name = "keyboard", size = 20, color = "primary" }),
    ui.column({ gap = 0 }, {
      ui.label({ text = "快捷键", fontSize = 15, fontWeight = "bold" }),
      ui.label({ text = "Super 就是 Win 键", fontSize = 10, color = "on_surface_variant" }),
    }),
    ui.spacer({ flexGrow = 1 }),
    ui.input({
      key = "search:" .. opened,
      value = query,
      placeholder = "搜索按键或功能…",
      focus = true,
      controlSize = "sm",
      width = 260,
      onChange = function(value)
        query = tostring(value)
        render()
      end,
    }),
  })

  local body
  if data == nil then
    body = ui.column({ flexGrow = 1, align = "center", justify = "center" }, {
      ui.label({ text = "读取中…", fontSize = 12, color = "on_surface_variant" }),
    })
  else
    local content = {}
    if type(data.error) == "string" then
      table.insert(content, ui.label({ text = data.error, fontSize = 11, color = "error" }))
    end
    local groups = filtered()
    if #groups == 0 and noctalia.string.trim(query) ~= "" then
      table.insert(content, ui.label({ text = "没有匹配的快捷键", fontSize = 12, color = "on_surface_variant" }))
    else
      table.insert(content, columns(groups))
    end
    body = ui.scroll({ flexGrow = 1, gap = 8 }, content)
  end

  local footer = ui.row({ align = "center", paddingH = 4 }, {
    ui.label({ text = "桌面快捷键在 ~/.config/umbriel/config.toml 的 [keybinds] 里改，Kitty 的在 ~/.config/kitty/kitty.conf 的 map 里改，这里会自动跟着变", fontSize = 10, color = "on_surface_variant" }),
  })

  -- 面板是半透明的，字多时背后的窗口会透上来，整体加一层底色
  panel.render(ui.column({ flexGrow = 1, gap = 10, padding = 14, radius = 14, fill = "surface/0.82" }, { header, body, footer }))
end

function onOpen(_context)
  data = noctalia.state.get("kb.data") or data
  query = ""
  opened += 1
  noctalia.state.set("kb.request", { nonce = noctalia.nowMs() })
  render()
end

noctalia.state.watch("kb.data", function(value)
  if type(value) == "table" then
    data = value
    render()
  end
end)
