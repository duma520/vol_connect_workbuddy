"""命令行入口：python -m relay.app 或 python relay/app.py。

不带参数直接启动中继（默认 127.0.0.1:17583）。
  --host / --port     覆盖监听地址
  --no-gui            只跑服务，不开面板
  --list-accounts     打印账号池状态后退出
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from relay import accounts, config, server
from relay.logging_setup import log_line


def _print_accounts() -> None:
    pool = accounts.pool()
    pool.reload()
    print("账号总数:", pool.count(), "| 可用:", pool.available_count())
    for row in pool.snapshot():
        state = "可用" if row["available"] else "冷却中"
        if row["cooldown_seconds"]:
            state += "(" + str(row["cooldown_seconds"]) + "s)"
        print("  -", row["label"], "|", state, "| 失败", row["failures"],
              "| 成功", row["success_count"], "|", row["fingerprint"])


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(description="WorkBuddy 本地中继")
    parser.add_argument("--host", default="")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--no-gui", action="store_true")
    parser.add_argument("--list-accounts", action="store_true")
    args = parser.parse_args(argv)

    config.ensure_dirs()
    accounts.pool().reload()
    log_line("INFO", "app", "启动：账号 " + str(accounts.pool().count()) + " 个")

    if args.list_accounts:
        _print_accounts()
        return 0

    host, port = server.server().start(args.host, args.port)
    print("中继已启动： http://" + host + ":" + str(port))
    print("  健康检查: http://" + host + ":" + str(port) + "/healthz")
    print("  Responses: http://" + host + ":" + str(port) + "/v1/responses")

    if args.no_gui:
        try:
            while True:
                time.sleep(1.0)
        except KeyboardInterrupt:
            print("已停止")
        finally:
            server.server().stop()
        return 0

    try:
        from gui.main_window import run_gui
    except ImportError as exc:
        print("GUI 不可用（" + str(exc) + "），退化为无界面模式")
        try:
            while True:
                time.sleep(1.0)
        except KeyboardInterrupt:
            print("已停止")
        finally:
            server.server().stop()
        return 0

    return run_gui(server.server())


if __name__ == "__main__":
    raise SystemExit(main())