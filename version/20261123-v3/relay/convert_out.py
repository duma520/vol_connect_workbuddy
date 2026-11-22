"""Chat Completions SSE → Responses API 事件流 的转换。

Codex 只认 Responses 的事件名。实测它处理的关键事件（少一个就报
`stream closed before response.completed`）：
  response.created
  response.output_item.added
  response.output_text.delta / response.output_text.done
  response.reasoning_summary_text.delta / .done
  response.function_call_arguments.delta / .done
  response.output_item.done
  response.completed            ← 必须有，且带 usage

本模块把这些事件的构造集中在一处，server 只负责把生成的 (event, data)
写成 SSE 行。
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any


def _now() -> int:
    return int(time.time())


def _new_id(prefix: str) -> str:
    return prefix + "_" + uuid.uuid4().hex


class ResponsesStreamBuilder:
    """把一路 Chat SSE 增量攒成 Responses 事件序列。

    用法：
        builder = ResponsesStreamBuilder(model)
        for event, data in builder.start():
            yield event, data
        builder.on_delta(text)          # 文本增量
        builder.on_reasoning(text)      # 思考增量（可选）
        builder.on_tool_call_delta(i, id, name, args_delta)
        for event, data in builder.finish(usage, finish_reason):
            yield event, data
    """

    def __init__(self, model: str, response_id: str = "") -> None:
        self.model = model
        self.response_id = response_id or _new_id("resp")
        self.created_at = _now()
        self.output_index = 0
        self._message_id = _new_id("msg")
        self._message_open = False
        self._message_text: list = []
        self._reasoning_id = _new_id("rs")
        self._reasoning_open = False
        self._reasoning_text: list = []
        self._tool_calls: dict = {}
        self._tool_order: list = []
        self._emitted_items: list = []

    # ---------- 事件构造 ----------

    @staticmethod
    def _sse(event: str, data: dict) -> tuple:
        return event, data

    def _response_object(self, status: str, output: list, usage: dict | None = None) -> dict:
        obj = {
            "id": self.response_id,
            "object": "response",
            "created_at": self.created_at,
            "status": status,
            "model": self.model,
            "output": output,
            "parallel_tool_calls": True,
            "tool_choice": "auto",
            "tools": [],
        }
        if usage is not None:
            obj["usage"] = usage
        return obj

    # ---------- 生命周期 ----------

    def start(self) -> list:
        """响应开始：response.created + in_progress。"""
        events = [
            self._sse("response.created", {
                "type": "response.created",
                "response": self._response_object("in_progress", []),
            }),
            self._sse("response.in_progress", {
                "type": "response.in_progress",
                "response": self._response_object("in_progress", []),
            }),
        ]
        return events

    # ---------- 文本 ----------

    def _open_message(self) -> list:
        if self._message_open:
            return []
        self._message_open = True
        item = {
            "id": self._message_id,
            "type": "message",
            "role": "assistant",
            "status": "in_progress",
            "content": [],
        }
        return [
            self._sse("response.output_item.added", {
                "type": "response.output_item.added",
                "output_index": self.output_index,
                "item": item,
            }),
        ]

    def on_delta(self, text: str) -> list:
        """收到一段正文增量。"""
        if not text:
            return []
        events = self._open_message()
        self._message_text.append(text)
        events.append(self._sse("response.output_text.delta", {
            "type": "response.output_text.delta",
            "item_id": self._message_id,
            "output_index": self.output_index,
            "content_index": 0,
            "delta": text,
        }))
        return events

    def on_reasoning(self, text: str) -> list:
        """收到一段思考增量（reasoning_summary）。"""
        if not text:
            return []
        events = []
        if not self._reasoning_open:
            self._reasoning_open = True
            events.append(self._sse("response.reasoning_summary_part.added", {
                "type": "response.reasoning_summary_part.added",
                "item_id": self._reasoning_id,
                "output_index": self.output_index,
                "summary_index": 0,
                "part": {"type": "summary_text", "text": ""},
            }))
        self._reasoning_text.append(text)
        events.append(self._sse("response.reasoning_summary_text.delta", {
            "type": "response.reasoning_summary_text.delta",
            "item_id": self._reasoning_id,
            "output_index": self.output_index,
            "summary_index": 0,
            "delta": text,
        }))
        return events

    # ---------- 工具调用 ----------

    def on_tool_call_delta(self, index: int, call_id: str, name: str, args_delta: str) -> list:
        """收到工具调用的一段增量。index 是上游 choices[0].delta.tool_calls[].index。"""
        events = []
        slot = self._tool_calls.get(index)
        if slot is None:
            slot = {
                "id": call_id or _new_id("call"),
                "name": name or "",
                "args": [],
                "output_index": None,
            }
            self._tool_calls[index] = slot
            self._tool_order.append(index)
            slot["output_index"] = self.output_index
            self.output_index += 1
            events.append(self._sse("response.output_item.added", {
                "type": "response.output_item.added",
                "output_index": slot["output_index"],
                "item": {
                    "id": slot["id"],
                    "type": "function_call",
                    "status": "in_progress",
                    "name": slot["name"],
                    "call_id": slot["id"],
                    "arguments": "",
                },
            }))
        else:
            if call_id and not slot["id"]:
                slot["id"] = call_id
            if name and not slot["name"]:
                slot["name"] = name
        if not args_delta:
            return events
        slot["args"].append(args_delta)
        events.append(self._sse("response.function_call_arguments.delta", {
            "type": "response.function_call_arguments.delta",
            "item_id": slot["id"],
            "output_index": slot["output_index"],
            "delta": args_delta,
        }))
        return events

    # ---------- 收尾 ----------

    def _close_message(self) -> tuple:
        """关掉正文项，返回 (事件列表, output item)。"""
        if not self._message_open:
            return [], None
        text = "".join(self._message_text)
        events = [
            self._sse("response.output_text.done", {
                "type": "response.output_text.done",
                "item_id": self._message_id,
                "output_index": self.output_index,
                "content_index": 0,
                "text": text,
            }),
        ]
        item = {
            "id": self._message_id,
            "type": "message",
            "role": "assistant",
            "status": "completed",
            "content": [{"type": "output_text", "text": text, "annotations": []}],
        }
        events.append(self._sse("response.output_item.done", {
            "type": "response.output_item.done",
            "output_index": self.output_index,
            "item": item,
        }))
        self.output_index += 1
        self._message_open = False
        return events, item

    def _close_reasoning(self) -> tuple:
        if not self._reasoning_open:
            return [], None
        text = "".join(self._reasoning_text)
        events = [
            self._sse("response.reasoning_summary_text.done", {
                "type": "response.reasoning_summary_text.done",
                "item_id": self._reasoning_id,
                "output_index": 0,
                "summary_index": 0,
                "text": text,
            }),
            self._sse("response.reasoning_summary_part.done", {
                "type": "response.reasoning_summary_part.done",
                "item_id": self._reasoning_id,
                "output_index": 0,
                "summary_index": 0,
                "part": {"type": "summary_text", "text": text},
            }),
        ]
        item = {
            "id": self._reasoning_id,
            "type": "reasoning",
            "summary": [{"type": "summary_text", "text": text}],
        }
        self._reasoning_open = False
        return events, item

    def _close_tools(self) -> tuple:
        events = []
        items = []
        for index in self._tool_order:
            slot = self._tool_calls[index]
            args = "".join(slot["args"])
            events.append(self._sse("response.function_call_arguments.done", {
                "type": "response.function_call_arguments.done",
                "item_id": slot["id"],
                "output_index": slot["output_index"],
                "arguments": args,
            }))
            item = {
                "id": slot["id"],
                "type": "function_call",
                "status": "completed",
                "name": slot["name"],
                "call_id": slot["id"],
                "arguments": args,
            }
            events.append(self._sse("response.output_item.done", {
                "type": "response.output_item.done",
                "output_index": slot["output_index"],
                "item": item,
            }))
            items.append((slot["output_index"], item))
        return events, items

    def finish(self, usage: dict | None = None, finish_reason: str = "") -> list:
        """收尾：关掉所有项，最后发 response.completed（Codex 认这个）。"""
        events: list = []
        collected: list = []

        reasoning_events, reasoning_item = self._close_reasoning()
        events.extend(reasoning_events)
        if reasoning_item is not None:
            collected.append((0, reasoning_item))

        msg_events, msg_item = self._close_message()
        events.extend(msg_events)
        if msg_item is not None:
            collected.append((self.output_index - 1, msg_item))

        tool_events, tool_items = self._close_tools()
        events.extend(tool_events)
        collected.extend(tool_items)

        collected.sort(key=lambda pair: pair[0])
        output = [item for _, item in collected]

        normalized_usage = {
            "input_tokens": int((usage or {}).get("prompt_tokens") or 0),
            "output_tokens": int((usage or {}).get("completion_tokens") or 0),
            "total_tokens": int((usage or {}).get("total_tokens") or 0),
        }
        details = (usage or {}).get("completion_tokens_details") or {}
        if details:
            normalized_usage["output_tokens_details"] = {
                "reasoning_tokens": int(details.get("reasoning_tokens") or 0)
            }

        events.append(self._sse("response.completed", {
            "type": "response.completed",
            "response": self._response_object("completed", output, normalized_usage),
        }))
        return events

    def fail(self, message: str, code: str = "upstream_error") -> list:
        """上游失败：发 response.failed，让 Codex 立刻结束而不是等到超时。"""
        return [self._sse("response.failed", {
            "type": "response.failed",
            "response": {
                "id": self.response_id,
                "object": "response",
                "created_at": self.created_at,
                "status": "failed",
                "model": self.model,
                "output": [],
                "error": {"code": code, "message": message[:1000]},
            },
        })]


def sse_encode(event: str, data: dict) -> bytes:
    """把一条事件编码成 SSE 字节（event 行 + data 行 + 空行）。"""
    payload = json.dumps(data, ensure_ascii=False)
    return ("event: " + event + "\ndata: " + payload + "\n\n").encode("utf-8")