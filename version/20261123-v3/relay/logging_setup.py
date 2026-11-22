"""日志：写在 logs/relay-YYYYMMDD.log，同时在内存里保留尾部若干行给 GUI。"""

from __future__ import annotations

import collections
import datetime
import threading
from typing import Any

from . import config

_lock = threading.RLock()
_buffer: collections.deque = collections.deque(maxlen=600)
_level_order = {"DEBUG": 10, "INFO": 20, "WARN": 30, "ERROR": 40}


def _threshold() -> int:
    return _level_order.get(str(config.get("log_level") or "INFO").upper(), 20)


def log_line(level: str, channel: str, message: str) -> None:
    """写一条日志。级别低于配置阈值就丢弃。"""
    level = level.upper()
    if _level_order.get(level, 20) < _threshold():
        return
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = stamp + " [" + level + "] [" + channel + "] " + message
    with _lock:
        _buffer.append(line)
        try:
            config.ensure_dirs()
            path = config.LOG_DIR / ("relay-" + datetime.date.today().strftime("%Y%m%d") + ".log")
            with path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        except OSError:
            pass


def recent_lines(count: int = 200) -> list:
    with _lock:
        items = list(_buffer)
    return items[-count:]