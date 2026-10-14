"""McAutoPilot 每日主循环入口：python -m agent.main

循环：感知（菜单/券/历史/营养/积分）→ 决策（规则打分）→ 执行（dry-run 算价草稿）
→ 记录（DECISIONS.md 插入 + 营养台账 + commit 消息）。

模式约定：
- mock（无 Token）：完整跑决策，但日记只写 state/preview.md，绝不碰 DECISIONS.md；
- live-dryrun（默认）：真实感知 + 真实算价（calculate-price 纯计算），写入 DECISIONS.md；
- live（MCD_DRY_RUN=false）：才会触发真实领券/下单（v2 实装，当前仍止步于草稿）。
"""
from __future__ import annotations

import asyncio
import json
import sys
from datetime import date

from . import report
from .brain import decide
from .config import REPO_ROOT, Settings
from .ledger import Ledger
from .mcp_client import make_client
from .perceive import perceive, price_check

DIARY = REPO_ROOT / "DECISIONS.md"
STATE_DIR = REPO_ROOT / "state"


async def run() -> int:
    settings = Settings.from_env()
    mode = settings.mode
    print(f"[McAutoPilot] 模式: {mode}" + ("（未配置 MCD_MCP_TOKEN，使用离线模拟数据）" if mode == "mock" else ""))
    print(f"[McAutoPilot] dry-run: {settings.dry_run} · 预算: ¥{settings.budget:.0f}")

    ledger = Ledger(STATE_DIR / "nutrition.json")

    async with make_client(settings) as client:
        snap = await perceive(client)
        print(f"[McAutoPilot] 感知: {snap.store_name or '未取到门店'} · 菜单 {len(snap.menu)} · 券 {len(snap.coupons)} · 历史订单 {len(snap.history)} · 营养库 {len(snap.nutrition)} 条")
        for f in snap.failures:
            print(f"  [降级] {f}")

        day = report.next_day(DIARY)
        try:
            decision = decide(snap, budget=settings.budget)
        except ValueError as exc:
            print(f"[McAutoPilot] 决策失败: {exc}", file=sys.stderr)
            entry = (
                f"## Day {day} · {date.today()} · ⚠️ 决策失败\n\n"
                f"今天没能做出决定：{exc}\n\n---\n"
            )
            if mode != "mock":
                report.insert_entry(DIARY, entry)
            return 1

        # 执行：dry-run = 真实算价草稿（纯计算，无任何账户副作用）
        price_info = None
        if mode != "mock" and snap.store_code:
            price_info = await price_check(client, snap.store_code, decision.items, decision.coupon)
            if price_info:
                print(f"[McAutoPilot] 算价: 原价 ¥{price_info['origin']:.1f} → 优惠 ¥{price_info['discount']:.1f} → 实付 ¥{price_info['pay']:.1f}")
            else:
                print("[McAutoPilot] 算价失败，按菜单价估算")

        ledger_reasons = ledger.gap_reasons()
        entry = report.render_entry(day, decision, snap, price_info, mode, ledger_reasons)

        pay = price_info["pay"] if price_info else round(decision.menu_price - decision.est_saving, 1)
        if mode == "mock" or settings.preview:
            STATE_DIR.mkdir(exist_ok=True)
            tag = "mock 模式" if mode == "mock" else "MCD_PREVIEW 预览"
            (STATE_DIR / "preview.md").write_text(
                f"<!-- {tag}（不写入 DECISIONS.md）· Day {day} -->\n\n" + entry,
                encoding="utf-8",
            )
            print(f"[McAutoPilot] 预览已写 {STATE_DIR / 'preview.md'}（不写入 DECISIONS.md）")
        else:
            report.insert_entry(DIARY, entry)
            if decision.nutrition:
                ledger.update(
                    date.today().isoformat(),
                    decision.nutrition["kcal"], decision.nutrition["protein"],
                    decision.nutrition["sodium"], pay,
                )
                ledger.save()
            STATE_DIR.mkdir(exist_ok=True)
            (STATE_DIR / "last-decision.json").write_text(json.dumps({
                "day": day, "date": date.today().isoformat(), "mode": mode,
                "items": [{"code": i.code, "name": i.name} for i in decision.items],
                "coupon": decision.coupon.title if decision.coupon else None,
                "pay": pay, "score": decision.score,
            }, ensure_ascii=False, indent=2), encoding="utf-8")
            items_short = " + ".join(i.name for i in decision.items)[:40]
            (STATE_DIR / "commit-msg.txt").write_text(
                f"🍱 Day {day}: {items_short} - ¥{pay:.1f}", encoding="utf-8"
            )
            print(f"[McAutoPilot] Day {day} 已写入 {DIARY.name}")

    print(f"[McAutoPilot] 完成 · 决策: {' + '.join(i.name for i in decision.items)} · ¥{pay:.1f} · score {decision.score}")
    return 0


def main() -> None:
    sys.exit(asyncio.run(run()))


if __name__ == "__main__":
    main()
