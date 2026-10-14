"""感知层：把 MCP 各工具的原始返回归一化为决策引擎可用的 Snapshot。

真实结构参考 docs/mcp-tool-samples/（2026-10-14 实测）：
- query-nearby-stores → data[{storeName, storeCode, ...}]
- query-meals → data{categories[{name, meals[{code,tags}]}], meals{code:{name,currentPrice,...}}}
- query-store-coupons → data[{title, couponId, couponCode, tradeDateTime, products[{productCode}]}]
- order-list → data{list[{createTime, orderProductList[{productName,quantity,comboItemList}], realTotalAmount}]}
- list-nutrition-foods → 文本 "[N]{列名}:
  CSV行"（单位：kcal/g/mg）
- query-my-account → data{availablePoint, ...}
- calculate-price → data{price, discount, ...}（单位：分）
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from .mcp_client.base import McpClientBase, ToolResult

logger = logging.getLogger("perceive")

ORDER_TYPE_DINEIN = 1
BETYPE_DINEIN = 1


@dataclass
class MenuItem:
    code: str
    name: str
    price: float
    category: str
    tags: list[str] = field(default_factory=list)


@dataclass
class Coupon:
    coupon_id: str
    coupon_code: str
    title: str
    product_codes: list[str]
    valid_text: str = ""


@dataclass
class HistoryOrder:
    date: str  # yyyy-MM-dd
    items: list[str]  # 菜品名（含套餐子项），已脱敏
    total: float


@dataclass
class Snapshot:
    store_code: str = ""
    store_name: str = ""
    menu: list[MenuItem] = field(default_factory=list)
    coupons: list[Coupon] = field(default_factory=list)
    history: list[HistoryOrder] = field(default_factory=list)
    nutrition: dict[str, dict[str, float]] = field(default_factory=dict)
    points: float = 0.0
    failures: list[str] = field(default_factory=list)  # 感知降级记录（写进日记，保证诚实）


def _payload(r: ToolResult):
    """提取 {"success":..,"data":..} 信封里的 data；失败返回 None 并记原因。"""
    if not r.ok:
        return None
    data = r.data
    if isinstance(data, dict):
        return data.get("data", data)
    return data


async def _call(client: McpClientBase, name: str, args: dict, snap: Snapshot, what: str):
    r = await client.call_tool(name, args)
    payload = _payload(r)
    if payload is None:
        snap.failures.append(f"{what}: {name} 无有效数据 ({r.text[:60]})")
    return payload


async def perceive(client: McpClientBase) -> Snapshot:
    snap = Snapshot()

    stores = await _call(client, "query-nearby-stores", {"beType": BETYPE_DINEIN, "searchType": 1}, snap, "门店")
    if isinstance(stores, list) and stores:
        snap.store_code = str(stores[0].get("storeCode", ""))
        snap.store_name = str(stores[0].get("storeName", ""))

    if snap.store_code:
        meals = await _call(
            client, "query-meals",
            {"storeCode": snap.store_code, "orderType": ORDER_TYPE_DINEIN, "beType": BETYPE_DINEIN},
            snap, "菜单",
        )
        if isinstance(meals, dict):
            category_of: dict[str, str] = {}
            for cat in meals.get("categories", []):
                for m in cat.get("meals", []):
                    category_of[str(m.get("code", ""))] = str(cat.get("name", ""))
            for code, info in (meals.get("meals") or {}).items():
                try:
                    snap.menu.append(MenuItem(
                        code=str(code),
                        name=str(info.get("name", "")),
                        price=float(info.get("currentPrice") or 0),
                        category=category_of.get(str(code), "其他"),
                        tags=[str(t) for t in (m.get("tags") or [])] or _tags_of(category_of.get(str(code), ""), info.get("name", "")),
                    ))
                except (TypeError, ValueError):
                    continue

        coupons = await _call(
            client, "query-store-coupons",
            {"storeCode": snap.store_code, "orderType": ORDER_TYPE_DINEIN, "beType": BETYPE_DINEIN},
            snap, "门店券",
        )
        if isinstance(coupons, list):
            for c in coupons:
                snap.coupons.append(Coupon(
                    coupon_id=str(c.get("couponId", "")),
                    coupon_code=str(c.get("couponCode", "")),
                    title=str(c.get("title", "")),
                    product_codes=[str(p.get("productCode", "")) for p in (c.get("products") or [])],
                    valid_text=str(c.get("tradeDateTime", "")),
                ))

    orders = await _call(client, "order-list", {}, snap, "历史订单")
    if isinstance(orders, dict) and isinstance(orders.get("list"), list):
        for o in orders["list"]:
            items: list[str] = []
            for p in o.get("orderProductList", []):
                qty = p.get("quantity", 1)
                name = str(p.get("productName", ""))
                items.append(f"{name}x{qty}" if qty and qty > 1 else name)
                for sub in p.get("comboItemList", []) or []:
                    items.append(str(sub.get("name", "")))
            snap.history.append(HistoryOrder(
                date=str(o.get("createTime", ""))[:10],
                items=[i for i in items if i],
                total=_to_float(o.get("realTotalAmount")),
            ))

    nutr = await _call(client, "list-nutrition-foods", {}, snap, "营养数据")
    if isinstance(nutr, str):
        snap.nutrition = parse_nutrition_table(nutr)

    account = await _call(client, "query-my-account", {}, snap, "积分")
    if isinstance(account, dict):
        snap.points = _to_float(account.get("availablePoint"))

    snap.history.sort(key=lambda h: h.date, reverse=True)
    return snap


def parse_nutrition_table(text: str) -> dict[str, dict[str, float]]:
    """解析 "[N]{productName,...,energyKcal,protein,...}:
      猪柳麦满分,null,1288,308,16,16,24,781,213" 表格文本。"""
    m = re.match(r"\[\d+\]\{([^}]*)\}:\s*\n", text.strip())
    if not m:
        return {}
    cols = [c.strip() for c in m.group(1).split(",")]
    out: dict[str, dict[str, float]] = {}
    for line in text.strip().splitlines()[1:]:
        parts = [p.strip() for p in line.lstrip().rstrip(",").split(",")]
        if len(parts) < len(cols):
            continue
        row = dict(zip(cols, parts))
        name = row.get("productName", "")
        if not name:
            continue
        try:
            out[name] = {
                "kcal": _to_float(row.get("energyKcal")),
                "protein": _to_float(row.get("protein")),
                "fat": _to_float(row.get("fat")),
                "carbs": _to_float(row.get("carbohydrate")),
                "sodium": _to_float(row.get("sodium")),
            }
        except (TypeError, ValueError):
            continue
    return out


