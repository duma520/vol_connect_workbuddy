"""GUI 工作线程：所有耗时操作都放这里，主线程只刷新界面。

规则 g6 / g7 / g25：耗时与网络请求走工作线程，主线程只负责更新进度，
进度回传做节流，避免每条子任务都触发重绘。
"""

from __future__ import annotations

import time
from typing import Any

from PySide6.QtCore import QThread, Signal

from relay import accounts, config, upstream


class AccountLoader(QThread):
    """重新读盘账号池（可能在慢速磁盘上，放线程里）。"""

    progress = Signal(int, str)
    finished_ok = Signal(dict)
    failed = Signal(str)

    def run(self) -> None:
        try:
            self.progress.emit(10, "读取配置…")
            settings = config.load(force=True)
            self.progress.emit(35, "扫描保险库目录…")
            pool = accounts.pool()
            loaded = pool.reload()
            self.progress.emit(80, "整理账号状态…")
            snapshot = pool.snapshot()
            self.progress.emit(100, "完成")
            self.finished_ok.emit({
                "settings": settings,
                "accounts": snapshot,
                "count": len(loaded),
                "available": pool.available_count(),
            })
        except Exception as exc:
            self.failed.emit(repr(exc)[:400])


class ProbeWorker(QThread):
    """给每个账号发一次最小请求，验证可用性。"""

    progress = Signal(int, str)
    one_done = Signal(str, str, str)
    finished_ok = Signal(dict)
    failed = Signal(str)

    def __init__(self, model: str = "", parent: Any = None) -> None:
        super().__init__(parent)
        self.model = model

    def run(self) -> None:
        try:
            settings = config.load()
            model = self.model or str(settings.get("default_model") or "deepseek-v4.1-flash")
            pool = accounts.pool()
            targets = pool.pick_order() or []
            if not targets:
                self.failed.emit("没有可用账号，先点「重新载入账号」。")
                return
            client = upstream.client()
            ok_count = 0
            fail_count = 0
            import httpx
            with httpx.Client() as http:
                total = len(targets)
                for index, account in enumerate(targets):
                    percent = int((index / max(1, total)) * 100)
                    self.progress.emit(percent, "检测 " + account.label + "（" + str(index + 1) + "/" + str(total) + "）")
                    body = {
                        "model": model,
                        "messages": [
                            {"role": "system", "content": "You are a helpful assistant."},
                            {"role": "user", "content": "回复两个字：可以"},
                        ],
                        "stream": True,
                        "max_tokens": 16,
                    }
                    body = upstream.normalize_body(body, settings)
                    attempt = client._try_one(account, body, http, settings)
                    if attempt.ok:
                        ok_count += 1
                        self.one_done.emit(account.label, "可用", "")
                        try:
                            attempt.response.close()
                        except Exception:
                            pass
                        pool.mark_success(account)
                    else:
                        fail_count += 1
                        failure = attempt.failure
                        kind = failure.kind if failure else "unknown"
                        message = failure.message if failure else "未返回内容"
                        self.one_done.emit(account.label, kind, message[:120])
                        pool.mark_failure(account, kind, message)
                    time.sleep(0.35)
            self.progress.emit(100, "检测完成")
            self.finished_ok.emit({"ok": ok_count, "fail": fail_count})
        except Exception as exc:
            self.failed.emit(repr(exc)[:400])