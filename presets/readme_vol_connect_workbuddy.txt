WorkBuddy（多账号中继）——把火山 Codex 接到 WorkBuddy 多账号池。

这个预设本身不联网，它把请求交给本机的一个中继程序，由中继去管 WorkBuddy 账号。
所以用之前必须先启动中继：双击项目目录里的「启动中继.bat」，
或者在本机执行 python -m relay.app。

一、装在哪
本预设的四个文件放在火山的模型目录：
  D:\voldev\plugins\vol_ai_codex\models\
   ├─ vol_connect_workbuddy.model
   ├─ vol_connect_workbuddy.toml
   ├─ model_catalog_vol_connect_workbuddy.json
   └─ readme_vol_connect_workbuddy.txt（本文件）
中继程序是独立项目，放在 G:\Python_Code\vol_connect_workbuddy\。

二、地址怎么填
导入预设时，服务地址填：http://127.0.0.1:17583/v1
密钥随便填（或填 local），中继会忽略它——真正的账号凭据由中继从
C:\Users\<你的用户名>\.dsh\workbuddy-vault 读取，不会写进任何预设文件。

三、为什么不用填 API Key
预设里的 experimental_bearer_token 写的是 PROXY_MANAGED，配合
requires_openai_auth = false，意思是「认证交给本地代理」。这是火山现有
vol_relay_* 与 vol_local_* 系列预设的统一做法。

四、能选哪些模型
上游实测可用的 25 个模型都在 model_catalog_vol_connect_workbuddy.json 里，
按积分倍率从低到高排。最省的是 glm-5.3-flash / space-bunny /
minimax-m3.1-flash（0.08 倍），最强的是 deepseek-v4-pro（0.51 倍）与
kimi-k3-1（1.62 倍）。

五、出问题先看哪里
1. 火山里报「connection refused」→ 中继没起，去双击启动中继.bat。
2. 中继面板显示「没有可用账号」→ 检查设置里的保险库目录，或点「重新载入账号」。
3. 报 11128 → 面板设置里「启用渠道校验规避」被关掉了，打开它。
4. 报 402 或积分不足 → 中继会自动换号；全都不够时面板会写明。

官方文档：https://github.com/duma520/vol_connect_workbuddy
本信息填写日期：2026年11月23日