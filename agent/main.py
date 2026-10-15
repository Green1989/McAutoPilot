"""McAutoPilot 每日主循环入口：python -m agent.main

循环：感知（菜单/券/历史/营养/积分 + 决策记忆）→ 决策（v1 规则打分 / v2 求解器，
MCD_ENGINE 切换）→ 执行（dry-run 算价草稿；live 走领券 + create-order 三重护栏）
→ 记录（DECISIONS.md 插入 + 营养台账 + 决策记忆 + commit 消息）。

模式约定：
- mock（无 Token）：完整跑决策，但日记只写 state/preview.md，绝不碰 DECISIONS.md；
- live-dryrun（默认）：真实感知 + 真实算价（calculate-price 纯计算），写入 DECISIONS.md；
- live（MCD_DRY_RUN=false）：执行链启用——需再过 MCD_CONFIRM_ORDER 当日二次确认
  与预算硬护栏，才会调 auto-bind-coupons / create-order（且支付永远人工完成）。

同日幂等：非 mock、非 preview 模式下，当天 DECISIONS.md 已有成功决策条目时整条
流水线直接跳过（exit 0，workflow 保持绿）——防 cron 补触发/误触 dispatch 写出同日
两条 Day 条目。MCD_FORCE=true 可绕过（测试/手动重写用）。
"""
from __future__ import annotations

import asyncio
import json
import sys

from . import report
from .brain import decide
from .config import REPO_ROOT, Settings, bj_today
from .executor import claim_coupons, execute_order
from .ledger import Ledger
from .mcp_client import make_client
from .memory import DecisionMemory
from .perceive import perceive, price_check

DIARY = REPO_ROOT / "DECISIONS.md"
STATE_DIR = REPO_ROOT / "state"


async def run() -> int:
    settings = Settings.from_env()
    mode = settings.mode
    print(f"[McAutoPilot] 模式: {mode}" + ("（未配置 MCD_MCP_TOKEN，使用离线模拟数据）" if mode == "mock" else ""))
    print(f"[McAutoPilot] dry-run: {settings.dry_run} · 预算: ¥{settings.budget:.0f} · 引擎: {settings.engine}")

    today = bj_today()  # 全流水线统一北京日期（runner 是 UTC，裸 today() 会差 8 小时）
    ledger = Ledger(STATE_DIR / "nutrition.json")

    # 同日幂等保护：今天已写过日记（成功决策条目）则整条流水线跳过。
    # 放在连 MCP 之前——所有写副作用（日记/台账/last-decision/live 下单）一并挡住。
    if mode != "mock" and not settings.preview and not settings.force and report.has_entry_for_today(DIARY, today):
        print(f"[McAutoPilot] 今天（{today}）已写过日记，幂等跳过本次运行（要重跑设 MCD_FORCE=true）")
        return 0

    async with make_client(settings) as client:
        # 可选前置写操作：自动领券（零成本）。默认关（MCD_AUTO_CLAIM），保持 dry-run 语义纯净。
        claimed = 0
        if settings.auto_claim and mode != "mock":
            claimed, note = await claim_coupons(client)
            print(f"[McAutoPilot] 自动领券: {claimed} 张" + ("" if claimed else f"（{note[:80]}）"))

        snap = await perceive(client)
        print(f"[McAutoPilot] 感知: {snap.store_name or '未取到门店'} · 菜单 {len(snap.menu)} · 券 {len(snap.coupons)} · 历史订单 {len(snap.history)} · 营养库 {len(snap.nutrition)} 条")
        for f in snap.failures:
            print(f"  [降级] {f}")

        # 决策记忆并回感知历史：dry-run 下的决策不是订单，order-list 看不见它们，
        # 不并回来的话换口味规则（v1 重复惩罚 / v2 新鲜度）就是瞎的。
        memory = DecisionMemory.load_or_seed(STATE_DIR / "decision-history.json", DIARY)
        merged = memory.merge_into(snap.history)
        seed_note = "（由 DECISIONS.md 种子解析）" if memory.seeded else ""
        print(f"[McAutoPilot] 决策记忆: {len(memory.days)} 天{seed_note} · 并入历史 {merged} 条（来源 decision-history）")

        day = report.next_day(DIARY)
        try:
            decision = decide(snap, budget=settings.budget, engine=settings.engine)
        except ValueError as exc:
            print(f"[McAutoPilot] 决策失败: {exc}", file=sys.stderr)
            entry = (
                f"## Day {day} · {today} · ⚠️ 决策失败\n\n"
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

        # 执行链 v2：live 模式才运行（内部还有二次确认 + 预算硬护栏）
        exec_summary = None
        if mode == "live" and snap.store_code:
            exec_summary = await execute_order(client, settings, snap.store_code, decision, price_info)
            print(f"[McAutoPilot] 执行链: {exec_summary.status} —— {exec_summary.reason}")
            if exec_summary.raw_snippet:
                STATE_DIR.mkdir(exist_ok=True)
                (STATE_DIR / "last-order.json").write_text(json.dumps({
                    "day": day, "date": today,
                    "status": exec_summary.status, "reason": exec_summary.reason,
                    "orderId": exec_summary.order_id, "payUrl": exec_summary.pay_url,
                    "pay": price_info["pay"] if price_info else None,
                    "raw": exec_summary.raw_snippet,
                }, ensure_ascii=False, indent=2), encoding="utf-8")

        ledger_reasons = ledger.gap_reasons()
        entry = report.render_entry(day, decision, snap, price_info, mode, ledger_reasons, exec_summary, claimed)

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
            # 决策记忆追加（含首次种子一并落盘）：明天的换口味规则靠它
            memory.record(today, [i.name for i in decision.items], pay)
            memory.save()
            if decision.nutrition:
                ledger.update(
                    today,
                    decision.nutrition["kcal"], decision.nutrition["protein"],
                    decision.nutrition["sodium"], pay,
                )
                ledger.save()
            STATE_DIR.mkdir(exist_ok=True)
            (STATE_DIR / "last-decision.json").write_text(json.dumps({
                "day": day, "date": today, "mode": mode, "engine": decision.engine,
                "items": [{"code": i.code, "name": i.name} for i in decision.items],
                "coupon": decision.coupon.title if decision.coupon else None,
                "pay": pay, "score": decision.score,
                "reasons": decision.reasons[:5],
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
