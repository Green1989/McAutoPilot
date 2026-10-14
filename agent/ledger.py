"""营养台账：state/nutrition.json，滚动记录每日计划摄入与支出。

只存决策摘要（日期 + 营养合计 + 花费），不存任何个人隐私字段。
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path


class Ledger:
    def __init__(self, path: Path):
        self.path = path
        self.days: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                self.days = json.loads(self.path.read_text(encoding="utf-8")).get("days", {})
            except (json.JSONDecodeError, OSError):
                self.days = {}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"days": self.days}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def update(self, day: str, kcal: float, protein: float, sodium: float, spend: float) -> None:
        self.days[day] = {
            "kcal": round(kcal, 1),
            "protein": round(protein, 1),
            "sodium": round(sodium, 1),
            "spend": round(spend, 2),
        }
        # 只保留最近 60 天，台账不无限膨胀
        cutoff = (date.today() - timedelta(days=60)).isoformat()
        self.days = {d: v for d, v in sorted(self.days.items()) if d >= cutoff}

    def rolling_avg(self, field: str, days: int = 7) -> float | None:
        """近 N 天某指标均值；无记录返回 None。"""
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        values = [v[field] for d, v in self.days.items() if d >= cutoff and isinstance(v.get(field), (int, float))]
        return sum(values) / len(values) if values else None

    def gap_reasons(self) -> list[str]:
        """用近 7 天均值生成营养缺口描述，供决策理由引用。"""
        reasons = []
        p = self.rolling_avg("protein")
        s = self.rolling_avg("sodium")
        spend = self.rolling_avg("spend")
        if p is not None:
            reasons.append(f"近7天蛋白均值 {p:.0f}g/餐（目标 ≥{30:.0f}g）")
        if s is not None and s > 1100:
            reasons.append(f"近7天钠均值 {s:.0f}mg/餐偏高，今天拉回均衡")
        if spend is not None:
            reasons.append(f"近7天单餐花费均值 ¥{spend:.1f}")
        return reasons