def _tags_of(category: str, name: str) -> list[str]:
    """菜单 tags 缺失时的兜底分类标签（按分类名/品名关键词）。"""
    tags = []
    for kw, tag in (("堡", "汉堡"), ("薯", "小食"), ("鸡", "鸡肉"), ("可乐", "饮料"), ("咖啡", "饮料"), ("茶", "饮料"), ("沙拉", "轻食"), ("奶", "饮料")):
        if kw in name or kw in category:
            tags.append(tag)
    return tags


def _to_float(v) -> float:
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


async def price_check(client: McpClientBase, store_code: str, items: list[MenuItem], coupon: Coupon | None) -> dict | None:
    """dry-run 的"订单草稿"：调 calculate-price 真实算价（纯计算，无副作用）。

    返回 {origin, pay, discount, product_list, take_ways}（金额为元）；
    take_ways 来自 data.takeWayList，是 create-order 必填的取餐方式来源。
    失败返回 None。
    """
    if not store_code:
        return None
    args_items = [{"productCode": it.code, "quantity": 1} for it in items]
    if coupon is not None:
        for it in args_items:
            if it["productCode"] in coupon.product_codes:
                it["couponId"] = coupon.coupon_id
                it["couponCode"] = coupon.coupon_code
    r = await client.call_tool("calculate-price", {
        "storeCode": store_code, "orderType": ORDER_TYPE_DINEIN, "beType": BETYPE_DINEIN,
        "items": args_items,
    })
    payload = _payload(r)
    if not isinstance(payload, dict) or "price" not in payload:
        return None
    fen = lambda v: _to_float(v) / 100  # 上游金额单位为分
    return {
        "origin": fen(payload.get("originalPrice")),
        "pay": fen(payload.get("price")),
        "discount": fen(payload.get("discount")),
        "product_list": payload.get("productList", []),
        "take_ways": payload.get("takeWayList", []) or [],
    }
