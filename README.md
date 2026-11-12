# noctalia-plugins

两个 [Noctalia](https://github.com/noctalia-dev) 插件，界面是简体中文。

| 插件 | ID | 说明 |
| --- | --- | --- |
| [CC Switch](cc-switch/) | `wolala/cc-switch` | 顶栏显示 Codex 订阅剩余额度；控制中心入口打开面板，切换 [CC Switch](https://github.com/farion1231/cc-switch) 的供应商、查看用量 |
| [快捷键速查表](keybinds/) | `wolala/keybinds` | 用中文分组列出 Umbriel、输入法和 Kitty 的快捷键，可以搜索 |

## 安装

在 `~/.local/state/noctalia/settings.toml` 里加一个 git 插件源：

```toml
[[plugins.source]]
kind = "git"
location = "https://github.com/WolalaQAQ/noctalia-plugins"
name = "wolala"
```

然后在 Noctalia 设置的插件页启用。也可以克隆到本地，用 `kind = "path"` 指向克隆目录。

两个插件都需要 `python3`（3.11 及以上，只用标准库），`plugin_api = 43`（Noctalia 5.4）。

## CC Switch

- 顶栏：OpenAI 图标 + 订阅额度圆环和百分比。
- 控制中心快捷按钮：`wolala/cc-switch:shortcut`。
- 面板（`noctalia msg panel-toggle wolala/cc-switch:panel`）：
  - 配置页：按应用（Claude Code、Codex 等）列出供应商，点击切换；
  - 用量页：今天 / 7 天 / 30 天 / 全部的请求数、Token、费用和趋势柱状图。

要求：

- CC Switch 在运行，托盘图标可用。切换是用 `busctl` 点击 CC Switch 自己的托盘菜单（`com.canonical.dbusmenu`），不改它的数据库和各工具的配置文件。
- 用量只读 `~/.cc-switch/cc-switch.db`。
- 订阅额度读 `~/.codex/auth.json` 里的登录令牌，只发给 `chatgpt.com` 查询，结果缓存在 `~/.cache/noctalia-cc-switch`（5 分钟）。

## 快捷键速查表

面板：`noctalia msg panel-toggle wolala/keybinds:panel`。可以在 Umbriel 里绑一个键：

```toml
"Mod+Slash" = { action = "spawn noctalia msg panel-toggle wolala/keybinds:panel", repeat = false }
```

每次打开都会重新读取：

- `~/.config/umbriel/config.toml` 的 `[keybinds]`，按动作名翻译成中文；没翻译到的动作用 `umbriel msg --help` 的英文说明兜底；
- fcitx5 的热键（`~/.config/fcitx5/config`）和 Rime 的切换键；
- `~/.config/kitty/kitty.conf` 里的 `map`（装了 kitty 时）。

## 许可

MIT。`cc-switch/icons/` 里的品牌图标归各自公司所有，仅用于标识对应服务。
