"""vol_connect_workbuddy 本地中继核心包。

模块职责：
- config      配置读写（实时落盘）
- accounts    账号池（读 DSH 保险库 + 手工追加）
- upstream    WorkBuddy 上游客户端
- convert_in  Responses 请求 → Chat Completions 请求
- convert_out Chat Completions SSE → Responses 事件
- server      HTTP 服务（/v1/responses 等）
- errors      上游错误分类
- transfer    账号导出 / 导入（与 dsh-connect-workbuddy 插件格式互通）
"""

__version__ = "1.1.0"
