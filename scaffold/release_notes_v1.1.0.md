# v1.1.0 —— 账号导出 / 导入（与 DSH 插件双向互通）

这次更新只做一件事：**把账号搬来搬去**。换电脑、备份、从 DSH 插件 `dsh-connect-workbuddy` 迁过来，都不用再手工贴 13 个 token。

## 一句话定位

火山软件开发平台的 Codex 只认 Responses 协议，WorkBuddy 上游只有 Chat Completions —— 本项目是中间那层翻译 + 多账号池 + 自动换号。本版再加账号导入导出。

## 本次新增

| 能力 | 在哪 | 说明 |
|---|---|---|
| 导出账号 | 面板「账号池」页 →「导出账号」 | 勾选后存 JSON，文件名 `workbuddy-accounts-日期.json` |
| 导入账号 | 面板「账号池」页 →「导入账号」 | 选文件 → 脱敏预览 → 勾选 → 导入 |
| 与插件互通 | 双向 | 本程序导出的文件插件能直接导入，插件导出的文件本程序能直接导入 |
| 幂等覆盖 | 自动 | 同一账号反复导入始终覆盖同一份文件，不会堆重复 |

## 两个技术要点（也是这次踩到的真坑）

1. **账号 id 必须是 `sha256("workbuddy\0" + uin)` 的前 24 位十六进制**。
   与插件 `workbuddyAccountId()` 逐字节一致。一开始直接拿 uin 当文件名，结果导入变成「新增 13 个」而不是「覆盖 13 个」（实测 cn 14 → 27 个文件）。改成同款算法后：cn 14 → 14，内容刷新、零新增。
2. **区域判定用严格版**：只认 `workbuddy.ai` / `codebuddy.ai`（global）与 `workbuddy.cn` / `codebuddy.cn` / `copilot.tencent.com`（cn），其余算「无法判定」直接跳过。
   宽松版「认不出就当国内版」会把外域或伪造凭据塞进国内版保险库。

## 三步安装（老用户升级）

1. 把 `relay/`、`gui/` 覆盖到项目目录，`presets/` 4 个文件重新复制到 `D:\voldev\plugins\vol_ai_codex\models\`。
2. 重启 `启动中继.bat`。
3. 火山里重新导入一次预设（toml 可能变了）。`config.json` 不用动，会自动补新字段。

## 全新的用户（从零）

1. 解压，双击 `启动中继.bat`，窗口显示「运行中（http://127.0.0.1:17583）」。
2. 把 `presets/` 里 4 个文件复制到 `D:\voldev\plugins\vol_ai_codex\models\`。
3. 火山软件开发平台 → 模型配置 → 选「WorkBuddy（多账号中继）」→ 导入 → 服务地址 `http://127.0.0.1:17583/v1`。

## 配置与数据在哪

| 东西 | 路径 |
|---|---|
| 配置文件 | `<项目目录>\config.json`（首次启动自动生成） |
| 日志 | `<项目目录>\logs\relay-YYYYMMDD.log` |
| 账号来源 | `C:\Users\<你>\.dsh\workbuddy-vault\{cn,global}\*.json`（与其他工具共用的保险库） |
| 导出的账号文件 | 你另存到哪就在哪（含明文 token，勿外发） |

## 版本历史

| 版本 | 日期 | 一句话变更 |
|---|---|---|
| v1.1.0 | 2026-11-23 | 账号导出/导入，与 dsh-connect-workbuddy 双向互通 |
| v1.0.0 | 2026-11-23 | 首个版本：多账号池、自动换号、token 刷新、协议转换、25 个模型、中文面板 |

## 已知限制

- 上游是第三方网关，**渠道校验（11128）与内容策略（11140）换号也没用**，会直接把原因告诉你。
- 国际版与国内版 token 不能互换，跨区域导入会被跳过。
- 导出的账号文件是**明文 token**，等于账号钥匙。别发群、别传网盘、别提到仓库。
- 只支持 OpenAI Responses 协议（火山 Codex 的要求），不做 Chat Completions 出站。

## 文档

- 完整说明书：[README.md](https://github.com/duma520/vol_connect_workbuddy#readme)（从零基础到高级应用，含 18 条 FAQ 与排错手册）
- 详细改动：[软件升级迭代记录.md](https://github.com/duma520/vol_connect_workbuddy/blob/main/%E8%BD%AF%E4%BB%B6%E5%8D%87%E7%BA%A7%E8%BF%AD%E4%BB%A3%E8%AE%B0%E5%BD%95.md)

## 本次验证

| 项 | 结果 |
|---|---|
| 编译 `compileall relay gui scaffold` | 退出码 0 |
| 区域判定 13 个用例（含仿冒域） | 13/13 通过 |
| 账号 id 与真实保险库文件名比对 | 13/13 一致 |
| HTTP 导出 / 预览 / 跨区域跳过 | 全部符合预期 |
| HTTP 导入（备份→导入→还原→哈希比对） | imported=13、cn 14→14（覆盖不新增）、还原哈希一致 |
| 往返一致（写盘→重载→再导出） | token/uin/uid 全保住，expiresAt 毫秒不变 |
| GUI offscreen 冒烟 | 两按钮存在、导出 13 行全勾、导入未选文件时禁用 |
| Responses 主链路 | SSE 正常，`output_text.delta` 有内容 |
| codex-app-server 端到端 | ok=true，thread 正常创建 |