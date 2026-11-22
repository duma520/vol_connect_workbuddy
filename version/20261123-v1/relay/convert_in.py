"""Responses 请求 → Chat Completions 请求 的转换。

输入是 Codex 发来的 Responses API 请求体（已实测的真实形状，见项目 README 的
「协议基准」一节），输出是可以直接 POST 给 WorkBuddy 上游 /v2/chat/completions
的 Chat Completions 请求体。

实测要点（不要凭记忆改）：
- Codex 发 store=false、input 是完整历史数组，从不发 previous_response_id，
  所以这里按「全量历史」处理，不维护 response_id 映射。
- input 元素可能是 message（role + content 数组）或 function_call /
  function_call_output（工具往返），两类都要还原成 chat 的 messages / tool 消息。
- tools 里既有 type=function，也有 type=namespace（Codex 的 multi_agent_v1），
  后者要把子工具摊平；上游 tool_choice 只接受字符串，对象形态必须压平。
"""

from __future__ import annotations

import json
from typing import Any

# Codex 会在 instructions 里塞一整套 CLI 提示；上游要求首条消息是 system，
# 而 instructions 恰好就是那个位置。两者都存在时合并进同一条 system。


def _text_of(content: Any) -> str:
    """把 Responses 的 content 数组拼成纯文本。"""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = []
    for item in content:
        if isinstance(item, str):
            parts.append(item)
            continue
        if not isinstance(item, dict):
            continue
        kind = item.get("type")
        if kind in ("input_text", "output_text", "text", "summary_text"):
            parts.append(str(item.get("text") or ""))
        elif kind in ("input_image", "image_url"):
            # 上游多模态模型支持 image_url；纯文本模型会忽略这一段的文字占位。
            parts.append("")
    return "".join(parts)


def _image_parts(content: Any) -> list:
    """提取 content 里的图片，转成 Chat 的 image_url 片段。"""
    out: list = []
    if not isinstance(content, list):
        return out
    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get("type") not in ("input_image", "image_url"):
            continue
        url = item.get("image_url") or item.get("url") or ""
        if isinstance(url, dict):
            url = url.get("url") or ""
        if url:
            out.append({"type": "image_url", "image_url": {"url": str(url)}})
    return out


def _collect_tools(tools: Any) -> list:
    """摊平 Responses 的 tools（含 namespace 子工具）成 Chat 的 function 数组。"""
    out: list = []
    if not isinstance(tools, list):
        return out
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        kind = tool.get("type")
        if kind == "function":
            name = tool.get("name") or ""
            if not name:
                continue
            entry = {
                "type": "function",
                "function": {
                    "name": str(name),
                    "description": str(tool.get("description") or ""),
                    "parameters": tool.get("parameters") or {"type": "object", "properties": {}},
                },
            }
            if isinstance(tool.get("strict"), bool):
                entry["function"]["strict"] = tool["strict"]
            out.append(entry)
        elif kind == "namespace" and isinstance(tool.get("tools"), list):
            out.extend(_collect_tools(tool["tools"]))
        elif kind in ("web_search", "web_search_preview", "code_interpreter", "file_search"):
            # 上游没有这些内建工具，直接忽略：Codex 侧会退化成普通对话。
            continue
    return out


def _flatten_tool_choice(choice: Any, tools: list) -> str | None:
    """把 Responses 的 tool_choice 压平成上游接受的字符串。"""
    if not tools:
        return None
    if choice is None:
        return "auto"
    if isinstance(choice, str):
        lowered = choice.strip().lower()
        if lowered in ("auto", "required", "none"):
            return lowered
        return choice
    if isinstance(choice, dict):
        if choice.get("type") == "function":
            name = choice.get("name") or (choice.get("function") or {}).get("name") or ""
            return str(name) if name else "auto"
        kind = choice.get("type")
        if kind in ("auto", "required", "none"):
            return str(kind)
    return "auto"


