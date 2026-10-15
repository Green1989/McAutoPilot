"""执行链三重护栏测试：全部走 MockMcpClient，绝不触发真实写操作。"""
import asyncio
from datetime import date, timedelta

from agent.brain import Decision
from agent.config import Settings, bj_today
from agent.executor import claim_coupons, execute_order
from agent.mcp_client.mock_client import MockMcpClient
from agent.perceive import Coupon, MenuItem


def _settings(**overrides) -> Settings:
    base = dict(
        mcp_url="https://mock", mcp_token="",
        dry_run=False, budget=40.0,
        confirm_order=bj_today(),
    )
    base.update(overrides)
    return Settings(**base)


def _decision() -> Decision:
    return Decision(
        items=[
            MenuItem(code="M1003", name="板烧鸡腿堡", price=23.0, category="汉堡"),
            MenuItem(code="S1001", name="中薯条", price=14.5, category="小食"),
        ],
        coupon=Coupon(
            coupon_id="C2401", coupon_code="MOCKC2401",
            title="板烧鸡腿堡买一送一", product_codes=["M1003"],
        ),
        menu_price=37.5,
    )


PRICE_OK = {
    "origin": 37.5, "pay": 25.5, "discount": 12.0,
    "take_ways": [{"code": "eat-in", "title": "堂食"}],
    "product_list": [],
}


def _run(coro):
    return asyncio.run(coro)


def test_guard_dry_run_blocks():
    r = _run(execute_order(MockMcpClient(), _settings(dry_run=True), "1000001", _decision(), PRICE_OK))
    assert r.status == "skipped"
    assert "dry-run" in r.reason


def test_guard_confirm_token_must_match_today():
    r = _run(execute_order(MockMcpClient(), _settings(confirm_order=""), "1000001", _decision(), PRICE_OK))
    assert r.status == "skipped" and "二次确认" in r.reason

    stale = (date.fromisoformat(bj_today()) - timedelta(days=1)).isoformat()
    r = _run(execute_order(MockMcpClient(), _settings(confirm_order=stale), "1000001", _decision(), PRICE_OK))
    assert r.status == "skipped" and "二次确认" in r.reason


def test_guard_requires_real_price():
    r = _run(execute_order(MockMcpClient(), _settings(), "1000001", _decision(), None))
    assert r.status == "skipped" and "算价" in r.reason


def test_guard_budget_hard_cap():
    pricey = dict(PRICE_OK, pay=45.5)
    r = _run(execute_order(MockMcpClient(), _settings(), "1000001", _decision(), pricey))
    assert r.status == "skipped" and "超预算" in r.reason


def test_guard_missing_take_way_aborts():
    no_way = dict(PRICE_OK, take_ways=[])
    r = _run(execute_order(MockMcpClient(), _settings(), "1000001", _decision(), no_way))
    assert r.status == "aborted" and "takeWayList" in r.reason


def test_create_order_happy_path_mock():
    r = _run(execute_order(MockMcpClient(), _settings(), "1000001", _decision(), PRICE_OK))
    assert r.status == "created"
    assert r.order_id.startswith("MOCK-")
    assert r.pay_url.startswith("https://mock.mcd.cn/pay/")


def test_claim_coupons_mock():
    count, note = _run(claim_coupons(MockMcpClient()))
    assert count == 3
    assert note
