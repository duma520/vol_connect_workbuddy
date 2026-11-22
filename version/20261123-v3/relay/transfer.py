"""账号导入导出：与 dsh-connect-workbuddy 插件**完全互通**的文件格式。

格式契约（全部来自插件源码实测，lib/index.js:11099-11342 与 15907-15950）：

  文件是一个 JSON 数组，也可能是 {accounts:[...]} / {data:[...]} /
  {records:[...]} 三种包装之一（还允许再嵌套一层 data/result）。

  每条记录是**扁平 snake_case**，字段：
    access_token      必填，空则该条被跳过
    refresh_token     可选
    uid               可选
    nickname          可选
    email             可选（只用于预览显示）
    domain            可选，用于判定所属区域（cn / global）
    expiresAt         **毫秒**（注意：保险库文件里是秒，换算只在边界做）
    refreshExpiresAt  **毫秒**
    auth_raw          可选，嵌套的 {auth:{...}, account:{...}} 原始文档；
                      导入时用它恢复 uin（账号 id 由 uin ?? uid ?? nickname 派生，
                      不恢复 uin 会导致同一账号被当成新账号重复导入）

  导入规则（与插件一致，不要改）：
    1. 缺 access_token → 跳过
    2. domain 判定的区域与目标区域不符 → 跳过
    3. 同一账号 id 已存在 → **覆盖**（重登后重新导入即刷新）
    4. 其余正常写入

  预览只回脱敏字段（index / uid / nickname / email / hasToken），不回明文 token。
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any

# 记录数组可能藏在这些键下（顺序即优先级，与插件一致）
RECORD_KEYS = ("accounts", "data", "records")
# 允许再嵌套一层的键
NESTED_KEYS = ("data", "result")


# 区域判定采用插件的**严格版** knownRegionOf（lib/host-heartbeat-*.js:4349-4357），
# 不是宽松版 regionOf。原因见插件注释：判定对象是「别人递过来的文件里的 domain」，
# 认不出来就必须算「无法归类」而跳过，不能默认归到国内版 —— 否则一个伪造或外域凭据
# 会被塞进国内版保险库。两边的可注册域都匹配，因此裸主机名与子域都算，
# 而 codebuddy.cn.evil.com 这类仿冒域不会被误判。
_GLOBAL_DOMAINS = ("workbuddy.ai", "codebuddy.ai")
_CN_DOMAINS = ("workbuddy.cn", "codebuddy.cn", "copilot.tencent.com")


def _matches(lowered: str, domains: tuple) -> bool:
    for item in domains:
        if lowered == item or lowered.endswith("." + item):
            return True
    return False


def region_of_domain(domain: str):
    """按凭据 domain 判区域，返回 "cn" / "global" / None（无法判定）。

    与插件 knownRegionOf 逐条对齐：
      global：workbuddy.ai、codebuddy.ai 及其子域
      cn    ：workbuddy.cn、codebuddy.cn、copilot.tencent.com 及其子域
      其余（含空串）→ None，导入时按「无法判定」跳过

    注意 copilot.tencent.com 是**国内**聊天网关本身，真实记录的 domain 字段就带它，
    插件特意把它算作 cn —— 不认它会导致插件自己的导出文件无法重新导入。
    """
    lowered = (domain or "").strip().lower()
    if lowered == "":
        return None
    if _matches(lowered, _GLOBAL_DOMAINS):
        return "global"
    if _matches(lowered, _CN_DOMAINS):
        return "cn"
    return None


def describe_shape(parsed: Any) -> str:
    """人话描述顶层是什么形状，用于报错。"""
    if parsed is None:
        return "null"
    if isinstance(parsed, list):
        return "一个数组"
    if not isinstance(parsed, dict):
        return "一个 " + type(parsed).__name__
    keys = list(parsed.keys())
    if not keys:
        return "一个空对象"
    return "一个对象，键为：" + ", ".join(str(k) for k in keys[:8])


def records_of(parsed: Any, depth: int = 0) -> list | None:
    """从顶层取出记录数组。取不到返回 None。"""
    if isinstance(parsed, list):
        return parsed
    if not isinstance(parsed, dict):
        return None
    for key in RECORD_KEYS:
        value = parsed.get(key)
        if isinstance(value, list):
            return value
    if depth >= 1:
        return None
    for key in NESTED_KEYS:
        value = parsed.get(key)
        if not isinstance(value, dict):
            continue
        inner = records_of(value, depth + 1)
        if inner is not None:
            return inner
    return None


def parse_transfer_file(text: str) -> list:
    """解析导入文件文本，返回记录列表。格式错抛 ValueError（带中文原因）。"""
    if not text or not text.strip():
        raise ValueError("文件是空的。")
    try:
        parsed = json.loads(text)
    except ValueError as exc:
        raise ValueError("文件不是合法 JSON：" + str(exc)[:200]) from exc
    records = records_of(parsed)
    if records is None:
        raise ValueError(
            '文件必须是账号记录数组，或者 {"accounts": [...]} 这类包装；'
            '实际是' + describe_shape(parsed) + '。'
        )
    for index, item in enumerate(records):
        if not isinstance(item, dict):
            raise ValueError("第 " + str(index + 1) + " 条不是账号对象。")
    return [_strip_redundant_raw(item) for item in records]


def _strip_redundant_raw(record: dict) -> dict:
    """丢掉形如 xxx_raw 的冗余快照，但保留 auth_raw（它带 uin）。"""
    kept = {}
    for key, value in record.items():
        if key != "auth_raw" and str(key).endswith("_raw"):
            continue
        kept[key] = value
    return kept


def _display_string(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    return ""


def has_token(record: dict) -> bool:
    token = record.get("access_token")
    return isinstance(token, str) and token != ""


def uin_of_raw(raw: Any) -> str:
    """从 auth_raw 里恢复 uin。两种文档形状都认。"""
    if not isinstance(raw, dict):
        return ""
    account = raw.get("account")
    holder = account if isinstance(account, dict) else raw
    return _display_string(holder.get("uin"))


def preview_transfer_file(text: str) -> dict:
    """脱敏预览：只返回 index / uid / nickname / email / hasToken。"""
    records = parse_transfer_file(text)
    items = []
    for index, record in enumerate(records):
        domain = _display_string(record.get("domain"))
        items.append({
            "index": index,
            "uid": _display_string(record.get("uid")),
            "nickname": _display_string(record.get("nickname")),
            "email": _display_string(record.get("email")),
            "domain": domain,
            "region": region_of_domain(domain) or "unknown",
            "hasToken": has_token(record),
        })
    return {"accounts": items, "total": len(items)}


def transfer_record_of(account: Any, vault_document: dict | None = None) -> dict:
    """把一个账号导出成 transfer 记录。expiresAt 一律输出**毫秒**。"""
    expires_ms = 0
    if getattr(account, "expires_at", 0):
        expires_ms = int(float(account.expires_at) * 1000)
    refresh_ms = 0
    if getattr(account, "refresh_expires_at", 0):
        refresh_ms = int(float(account.refresh_expires_at) * 1000)

    record: dict = {"access_token": account.access_token}
    if getattr(account, "refresh_token", ""):
        record["refresh_token"] = account.refresh_token
    if getattr(account, "uid", ""):
        record["uid"] = account.uid
    if getattr(account, "nickname", None) is not None:
        record["nickname"] = account.nickname
    if getattr(account, "domain", ""):
        record["domain"] = account.domain
    if expires_ms > 0:
        record["expiresAt"] = expires_ms
    if refresh_ms > 0:
        record["refreshExpiresAt"] = refresh_ms

    raw = vault_document
    if not isinstance(raw, dict):
        raw = {
            "auth": {
                "accessToken": account.access_token,
                "refreshToken": getattr(account, "refresh_token", ""),
                "expiresAt": int(float(getattr(account, "expires_at", 0) or 0)),
                "domain": getattr(account, "domain", ""),
            },
            "account": {
                "uid": getattr(account, "uid", ""),
                "nickname": getattr(account, "nickname", ""),
                "uin": getattr(account, "uin", ""),
            },
        }
        if refresh_ms > 0:
            raw["auth"]["refreshExpiresAt"] = int(refresh_ms / 1000)
    record["auth_raw"] = raw
    return record


def credential_of_record(record: dict) -> dict | None:
    """把一条记录还原成中继内部用的账号字典。缺 token 返回 None。"""
    token = record.get("access_token")
    if not isinstance(token, str) or token == "":
        return None
    refresh = record.get("refresh_token")
    refresh = refresh if isinstance(refresh, str) else ""

    expires_ms = record.get("expiresAt")
    expires_s = 0.0
    if isinstance(expires_ms, (int, float)) and expires_ms > 0:
        expires_s = float(expires_ms) / 1000.0

    refresh_ms = record.get("refreshExpiresAt")
    refresh_s = 0.0
    if isinstance(refresh_ms, (int, float)) and refresh_ms > 0:
        refresh_s = float(refresh_ms) / 1000.0

    uin = uin_of_raw(record.get("auth_raw"))
    return {
        "access_token": token,
        "refresh_token": refresh,
        "expires_at": expires_s,
        "refresh_expires_at": refresh_s,
        "domain": _display_string(record.get("domain")),
        "uid": _display_string(record.get("uid")),
        "nickname": _display_string(record.get("nickname")),
        "uin": uin,
    }


def account_id_of(credential: dict) -> str:
    """稳定账号 id：与插件 workbuddyAccountId **逐字节一致**（关键兼容点）。

    插件源码 lib/host-heartbeat-BzYVKa0r.js:8621-8624：
        stable = uin ?? uid ?? nickname ?? "unknown"
        id     = sha256("workbuddy\0" + stable).hex.slice(0, 24)

    必须用这个算法而不是直接拿 uin 当 id —— 插件侧账号 id 必须是 24 位十六进制
    （VAULT_ACCOUNT_ID_RE = /^[0-9a-f]{24}$/，见 8612 行），拿 uin 命名会被它判为非法 id。
    算对了，本程序导入后写出的文件名与插件原有文件名**完全同名**，导入即覆盖、幂等。
    """
    stable = ""
    for key in ("uin", "uid", "nickname"):
        value = credential.get(key) or ""
        if value:
            stable = str(value)
            break
    if not stable:
        stable = "unknown"
    digest = hashlib.sha256(("workbuddy\0" + stable).encode("utf-8")).hexdigest()
    return digest[:24]


def merge_records(records: list, indexes: list, region: str) -> dict:
    """纯合并：返回 {changes, imported, skipped, skip_reasons}。"""
    changes: dict = {}
    imported = 0
    skipped = 0
    reasons: list = []
    for index in indexes:
        if not isinstance(index, int) or index < 0 or index >= len(records):
            skipped += 1
            reasons.append("第 " + str(index + 1) + " 条：序号越界")
            continue
        record = records[index]
        credential = credential_of_record(record)
        if credential is None:
            skipped += 1
            reasons.append("第 " + str(index + 1) + " 条：缺少 access_token")
            continue
        record_region = region_of_domain(credential["domain"])
        if record_region is None:
            skipped += 1
            reasons.append(
                "第 " + str(index + 1) + " 条：domain 为 \"" + (credential["domain"] or "") +
                "\"，无法判定所属区域"
            )
            continue
        if record_region != region:
            skipped += 1
            reasons.append(
                "第 " + str(index + 1) + " 条：属于 " + record_region +
                " 区域，与目标区域 " + region + " 不符"
            )
            continue
        changes[account_id_of(credential)] = credential
        imported += 1
    return {
        "changes": changes,
        "imported": imported,
        "skipped": skipped,
        "skip_reasons": reasons,
    }


def export_payload(records: list) -> dict:
    """导出文件的最终形态（与插件 export 端点同形：{accounts: [...]}）。"""
    return {"accounts": records}


def default_export_name(when: float | None = None) -> str:
    """默认导出文件名，与插件完全一致：workbuddy-accounts-YYYY-MM-DD.json"""
    stamp = time.localtime(when if when is not None else time.time())
    return "workbuddy-accounts-" + time.strftime("%Y-%m-%d", stamp) + ".json"