def _convert_item(item: Any, messages: list, pending_tool_names: dict) -> None:
    """把一个 Responses input 元素追加到 messages。"""
    if not isinstance(item, dict):
        return
    kind = item.get("type")

    if kind == "message" or ("role" in item and "content" in item):
        role = str(item.get("role") or "user")
        if role == "developer":
            role = "system"
        text = _text_of(item.get("content"))
        images = _image_parts(item.get("content"))
        if images:
            parts = []
            if text:
                parts.append({"type": "text", "text": text})
            parts.extend(images)
            messages.append({"role": role, "content": parts})
        else:
            messages.append({"role": role, "content": text})
        return

    if kind == "function_call":
        call_id = str(item.get("call_id") or item.get("id") or "")
        name = str(item.get("name") or "")
        arguments = item.get("arguments")
        if not isinstance(arguments, str):
            arguments = json.dumps(arguments or {}, ensure_ascii=False)
        pending_tool_names[call_id] = name
        tool_call = {
            "id": call_id,
            "type": "function",
            "function": {"name": name, "arguments": arguments},
        }
        # 同一个 assistant 轮里的多个调用要合并进同一条 assistant 消息。
        if messages and messages[-1].get("role") == "assistant" and "tool_calls" in messages[-1]:
            messages[-1]["tool_calls"].append(tool_call)
            if messages[-1].get("content") in (None, ""):
                messages[-1]["content"] = None
        else:
            messages.append({
                "role": "assistant",
                "content": _text_of(item.get("content")) or None,
                "tool_calls": [tool_call],
            })
        return

    if kind in ("function_call_output", "custom_tool_call_output"):
        call_id = str(item.get("call_id") or "")
        output = item.get("output")
        if isinstance(output, dict):
            output = output.get("content") or json.dumps(output, ensure_ascii=False)
        if not isinstance(output, str):
            output = json.dumps(output, ensure_ascii=False)
        messages.append({
            "role": "tool",
            "tool_call_id": call_id,
            "name": pending_tool_names.get(call_id, ""),
            "content": output,
        })
        return

    # 其余类型（reasoning / web_search_call / compaction 等）上游不认识，跳过。


def ensure_system_head(messages: list, placeholder: str = "You are a helpful coding assistant.") -> None:
    """保证首条是 system；这是上游的硬闸门之一（缺了必 400/11128）。"""
    if not messages:
        messages.append({"role": "system", "content": placeholder})
        return
    first = messages[0]
    if first.get("role") == "system":
        return
    messages.insert(0, {"role": "system", "content": placeholder})


def to_chat_request(responses_body: dict, settings: dict) -> dict:
    """把 Responses 请求体转成 Chat Completions 请求体。"""
    body = responses_body if isinstance(responses_body, dict) else {}

    model = str(body.get("model") or settings.get("default_model") or "deepseek-v4.1-flash")
    whitelist = settings.get("model_whitelist") or []
    if whitelist and model not in whitelist:
        # 预设里写的是逻辑名（如 wb-code），这里映射成真实模型。
        mapped = str(settings.get("default_model") or "")
        if mapped:
            model = mapped

    messages: list = []
    instructions = body.get("instructions")
    if isinstance(instructions, str) and instructions.strip():
        messages.append({"role": "system", "content": instructions})

    pending: dict = {}
    raw_input = body.get("input")
    if isinstance(raw_input, str):
        raw_input = [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": raw_input}]}]
    if isinstance(raw_input, list):
        for item in raw_input:
            _convert_item(item, messages, pending)

    ensure_system_head(messages, str(settings.get("system_head_placeholder") or "You are a helpful coding assistant."))

    chat: dict = {
        "model": model,
        "messages": messages,
        "stream": True,
    }

    if settings.get("pass_tools", True):
        tools = _collect_tools(body.get("tools"))
        if tools:
            chat["tools"] = tools
            choice = _flatten_tool_choice(body.get("tool_choice"), tools)
            if choice == "none":
                # 上游语义：none 等于不要工具，直接删掉 tools。
                chat.pop("tools", None)
            elif choice:
                chat["tool_choice"] = choice
            if isinstance(body.get("parallel_tool_calls"), bool):
                chat["parallel_tool_calls"] = body["parallel_tool_calls"]

    reasoning = body.get("reasoning")
    if isinstance(reasoning, dict):
        effort = reasoning.get("effort")
        if isinstance(effort, str) and effort and effort != "off":
            chat["reasoning_effort"] = effort
        elif effort == "off" and not settings.get("strip_reasoning_effort_off", True):
            chat["reasoning_effort"] = "minimal"

    return chat