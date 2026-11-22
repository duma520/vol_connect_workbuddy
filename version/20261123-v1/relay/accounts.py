"""账号池：读取 DSH 保险库、合并手工账号、按健康度选号。

账号来源优先级：
1. 保险库目录（默认 ~/.dsh/workbuddy-vault/{cn,global}/*.json）
2. 配置里的 extra_accounts（手工追加，字段同保险库 auth 结构）

绝不打印 accessToken / refreshToken 的值；只暴露掩码指纹。
"""

from __future__ import annotations

import glob
import json
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import config

# 一次失败后冷却多久（秒）
COOLDOWN_BY_KIND = {
    "hard_credit": 3600,
    "account_restricted": 3600,
    "session_dead": 1800,
    "soft_rate": 60,
    "model_busy": 30,
    "model_cannot_produce": 120,
}
DEFAULT_COOLDOWN = 120


@dataclass
class Account:
    """一个 WorkBuddy 账号的运行时视图。"""

    account_id: str
    region: str
    access_token: str
    refresh_token: str
    expires_at: float
    refresh_expires_at: float
    domain: str
    uid: str
    nickname: str
    uin: str
    source: str = "vault"
    path: str = ""

    failures: int = 0
    cooldown_until: float = 0.0
    last_error: str = ""
    last_used_at: float = 0.0
    success_count: int = 0

    @property
    def available(self) -> bool:
        """当前是否可用（没在冷却，且刷新令牌没彻底过期）。"""
        now = time.time()
        if self.cooldown_until > now:
            return False
        if self.refresh_expires_at and self.refresh_expires_at < now:
            return False
        return bool(self.access_token)

    @property
    def token_expired(self) -> bool:
        return bool(self.expires_at) and self.expires_at < time.time()

    @property
    def label(self) -> str:
        who = self.nickname or self.uin or self.account_id[:8]
        return self.region + "/" + who

    def fingerprint(self) -> str:
        """给日志用的安全指纹：不泄漏 token 内容。"""
        token = self.access_token or ""
        head = token[:6] if len(token) > 12 else ""
        return head + "...(" + str(len(token)) + "B)"


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _parse_account(raw: dict, region: str, source: str, path: str = "") -> Account | None:
    auth = raw.get("auth") or {}
    info = raw.get("account") or {}
    token = auth.get("accessToken") or ""
    if not token:
        return None
    return Account(
        account_id=str(raw.get("accountId") or info.get("uid") or path or "unknown"),
        region=region,
        access_token=token,
        refresh_token=auth.get("refreshToken") or "",
        expires_at=_to_float(auth.get("expiresAt")),
        refresh_expires_at=_to_float(auth.get("refreshExpiresAt")),
        domain=auth.get("domain") or "",
        uid=str(info.get("uid") or ""),
        nickname=str(info.get("nickname") or ""),
        uin=str(info.get("uin") or ""),
        source=source,
        path=path,
    )


def load_from_vault(vault_dir: str, regions: list) -> list:
    """从保险库目录读出全部账号。regions 是 ["cn"] / ["global"] / 两者。"""
    out: list = []
    if not vault_dir or not os.path.isdir(vault_dir):
        return out
    for region in regions:
        pattern = os.path.join(vault_dir, region, "*.json")
        for path in sorted(glob.glob(pattern)):
            try:
                raw = json.loads(Path(path).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not isinstance(raw, dict):
                continue
            account = _parse_account(raw, region, "vault", path)
            if account is not None:
                out.append(account)
    return out


def load_extra(entries: list) -> list:
    """从配置的手工账号列表构造账号。"""
    out: list = []
    for index, entry in enumerate(entries or []):
        if not isinstance(entry, dict):
            continue
        region = str(entry.get("region") or "cn")
        payload = entry.get("vault")
        if not isinstance(payload, dict):
            payload = {
                "accountId": entry.get("account_id") or ("extra-" + str(index)),
                "auth": {
                    "accessToken": entry.get("access_token") or "",
                    "refreshToken": entry.get("refresh_token") or "",
                    "expiresAt": entry.get("expires_at") or 0,
                    "refreshExpiresAt": entry.get("refresh_expires_at") or 0,
                    "domain": entry.get("domain") or "",
                },
                "account": {
                    "uid": entry.get("uid") or "",
                    "nickname": entry.get("nickname") or "",
                    "uin": entry.get("uin") or "",
                },
            }
        account = _parse_account(payload, region, "manual")
        if account is not None:
            out.append(account)
    return out


class AccountPool:
    """账号池：按健康度挑号、记失败、冷却、换号。"""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._accounts: list = []

    def reload(self) -> list:
        """重新读盘。会保留已有账号的健康度状态。"""
        settings = config.load()
        regions = []
        if settings.get("include_cn", True):
            regions.append("cn")
        if settings.get("include_global", False):
            regions.append("global")

        fresh = load_from_vault(str(settings.get("vault_dir") or ""), regions)
        fresh.extend(load_extra(settings.get("extra_accounts") or []))

        with self._lock:
            previous = {}
            for account in self._accounts:
                previous[account.account_id + "|" + account.region] = account
            for account in fresh:
                old = previous.get(account.account_id + "|" + account.region)
                if old is not None:
                    account.failures = old.failures
                    account.cooldown_until = old.cooldown_until
                    account.last_error = old.last_error
                    account.last_used_at = old.last_used_at
                    account.success_count = old.success_count
            self._accounts = fresh
            return list(fresh)

    def snapshot(self) -> list:
        """给 GUI / 接口看的只读视图。"""
        with self._lock:
            now = time.time()
            out = []
            for account in self._accounts:
                out.append({
                    "label": account.label,
                    "region": account.region,
                    "uid": account.uid,
                    "nickname": account.nickname,
                    "domain": account.domain,
                    "available": account.available,
                    "cooldown_seconds": max(0, int(account.cooldown_until - now)),
                    "failures": account.failures,
                    "success_count": account.success_count,
                    "last_error": account.last_error,
                    "token_expired": account.token_expired,
                    "expires_at": account.expires_at,
                    "refresh_expires_at": account.refresh_expires_at,
                    "source": account.source,
                    "fingerprint": account.fingerprint(),
                })
            return out

    def count(self) -> int:
        with self._lock:
            return len(self._accounts)

    def available_count(self) -> int:
        with self._lock:
            return sum(1 for a in self._accounts if a.available)

    def pick_order(self) -> list:
        """返回本轮尝试顺序：可用账号按（失败次数，上次使用时间）排前面。"""
        with self._lock:
            usable = [a for a in self._accounts if a.available]
            usable.sort(key=lambda a: (a.failures, a.last_used_at))
            return usable

    def mark_success(self, account: Account) -> None:
        with self._lock:
            account.failures = 0
            account.cooldown_until = 0.0
            account.last_error = ""
            account.success_count += 1
            account.last_used_at = time.time()

    def mark_failure(self, account: Account, kind: str, message: str) -> int:
        """记一次失败并进入冷却，返回冷却秒数。"""
        seconds = COOLDOWN_BY_KIND.get(kind, DEFAULT_COOLDOWN)
        with self._lock:
            account.failures += 1
            account.last_error = (kind + ": " + message)[:400]
            account.cooldown_until = time.time() + seconds
            account.last_used_at = time.time()
            return seconds


_pool = AccountPool()


def pool() -> AccountPool:
    return _pool