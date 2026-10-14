"""执行层 v2：MCD_DRY_RUN=false 时的真实写操作链（领券 / 创建订单）。

三重护栏（全部通过才会调用 create-order）：
1. 双开关：MCD_DRY_RUN=false（总闸）+ MCD_CONFIRM_ORDER=运行当天日期（二次确认——
   日期每天变，陈旧配置无法持续授权下单，想开一天就显式设一天）；
2. 预算硬上限：以 calculate-price 的**真实实付**为准，超过 MCD_BUDGET 即中止（不用估值）；
3. 支付留人：MCP 的 create-order 只生成"待支付订单"+支付链接，支付永远人工完成，
   agent 不碰任何支付动作。

订单结果只落本地 state/last-order.json（支付链接含账号上下文，绝不提交仓库）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from .config import Settings
from .mcp_client.base import McpClientBase
from .perceive import BETYPE_DINEIN, ORDER_TYPE_DINEIN, _payload


@dataclass
class ExecutionResult:
    status: str            # created / skipped / aborted / failed
    reason: str = ""
    order_id: str = ""
    pay_url: str = ""
    raw_snippet: str = ""


async def claim_coupons(client: McpClientBase) -> tuple[int, str]:
    """自动领取麦麦省当前可用券（auto-bind-coupons，无参数写操作，零成本）。

    尽力而为：失败只记原因，绝不阻塞主流程。返回 (领取数, 返回摘要)。
    """
    r = await client.call_tool("auto-bind-coupons", {})
    text = r.text or ""
    if not r.ok:
        return 0, f"auto-bind-coupons 调用失败: {text[:120]}"
    count: int | None = None
    data = _payload(r)
    if isinstance(data, dict):
        for key in ("bindCount", "count", "successCount", "total"):
            v = data.get(key)
            if isinstance(v, bool):
                continue
            if isinstance(v, (int, float)):
                count = int(v)
                break
            if isinstance(v, str) and v.strip().isdigit():
                count = int(v.strip())
                break
    if count is None:
        m = re.search(r"(\d+)\s*张", text)
        count = int(m.group(1)) if m else 0
    return count, text[:200]


def _guards(settings: Settings, price_info: dict | None, today: str) -> tuple[bool, str]:
    """下单前三重护栏检查，返回 (是否放行, 原因)。"""
    if settings.dry_run:
        return False, "dry-run 开启（MCD_DRY_RUN 未设为 false），按设计止步于订单草稿"
    if settings.confirm_order != today:
        return False, (
            f"缺少当日二次确认：MCD_CONFIRM_ORDER 需等于 {today}"
            f"（当前: {settings.confirm_order or '未设置'}）"
        )
    if not price_info:
        return False, "无 calculate-price 真实算价结果，拒绝在未算价时下单"
    pay = price_info.get("pay", 0.0)
    if pay > settings.budget:
        return False, f"实付 ¥{pay:.1f} 超预算硬上限 ¥{settings.budget:.0f}，中止"
    return True, ""


async def execute_order(
    client: McpClientBase,
    settings: Settings,
    store_code: str,
    decision,
    price_info: dict | None,
) -> ExecutionResult:
    """真实下单：护栏检查 → create-order（待支付订单）→ 解析订单号与支付链接。"""
    today = date.today().isoformat()
    ok, why = _guards(settings, price_info, today)
    if not ok:
        return ExecutionResult(status="skipped", reason=why)

    take_ways = (price_info or {}).get("take_ways") or []
    if not take_ways:
        return ExecutionResult(status="aborted", reason="算价结果缺少 takeWayList，无法确定取餐方式（堂食/外带）")
    take_way_code = str(take_ways[0].get("code", ""))

    items = []
    for it in decision.items:
        entry: dict = {"productCode": it.code, "quantity": 1}
        if decision.coupon is not None and it.code in decision.coupon.product_codes:
            entry["couponId"] = decision.coupon.coupon_id
            entry["couponCode"] = decision.coupon.coupon_code
        items.append(entry)

    r = await client.call_tool("create-order", {
        "storeCode": store_code,
        "orderType": ORDER_TYPE_DINEIN,
        "beType": BETYPE_DINEIN,
        "takeWayCode": take_way_code,
        "items": items,
        "needTableware": False,
    })
    text = r.text or ""
    if not r.ok:
        return ExecutionResult(status="failed", reason=f"create-order 调用失败: {text[:150]}", raw_snippet=text[:400])

    data = _payload(r)
    if not isinstance(data, dict):
        return ExecutionResult(status="failed", reason=f"create-order 返回无法解析: {text[:150]}", raw_snippet=text[:400])

    def _find(*keys: str) -> str:
        for k in keys:
            v = data.get(k)
            if v:
                return str(v)
        return ""

    order_id = _find("orderId", "orderNo", "order_id", "tradeNo", "orderNumber")
    pay_url = _find("payUrl", "payLink", "paymentUrl", "payQrCode", "qrCodeUrl", "payInfo", "url")
    if not order_id:
        return ExecutionResult(status="failed", reason="create-order 返回中未识别到订单号（首次 live 调用？请核对 state/last-order.json 的原始返回）", raw_snippet=text[:400])
    return ExecutionResult(
        status="created",
        reason="订单已创建，待人工支付（支付链接不进日记，只落本地 state/last-order.json）",
        order_id=order_id,
        pay_url=pay_url,
        raw_snippet=text[:400],
    )
