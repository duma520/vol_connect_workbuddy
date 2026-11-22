"""本地 HTTP 服务：对火山 Codex 暴露 /v1/responses，对面板暴露 /admin/*。

路由清单：
  GET  /healthz            健康检查（Codex 与脚本都可用）
  GET  /v1/models          模型列表（Codex 只在少数场景读它）
  POST /v1/responses       Responses API —— Codex 真正走的路
  GET  /admin/status       账号池与控制面板状态
  POST /admin/reload       重新读盘账号
  POST /admin/config       实时改配置（立即落盘）
  GET  /admin/logs         最近日志（尾部 N 行）

实现用标准库 ThreadingHTTPServer，不引入 Flask/FastAPI 依赖。
"""

from __future__ import annotations

import json
import os
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import httpx

from . import __version__
from . import accounts as accounts_mod
from . import config
from . import convert_in, convert_out, transfer, upstream
from .logging_setup import log_line, recent_lines


class RelayHandler(BaseHTTPRequestHandler):
    """所有路由的实现。"""

    server_version = "vol-connect-workbuddy/" + __version__
    protocol_version = "HTTP/1.1"

    # ---------- 小工具 ----------

    def log_message(self, fmt: str, *args: Any) -> None:
        log_line("INFO", "http", fmt % args)

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def _sse_start(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()

    def _sse_write(self, event: str, data: dict) -> None:
        try:
            self.wfile.write(convert_out.sse_encode(event, data))
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            raise _ClientGone()

    # ---------- GET ----------

    def do_GET(self) -> None:
        path = self.path.split("?")[0].rstrip("/") or "/"
        try:
            if path in ("/healthz", "/health"):
                pool = accounts_mod.pool()
                self._json(200, {
                    "ok": True,
                    "service": "vol_connect_workbuddy",
                    "accounts": pool.count(),
                    "available": pool.available_count(),
                    "time": int(time.time()),
                })
                return
            if path in ("/v1/models", "/models"):
                self._json(200, {"object": "list", "data": self._model_list()})
                return
            if path == "/admin/status":
                pool = accounts_mod.pool()
                self._json(200, {
                    "config": config.load(),
                    "accounts": pool.snapshot(),
                    "account_count": pool.count(),
                    "available_count": pool.available_count(),
                })
                return
            if path == "/admin/logs":
                self._json(200, {"lines": recent_lines(200)})
                return
            if path == "/admin/export":
                self._handle_export()
                return
            self._json(404, {"error": "not found", "path": path})
        except Exception as exc:
            log_line("ERROR", "http", "GET " + path + " 失败: " + repr(exc))
            self._json(500, {"error": str(exc)[:400]})

    # ---------- POST ----------

    def do_POST(self) -> None:
        path = self.path.split("?")[0].rstrip("/") or "/"
        try:
            if path in ("/v1/responses", "/responses"):
                self._handle_responses()
                return
            if path == "/admin/reload":
                pool = accounts_mod.pool()
                loaded = pool.reload()
                log_line("INFO", "admin", "重新载入账号 " + str(len(loaded)) + " 个")
                self._json(200, {"ok": True, "accounts": len(loaded)})
                return
            if path == "/admin/config":
                patch = self._read_json()
                merged = config.save(patch)
                log_line("INFO", "admin", "配置已更新并落盘")
                self._json(200, {"ok": True, "config": merged})
                return
            if path == "/admin/transfer/preview":
                self._handle_preview()
                return
            if path == "/admin/transfer/import":
                self._handle_import()
                return
            self._json(404, {"error": "not found", "path": path})
        except _ClientGone:
            log_line("WARN", "http", "客户端提前断开 " + path)
        except Exception as exc:
            log_line("ERROR", "http", "POST " + path + " 失败: " + repr(exc))
            log_line("ERROR", "http", traceback.format_exc()[:1200])
            try:
                self._json(500, {"error": str(exc)[:400]})
            except Exception:
                pass

    # ---------- 账号导出 / 导入（与 dsh-connect-workbuddy 完全兼容）----------

    def _handle_export(self) -> None:
        """导出账号。GET /admin/export?ids=a,b,c（省略 ids 表示全部）。"""
        query = self.path.split("?", 1)[1] if "?" in self.path else ""
        wanted: list = []
        for pair in query.split("&"):
            if pair.startswith("ids="):
                raw = pair[3:]
                wanted = [x for x in raw.replace("%2C", ",").split(",") if x]
        pool = accounts_mod.pool()
        rows = pool.snapshot()
        if wanted:
            rows = [r for r in rows if str(r.get("uid") or r.get("label") or "") in wanted]
            if not rows:
                # 也允许按账号 id / nickname 匹配
                rows = [r for r in pool.snapshot()
                        if str(r.get("nickname") or "") in wanted or str(r.get("label") or "") in wanted]
        accounts = pool.accounts() if hasattr(pool, "accounts") else []
        by_key = {}
        for account in accounts:
            by_key[str(account.uid or "")] = account
            by_key[str(account.account_id or "")] = account
            by_key[str(account.label or "")] = account
            by_key[str(account.nickname or "")] = account

        picked = []
        if wanted:
            seen = set()
            for key in wanted:
                account = by_key.get(key)
                if account is not None and id(account) not in seen:
                    seen.add(id(account))
                    picked.append(account)
        else:
            picked = list(accounts)

        records = []
        for account in picked:
            try:
                records.append(transfer.transfer_record_of(account))
            except Exception as exc:
                log_line("WARN", "transfer", "导出 " + account.label + " 失败: " + repr(exc)[:200])

        payload = transfer.export_payload(records)
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        filename = transfer.default_export_name()
        log_line("INFO", "transfer", "导出 " + str(len(records)) + " 个账号")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Disposition", "attachment; filename=\"" + filename + "\"")
        self.send_header("X-Export-Filename", filename)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _handle_preview(self) -> None:
        """脱敏预览导入文件。请求体 {"text": "<文件文本>"}。"""
        body = self._read_json()
        text = body.get("text")
        if not isinstance(text, str):
            self._json(400, {"ok": False, "error": "缺少 text 字段（文件文本）。"})
            return
        try:
            result = transfer.preview_transfer_file(text)
        except ValueError as exc:
            self._json(400, {"ok": False, "error": str(exc)})
            return
        self._json(200, {"ok": True, **result})

    def _handle_import(self) -> None:
        """导入账号。请求体 {"text": ..., "indexes": [...], "region": "cn"|"global"}。"""
        body = self._read_json()
        text = body.get("text")
        indexes = body.get("indexes")
        region = str(body.get("region") or "cn")
        if not isinstance(text, str):
            self._json(400, {"ok": False, "error": "缺少 text 字段（文件文本）。"})
            return
        if not isinstance(indexes, list) or not indexes:
            self._json(400, {"ok": False, "error": "缺少 indexes 字段（要导入的条目序号）。"})
            return
        try:
            records = transfer.parse_transfer_file(text)
        except ValueError as exc:
            self._json(400, {"ok": False, "error": str(exc)})
            return

        settings = config.load()
        vault_dir = str(settings.get("vault_dir") or "")
        if not vault_dir or not os.path.isdir(vault_dir):
            self._json(400, {"ok": False, "error": "保险库目录不存在，无法写入：" + vault_dir})
            return

        merged = transfer.merge_records(records, indexes, region)
        written = []
        failed = []
        for account_id, credential in merged["changes"].items():
            try:
                path = accounts_mod.write_vault_account(credential, region, vault_dir)
                written.append({"id": account_id, "path": path})
            except Exception as exc:
                failed.append({"id": account_id, "error": repr(exc)[:200]})

        log_line(
            "INFO", "transfer",
            "导入 " + region + "：成功 " + str(len(written)) +
            "，跳过 " + str(merged["skipped"]) +
            "，写入失败 " + str(len(failed)),
        )
        self._json(200, {
            "ok": True,
            "imported": len(written),
            "skipped": merged["skipped"],
            "skip_reasons": merged["skip_reasons"],
            "written": written,
            "failed": failed,
        })

    # ---------- 核心：/v1/responses ----------

    def _model_list(self) -> list:
        settings = config.load()
        whitelist = settings.get("model_whitelist") or []
        if whitelist:
            return [{"id": str(x), "object": "model", "owned_by": "workbuddy"} for x in whitelist]
        default = str(settings.get("default_model") or "deepseek-v4.1-flash")
        return [{"id": default, "object": "model", "owned_by": "workbuddy"}]

    def _handle_responses(self) -> None:
        body = self._read_json()
        settings = config.load()
        log_line("INFO", "responses", "收到请求 model=" + str(body.get("model")) +
                 " input=" + str(len(body.get("input") or [])))

        chat_body = convert_in.to_chat_request(body, settings)
        chat_body = upstream.normalize_body(chat_body, settings)

        self._sse_start()
        builder = convert_out.ResponsesStreamBuilder(str(chat_body.get("model") or "workbuddy"))
        try:
            for event, data in builder.start():
                self._sse_write(event, data)
        except _ClientGone:
            return

        client = httpx.Client(follow_redirects=True)
        try:
            attempt = upstream.client().open_chat(chat_body, client, settings)
            if not attempt.ok or attempt.response is None:
                failure = attempt.failure
                message = failure.message if failure else "上游未返回内容。"
                log_line("ERROR", "responses", message)
                for event, data in builder.fail(message, failure.kind if failure else "upstream_error"):
                    self._sse_write(event, data)
                return

            finished_normally = self._pump(attempt.response, builder)
            if attempt.account is not None:
                accounts_mod.pool().mark_success(attempt.account)
            if not finished_normally:
                log_line("WARN", "responses", "上游流未正常收尾，仍补发 completed")
        finally:
            try:
                if attempt is not None and attempt.response is not None:
                    attempt.response.close()
            except Exception:
                pass
            client.close()

    def _pump(self, response: Any, builder: convert_out.ResponsesStreamBuilder) -> bool:
        """把上游 SSE 泵进 builder，边收边发。返回是否收到正常收尾。"""
        usage: dict = {}
        finish_reason = ""
        finished = False
        try:
            for chunk in upstream.iter_chat_chunks(response.iter_lines()):
                if isinstance(chunk.get("usage"), dict) and chunk["usage"]:
                    usage = chunk["usage"]
                choices = chunk.get("choices") or []
                if not choices:
                    continue
                choice = choices[0]
                if not isinstance(choice, dict):
                    continue
                delta = choice.get("delta") or {}
                reasoning = delta.get("reasoning_content") or delta.get("reasoning")
                if isinstance(reasoning, str) and reasoning:
                    for event, data in builder.on_reasoning(reasoning):
                        self._sse_write(event, data)
                content = delta.get("content")
                if isinstance(content, str) and content:
                    for event, data in builder.on_delta(content):
                        self._sse_write(event, data)
                for call in delta.get("tool_calls") or []:
                    if not isinstance(call, dict):
                        continue
                    function = call.get("function") or {}
                    for event, data in builder.on_tool_call_delta(
                        int(call.get("index") or 0),
                        str(call.get("id") or ""),
                        str(function.get("name") or ""),
                        str(function.get("arguments") or ""),
                    ):
                        self._sse_write(event, data)
                reason = choice.get("finish_reason")
                if reason:
                    finish_reason = str(reason)
                    finished = True
        except _ClientGone:
            raise
        except Exception as exc:
            log_line("ERROR", "responses", "读取上游流异常: " + repr(exc)[:300])

        for event, data in builder.finish(usage, finish_reason):
            self._sse_write(event, data)
        return finished


