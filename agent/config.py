"""McAutoPilot 全局配置：一切敏感信息只从环境变量读取，永不落仓库。"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# 可选依赖：本地开发装了 python-dotenv 就自动加载 .env（.env 已进 .gitignore）
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

REPO_ROOT = Path(__file__).resolve().parent.parent


def _env_bool(key: str, default: bool) -> bool:
    raw = os.environ.get(key)
    if raw is None:
        return default
    return raw.strip().lower() not in ("0", "false", "no", "off", "")


@dataclass
class Settings:
    mcp_url: str = "https://mcp.mcd.cn"
    mcp_token: str = ""
    # 默认 dry-run：只生成决策与订单草稿，绝不真实下单。显式设 MCD_DRY_RUN=false 才会动真格。
    dry_run: bool = True
    budget: float = 40.0  # 单餐预算上限（元）
    # true = 用真实数据跑完整决策但只写 state/preview.md，不落 DECISIONS.md（验证/fork 试跑用）
    preview: bool = False
    # 上游限流 600 req/min（0.1s/req），留出安全余量
    request_interval: float = 0.15
    request_timeout: float = 30.0
    state_dir: Path = field(default_factory=lambda: REPO_ROOT / "state")

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            mcp_url=os.environ.get("MCD_MCP_URL", cls.mcp_url),
            mcp_token=os.environ.get("MCD_MCP_TOKEN", ""),
            dry_run=_env_bool("MCD_DRY_RUN", True),
            budget=float(os.environ.get("MCD_BUDGET", "40")),
            preview=_env_bool("MCD_PREVIEW", False),
            request_interval=float(os.environ.get("MCD_REQUEST_INTERVAL", "0.15")),
            request_timeout=float(os.environ.get("MCD_REQUEST_TIMEOUT", "30")),
        )

    @property
    def has_token(self) -> bool:
        return bool(self.mcp_token.strip())

    @property
    def mode(self) -> str:
        if not self.has_token:
            return "mock"
        return "live-dryrun" if self.dry_run else "live"
