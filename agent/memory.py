"""决策记忆：state/decision-history.json，滚动 60 天的每日决策摘要。

为什么需要它：dry-run 下 order-list 只含"真实下过的单"，不含日记里的决策——
引擎因此看不见 McAutoPilot 自己昨天选了什么（Day 2 与 Day 1 选了同款的根因）。
本模块把每次成功写入日记的决策持久化，感知阶段并回 snap.history，
v1 的重复惩罚与 v2 的新鲜度由此同时生效。

结构（JSON 数组，滚动 60 天）：
    [{"date": "YYYY-MM-DD", "items": ["菜品名", ...], "pay": 31.5}, ...]

首次运行文件缺失/为空时，从 DECISIONS.md 的 Day 条目解析种子（惰性：只在
record 落盘时才写出，mock/preview 模式零写副作用）。DECISIONS.md 始终是
可追溯的真相源，本文件只是引擎的加速读。
"""
from __future__ import annotations

import json
import re
from datetime import date, timedelta
from pathlib import Path

from .config import bj_today
from .perceive import HistoryOrder

ROLLING_DAYS = 60

# Day 条目标题：## Day N · YYYY-MM-DD（"· 周X" / "· ⚠️ 决策失败" 等后缀可有可无）
_DAY_HEAD = re.compile(r"^## Day (\d+) · (\d{4}-\d{2}-\d{2})", re.M)
# 决策行：**今日决策**：A + B —— 实测算价 ¥31.5（…） / 菜单价 ¥30，券后约 ¥28（离线估算）
_DECISION_LINE = re.compile(r"\*\*今日决策\*\*：(.+?)\s*——")
# 实付口径按优先级取：实测算价（真实）> 券后约（估算实付）> 菜单价（未折）
_PAY_PATTERNS = (
    re.compile(r"实测算价\s*¥(\d+(?:\.\d+)?)"),
    re.compile(r"券后约\s*¥(\d+(?:\.\d+)?)"),
    re.compile(r"菜单价\s*¥(\d+(?:\.\d+)?)"),
)


def parse_diary(text: str) -> list[dict]:
    """从 DECISIONS.md 文本解析每日决策，返回按日期升序的 [{date, items, pay}]。

    跳过两类条目：Day 0 式手写占位（"今日决策：（无——…"）、决策失败条目（无决策行）。
    """
    days: list[dict] = []
    heads = list(_DAY_HEAD.finditer(text))
    for i, m in enumerate(heads):
        if int(m.group(1)) < 1:
            continue  # Day 0 是初始化占位，不进决策序列
        seg = text[m.end(): heads[i + 1].start() if i + 1 < len(heads) else len(text)]
        dm = _DECISION_LINE.search(seg)
        if not dm:
            continue  # 决策失败条目没有 "今日决策：…——…" 行
        items = [s.strip() for s in dm.group(1).split("+") if s.strip()]
        if not items or any(it.startswith("（") or it == "无" for it in items):
            continue  # "（无——今天我刚刚出生）"式占位
        pay = None
        for pat in _PAY_PATTERNS:
            pm = pat.search(seg)
            if pm:
                pay = float(pm.group(1))
                break
        days.append({"date": m.group(2), "items": items, "pay": pay})
    days.sort(key=lambda d: d["date"])
    return days


class DecisionMemory:
    def __init__(self, path: Path, days: list[dict] | None = None):
        self.path = path
        self.seeded = False  # 本次记忆来自 DECISIONS.md 种子解析（而非记忆文件）
        self.days: list[dict] = days if days is not None else self._load()

    def _load(self) -> list[dict]:
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    return [
                        d for d in data
                        if isinstance(d, dict) and d.get("date") and isinstance(d.get("items"), list)
                    ]
            except (json.JSONDecodeError, OSError):
                pass
        return []

    @classmethod
    def load_or_seed(cls, path: Path, diary_path: Path) -> "DecisionMemory":
        """记忆文件有货直接用；缺失/为空（首次运行）则从 DECISIONS.md 解析种子。

        种子只进内存不落盘——直到下一次成功写日记 record 时才随记忆一起写出，
        保证 mock/preview 模式不产生任何写副作用。
        """
        mem = cls(path)
        if not mem.days and diary_path.exists():
            seeded = parse_diary(diary_path.read_text(encoding="utf-8"))
            if seeded:
                mem.days, mem.seeded = seeded, True
        return mem

    def record(self, day: str, items: list[str], pay: float) -> None:
        """记录一天的决策（同日重写 = 覆盖），保持按日期升序 + 滚动 60 天。"""
        self.days = [d for d in self.days if d["date"] != day]
        self.days.append({"date": day, "items": [str(i) for i in items], "pay": round(float(pay), 2)})
        self.days.sort(key=lambda d: d["date"])
        cutoff = (date.fromisoformat(bj_today()) - timedelta(days=ROLLING_DAYS)).isoformat()
        self.days = [d for d in self.days if d["date"] >= cutoff]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.days, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def to_history(self) -> list[HistoryOrder]:
        """转成感知层的 HistoryOrder（最新在前，与 perceive 的倒序约定一致）。"""
        return [
            HistoryOrder(
                date=str(d["date"]),
                items=[str(i) for i in d["items"]],
                total=float(d.get("pay") or 0.0),
                source="decision-history",
            )
            for d in reversed(self.days)
        ]

    def merge_into(self, history: list[HistoryOrder]) -> int:
        """把决策记忆并入感知历史：同日已有真实订单的跳过（真实 > 计划），返回并入条数。"""
        existing = {h.date for h in history}
        merged = [h for h in self.to_history() if h.date not in existing]
        history.extend(merged)
        history.sort(key=lambda h: h.date, reverse=True)
        return len(merged)
