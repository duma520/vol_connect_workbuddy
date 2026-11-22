"""配置读写：实时落盘、启动自动加载。

配置文件位置：项目根目录下的 config.json。
所有字段都有默认值，缺字段自动补，老配置升级不会崩。
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config.json"
LOG_DIR = PROJECT_ROOT / "logs"

# 默认配置。改这里就改默认值。
DEFAULTS: dict[str, Any] = {
    "listen_host": "127.0.0.1",
    "listen_port": 17583,
    "vault_dir": "",
    "include_cn": True,
    "include_global": False,
    "extra_accounts": [],
    "default_model": "deepseek-v4.1-flash",
    "model_whitelist": [],
    "token_policy": "lazy",
    "max_failover": 3,
    "request_timeout_seconds": 600,
    "connect_timeout_seconds": 30,
    "log_level": "INFO",
    "log_keep_days": 14,
    "enable_progress_log": True,
    "system_head_placeholder": "You are a helpful coding assistant.",
    "neutral_head": "You are a helpful coding assistant.",
    "enable_channel_gate_fix": True,
    "strip_reasoning_effort_off": True,
    "pass_tools": True,
    "auto_start_gui": True,
    "theme": "dark",
}

_lock = threading.RLock()
_cache: dict[str, Any] | None = None


def default_vault_dir() -> str:
    """DSH 保险库的默认位置。"""
    home = os.path.expanduser("~")
    return str(Path(home) / ".dsh" / "workbuddy-vault")


def _merge_defaults(raw: dict[str, Any]) -> dict[str, Any]:
    merged = dict(DEFAULTS)
    for key, value in raw.items():
        if key in DEFAULTS:
            merged[key] = value
        else:
            merged[key] = value
    if not merged.get("vault_dir"):
        merged["vault_dir"] = default_vault_dir()
    return merged


def load(force: bool = False) -> dict[str, Any]:
    """读取配置；首次调用会建默认配置文件。"""
    global _cache
    with _lock:
        if _cache is not None and not force:
            return dict(_cache)
        if CONFIG_PATH.exists():
            try:
                raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                if not isinstance(raw, dict):
                    raw = {}
            except (OSError, ValueError):
                raw = {}
            data = _merge_defaults(raw)
        else:
            data = _merge_defaults({})
            _write(data)
        _cache = data
        return dict(data)


def _write(data: dict[str, Any]) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, CONFIG_PATH)


def save(patch: dict[str, Any]) -> dict[str, Any]:
    """合并写入并立即落盘，返回新配置。"""
    global _cache
    with _lock:
        data = load()
        for key, value in patch.items():
            data[key] = value
        _write(data)
        _cache = data
        return dict(data)


def get(key: str, default: Any = None) -> Any:
    return load().get(key, DEFAULTS.get(key, default))


def ensure_dirs() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
