"""MCP 客户端统一接口：真实客户端与离线 Mock 客户端实现同一套契约。"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


def extract_json(text: str) -> Any:
    """从 MCP 的 LLM 友好文本中提取数据。

    上游返回通常是「markdown 字段说明 + ## Original Response + 原始 JSON」，
    部分工具直接给 markdown 列表/表格文本。按优先级：
    Original Response 段 > 首个花括号/方括号配平的 JSON 片段。
    """
    text = text.strip()
    if not text:
        return None
    marker = "Original Response"
    if marker in text:
        tail = text[text.rindex(marker) + len(marker):].strip()
        parsed = _loads_balanced(tail)
        if parsed is not None:
            return parsed
    return _loads_balanced(text)


def _loads_balanced(text: str) -> Any:
    """扫描文本，解析第一个花括号/方括号配平的 JSON 片段。"""
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        while start != -1:
            depth, in_str, escape = 0, False, False
            for i in range(start, len(text)):
                ch = text[i]
                if in_str:
                    if escape:
                        escape = False
                    elif ch == "\\":
                        escape = True
                    elif ch == '"':
                        in_str = False
                    continue
                if ch == '"':
                    in_str = True
                elif ch == opener:
                    depth += 1
                elif ch == closer:
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[start:i + 1])
                        except json.JSONDecodeError:
                            break
            start = text.find(opener, start + 1)
    return None


@dataclass
class ToolResult:
    """call_tool 的归一化返回：不管上游返回什么内容块，文本总能从 .text 拿到。"""

    name: str
    text: str = ""
    is_error: bool = False
    raw: Any = None
    data: Any = field(default=None)  # text 能解析成 JSON 时自动填充

    @property
    def ok(self) -> bool:
        return not self.is_error


class McpClientBase:
    """子类需实现 list_tools / call_tool，并支持 async with。"""

    async def __aenter__(self) -> "McpClientBase":
        return self

    async def __aexit__(self, *exc) -> None:
        await self.close()

    async def list_tools(self) -> list[dict]:
        """返回 [{"name": ..., "description": ..., "inputSchema": {...}}, ...]"""
        raise NotImplementedError

    async def call_tool(self, name: str, arguments: dict | None = None) -> ToolResult:
        raise NotImplementedError

    async def close(self) -> None:
        pass

    async def find_tools(self, *keywords: str) -> list[dict]:
        """按名称/描述关键词模糊匹配工具，用于拿到 Token 前不知道确切工具名的场景。"""
        matched = []
        for tool in await self.list_tools():
            hay = f"{tool.get('name', '')} {tool.get('description', '')}".lower()
            if any(kw.lower() in hay for kw in keywords):
                matched.append(tool)
        return matched
