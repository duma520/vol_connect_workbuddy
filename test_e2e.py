"""端到端联调：起中继 → 用 codex-app-server 真实对话 → 打印事件。

这不是单元测试，是「火山 codex 真的能连上」的证据。
用法：python test_e2e.py [--model deepseek-v4.1-flash]
"""

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXE = r"D:\voldev\plugins\vol_ai_codex\sdk\codex\bin\codex-app-server.exe"
HOME = ROOT / "_e2e_codex_home"
PORT = int(os.environ.get("RELAY_PORT", "17583"))


def prepare_home(model: str) -> None:
    shutil.rmtree(HOME, ignore_errors=True)
    HOME.mkdir(parents=True, exist_ok=True)
    cfg = "\n".join([
        "model = " + json.dumps(model),
        "model_provider = \"vol_workbuddy\"",
        "model_reasoning_effort = \"medium\"",
        "approval_policy = \"never\"",
        "sandbox_mode = \"workspace-write\"",
        "web_search = \"disabled\"",
        "project_root_markers = []",
        "",
        "[model_providers.vol_workbuddy]",
        "name = \"WorkBuddy (vol_connect_workbuddy)\"",
        "base_url = \"http://127.0.0.1:" + str(PORT) + "/v1\"",
        "wire_api = \"responses\"",
        "experimental_bearer_token = \"PROXY_MANAGED\"",
        "requires_openai_auth = false",
        "",
    ])
    (HOME / "config.toml").write_text(cfg, encoding="utf-8")


def run_codex(model: str, prompt: str, timeout: float = 120.0) -> dict:
    prepare_home(model)
    env = dict(os.environ)
    env["CODEX_HOME"] = str(HOME)
    proc = subprocess.Popen(
        [EXE, "--listen", "stdio://"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env=env, bufsize=0,
    )
    lines = []
    stop = threading.Event()

    def reader(stream, tag):
        for raw in iter(stream.readline, b""):
            text = raw.decode("utf-8", "replace").rstrip()
            if not text:
                continue
            lines.append((tag, text))
            if "turn/completed" in text or "turn/failed" in text:
                stop.set()

    threading.Thread(target=reader, args=(proc.stdout, "OUT"), daemon=True).start()
    threading.Thread(target=reader, args=(proc.stderr, "ERR"), daemon=True).start()

    def send(obj):
        proc.stdin.write((json.dumps(obj) + "\n").encode())
        proc.stdin.flush()

    time.sleep(1.2)
    send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
          "params": {"clientInfo": {"name": "e2e", "version": "0.0.1"}}})
    time.sleep(1.0)
    send({"jsonrpc": "2.0", "id": 2, "method": "thread/start", "params": {}})
    time.sleep(1.5)

    thread_id = None
    for tag, line in lines:
        if '"id":2' in line:
            try:
                thread_id = json.loads(line)["result"]["thread"]["id"]
            except Exception:
                pass
    if thread_id is None:
        proc.kill()
        return {"ok": False, "error": "thread/start 没有返回 thread id", "lines": lines[-10:]}

    send({"jsonrpc": "2.0", "id": 3, "method": "turn/start",
          "params": {"threadId": thread_id, "input": [{"type": "text", "text": prompt}]}})

    deadline = time.time() + timeout
    while time.time() < deadline and not stop.is_set():
        time.sleep(0.4)
    proc.kill()

    reply = ""
    failed = ""
    for tag, line in lines:
        if "turn/completed" in line:
            try:
                payload = json.loads(line)
                items = payload.get("params", {}).get("turn", {}).get("items") or []
                texts = [i.get("text", "") for i in items if isinstance(i, dict)]
                reply = "".join(texts)
            except Exception:
                pass
        if "turn/failed" in line:
            failed = line[:300]
        elif "turn/completed" in line:
            try:
                payload = json.loads(line)
                turn = payload.get("params", {}).get("turn", {})
                if turn.get("status") == "failed":
                    err = turn.get("error") or {}
                    failed = str(err.get("message") or err)[:300]
            except Exception:
                pass
    return {
        "ok": bool(reply) and not failed,
        "reply": reply,
        "failed": failed,
        "thread_id": thread_id,
        "line_count": len(lines),
    }


def main() -> int:
    model = "deepseek-v4.1-flash"
    prompt = "只回复四个字：连接成功"
    for arg in sys.argv[1:]:
        if arg.startswith("--model="):
            model = arg.split("=", 1)[1]
        elif arg.startswith("--prompt="):
            prompt = arg.split("=", 1)[1]
    result = run_codex(model, prompt)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())