class _ClientGone(Exception):
    pass


class RelayServer:
    """可嵌入 GUI 的服务封装（后台线程跑 serve_forever）。"""

    def __init__(self) -> None:
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.host = ""
        self.port = 0

    @property
    def running(self) -> bool:
        return self._httpd is not None

    def start(self, host: str = "", port: int = 0) -> tuple:
        if self._httpd is not None:
            return self.host, self.port
        settings = config.load()
        host = host or str(settings.get("listen_host") or "127.0.0.1")
        port = port or int(settings.get("listen_port") or 17583)
        httpd = ThreadingHTTPServer((host, port), RelayHandler)
        httpd.daemon_threads = True
        self._httpd = httpd
        self.host, self.port = host, httpd.server_address[1]
        self._thread = threading.Thread(target=httpd.serve_forever, name="relay-http", daemon=True)
        self._thread.start()
        log_line("INFO", "server", "监听 http://" + host + ":" + str(self.port))
        return self.host, self.port

    def stop(self) -> None:
        httpd = self._httpd
        self._httpd = None
        if httpd is not None:
            try:
                httpd.shutdown()
                httpd.server_close()
            except Exception:
                pass
        log_line("INFO", "server", "已停止")


_server = RelayServer()


def server() -> RelayServer:
    return _server