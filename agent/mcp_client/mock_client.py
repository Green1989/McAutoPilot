"""离线 Mock 客户端：无 Token 时的开发/演示/CI 数据源。

工具名与返回结构**逐字段对齐真实服务**（2026-10-14 实测探针结果），
因此 mock 与 live 走完全相同的归一化管线——mock 测过即 live 可用。
数据来自 agent/mcp_client/fixtures/（价格与营养为演示用近似值）。
"""
from __future__ import annotations

import json
from pathlib import Path

from .base import McpClientBase, ToolResult, extract_json

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _load(name: str):
    with open(FIXTURE_DIR / f"{name}.json", encoding="utf-8") as f:
        return json.load(f)


def _ok(data) -> str:
    return json.dumps({"success": True, "code": 200, "message": "请求成功", "data": data}, ensure_ascii=False)


MOCK_STORE_CODE = "1000001"

_MOCK_TOOLS: list[dict] = [
    {"name": "query-nearby-stores", "description": "查询用户可点餐门店", "inputSchema": {}},
    {"name": "query-meals", "description": "餐品列表, 支持到店自提(orderType=1)和外送(orderType=2)两种场景", "inputSchema": {}},
    {"name": "query-store-coupons", "description": "查询【指定门店+订单类型】下可使用的优惠券", "inputSchema": {}},
    {"name": "order-list", "description": "查询麦当劳历史订单", "inputSchema": {}},
    {"name": "list-nutrition-foods", "description": "获取麦当劳常见餐品的营养成分数据", "inputSchema": {}},
    {"name": "query-my-account", "description": "查询用户积分账户详情", "inputSchema": {}},
    {"name": "calculate-price", "description": "计算商品的价格（含优惠）", "inputSchema": {}},
    {"name": "auto-bind-coupons", "description": "自动领取麦麦省所有当前可用的麦当劳优惠券", "inputSchema": {}},
    {"name": "create-order", "description": "创建麦当劳订单（mock 下永远不触发）", "inputSchema": {}},
]


class MockMcpClient(McpClientBase):
    async def list_tools(self) -> list[dict]:
        return [dict(t) for t in _MOCK_TOOLS]

    async def call_tool(self, name: str, arguments: dict | None = None) -> ToolResult:
        arguments = arguments or {}
        result = ToolResult(name=name)
        menu = _load("menu")

        if name == "query-nearby-stores":
            data = [{"storeName": "麦当劳模拟体验馆餐厅", "storeCode": MOCK_STORE_CODE, "distance": 0}]
            result.text = _ok(data)
        elif name == "query-meals":
            categories: list[dict] = []
            meals: dict[str, dict] = {}
            for item in menu:
                cat = item["category"]
                target = next((c for c in categories if c["name"] == cat), None)
                if target is None:
                    target = {"name": cat, "meals": []}
                    categories.append(target)
                target["meals"].append({"code": item["productCode"], "tags": item.get("tags", [])})
                meals[item["productCode"]] = {
                    "name": item["name"],
                    "image": "",
                    "currentPrice": str(item["price"]),
                    "originalPrice": str(round(item["price"] * 1.35, 1)),
                    "canWithOrder": False,
                }
            result.text = _ok({"categories": categories, "meals": meals, "frequent": {}})
        elif name == "query-store-coupons":
            data = [
                {
                    "title": c["title"],
                    "couponId": c["couponId"],
                    "couponCode": f"MOCK{c['couponId']}",
                    "tradeDateTime": f"2026-10-01 00:00:00-{c['expiry']} 23:59:59",
                    "products": [
                        {"productCode": code, "productName": next((i["name"] for i in menu if i["productCode"] == code), code)}
                        for code in c["applicable"] if code != "*"
                    ],
                    "promotionId": c["couponId"],
                }
                for c in _load("coupons")
                if c.get("applicable") not in (["*"], None)
            ]
            result.text = _ok(data)
        elif name == "order-list":
            data = {
                "list": [
                    {
                        "orderId": o["orderId"],
                        "createTime": o["date"] + " 12:0" + str(i % 10) + ":00",
                        "storeName": "麦当劳模拟体验馆餐厅",
                        "orderStatus": "订单已完成",
                        "orderProductList": [
                            {
                                "productCode": it["productCode"],
                                "productName": it["name"],
                                "quantity": it.get("qty", 1),
                                "comboItemList": [],
                            }
                            for it in o["items"]
                        ],
                        "realTotalAmount": str(o["total"]),
                    }
                    for i, o in enumerate(_load("orders"))
                ]
            }
            result.text = _ok(data)
        elif name == "list-nutrition-foods":
            # 真实服务返回 "[N]{列名}:\n  CSV行" 的表格文本，mock 按同格式构造
            cols = "productName,nutritionDescription,energyKj,energyKcal,protein,fat,carbohydrate,sodium,calcium"
            rows = [
                f"  {i['name']},null,0,{i['kcal']},{i['protein_g']},{i['fat_g']},{i['carbs_g']},{i['sodium_mg']},0"
                for i in menu
            ]
            result.text = _ok(f"[{len(menu)}]{{{cols}}}:\n" + "\n".join(rows))
        elif name == "query-my-account":
            result.text = _ok({"availablePoint": "4820", "currency": "麦享会积分", "expiredPoint": "0", "usedPoint": "73"})
        elif name == "calculate-price":
            items = arguments.get("items", [])
            by_code = {i["productCode"]: i for i in menu}
            product_list, product_price = [], 0
            for it in items:
                info = by_code.get(it.get("productCode", ""))
                qty = it.get("quantity", 1)
                sub = round(info["price"] * qty * 100) if info else 0
                product_price += sub
                product_list.append({"productCode": it.get("productCode"), "productName": info["name"] if info else "?", "quantity": qty, "originalSubtotal": sub, "subtotal": sub})
            data = {
                "productOriginalPrice": product_price,
                "productPrice": product_price,
                "originalPrice": product_price,
                "discount": 0,
                "price": product_price,
                "productList": product_list,
                "takeWayList": [{"code": "eat-in", "title": "堂食"}, {"code": "take-in-store", "title": "外带"}],
            }
            result.text = _ok(data)
        else:
            result.is_error = True
            result.text = f"未知工具: {name}"
        if not result.is_error:
            result.data = extract_json(result.text)
        return result
