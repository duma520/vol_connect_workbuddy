"""上游错误分类。

把 WorkBuddy 网关返回的各种失败归到少数几个可决策的类别：
- hard_credit    积分/额度耗尽（402 或 body 含 credits 相关标记）
- session_dead   登录态失效（token 过期且刷新失败）
- account_restricted 账号被限制（11140 内容策略族 + 限制文案）
- policy_reject  内容策略拒绝（11140）
- channel_reject 渠道校验失败（11128 家族，与账号/区域无关，换号无用）
- model_busy     模型排队/繁忙
- soft_rate      限流（429）
- server         其它服务端错误

只有 hard_credit / session_dead / account_restricted / soft_rate / model_busy
值得换号重试；channel_reject 与 policy_reject 换号也没用，必须原样抛给用户。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

# 与 WorkBuddy 上游约定的业务码
CODE_CONTENT_POLICY = 11140
CODE_CHANNEL_REJECT = 11128
CODE_MODEL_CANNOT_PRODUCE = 11133

# 换号后值得重试的类别
FAILOVER_KINDS = frozenset(
    {"hard_credit", "session_dead", "account_restricted", "soft_rate", "model_busy"}
)

# 账号受限的文案线索（必须与业务码同时命中，避免误伤）
_RESTRICTION_HINTS = (
    "account restricted",
    "account has been restricted",
    "账号已被限制",
    "账号被限制",
    "账号异常",
    "封禁",
)

_CREDIT_HINTS = ("credit", "积分", "额度不足", "余额不足", "quota")


@dataclass(frozen=True)
class UpstreamFailure:
    """一次上游失败的结构化描述。"""

    kind: str
    status: int
    message: str
    detail: str = ""

    @property
    def worthy_of_failover(self) -> bool:
        """该失败是否值得切换到下一个账号重试。"""
        return self.kind in FAILOVER_KINDS

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "status": self.status,
            "message": self.message,
            "detail": self.detail,
            "worthy_of_failover": self.worthy_of_failover,
        }


def _extract_business_code(text: str) -> int | None:
    """从失败体里读出业务码。

    上游的失败体形状不统一，实测出现过：
      {"code":11128}  {"code": 11128}  {"code":"11128"}  {"error":{"code":11128}}
    这里按「先解析 JSON，再回落到正则」的顺序读，兼容上述全部拼写。
    """
    if not text:
        return None
    stripped = text.strip()
    if stripped.startswith("{"):
        try:
            parsed = json.loads(stripped)
        except (ValueError, TypeError):
            parsed = None
        if isinstance(parsed, dict):
            for candidate in (parsed.get("code"), parsed.get("businessCode")):
                if isinstance(candidate, int):
                    return candidate
                if isinstance(candidate, str) and candidate.isdigit():
                    return int(candidate)
            nested = parsed.get("error")
            if isinstance(nested, dict):
                candidate = nested.get("code")
                if isinstance(candidate, int):
                    return candidate
                if isinstance(candidate, str) and candidate.isdigit():
                    return int(candidate)
            data = parsed.get("data")
            if isinstance(data, dict):
                candidate = data.get("code")
                if isinstance(candidate, int):
                    return candidate
    match = re.search(r'"code"\s*:\s*"?(-?\d+)"?', text)
    if match:
        return int(match.group(1))
    return None


def classify(status: int, body: str) -> UpstreamFailure:
    """把一次 HTTP 失败归类。"""
    lowered = (body or "").lower()
    code = _extract_business_code(body or "")

    if code == CODE_CHANNEL_REJECT or "11128" in lowered:
        return UpstreamFailure(
            "channel_reject",
            status,
            "上游渠道校验失败（11128）：请求被判定为非官方客户端或缺少会话身份，换账号无效。",
            (body or "")[:600],
        )

    if code == CODE_CONTENT_POLICY or "11140" in lowered:
        restricted = any(hint in lowered for hint in _RESTRICTION_HINTS)
        kind = "account_restricted" if restricted else "policy_reject"
        message = (
            "账号被上游限制（11140），建议换号。"
            if restricted
            else "内容策略拒绝（11140），换账号无效，请调整提问内容。"
        )
        return UpstreamFailure(kind, status, message, (body or "")[:600])

    if code == CODE_MODEL_CANNOT_PRODUCE or "11133" in lowered:
        return UpstreamFailure(
            "model_cannot_produce",
            status,
            "模型无法产出结果（11133）：常见原因是推理强度被设为 off，或该模型不支持当前请求形态。",
            (body or "")[:600],
        )

    if status == 402 or any(hint in lowered for hint in _CREDIT_HINTS):
        return UpstreamFailure(
            "hard_credit", status, "积分或额度不足（402 / credits）。", (body or "")[:600]
        )

    if status == 401 or status == 403:
        return UpstreamFailure(
            "session_dead", status, "登录态失效（401/403），需要刷新或重新登录。", (body or "")[:600]
        )

    if status == 429:
        return UpstreamFailure("soft_rate", status, "被上游限流（429）。", (body or "")[:600])

    if "busy" in lowered or "queued" in lowered or "排队" in (body or ""):
        return UpstreamFailure("model_busy", status, "模型繁忙或在排队。", (body or "")[:600])

    if status >= 500:
        return UpstreamFailure("server", status, f"上游服务端错误（{status}）。", (body or "")[:600])

    return UpstreamFailure("client", status, f"上游拒绝了请求（{status}）。", (body or "")[:600])
