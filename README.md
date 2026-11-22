# vol_connect_workbuddy —— 火山 Codex 的 WorkBuddy 多账号中继

> **一句话**：让火山软件开发平台（voldev）里的 Codex，用上 WorkBuddy 的模型和你的所有账号，并且一个号额度用完了自动换下一个，你完全不用管。
>
> **适合谁**：手上有一个或好几个 WorkBuddy / CodeBuddy 账号，想在火山里写代码，又不想每次手动换号、手动贴 token 的人。
>
> **解决什么问题**：WorkBuddy 官方只给「一套客户端一个账号」的用法。这个项目把它的接口包了一层，做成火山能直接用的「模型预设 + 本地中继」，于是你可以像选内置模型一样选它，背后有 13 个账号在轮换。

---

## 目录

- [一分钟看懂这个项目](#一分钟看懂这个项目)
- [零基础入门（完全不懂电脑也能照做）](#零基础入门完全不懂电脑也能照做)
- [日常使用手册（每个按钮、每个设置项）](#日常使用手册每个按钮每个设置项)
- [四个预设文件详解](#四个预设文件详解)
- [配置文件详解（config.json）](#配置文件详解configjson)
- [工作原理（技术参考）](#工作原理技术参考)
- [排错手册（按症状查）](#排错手册按症状查)
- [常见问题 FAQ](#常见问题-faq)
- [版本更新简介](#版本更新简介)
- [已知限制与安全说明](#已知限制与安全说明)
- [开发者：目录结构、构建与回归](#开发者目录结构构建与回归)
- [贡献与许可](#贡献与许可)

---

## 一分钟看懂这个项目

### 它是什么

两个东西的组合：

| 组成 | 是什么 | 在哪 |
|---|---|---|
| **本地中继** | 一个在你电脑上跑的小程序，负责登录 WorkBuddy、管理多账号、自动换号、把两边的协议翻译过来 | `G:\Python_Code\vol_connect_workbuddy\` |
| **火山预设** | 4 个配置文件，让火山知道「有这么个模型，地址是 127.0.0.1:17583」 | `D:\voldev\plugins\vol_ai_codex\models\` |

### 它怎么工作（一句话版）

```
火山 Codex  ──请求──▶  本地中继（127.0.0.1:17583）  ──请求──▶  WorkBuddy 服务器
                              │
                              ├─ 挑一个还有额度的账号
                              ├─ 带上这个账号的登录凭证
                              ├─ 把 Responses 格式翻译成 Chat 格式
                              └─ 把回复再翻译回去
```

### 你能得到什么

- ✅ 一个号额度用完了，**自动换下一个**，界面上不会中断
- ✅ 登录过期了，**自动刷新**，不用重新登录
- ✅ 火山里能选 25 个 WorkBuddy 模型，从最省的 0.08 倍到最强的 1.62 倍
- ✅ 一个中文控制面板，能看见每个账号还能不能用、为什么不能用
- ✅ 所有配置实时保存，重启不丢

---
## 零基础入门（完全不懂电脑也能照做）

### 第 0 步：先确认这三样东西在不在

打开「此电脑」，依次点进去看：

| 要确认的 | 路径 | 看不到怎么办 |
|---|---|---|
| 火山软件开发平台 | `D:\voldev\bin\x64\voldev_wp.exe` | 火山装到别处了？那后面所有 `D:\voldev` 都要换成你的实际位置 |
| Python | 开始菜单搜 `cmd` 打开，输入 `python --version` 回车 | 显示 `Python 3.10.x` 就对了；提示「不是内部或外部命令」说明没装，去 python.org 装 3.10 以上，**务必勾 Add Python to PATH** |
| DSH 的 WorkBuddy 登录 | 资源管理器地址栏输入 `%USERPROFILE%\.dsh\workbuddy-vault` 回车 | 打不开或里面是空的，说明还没在 DSH 里登录过 WorkBuddy，先去登录一次 |

> 💡 **为什么需要 DSH 的登录？** 本项目不重做登录界面，直接复用你已在 DSH 登录过的账号凭证，省得手工贴 13 个 token。

### 第 1 步：把项目放到电脑上

把整个 `vol_connect_workbuddy` 文件夹放到 `G:\Python_Code\`，放好后应该能看到：

```
vol_connect_workbuddy\
├─ 启动中继.bat              ← 最常用，双击这个
├─ 启动中继_无界面.bat        ← 不想开窗口时用
├─ requirements.txt
├─ README.md                 ← 你正在看的这份
├─ presets\                  ← 4 个火山预设文件
├─ relay\                    ← 中继程序本体
└─ gui\                      ← 中文控制面板
```

### 第 2 步：安装依赖（只做一次）

1. 在文件夹空白处按住 `Shift` 点右键 → 「在此处打开 PowerShell 窗口」
2. 输入下面这行，回车，等它跑完：

```
python -m pip install -r requirements.txt
```

3. 看到最后一行 `Successfully installed ...` 就成功了。
> ⚠️ 卡住不动就换国内源：`python -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple`

### 第 3 步：启动中继

**双击 `启动中继.bat`**。正常会弹出中文窗口，左上角显示：

```
服务状态：运行中（http://127.0.0.1:17583）
```

下面的账号表格自动填满，第一列账号名，第三列写「可用」就是好的。
> 看不到窗口？说明启动失败。改双击 `启动中继_无界面.bat`，报错留在黑窗口里，记下文字去 [排错手册](#排错手册按症状查)。

### 第 4 步：把预设装进火山

1. 打开火山（`D:\voldev\bin\x64\voldev_wp.exe`）
2. 找到「模型配置」
3. 列表里应出现 **WorkBuddy（多账号中继）**
   - 没出现？检查 `D:\voldev\plugins\vol_ai_codex\models\` 有没有这 4 个文件：`vol_connect_workbuddy.model`、`vol_connect_workbuddy.toml`、`model_catalog_vol_connect_workbuddy.json`、`readme_vol_connect_workbuddy.txt`
4. 选中它 → 点「导入」
5. 若弹「服务地址」，填 `http://127.0.0.1:17583/v1`
6. 若弹「API Key」，**随便填**（`local` 或 `1` 都行）——真正的账号由中继自己管

### 第 5 步：试一句

在火山 AI 对话框输入：

```
你好，请告诉我你是什么模型
```

能正常回话，整条链路就通了。

---
## 日常使用手册（每个按钮、每个设置项）

打开 `启动中继.bat` 后看到的窗口，从上到下是这样：

### 顶部状态条

| 元素 | 作用 | 取值 | 推荐 | 什么时候看 |
|---|---|---|---|---|
| 服务状态文字 | 显示中继有没有在监听 | `运行中（http://127.0.0.1:17583）` / `未启动` | 正常用就该是「运行中」 | 火山报 connection refused 时第一个看这里 |
| 启动/停止服务按钮 | 手动开关监听 | 点一下切换 | 平时不用碰 | 改过端口、或想释放端口给别人用时 |

### 进度条

界面中间那条。**重新载入账号**、**检测全部账号** 时会跑起来。

- 跑完停在 100% 是正常的，不是卡住
- 它做了节流（每 120 毫秒最多刷新一次），所以看起来是平滑推进而不是疯狂跳动

### 账号池标签页

| 按钮/列 | 作用 | 说明 |
|---|---|---|
| **重新载入账号** | 重新扫一遍保险库目录 | 刚在 DSH 里登录了新账号，点这个就能看到 |
| **检测全部账号** | 给每个账号发一次最小的请求，真实验证能不能用 | 会花极少量积分（每个账号几个 token）。切模型后建议点一次 |
| **导出账号** | 把勾选的账号存成一个 JSON 文件 | 文件格式与 DSH 插件 `dsh-connect-workbuddy` **完全一致**，可以反过来丢给插件导入。详见下面「账号导出与导入」一节 |
| **导入账号** | 从 JSON 文件读账号写进保险库 | 插件的 `workbuddy-accounts-日期.json` 可以直接用。导入前会先给脱敏预览让你勾选 |
| 账号列 | 区域/昵称 | 例如 `cn/153` 表示国内区、昵称 153 |
| 区域列 | `cn` 或 `global` | 国内版 / 国际版，两边的 token 不能互换 |
| 状态列 | `可用` / `冷却中` / `冷却中（token 已过期）` | 冷却中表示刚失败过，正在休息 |
| 失败列 | 累计失败次数 | 一直是 0 说明这个号很稳 |
| 成功列 | 累计成功次数 | 用得越多越大，可以用来判断哪个号最健康 |
| 冷却(秒)列 | 还要等多少秒才能再用 | 冷却时长按失败类型不同（见下表） |
| 最近错误列 | 上一次失败的原因 | 例如 `hard_credit: 积分或额度不足（402 / credits）` |

### 账号导出与导入（和 DSH 插件互通）

这是给「换电脑」「备份账号」「从 DSH 插件搬过来」用的。两个按钮都在「账号池」页右上角。

#### 导出账号

1. 点「导出账号」，弹出窗口**默认全勾** 13 个账号，也可以只勾几个。
2. 点「导出…」，文件名默认就是 `workbuddy-accounts-2026-11-23.json`（与插件同名同格式）。
3. 存下来就完事了。

#### 导入账号

1. 点「导入账号」→「选择文件…」，挑一个 `workbuddy-accounts-*.json`。
2. 窗口里出现**脱敏预览**：只有昵称、区域、有没有 token，**不显示 token 明文**。
3. 勾选要导入的（默认全勾，缺 token 的默认不勾），选好「导入到区域」。
4. 点「导入选中」。结束后会告诉你导入了几个、跳过几个、为什么跳过。

#### 兼容性是双向的

| 方向 | 支持 | 说明 |
|---|---|---|
| 本程序导出 → DSH 插件导入 | ✅ | 文件名、字段、区域判定全部对齐插件 |
| DSH 插件导出 → 本程序导入 | ✅ | 直接选文件即可，不用改任何东西 |
| 本程序导出 → 本程序导入（换机） | ✅ | 幂等：同一账号反复导入始终覆盖同一份文件，不会堆重复 |

#### 三条跳过/覆盖规则（与插件逐条一致，别以为是 bug）

| 规则 | 行为 | 举例 |
|---|---|---|
| 缺 `access_token` | 跳过 | 文件里某条只剩昵称，没 token |
| `domain` 判不出区域 | 跳过 | `domain` 为空、或是个不认识的外域 |
| 记录区域 ≠ 目标区域 | 跳过 | 国内号往「国际版」导入 → 全部跳过并逐条说明 |
| 账号 id 已存在 | **覆盖** | 重登后重新导入即刷新 token，不会变成两个号 |

> **账号 id 是怎么算的**：`sha256("workbuddy\0" + uin)` 取前 24 位十六进制（没有 uin 就用 uid，再没有用 nickname）。
> 这与插件的 `workbuddyAccountId()` 逐字节一致，所以导入后写出的文件名与插件原有文件名**完全同名**——这正是「覆盖而不是新增」的技术原因。

> ⚠️ 导出的文件里有**明文 token**，等于账号钥匙。别发群里、别传网盘、别提到 GitHub。用完建议删掉。

### 冷却时长是怎么定的

| 失败类型 | 冷却多久 | 为什么要这么久 |
|---|---|---|
| `hard_credit`（积分不足） | 3600 秒（1 小时） | 积分不会几分钟就回来，频繁试只是浪费请求 |
| `account_restricted`（账号被限制） | 3600 秒 | 同上 |
| `session_dead`（登录失效） | 1800 秒（30 分钟） | 给刷新令牌留时间 |
| `soft_rate`（被限流 429） | 60 秒 | 限流通常很快恢复 |
| `model_busy`（模型繁忙） | 30 秒 | 排队而已，稍等即可 |
| `model_cannot_produce`（模型产不出） | 120 秒 | 可能是临时故障 |
| 其它 | 120 秒 | 保守值 |

### 设置标签页

**改完立即生效并写入 `config.json`，不需要点保存。**

#### 监听与服务

| 项 | 作用 | 取值范围 | 默认 | 什么时候改 |
|---|---|---|---|---|
| 监听地址 | 中继绑在哪个网卡 | IP 字符串 | `127.0.0.1` | 只有想让局域网别的机器也用才改成 `0.0.0.0`（有安全风险，见 [安全说明](#已知限制与安全说明)） |
| 端口 | 监听端口 | 1024–65535 | `17583` | 万一 17583 被别的软件占了，改成 17584 之类，**同时要改火山的服务地址** |

> ⚠️ 改完地址或端口，必须点「停止服务」再「启动服务」才生效——已经在监听的 socket 不会自己搬家。

#### 默认模型与换号

| 项 | 作用 | 取值范围 | 默认 | 什么时候改 |
|---|---|---|---|---|
| 默认模型 | 火山没指定模型时用哪个 | 下拉里 11 个常用模型 | `deepseek-v4.1-flash` | 想省钱选 0.08 倍的；想更强选 `deepseek-v4-pro` |
| 最多换号 | 一次请求最多试几个账号 | 1–20 | `3` | 账号很多且都想用上时调到 6 或 8；想省时间就调回 2–3 |

#### 账号来源

| 项 | 作用 | 默认 | 什么时候改 |
|---|---|---|---|
| 保险库目录 | 去哪读账号凭证 | `%USERPROFILE%\.dsh\workbuddy-vault` | DSH 装在别的用户下、或你有一份自己的保险库时 |
| 国内版勾选框 | 是否加载 `cn` 子目录的账号 | 勾上 | 只有国际版账号时取消 |
| 国际版勾选框 | 是否加载 `global` 子目录 | **不勾** | 你有 workbuddy.ai 账号时勾上 |

#### 上游兼容（不建议动）

| 项 | 作用 | 关掉会怎样 |
|---|---|---|
| 启用渠道校验规避 | 在 system 消息开头垫一句中性话，绕过 WorkBuddy 网关的前缀检查 | **约 90% 请求直接 400 / 业务码 11128**，火山里表现为「请求被拒绝」 |
| 把工具调用透传给上游 | 把 Codex 的 exec_command / apply_patch 等工具声明发给上游 | Codex 就只会聊天，**无法执行任何命令、无法改文件** |

### 运行日志标签页

点「刷新日志」看最近 300 行。日志同时写在 `logs\relay-YYYYMMDD.log`。

典型的好日志长这样：

```
2026-11-23 05:35:02 [INFO] [responses] 收到请求 model=deepseek-v4.1-flash input=3
2026-11-23 05:35:02 [INFO] [http] "POST /v1/responses HTTP/1.1" 200 -
2026-11-23 05:35:03 [INFO] [chat_ok] account=cn/153
```

出了问题会看到：

```
2026-11-23 05:31:08 [ERROR] [responses] 上游渠道校验失败（11128）：请求被判定为非官方客户端或缺少会话身份，换账号无效。
2026-11-23 05:33:10 [WARN]  [failover] account=cn/153 kind=hard_credit cooldown_seconds=3600
```

### 使用说明标签页

就是一份落在界面里的速查卡，忘了步骤时点开看。

---
## 四个预设文件详解

火山认一个预设 = **4 个文件**，放同一个目录（`D:\voldev\plugins\vol_ai_codex\models\`），文件名后缀前必须是同一个名字。

### 1. `vol_connect_workbuddy.model`

这是火山的「入口清单」，JSON 格式，决定这个预设在列表里叫什么、引用哪几个附属文件。

```json
{
  "displayName": "WorkBuddy（多账号中继）",
  "tomlFile": "vol_connect_workbuddy.toml",
  "jsonFiles": ["model_catalog_vol_connect_workbuddy.json"],
  "readmeFile": "readme_vol_connect_workbuddy.txt",
  "docsUrl": "https://github.com/duma520/vol_connect_workbuddy"
}
```

| 字段 | 必填 | 作用 | 改错会怎样 |
|---|---|---|---|
| `displayName` | 是 | 模型配置窗口里显示的名字 | 空的话列表里显示空白，仍可选 |
| `tomlFile` | 是 | 指向同目录的 toml 文件名 | 写错 → 导入时报找不到文件 |
| `jsonFiles` | 是 | 导入时要一起复制的 json 文件名单（字符串数组） | 写错 → 模型列表为空，选不到任何模型 |
| `readmeFile` | 是 | 同目录的说明文本，可以是空串 | 写错 → 说明页空白，不影响使用 |
| `docsUrl` | 否 | 必须 http/https，填了启用「文档」按钮 | 填本地路径 → 「文档」按钮不出现 |
| `apiKeyUrl` | 否 | 同上，启用「获取密钥」按钮 | 本项目不填，因为不需要用户填密钥 |

> ⚠️ 附属文件只能写**单个文件名**，不能带路径、不能写 `../`。这是火山的硬规定。

### 2. `vol_connect_workbuddy.toml`

真正生效的 Codex 配置片段。导入时火山按键合并进 `%USERPROFILE%\.codex\config.toml`（或 `CODEX_HOME` 指向的位置）。

```toml
model = "deepseek-v4.1-flash"
model_provider = "vol_connect_workbuddy"
model_catalog_json = "model_catalog_vol_connect_workbuddy.json"
model_supports_reasoning_summaries = "__vol_none__"
model_context_window = "__vol_none__"
model_auto_compact_token_limit = "__vol_none__"
review_model = "__vol_none__"

[model_providers.vol_connect_workbuddy]
name = "WorkBuddy（多账号中继）"
base_url = "http://127.0.0.1:17583/v1"
wire_api = "responses"
experimental_bearer_token = "PROXY_MANAGED"
requires_openai_auth = false
```

| 键 | 值 | 为什么这么写 |
|---|---|---|
| `model` | `deepseek-v4.1-flash` | 默认模型 |
| `model_provider` | `vol_connect_workbuddy` | 必须和下面 `[model_providers.xxx]` 表名一致 |
| `model_catalog_json` | 模型目录文件名 | 告诉 Codex 去哪读模型元数据 |
| `__vol_none__` | 特殊标记 | **导入时删除该键**，清掉上一个预设的残留设置 |
| `base_url` | `http://127.0.0.1:17583/v1` | 指向本机中继。**改了面板端口这里必须同步改** |
| `wire_api` | `responses` | 火山这套 Codex **只支持 responses**；写 `chat` 会报 `wire_api = "chat" is no longer supported` |
| `experimental_bearer_token` | `PROXY_MANAGED` | 表示「认证交给本地代理」，是火山中转类预设的统一写法 |
| `requires_openai_auth` | `false` | 关掉 Codex 自带登录流程 |

### 3. `model_catalog_vol_connect_workbuddy.json`

模型目录，结构 `{"models": [...]}`，共 25 个模型，按积分倍率从低到高排。单个模型的结构：

```json
{
  "slug": "deepseek-v4.1-flash",
  "display_name": "DeepSeek-V4.1-Flash",
  "description": "最省积分（0.11 倍），速度快，适合日常编码。",
  "base_instructions": "",
  "supported_reasoning_levels": [],
  "shell_type": "shell_command",
  "visibility": "list",
  "supported_in_api": true,
  "priority": 0,
  "support_verbosity": false,
  "truncation_policy": {"mode": "tokens", "limit": 10000},
  "supports_parallel_tool_calls": false,
  "experimental_supported_tools": [],
  "input_modalities": ["text"],
  "supports_reasoning_summaries": false,
  "supports_reasoning_summary_parameter": false,
  "context_window": 262144,
  "max_context_window": 262144,
  "prefer_websockets": false
}
```

**最关键的是 `slug`**：必须等于 WorkBuddy 服务端真实接受的模型 ID，否则上游回 400 或「模型不存在」。本文件 25 个 slug 都是 2026-11-23 从上游 `/v3/config` 实测取回的。

| 字段 | 作用 | 改错会怎样 |
|---|---|---|
| `slug` | 发给上游的模型名 | 写错 → 上游报模型不存在 |
| `display_name` | 下拉里显示的 | 只影响观感 |
| `priority` | 排序，小的在前 | 只影响顺序 |
| `context_window` / `max_context_window` | 上下文窗口 | 太大被上游截断；太小 Codex 过早压缩 |
| `input_modalities` | 支持哪些输入 | 纯文本模型写 `image` 会在传图时报错 |

### 4. `readme_vol_connect_workbuddy.txt`

纯文本，导入后在火山里点「说明」能看到。写的是给普通用户看的安装与排错要点，不影响运行。

---
## 配置文件详解（config.json）

位置：`G:\Python_Code\vol_connect_workbuddy\config.json`。**首次启动自动创建**，之后每次改设置立即写盘（原子写：先写 `.tmp` 再 rename，断电不会写出半个文件）。

### 完整示例

```json
{
  "listen_host": "127.0.0.1",
  "listen_port": 17583,
  "vault_dir": "C:\\Users\\你的用户名\\.dsh\\workbuddy-vault",
  "include_cn": true,
  "include_global": false,
  "extra_accounts": [],
  "default_model": "deepseek-v4.1-flash",
  "model_whitelist": [],
  "token_policy": "lazy",
  "max_failover": 3,
  "request_timeout_seconds": 600,
  "connect_timeout_seconds": 30,
  "log_level": "INFO",
  "log_keep_days": 14,
  "enable_progress_log": true,
  "system_head_placeholder": "You are a helpful coding assistant.",
  "neutral_head": "You are a helpful coding assistant.",
  "enable_channel_gate_fix": true,
  "strip_reasoning_effort_off": true,
  "pass_tools": true,
  "auto_start_gui": true,
  "theme": "dark"
}
```

### 每个字段

| 字段 | 类型 | 默认 | 取值范围 | 作用 | 改错会怎样 |
|---|---|---|---|---|---|
| `listen_host` | 字符串 | `127.0.0.1` | 任意 IPv4 | 中继绑定的网卡 | 写 `0.0.0.0` 会让局域网能访问（有风险） |
| `listen_port` | 整数 | `17583` | 1024–65535 | 监听端口 | 被占用会启动失败；改了要同步改火山服务地址 |
| `vault_dir` | 字符串 | 自动填 | 目录路径 | 去哪读账号 | 写错 → 账号列表为空 |
| `include_cn` | 布尔 | `true` | true/false | 是否加载国内版账号 | 关掉后国内账号全部消失 |
| `include_global` | 布尔 | `false` | true/false | 是否加载国际版账号 | 打开后多出 global 账号 |
| `extra_accounts` | 数组 | `[]` | 见下方 | 手工追加的账号 | 结构错 → 该条被跳过，不影响其它 |
| `default_model` | 字符串 | `deepseek-v4.1-flash` | 上游真实 ID | 默认模型 | 写错 → 上游报模型不存在 |
| `model_whitelist` | 数组 | `[]` | 模型 ID 列表 | 非空时只对外暴露这些 | 留空 = 用 `default_model` |
| `token_policy` | 字符串 | `lazy` | `lazy` / `never` | `lazy`=过期才刷；`never`=永不主动刷 | 设 `never` 后 token 过期只能等 DSH 那边刷 |
| `max_failover` | 整数 | `3` | 1–20 | 一次请求最多试几个账号 | 设 1 等于不换号 |
| `request_timeout_seconds` | 整数 | `600` | ≥30 | 单次请求总超时 | 太小长回答会被截断 |
| `connect_timeout_seconds` | 整数 | `30` | ≥5 | 连接超时 | 太小弱网下容易失败 |
| `log_level` | 字符串 | `INFO` | DEBUG/INFO/WARN/ERROR | 日志级别 | 设 DEBUG 日志会很多 |
| `log_keep_days` | 整数 | `14` | ≥1 | 日志保留天数（预留） | 目前只记录不自动删 |
| `enable_progress_log` | 布尔 | `true` | true/false | 是否记录进度类日志 | 关掉后日志更干净 |
| `system_head_placeholder` | 字符串 | 见上 | 任意非空 | 没有 system 消息时补的默认值 | — |
| `neutral_head` | 字符串 | 见上 | 任意非空 | 垫在 system 开头的中性话 | 改成空串 → 11128 会回来 |
| `enable_channel_gate_fix` | 布尔 | `true` | true/false | 是否启用渠道校验规避 | **关掉 → 约 90% 请求 11128** |
| `strip_reasoning_effort_off` | 布尔 | `true` | true/false | 是否把 `reasoning_effort=off` 丢掉 | 关掉后部分模型会 11133 |
| `pass_tools` | 布尔 | `true` | true/false | 是否透传工具调用 | 关掉 → Codex 不能执行命令 |
| `auto_start_gui` | 布尔 | `true` | true/false | 启动时是否开面板 | 关掉后只跑服务 |
| `theme` | 字符串 | `dark` | dark/light | 面板主题（预留） | — |

### 手工追加账号的两种写法

**写法一（推荐）：直接贴 DSH 保险库的原样结构**

```json
{
  "region": "cn",
  "vault": {
    "accountId": "my-account-1",
    "auth": {
      "accessToken": "这里填 accessToken",
      "refreshToken": "这里填 refreshToken",
      "expiresAt": 1795000000000,
      "refreshExpiresAt": 1795200000000,
      "domain": "www.codebuddy.cn"
    },
    "account": {
      "uid": "用户ID",
      "nickname": "显示名",
      "uin": ""
    }
  }
}
```

**写法二：平铺字段**

```json
{
  "region": "cn",
  "account_id": "my-account-2",
  "access_token": "...",
  "refresh_token": "...",
  "expires_at": 1795000000000,
  "refresh_expires_at": 1795200000000,
  "domain": "www.codebuddy.cn",
  "uid": "...",
  "nickname": "小号2",
  "uin": ""
}
```

> 🔐 **安全提醒**：`config.json` 里填了 token，这个文件就是凭据文件，**绝不能提交到 GitHub、不能发给别人**。项目自带 `.gitignore` 已排除它。

---
## 工作原理（技术参考）

这一节写给想改代码、想搞清楚「为什么这么设计」的人。普通用户可以跳过。

### 数据是怎么流动的

```
┌──────────────┐   ①POST /v1/responses        ┌─────────────────────┐
│ 火山 Codex    │ ───────────────────────────▶ │ 中继 server.py       │
│ (app-server)  │   Responses 请求（JSON）      │ RelayHandler         │
└──────────────┘                              └──────────┬──────────┘
                                                          │ ②convert_in.to_chat_request
                                                          ▼
                                              ┌─────────────────────┐
                                              │ convert_in.py       │
                                              │ Responses → Chat    │
                                              └──────────┬──────────┘
                                                          │ ③upstream.normalize_body
                                                          │   （stream=true / 首条 system /
                                                          │     tool_choice 压平 / 垫中性 head）
                                                          ▼
                                              ┌─────────────────────┐
                                              │ upstream.py         │
                                              │ 挑账号 → 加头 → POST │
                                              └──────────┬──────────┘
                                                          │ ④POST /v2/chat/completions
                                                          ▼
                                              ┌─────────────────────┐
                                              │ WorkBuddy 上游网关    │
                                              └──────────┬──────────┘
                                                          │ ⑤Chat SSE（data: {...}）
                                                          ▼
                                              ┌─────────────────────┐
                                              │ convert_out.py      │
                                              │ Chat SSE → Responses │
                                              └──────────┬──────────┘
                                                          │ ⑥event: response.*
                                                          ▼
                                                    火山 Codex 收到
```

### 为什么要做协议转换（这是全项目的地基）

两边的「说话方式」根本不同：

| | 火山这套 Codex | WorkBuddy 上游 |
|---|---|---|
| 协议名 | Responses API | Chat Completions API |
| 请求路径 | `{base_url}/responses` | `{base_url}/v2/chat/completions` |
| 请求体 | `input`（元素数组，带 `type`） + `instructions` | `messages`（role/content） |
| 流式事件 | `event: response.output_text.delta` | `data: {choices:[{delta:{content}}]}` |
| 收尾标志 | `response.completed` | `data: [DONE]` |
| 工具声明 | `{type:"function", name, parameters}` | `{type:"function", function:{name, parameters}}` |
| 支持 chat wire？ | **不支持**（二进制里写死报错） | 只支持 chat |

所以中间必须有一层翻译。这不是「可选优化」，是**不做就跑不起来**。

### 三道上游闸门（每一条都实测过，漏一条就 400）

#### 闸门一：会话身份三连

每个请求必须带三个 UUID 头：

```
X-Conversation-ID: <uuid>
X-Conversation-Request-ID: <uuid>
X-Conversation-Message-ID: <uuid>
```

**网关不校验这些 id 从哪来**——任何格式合法的 UUID 都能过。缺一个就是 `400 + 11128 / conversation id missing`。

实测对照（来自 DSH 插件 5.30.0 的记录，本项目独立复现）：

| 头 | messages | 结果 |
|---|---|---|
| 无三连 | `[system, user]` | 400 / 11128 |
| 有三连 | `[system, user]` | 200 |
| 有三连 | `[user]`（无 system 头） | 400 / 11128 |

#### 闸门二：首条必须是 system

`messages[0].role` 必须是 `system`。Codex 发来的 `developer` 角色上游不认，必须先改名。本项目在 `normalize_body()` 里做这件事。

#### 闸门三：system 开头不能是第三方 CLI 身份句

这是最难发现、也最关键的一条。网关对 `system` 消息做**前缀匹配**，开头若是别的 AI 工具的身份句，整单拒绝。

实测（2026-11-23，deepseek-v4.1-flash，其余字段全部固定）：

| system 开头 | 结果 |
|---|---|
| `You are a coding agent running in the Codex CLI, ...` | **400 / 11128** |
| 上面同一句，前面加 `Okay.` | 200 |
| 上面同一句，前面加 `1` | 200 |
| 上面同一句，前面加 `Hi.` | 200 |
| 同一句改一个词（`OpenAI`→`the vendor`） | 200 |
| 同一句末尾加空格 | 400 / 11128 |
| 同一句插零宽字符 U+200B | 400 / 11128 |

**所以解法是：在 system 开头垫一句中性话。** 见 `upstream.apply_channel_gate()`。

> 💡 为什么不用「逐句改写原文」？因为改原文会改变模型看到的提示，可能影响行为；垫一句话几乎不影响，而且实现简单、幂等、可关。
> ⚠️ 为什么零宽字符无效？因为上游在匹配前会归一化不可见字符。这一条是 DSH 插件 2026-10-29 两次独立探测测出来的，本项目复现一致。

### 换号是怎么触发的

`UpstreamClient.open_chat()` 按账号池顺序逐个试：

```python
candidates = self.pool.pick_order()        # 按 (失败次数, 上次使用时间) 排序
for account in candidates[:max_failover]:
    if account.token_expired:
        self.refresh_token(account)        # 只在确已过期时刷（策略 A）
    attempt = self._try_one(account, body)
    if attempt.ok:
        return attempt                     # 成功就返回
    failure = attempt.failure
    if not failure.worthy_of_failover:
        return attempt                     # 不值得换号 → 直接抛给用户
    self.pool.mark_failure(account, failure.kind, failure.message)  # 进冷却
```

哪些失败值得换号、哪些不值得：

| 失败类型 | 业务码/HTTP | 换号有用吗 | 为什么 |
|---|---|---|---|
| `hard_credit` | 402 / 含 credits | ✅ 有用 | 这个号没额度了，换一个就有 |
| `session_dead` | 401 / 403 | ✅ 有用 | 这个号登录坏了，别的号是好的 |
| `account_restricted` | 11140 + 限制文案 | ✅ 有用 | 这个号被限制，换一个 |
| `soft_rate` | 429 | ✅ 有用 | 这个号被限流，换一个绕过 |
| `model_busy` | 含 busy/排队 | ✅ 有用 | 这个号排队长 |
| `channel_reject` | 11128 | ❌ **没用** | 是请求形态问题，所有号都一样 |
| `policy_reject` | 11140（无限制文案） | ❌ **没用** | 是内容问题，换号也一样拒 |
| `model_cannot_produce` | 11133 | ⚠️ 有限 | 常见原因是 reasoning_effort=off |

这个设计直接照抄了 DSH 插件 `isFailoverWorthy` 的判断——刻意**不**因为「网关匹配消息开头」就误换号，否则一个 11128 会把 13 个号全打进冷却。

### token 刷新策略（为什么是「懒」）

WorkBuddy 的 `refreshToken` 是**轮换式**的：刷新一次，旧的 refreshToken 立即失效。

这意味着：**如果中继和 DSH 插件同时刷同一个账号，先刷的那份会让另一份失效。**

所以 `token_policy` 默认是 `lazy`：

- 平时只读 token，不刷
- 只有当 `expiresAt` 已经过期，才刷一次
- 刷完立即写回保险库 JSON（原子写），DSH 那边也能用上

如果你完全不用 DSH 的 WorkBuddy 功能，可以把策略保持 `lazy` 并放心让它刷；如果要两边同时长跑，见 [已知限制](#已知限制与安全说明)。

### 上游 SSE 长什么样

实测一帧（`deepseek-v4.1-flash`，真实返回）：

```
data: {"id":"1875a413-...","model":"deepseek-v4.1-flash","object":"chat.completion.chunk","created":1795382744,"choices":[{"index":0,"delta":{"role":"assistant","content":"","reasoning_content":"","function_call":null,"refusal":"","tool_calls":[],"extra_fields":null},"logprobs":null,"finish_reason":""}],"usage":null}
```

注意几个细节：

- `delta.content` 是正文增量
- `delta.reasoning_content` 是思考增量（DeepSeek 系有）
- `delta.tool_calls` 是工具调用增量（按 `index` 分组累积）
- 最后一帧带 `usage`
- 结束时发 `data: [DONE]`

### 中继发回的 Responses 事件序列

```
event: response.created
event: response.in_progress
event: response.output_item.added          （正文项开始）
event: response.output_text.delta          × N
event: response.output_text.done
event: response.output_item.done
event: response.completed                  ← Codex 认这个作为结束
```

如果有工具调用，中间会插：

```
event: response.output_item.added          （function_call 项，status=in_progress）
event: response.function_call_arguments.delta   × N
event: response.function_call_arguments.done
event: response.output_item.done
```

如果有思考内容：

```
event: response.reasoning_summary_part.added
event: response.reasoning_summary_text.delta   × N
event: response.reasoning_summary_text.done
event: response.reasoning_summary_part.done
```

> ⚠️ **`response.completed` 是必须的。** Codex 二进制里有明确报错串 `stream closed before response.completed`——少发这个事件，火山里会显示「流意外中断」。

### 性能与限制

| 项 | 数值 | 说明 |
|---|---|---|
| 单请求延迟 | 上游首字延迟 + 中继转换开销（<10ms） | 中继是纯 Python 转发，不缓存、不改写正文 |
| 并发 | 理论无上限（`ThreadingHTTPServer`） | 但上游有账号级限流，并发太高会大量 429 |
| 上下文窗口 | 262144 tokens | 目录里所有模型都按这个填，实际以上游为准 |
| 请求体大小 | 实测 Codex 首轮 41108 字节 | 随对话增长；没有硬限制，但越大首字越慢 |
| 日志写入 | 同步写，每行一次 open/append/close | 量不大，实测无感知 |

---
## 排错手册（按症状查）

### 症状：火山里报「连接失败 / connection refused / 无法连接」

| 原因 | 怎么确认 | 怎么解决 |
|---|---|---|
| 中继没启动 | 浏览器打开 `http://127.0.0.1:17583/healthz` 打不开 | 双击 `启动中继.bat` |
| 端口改了但火山没改 | 面板显示 `运行中（http://127.0.0.1:17584）` 之类 | 把火山里那个预设重新导入，服务地址填新端口 |
| 端口被别的软件占了 | 启动时弹「端口可能被占用」 | 面板里把端口改成 17584，重启服务，再改火山 |
| 防火墙拦了 | 少见（本地回环一般不过防火墙） | 检查杀毒软件的「网络防护」 |

### 症状：火山里报「请求被拒绝」/ HTTP 400 / 业务码 11128

**这是最常见的问题。** 业务码 11128 = 渠道校验失败。

| 原因 | 怎么确认 | 怎么解决 |
|---|---|---|
| 渠道校验规避被关了 | 面板 → 设置 → 「启用渠道校验规避」没勾 | **勾上它**（默认是勾的） |
| `neutral_head` 被清空 | 打开 `config.json` 看 `neutral_head` 是不是 `""` | 改回 `"You are a helpful coding assistant."` |
| 中继版本太老 | 看面板标题的版本号 | 升级到 v1.1.0 或以上 |

日志里会明确写：

```
2026-11-23 05:31:08 [ERROR] [responses] 上游渠道校验失败（11128）：请求被判定为非官方客户端或缺少会话身份，换账号无效。
```

> 💡 注意这条错误的最后四个字「换账号无效」——换号是解决不了 11128 的，别浪费时间点「检测全部账号」。

### 症状：火山里报「积分不足 / 402」

| 原因 | 怎么确认 | 怎么解决 |
|---|---|---|
| 所有账号都没额度了 | 面板账号池，看「最近错误」列是不是全是 `hard_credit` | 给账号充值 / 换有额度的号加入池子 / 换更省的模型 |
| 用了最贵的模型 | 面板 → 默认模型是不是 `kimi-k3-1`（1.62 倍） | 换 `glm-5.3-flash`（0.08 倍），省 20 倍 |

### 症状：账号列表是空的 / 显示「没有可用账号」

| 原因 | 怎么确认 | 怎么解决 |
|---|---|---|
| 保险库目录不对 | 面板 → 设置 → 保险库目录，看路径存不存在 | 改成正确路径（默认 `%USERPROFILE%\.dsh\workbuddy-vault`） |
| 从没在 DSH 登录过 | 那个目录存在但是空的 | 打开 DSH，登录一次 WorkBuddy |
| 区域勾选错了 | 设置里「国内版」没勾 | 勾上国内版 |
| 有账号但都过期了 | 状态列显示「冷却中（token 已过期）」 | 去 DSH 重新登录刷新，或面板点「重新载入账号」 |

### 症状：一直转圈不回复 / 超时

| 原因 | 怎么确认 | 怎么解决 |
|---|---|---|
| 上游在排队 | 日志里有 `model_busy` 或 `cooldown_seconds=30` | 等一会儿，或换账号（点「检测全部账号」会触发换号） |
| `request_timeout_seconds` 太小 | 你的问题特别长、模型在深度思考 | 改大到 900 或 1200 |
| 网络到腾讯云不通 | `curl https://copilot.tencent.com` 试一下 | 换网络 / 挂代理 |
| 模型不支持当前请求 | 日志有 `model_cannot_produce` / 11133 | 换模型，或打开 `strip_reasoning_effort_off` |

### 症状：Codex 只会聊天，不执行命令、不改文件

| 原因 | 怎么确认 | 怎么解决 |
|---|---|---|
| `pass_tools` 被关了 | 面板 → 设置 → 「把工具调用透传给上游」没勾 | **勾上它** |
| 上游模型不支持工具调用 | 看该模型的 `supportsToolCall` 字段 | 换 `deepseek-v4.1-flash` 或 `glm-5.3` |
| Codex 自己的沙箱/审批策略拦的 | 火山里会显示 `Rejected(...): blocked by policy` | 这是**Codex 侧**的限制，不是本项目的问题；去火山/Codex 的配置里调 `approval_policy` 与 `sandbox_mode` |

> 💡 实测样例：问模型「执行 echo HELLO」，它回「我这边的 shell 执行能力被禁用（approval policy: never + 只读沙箱），所以我无法提供原样输出」。这说明**工具调用链路是通的**，只是 Codex 不让它执行。

### 症状：回复是空的 / `stream closed before response.completed`

| 原因 | 怎么确认 | 怎么解决 |
|---|---|---|
| 中继发的事件序列缺 `response.completed` | 日志有「上游流未正常收尾，仍补发 completed」 | 看上面的错误，通常是上游提前断了 |
| 上游返回了非 SSE 内容 | 日志有「读取上游流异常」 | 把日志最后 50 行发给开发者 |

### 症状：GUI 打不开 / 一闪就没了

| 原因 | 怎么确认 | 怎么解决 |
|---|---|---|
| 没装 PySide6 | 命令行跑 `python -c "import PySide6"` 报错 | `python -m pip install PySide6` |
| Python 太老 | `python --version` 低于 3.8 | 装 3.10 |
| 启动就崩 | 改跑 `启动中继_无界面.bat`，看报错 | 把报错发给开发者 |

> 没有 PySide6 也能用：`启动中继_无界面.bat` 只跑服务不开面板，功能完全一样。

### 症状：日志里有一堆 `cooldown_seconds=3600`

说明有账号因为积分不足或受限被打进 1 小时冷却。这是**正常设计**，不是 bug——省得对着一个没额度的号反复试。

想早点解封：面板里点「重新载入账号」不会清冷却（刻意的：清了只会再失败一次）。真要清，重启中继即可（冷却状态在内存里，重启即清）。

### 日志在哪、怎么读

两个地方：

1. 面板 → 「运行日志」标签页，点「刷新日志」，看最近 300 行
2. 文件：`G:\Python_Code\vol_connect_workbuddy\logs\relay-YYYYMMDD.log`

日志格式：

```
<时间> [<级别>] [<通道>] <内容>
```

| 通道 | 含义 |
|---|---|
| `app` | 进程启停 |
| `server` | HTTP 服务监听 |
| `http` | 每个请求的路径与状态码 |
| `responses` | Responses 请求处理（含上游错误） |
| `chat_ok` / `chat_fail` | 单次上游调用结果 |
| `failover` | 换号事件 |
| `refresh` | token 刷新结果 |
| `probe` | 账号检测结果 |
| `admin` | 面板操作 |

常见报错原文对照：

| 日志原文 | 含义 | 该做什么 |
|---|---|---|
| `上游渠道校验失败（11128）` | system 开头被拒 | 打开「渠道校验规避」 |
| `积分或额度不足（402 / credits）` | 这个号没额度 | 换号/充值 |
| `登录态失效（401/403）` | token 坏了 | 刷新或重新登录 |
| `被上游限流（429）` | 请求太密 | 降低并发，等 60 秒 |
| `模型繁忙或在排队` | 上游排队 | 等 30 秒 |
| `模型无法产出结果（11133）` | 常见 reasoning_effort=off | 换模型 |
| `连接上游失败：...` | 网络不通 | 检查网络 |
| `读取上游流异常` | 上游返回格式异常 | 看详情 |

---
## 常见问题 FAQ

**Q1：我需要自己填 API Key 吗？**
A：不需要。预设里 `experimental_bearer_token = "PROXY_MANAGED"` 就是「认证交给本地代理」的意思。导入时如果弹出密钥框，随便填。

**Q2：我的账号凭证会传到别的地方吗？**
A：不会。凭证只从本机 `workbuddy-vault` 目录读取，直接发给腾讯的 `copilot.tencent.com`（就是你平时用 WorkBuddy 时本来就发的地方），中间不经过任何第三方。中继只跑在 `127.0.0.1`。

**Q3：13 个账号会被一起消耗吗？**
A：不会。默认只用一个账号，用不了才换下一个。`max_failover` 控制最多试几个（默认 3）。

**Q4：会不会和 DSH 的 WorkBuddy 插件冲突？**
A：**只有一点会**：token 刷新。`refreshToken` 是轮换式的，两边同时刷会让先刷的那份失效。本项目的 `token_policy=lazy` 已经把这个风险降到最低（只在确已过期时刷，且刷完写回保险库）。要完全避免，就不同时在 DSH 里跑长任务。

**Q5：能同时开多个火山窗口用吗？**
A：可以。中继是多线程服务（`ThreadingHTTPServer`），能同时处理多个请求。但注意账号级限流——同时开太多会被上游 429。

**Q6：为什么模型列表里有 25 个，但火山的目录里我看到的是 11 个？**
A：面板「默认模型」下拉只放 11 个最常用的；火山里的模型目录（model_catalog）放全 25 个。两者不冲突：目录决定你能选什么，默认模型决定没指定时用哪个。

**Q7：哪个模型最省钱？**
A：`glm-5.3-flash`、`space-bunny`、`minimax-m3.1-flash` 都是 0.08 倍。日常编码用 `deepseek-v4.1-flash`（0.11 倍）性价比最好。

**Q8：哪个模型最强？**
A：按积分倍率看，`kimi-k3-1`（1.62 倍）最贵，`kimi-k3.1-pro`（0.97 倍）与 `glm-5.0-turbo`（0.95 倍）次之；纯文本强推理推荐 `deepseek-v4-pro`（0.51 倍），性价比比 kimi 好得多。

**Q9：支持图片输入吗？**
A：取决于模型。`glm-4.6v`、`glm-5.3-flash`、`deepseek-v4.1-flash`、`kimi-k2.6` 之后的多模态模型支持。中继会把 Responses 的 `input_image` 转成 Chat 的 `image_url`。

**Q10：为什么 Codex 不能执行命令？**
A：这是 **Codex 自己的** `approval_policy` 与 `sandbox_mode` 决定的，不是本项目限制。本项目只负责把工具声明传上去、把模型的调用意图传回来。想让它能执行，去火山/Codex 的配置里放开审批与沙箱。

**Q11：中继关掉会怎样？**
A：火山里所有 WorkBuddy 请求立即失败（连接被拒绝）。它就是个代理，必须一直开着。想开机自启，把 `启动中继_无界面.bat` 的快捷方式放进「启动」文件夹（`Win+R` → 输入 `shell:startup`）。

**Q12：能装在别的电脑上吗？**
A：可以。拷贝整个文件夹，装 `requirements.txt` 里的依赖，然后把那台电脑上的 `workbuddy-vault` 准备好（在 DSH 里登录一次），或者手工往 `extra_accounts` 里填账号。

**Q13：为什么日志里显示 `account=cn/153`，153 是什么？**
A：是账号的昵称。WorkBuddy 有些账号的 nickname 就是数字。

**Q14：改了端口之后要做什么？**
A：两件事：① 面板里点「停止服务」再「启动服务」；② 把火山里的预设重新导入一次，服务地址改成新端口。

**Q15：`config.json` 被我改坏了怎么办？**
A：删掉它，重启中继，会自动生成一份默认配置。唯一要重填的是 `extra_accounts`（如果你手工加过号）。

**Q16：能用于商业项目吗？**
A：本项目代码是 MIT 许可，随便用。但 **WorkBuddy 服务本身有它自己的服务条款**，你拿它做什么由你负责——本项目只是把你已有的账号接进来。

**Q17：为什么不直接改 DSH 那个插件，非要重写一份？**
A：因为它是个打包好的 ESM bundle，跑在 DSH 进程里，端口随机、secret 进程内随机、且只开 `/v1/chat/completions` 不开 `/v1/responses`。火山这套 Codex 只认 Responses 协议，所以外面接不进去，必须自己写一份中间的翻译层。

**Q18：更新版本后要做什么？**
A：把新的 `relay/`、`gui/` 覆盖进去，把 `presets/` 里 4 个文件重新复制到 `D:\voldev\plugins\vol_ai_codex\models\`，然后在火山里重新导入一次预设（因为 toml 可能变了）。配置文件不用动，会自动补新字段。

---

## 版本更新简介

| 版本 | 日期 | 一句话变更 |
|---|---|---|
| v1.1.0 | 2026-11-23 | 新增账号导出/导入，文件格式与 DSH 插件 `dsh-connect-workbuddy` 双向互通；面板「账号池」页加两个按钮 |
| v1.0.0 | 2026-11-23 | 首个版本：多账号池、自动换号、token 刷新、Responses⇄Chat 协议转换、25 个模型、PySide6 中文面板 |

> 每个新版本会在这里加一行。想看重细节去看《软件升级迭代记录.md》。

---

## 已知限制与安全说明

### 已知限制

| 限制 | 影响 | 有没有办法绕过 |
|---|---|---|
| 中继必须一直开着 | 关掉就连不上 | 把 `启动中继_无界面.bat` 放启动项 |
| token 刷新会和 DSH 抢 | 两边同时刷会让先刷的失效 | 用 `token_policy=lazy`；或不同时跑 |
| 只支持 `wire_api = "responses"` | 老的 chat 型客户端接不进来 | 无（这是火山这套 Codex 的限制） |
| 不提供登录界面 | 新账号必须先在 DSH 登录，或手工填 token | 用 `extra_accounts` |
| 没有积分查询面板 | 看不到还剩多少积分 | 中继的失败分类会告诉你「没额度了」 |
| 不含生图/生视频 | 只能做代码与文本对话 | 那是另一个需求，本项目不做 |
| 日志不自动清理 | 长期跑会积累文件 | 手动删 `logs\` 里旧的 |

### 安全说明

**凭证处理原则：**

1. 凭证只从本机 `workbuddy-vault` 读取，**不写入任何预设文件**（`.model` / `.toml` / `model_catalog` 里没有任何 token）
2. 日志里**只打掩码指纹**（token 前 6 字符 + 字节数），从不打完整 token
3. 刷新后的 token 写回保险库时用**原子写**（`.tmp` + rename），断电不会写坏
4. `.gitignore` 已排除 `config.json`、`logs/`、`.env`、`*vault*/`、`*.token`

**网络边界：**

- 中继默认只绑 `127.0.0.1`，**局域网内其它机器访问不到**
- 改成 `0.0.0.0` 会让同网段任何机器都能用你的 WorkBuddy 账号——**强烈不建议**
- 出站只连腾讯的 `copilot.tencent.com` / `www.codebuddy.cn`（或国际版 `workbuddy.ai`）
- 没有遥测、没有回传、没有第三方请求

**合规提醒：**

- 本项目是**非官方**工具，与腾讯 / WorkBuddy 无关联
- 大量账号轮换使用可能违反 WorkBuddy 的服务条款，风险自负
- 请只用于你自己合法拥有的账号

---

## 开发者：目录结构、构建与回归

### 目录结构

```
vol_connect_workbuddy\
├─ relay\                        中继核心（每个模块 < 400 行）
│  ├─ __init__.py                 版本号
│  ├─ config.py                   配置读写（原子写）
│  ├─ accounts.py                 账号池与健康度
│  ├─ upstream.py                 上游客户端 + 渠道闸门规避
│  ├─ convert_in.py               Responses → Chat
│  ├─ convert_out.py              Chat SSE → Responses
│  ├─ server.py                   HTTP 路由
│  ├─ errors.py                   失败分类
│  ├─ logging_setup.py            日志
│  └─ app.py                      命令行入口
├─ gui\                           PySide6 中文面板
│  ├─ __init__.py
│  ├─ main_window.py              主窗口（< 450 行）
│  └─ workers.py                  QThread 工作线程
├─ presets\                       4 个火山预设文件（源）
├─ version\                       历史版本备份
├─ logs\                          运行日志（git 忽略）
├─ test_e2e.py                    端到端联调脚本
├─ requirements.txt
├─ config.json                    运行时配置（git 忽略）
├─ 启动中继.bat
├─ 启动中继_无界面.bat
├─ README.md
├─ 软件升级迭代记录.md
└─ LICENSE
```

### 常用命令

```bash
# 编译检查（改了代码先跑这个）
python -m compileall -q relay gui

# 只跑服务，不开面板（调试用）
python -m relay.app --no-gui

# 列出账号池状态后退出
python -m relay.app --list-accounts

# 端到端联调（真的会花积分）
python test_e2e.py
python test_e2e.py --prompt="说个笑话"

# 换模型联调
python test_e2e.py --model=glm-5.3-flash
```

### 手工验证清单（改完代码照着过一遍）

| 检查项 | 命令 | 期望 |
|---|---|---|
| 语法 | `python -m compileall -q relay gui` | 退出码 0 |
| 导入 | `python -c "from relay import server, upstream, convert_in, convert_out"` | 无异常 |
| 健康 | `curl http://127.0.0.1:17583/healthz` | `{"ok":true,...}` |
| 模型列表 | `curl http://127.0.0.1:17583/v1/models` | 含 `data` 数组 |
| Responses | `curl -X POST http://127.0.0.1:17583/v1/responses -d @_payload.json` | 以 `event: response.completed` 结尾 |
| 账号池 | `python -m relay.app --list-accounts` | 列出账号且状态正确 |
| GUI | `python -m relay.app` | 窗口起来、表格有内容 |

### 改代码时最需要注意的三件事

1. **别动 `apply_channel_gate()`**——它是 11128 的唯一解药。真要改，改完必须拿真实请求验证。
2. **别丢 `response.completed`**——Codex 靠它判断结束，丢了就是「流意外中断」。
3. **别把 token 写进日志或预设文件**——这是硬红线。

---

## 贡献与许可

### 许可

MIT License，见 [LICENSE](LICENSE)。你可以自由使用、修改、分发、商用，唯一要求是保留版权声明。

### 贡献

发现问题欢迎提 Issue，写清楚：

1. 你的火山版本、Codex 版本（`codex-app-server --version`）、本项目版本
2. 复现步骤
3. 日志最后 50 行（**注意先检查里面没有 token**）

### 致谢

- 协议细节、上游地址、错误分类口径，大量参考了 [dsh-connect-workbuddy](https://github.com/duma520/dsh-connect-workbuddy)（作者 dingminhua，MIT）的实现与实测记录
- 火山软件开发平台的模型预设机制由 vol_ai_codex 插件提供

---

> 本 README 最后更新：2026-11-23（v1.1.0）