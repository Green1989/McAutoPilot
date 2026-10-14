"""日记渲染：把 Decision 渲染成 DECISIONS.md 的每日条目并插入。"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

WEEKDAY_CN = "一二三四五六日"
BADGES = {5: "🏅", 10: "🥈", 15: "🥇", 30: "🏆", 50: "💎", 100: "👑"}


def _badge(day: int) -> str:
    for threshold in sorted(BADGES, reverse=True):
        if day >= threshold:
            return f" {BADGES[threshold]} 连续决策第 {day} 天里程碑"
    return ""


def next_day(diary_path: Path) -> int:
    if not diary_path.exists():
        return 1
    days = [int(m.group(1)) for m in re.finditer(r"^## Day (\d+)", diary_path.read_text(encoding="utf-8"), re.M)]
    return max(days) + 1 if days else 1


def render_entry(
    day: int,
    decision,
    snap,
    price_info: dict | None,
    mode: str,
    ledger_reasons: list[str],
    exec_summary=None,
    claimed: int = 0,
) -> str:
    today = datetime.now()
    items_txt = " + ".join(it.name for it in decision.items)
    engine_name = "求解器引擎 v2" if getattr(decision, "engine", "v1") == "v2" else "规则引擎 v1"
    lines: list[str] = []
    lines.append(f"## Day {day} · {today:%Y-%m-%d} · 周{WEEKDAY_CN[today.weekday()]}{_badge(day)}")
    lines.append("")

    if price_info:
        pay_line = f"**今日决策**：{items_txt} —— 实测算价 ¥{price_info['pay']:.1f}（原价 ¥{price_info['origin']:.1f}，优惠 ¥{price_info['discount']:.1f}）"
    else:
        pay = round(decision.menu_price - decision.est_saving, 1)
        saving = f"，券后约 ¥{pay}" if decision.coupon else ""
        pay_line = f"**今日决策**：{items_txt} —— 菜单价 ¥{decision.menu_price:.1f}{saving}（离线估算，未接真实算价）"
    lines.append(pay_line)
    lines.append("")

    lines.append("**为什么**：")
    idx = 1
    for reason in decision.reasons:
        lines.append(f"{idx}. {reason}")
        idx += 1
    for reason in ledger_reasons:
        lines.append(f"{idx}. {reason}")
        idx += 1
    lines.append("")

    breakdown = getattr(decision, "breakdown", None)
    if breakdown:
        parts = [f"{label} {'+' if c >= 0 else ''}{c:.1f}" for label, c, _ in breakdown]
        lines.append("**分数构成**：" + " · ".join(parts))
        lines.append("")

    if decision.nutrition:
        n = decision.nutrition
        lines.append(
            f"**营养台账**：kcal {n['kcal']:.0f}/2000 · 蛋白 {n['protein']:.0f}/60g · 钠 {n['sodium']:.0f}/2000mg"
        )
    else:
        lines.append("**营养台账**：本组合未匹配到营养数据，暂不计入")
    lines.append("")

    if mode == "live" and exec_summary is not None:
        if exec_summary.status == "created":
            exec_line = f"**执行**：✅ 已创建订单（{exec_summary.order_id}，待人工支付——支付链接只落本地 state/last-order.json，不进仓库）"
        else:
            exec_line = f"**执行**：未创建订单——{exec_summary.reason}"
    elif mode == "live":
        exec_line = "**执行**：live 模式但执行链未运行（见 Actions 日志）"
    else:
        claim_note = f"（另：自动领取了 {claimed} 张券）" if claimed else ""
        exec_line = f"**执行**：dry-run —— 订单草稿已生成，未下单{claim_note}（真实下单需 MCD_DRY_RUN=false + 当日二次确认）"
    store_line = f"**数据源**：{snap.store_name or '未知门店'} · {len(snap.menu)} 个在售餐品 · {len(snap.coupons)} 张可用券 · 积分 {snap.points:.0f}"
    lines.append(exec_line)
    lines.append(store_line)

    if snap.failures:
        lines.append("")
        lines.append("**感知降级**：" + "；".join(snap.failures))
    lines.append("")
    lines.append(f"<sub>score {decision.score} · 由 McAutoPilot {engine_name} 于 {today:%H:%M} 自动生成</sub>")
    lines.append("")
    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def insert_entry(diary_path: Path, entry: str) -> None:
    """新条目插到格式说明注释块之后、最早的 Day 条目之前（新在上，旧在下）。"""
    text = diary_path.read_text(encoding="utf-8") if diary_path.exists() else ""
    m = re.search(r"^## Day \d+", text, re.M)
    if m:
        text = text[: m.start()] + entry + "\n" + text[m.start():]
    else:
        text = text.rstrip("\n") + ("\n\n" if text else "") + entry
    diary_path.write_text(text, encoding="utf-8")
