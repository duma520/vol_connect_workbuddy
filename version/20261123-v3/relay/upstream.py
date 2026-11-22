"""WorkBuddy 上游客户端：发聊天请求、刷新 token、按错误类别换号。

上游真相（全部为实测，不要凭记忆改）：
- 聊天端点 POST {chatBase}/v2/chat/completions，普通 OpenAI Chat Completions SSE。
- 国内区 chatBase = https://copilot.tencent.com；国际区用凭据自己的 domain。
- 两道硬闸门：会话身份三连（X-Conversation-ID / -Request-ID / -Message-ID）必发，
  且 messages 首条必须是 system。缺任何一个都是 400 + 业务码 11128。
- 上游拒绝非流式，stream 必须为 true。
- 刷新端点 POST {base}/v2/plugin/auth/token/refresh，头 X-Refresh-Token。
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Iterator

import httpx

from . import accounts as accounts_mod
from . import config
from .errors import UpstreamFailure, classify

CN_CHAT_BASE = "https://copilot.tencent.com"
CN_BILLING_BASE = "https://www.codebuddy.cn"
GLOBAL_BASE = "https://www.workbuddy.ai"
CLIENT_UA = "CLI/2.63.2 CodeBuddy/2.63.2"
APP_VERSION = "5.8.3"
CLIENT_NAME = "WorkBuddy"

# 单次请求最多尝试多少个账号


def _uuid() -> str:
    return str(uuid.uuid4())


def region_of(domain: str) -> str:
    """按凭据 domain 判区域。国际版走 workbuddy.ai，其余按国内版处理。"""
    lowered = (domain or "").lower()
    if lowered == "workbuddy.ai" or lowered.endswith(".workbuddy.ai"):
        return "global"
    return "cn"


def chat_base(account: accounts_mod.Account) -> str:
    if region_of(account.domain) == "global":
        host = (account.domain or GLOBAL_BASE).strip()
        if not host.startswith("http"):
            host = "https://" + host
        return host.rstrip("/")
    return CN_CHAT_BASE


def origin_referer(account: accounts_mod.Account) -> str:
    if region_of(account.domain) == "global":
        return GLOBAL_BASE
    return CN_BILLING_BASE


def build_chat_headers(account: accounts_mod.Account) -> dict:
    """构造一次聊天请求的全部头。会话三连每次新生成。"""
    origin = origin_referer(account)
    language = "en-US" if region_of(account.domain) == "global" else "zh-CN"
    headers = {
        "Authorization": "Bearer " + account.access_token,
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": origin,
        "Referer": origin + "/",
        "User-Agent": CLIENT_UA,
        "X-CodeBuddy-Request": "1",
        "Accept-Language": language,
        "X-Agent-Purpose": "conversation",
        "X-IDE-Name": CLIENT_NAME,
        "X-IDE-Type": CLIENT_NAME,
        "X-IDE-Version": APP_VERSION,
        "X-Product": CLIENT_NAME,
        "X-Conversation-ID": _uuid(),
        "X-Conversation-Request-ID": _uuid(),
        "X-Conversation-Message-ID": _uuid(),
        "X-Root-Request-ID": _uuid(),
    }
    if account.uid:
        headers["X-User-Id"] = account.uid
    else:
        headers["X-No-User-Id"] = "1"
    headers["X-No-Enterprise-Id"] = "1"
    if account.domain:
        headers["X-Domain"] = account.domain
    else:
        headers["X-No-Department-Info"] = "1"
    return headers


def build_refresh_headers(account: accounts_mod.Account) -> dict:
    origin = origin_referer(account)
    return {
        "Accept": "application/json, text/plain, */*",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": origin,
        "Referer": origin + "/",
        "User-Agent": CLIENT_UA,
        "X-Refresh-Token": account.refresh_token,
        "X-Auth-Refresh-Source": "workbuddy",
    }


def ensure_system_head(body: dict, placeholder: str) -> None:
    """上游硬闸门：首条必须是 system。就地修改 body。"""
    messages = body.get("messages")
    if not isinstance(messages, list) or not messages:
        body["messages"] = [{"role": "system", "content": placeholder}]
        return
    first = messages[0]
    if isinstance(first, dict) and first.get("role") == "system":
        return
    messages.insert(0, {"role": "system", "content": placeholder})


# 上游网关的「渠道校验」是**前缀匹配**：只要某条 system 消息的开头是第三方
# CLI 的身份句，就整单 400 + 业务码 11128。实测（2026-11-23，deepseek-v4.1-flash）：
#   Codex 原文 "You are a coding agent running in the Codex CLI, ..."  → 400/11128
#   同样文本前面加 "Okay."、加 "1"、加 "Hi."                        → 200
# 结论：不需要逐句改写原文，只要在 system 开头垫一句中性话就能过闸；
# 这也是 dsh-connect-workbuddy 里 neutralizeChannelFingerprints 的等价效果，
# 而且不改变原文一个字，模型看到的提示基本不变。
NEUTRAL_HEAD = "You are a helpful coding assistant."


def apply_channel_gate(body: dict, settings: dict) -> None:
    """给每条会被网关扫描的角色（system / assistant）垫中性开头。"""
    if not settings.get("enable_channel_gate_fix", True):
        return
    messages = body.get("messages")
    if not isinstance(messages, list):
        return
    head = str(settings.get("neutral_head") or NEUTRAL_HEAD)
    for index, message in enumerate(messages):
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "").strip().lower()
        if role not in ("system", "assistant"):
            continue
        content = message.get("content")
        if isinstance(content, str):
            if not content.startswith(head):
                message["content"] = head + "\n\n" + content if content else head
            continue
        if isinstance(content, list):
            for part in content:
                if not isinstance(part, dict):
                    continue
                if str(part.get("type") or "").strip().lower() != "text":
                    continue
                text = part.get("text")
                if not isinstance(text, str):
                    continue
                if not text.startswith(head):
                    part["text"] = head + "\n\n" + text if text else head
        elif index == 0:
            message["content"] = head


def normalize_body(body: dict, settings: dict) -> dict:
    """上游强制的整形：stream=true、developer→system、首条 system、tool_choice 压平。"""
    out = dict(body)
    out["stream"] = True
    messages = out.get("messages")
    if isinstance(messages, list):
        fixed = []
        for message in messages:
            if isinstance(message, dict) and message.get("role") == "developer":
                message = dict(message)
                message["role"] = "system"
            fixed.append(message)
        out["messages"] = fixed
    ensure_system_head(out, str(settings.get("system_head_placeholder") or NEUTRAL_HEAD))
    apply_channel_gate(out, settings)

    tools = out.get("tools")
    if not isinstance(tools, list) or not tools:
        out.pop("tool_choice", None)
        return out
    choice = out.get("tool_choice")
    if isinstance(choice, dict):
        if choice.get("type") == "function":
            name = choice.get("name") or (choice.get("function") or {}).get("name") or ""
            out["tool_choice"] = str(name) if name else "auto"
        elif choice.get("type") in ("auto", "required", "none"):
            out["tool_choice"] = str(choice.get("type"))
        else:
            out["tool_choice"] = "auto"
    elif isinstance(choice, str):
        out["tool_choice"] = choice
    else:
        out["tool_choice"] = "auto"

    if out.get("tool_choice") == "none":
        out.pop("tools", None)
        out.pop("tool_choice", None)
    return out


@dataclass
class ChatAttempt:
    """一次聊天尝试的结果：成功时 stream 是已打开的上游响应。"""

    ok: bool
    account: accounts_mod.Account | None = None
    response: Any = None
    failure: UpstreamFailure | None = None


class UpstreamClient:
    """带账号池的上游客户端。"""

    def __init__(self, pool: accounts_mod.AccountPool | None = None) -> None:
        self.pool = pool or accounts_mod.pool()
        self._lock = threading.RLock()
        self._refresh_lock = threading.Lock()
        self.on_event: Callable[[str, dict], None] | None = None

    def _emit(self, kind: str, payload: dict) -> None:
        if self.on_event is not None:
            try:
                self.on_event(kind, payload)
            except Exception:
                pass

    # ---------- token 刷新 ----------

    def refresh_token(self, account: accounts_mod.Account, client: httpx.Client) -> bool:
        """刷新一个账号的 accessToken。策略 A：只在确已过期时调用。"""
        if not account.refresh_token:
            return False
        with self._refresh_lock:
            url = CN_BILLING_BASE + "/v2/plugin/auth/token/refresh"
            if region_of(account.domain) == "global":
                url = (account.domain or GLOBAL_BASE).rstrip("/") + "/v2/plugin/auth/token/refresh"
            try:
                response = client.post(url, headers=build_refresh_headers(account), timeout=30.0)
            except httpx.HTTPError as exc:
                self._emit("refresh", {"account": account.label, "ok": False, "error": str(exc)[:200]})
                return False
            if response.status_code != 200:
                self._emit("refresh", {"account": account.label, "ok": False, "status": response.status_code})
                return False
            try:
                payload = response.json()
            except ValueError:
                return False
            data = payload.get("data") if isinstance(payload, dict) else None
            if not isinstance(data, dict):
                data = payload if isinstance(payload, dict) else {}
            token = data.get("accessToken") or data.get("access_token") or ""
            if not token:
                self._emit("refresh", {"account": account.label, "ok": False, "error": "no accessToken in reply"})
                return False
            account.access_token = str(token)
            new_refresh = data.get("refreshToken") or data.get("refresh_token")
            if new_refresh:
                account.refresh_token = str(new_refresh)
            expires = data.get("expiresAt") or data.get("expires_at")
            if expires:
                account.expires_at = float(expires)
            refresh_expires = data.get("refreshExpiresAt") or data.get("refresh_expires_at")
            if refresh_expires:
                account.refresh_expires_at = float(refresh_expires)
            self._persist_refreshed(account)
            self._emit("refresh", {"account": account.label, "ok": True})
            return True

    @staticmethod
    def _persist_refreshed(account: accounts_mod.Account) -> None:
        """把刷新结果写回保险库文件（原子写）。只动 auth 段，保留其它字段。"""
        if account.source != "vault" or not account.path:
            return
        try:
            from pathlib import Path
            path = Path(account.path)
            if not path.exists():
                return
            import json as _json
            payload = _json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return
            auth = payload.get("auth")
            if not isinstance(auth, dict):
                auth = {}
                payload["auth"] = auth
            auth["accessToken"] = account.access_token
            if account.refresh_token:
                auth["refreshToken"] = account.refresh_token
            if account.expires_at:
                auth["expiresAt"] = account.expires_at
            if account.refresh_expires_at:
                auth["refreshExpiresAt"] = account.refresh_expires_at
            payload["refreshedAtMs"] = int(time.time() * 1000)
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(_json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(path)
        except Exception:
            # 写回失败不影响本次请求：内存里的新 token 照样可用。
            pass

    # ---------- 聊天 ----------

    def open_chat(self, body: dict, client: httpx.Client, settings: dict) -> ChatAttempt:
        """按账号池顺序尝试，返回第一个成功的 attempt。"""
        candidates = self.pool.pick_order()
        if not candidates:
            return ChatAttempt(False, failure=UpstreamFailure(
                "no_account", 0, "没有可用账号：请检查保险库目录或手工追加账号。"))

        max_tries = int(settings.get("max_failover") or 3)
        last: ChatAttempt | None = None
        for account in candidates[:max_tries]:
            if account.token_expired and str(settings.get("token_policy")) != "never":
                self.refresh_token(account, client)
            attempt = self._try_one(account, body, client, settings)
            if attempt.ok:
                return attempt
            last = attempt
            failure = attempt.failure
            if failure is None:
                continue
            if not failure.worthy_of_failover:
                return attempt
            cooldown = self.pool.mark_failure(account, failure.kind, failure.message)
            self._emit("failover", {
                "account": account.label,
                "kind": failure.kind,
                "status": failure.status,
                "cooldown_seconds": cooldown,
            })
        if last is None:
            last = ChatAttempt(False, failure=UpstreamFailure("no_account", 0, "没有可用账号。"))
        return last

    def _try_one(self, account: accounts_mod.Account, body: dict, client: httpx.Client, settings: dict) -> ChatAttempt:
        url = chat_base(account) + "/v2/chat/completions"
        headers = build_chat_headers(account)
        try:
            request = client.build_request(
                "POST",
                url,
                headers=headers,
                content=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                timeout=float(settings.get("request_timeout_seconds") or 600),
            )
            response = client.send(request, stream=True)
        except httpx.HTTPError as exc:
            return ChatAttempt(False, account, failure=UpstreamFailure(
                "server", 0, "连接上游失败：" + str(exc)[:300]))

        if response.status_code == 200:
            self._emit("chat_ok", {"account": account.label})
            return ChatAttempt(True, account, response=response)

        try:
            raw = response.read().decode("utf-8", "replace")
        except Exception:
            raw = ""
        try:
            response.close()
        except Exception:
            pass
        failure = classify(response.status_code, raw)
        self._emit("chat_fail", {
            "account": account.label,
            "status": response.status_code,
            "kind": failure.kind,
        })
        return ChatAttempt(False, account, failure=failure)


def iter_chat_chunks(lines: Iterator) -> Iterator[dict]:
    """把上游 SSE 行流解析成 chunk 字典。遇到 [DONE] 结束。

    httpx 的 iter_lines() 已经解码成 str；这里同时兼容 bytes，避免调用方版本差异。
    """
    for raw in lines:
        if not raw:
            continue
        line = raw.decode("utf-8", "replace").strip() if isinstance(raw, (bytes, bytearray)) else str(raw).strip()
        if not line:
            continue
        if line.startswith(":"):
            continue
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if not payload or payload == "[DONE]":
            if payload == "[DONE]":
                return
            continue
        try:
            yield json.loads(payload)
        except ValueError:
            continue


def list_models(account: accounts_mod.Account, client: httpx.Client) -> list:
    """读上游 /v3/config 的模型清单。失败返回空列表。"""
    origin = origin_referer(account)
    headers = {
        "Authorization": "Bearer " + account.access_token,
        "Accept": "application/json, text/plain, */*",
        "User-Agent": CLIENT_UA,
        "X-CodeBuddy-Request": "1",
        "Accept-Language": "en-US" if region_of(account.domain) == "global" else "zh-CN",
    }
    if account.uid:
        headers["X-User-Id"] = account.uid
    if account.domain:
        headers["X-Domain"] = account.domain
    try:
        response = client.get(chat_base(account) + "/v3/config", headers=headers, timeout=30.0)
        if response.status_code != 200:
            return []
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        return []
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return []
    models = data.get("models")
    return models if isinstance(models, list) else []


_client: UpstreamClient | None = None


def client() -> UpstreamClient:
    global _client
    if _client is None:
        _client = UpstreamClient()
    return _client