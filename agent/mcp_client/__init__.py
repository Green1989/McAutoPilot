"""客户端工厂：有 Token 走真实 HTTP 客户端，无 Token 自动降级 Mock。"""
from __future__ import annotations

from ..config import Settings
from .base import McpClientBase
from .mock_client import MockMcpClient


def make_client(settings: Settings) -> McpClientBase:
    if settings.has_token:
        # 懒加载：仅真实模式需要官方 SDK
        from .http_client import HttpMcpClient

        return HttpMcpClient(
            url=settings.mcp_url,
            token=settings.mcp_token,
            request_interval=settings.request_interval,
            request_timeout=settings.request_timeout,
        )
    return MockMcpClient()
