"""真实麦当劳 MCP 客户端（Streamable HTTP + Bearer Token）。

官方 SDK `mcp` 做懒加载：没有 Token / 没装依赖的离线场景完全不需要它，
Mock 模式零依赖可跑。
"""
from __future__ import annotations

import asyncio
import json
import logging
from contextlib import AsyncExitStack
from typing import Any

from .base import McpClientBase, ToolResult, extract_json

logger = logging.getLogger("mcp-client")


class HttpMcpClient(McpClientBase):
    def __init__(
        self,
        url: str,
        token: str,
        request_interval: float = 0.15,
        request_timeout: float = 30.0,
    ) -> None:
        self.url = url.rstrip("/")
        self.token = token
        self.request_interval = request_interval
        self.request_timeout = request_timeout
        self._session = None
        self._stack: AsyncExitStack | None = None
        self._last_call = 0.0

    async def __aenter__(self) -> "HttpMcpClient":
        await self._connect()
        return self

    async def _connect(self) -> None:
        # 懒加载官方 SDK：仅真实模式需要
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client

        headers = {"Authorization": f"Bearer {self.token}"}
        self._stack = AsyncExitStack()
        # streamablehttp_client 返回 (read_stream, write_stream, get_session_id)
        read, write, _ = await self._stack.enter_async_context(
            streamablehttp_client(self.url, headers=headers, timeout=self.request_timeout)
        )
        self._session = await self._stack.enter_async_context(ClientSession(read, write))
        await self._session.initialize()

    async def _disconnect(self) -> None:
        if self._stack is not None:
            try:
                await self._stack.aclose()
            except Exception:  # 关闭阶段的网络抖动不应炸掉整个运行
                pass
            self._stack = None
        self._session = None

    async def _with_retry(self, coro_factory):
        """瞬时断连时重建会话并重试一次（公网到 mcp.mcd.cn 偶发抖动）。"""
        try:
            return await coro_factory()
        except Exception as first_exc:
            logger.warning("调用失败（%s），重建会话重试一次", first_exc)
            await self._disconnect()
            await asyncio.sleep(1.5)
            await self._connect()
            return await coro_factory()

    async def _throttle(self) -> None:
        """上游限流 600 req/min；串行调用并保持最小间隔。"""
        now = asyncio.get_event_loop().time()
        wait = self._last_call + self.request_interval - now
        if wait > 0:
            await asyncio.sleep(wait)
        self._last_call = asyncio.get_event_loop().time()

    async def list_tools(self) -> list[dict]:
        await self._throttle()

        async def _do():
            resp = await self._session.list_tools()
            return [
                {
                    "name": tool.name,
                    "description": tool.description or "",
                    "inputSchema": getattr(tool, "inputSchema", None) or {},
                }
                for tool in resp.tools
            ]

        return await self._with_retry(_do)

    async def call_tool(self, name: str, arguments: dict | None = None) -> ToolResult:
        await self._throttle()

        async def _do():
            return await self._session.call_tool(name, arguments or {})

        try:
            resp = await self._with_retry(_do)
        except Exception as exc:  # 网络/协议层异常统一归一为错误结果，不让单点失败炸掉整个循环
            logger.warning("call_tool %s 传输异常: %s", name, exc)
            return ToolResult(name=name, is_error=True, raw=str(exc))

        texts = [
            block.text
            for block in (resp.content or [])
            if getattr(block, "type", "") == "text"
        ]
        text = "\n".join(texts)
        result = ToolResult(
            name=name,
            text=text,
            is_error=bool(getattr(resp, "isError", False)),
            raw=resp,
        )
        result.data = extract_json(text)
        return result

    async def __aexit__(self, *exc) -> None:
        await self._disconnect()
