"""McAutoPilot 全局配置：一切敏感信息只从环境变量读取，永不落仓库。"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

# 可选依赖：本地开发装了 python-dotenv 就自动加载 .env（.env 已进 .gitignore）
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

REPO_ROOT = Path(__file__).resolve().parent.parent

# 统一北京时区（UTC+8 固定偏移，无夏令时）：日记时间戳、同日幂等的"今天"、
# 下单二次确认的当日令牌全用这个口径——GitHub runner 是 UTC，裸 now() 会差 8 小时。
BJ_TZ = timezone(timedelta(hours=8))


def bj_now() -> datetime:
    return datetime.now(BJ_TZ)


def bj_today() -> str:
    return bj_now().date().isoformat()


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
    budget: float = 40.0  # 单餐预算上限（元，执行链硬护栏）
    # true = 用真实数据跑完整决策但只写 state/preview.md，不落 DECISIONS.md（验证/fork 试跑用）
    preview: bool = False
    # 决策引擎：v1 = 规则打分（默认，保守）；v2 = 求解器（硬约束 + 加权目标）。非法值回落 v1。
    engine: str = "v1"
    # 下单二次确认：必须等于运行当天日期（YYYY-MM-DD）。日期每天变，陈旧配置无法持续授权。
    confirm_order: str = ""
    # 自动领券（auto-bind-coupons 写操作，零成本）。默认关，保持 dry-run 语义纯净。
    auto_claim: bool = False
    # 跳过同日幂等保护（同一天已写过日记仍强制重跑；测试/手动重写用）
    force: bool = False
    # 今日决策卡 webhook（企业微信/飞书/Discord/通用）。空 = 关闭。
    webhook_url: str = ""
    # 上游限流 600 req/min（0.1s/req），留出安全余量
    request_interval: float = 0.15
    request_timeout: float = 30.0
    state_dir: Path = field(default_factory=lambda: REPO_ROOT / "state")

    @classmethod
    def from_env(cls) -> "Settings":
        engine = os.environ.get("MCD_ENGINE", "v1").strip().lower()
        return cls(
            mcp_url=os.environ.get("MCD_MCP_URL", cls.mcp_url),
            mcp_token=os.environ.get("MCD_MCP_TOKEN", ""),
            dry_run=_env_bool("MCD_DRY_RUN", True),
            budget=float(os.environ.get("MCD_BUDGET", "40")),
            preview=_env_bool("MCD_PREVIEW", False),
            engine=engine if engine in ("v1", "v2") else "v1",
            confirm_order=os.environ.get("MCD_CONFIRM_ORDER", "").strip(),
            auto_claim=_env_bool("MCD_AUTO_CLAIM", False),
            force=_env_bool("MCD_FORCE", False),
            webhook_url=os.environ.get("MCD_WEBHOOK_URL", "").strip(),
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
