"""求解器引擎 v2 的约束、可解释性与兼容性测试（纯离线，不碰网络）。"""
from datetime import date, timedelta

from agent.brain import SODIUM_HARD_CAP, decide
from agent.perceive import Coupon, HistoryOrder, MenuItem, Snapshot


def _item(code, name, price, cat):
    return MenuItem(code=code, name=name, price=price, category=cat)


def _base_snapshot():
    menu = [
        _item("M1", "巨无霸", 25.5, "汉堡"),
        _item("M2", "板烧鸡腿堡", 23.0, "汉堡"),
        _item("M3", "麦辣鸡腿堡", 22.5, "汉堡"),
        _item("S1", "中薯条", 14.5, "小食"),
        _item("S2", "麦乐鸡", 13.5, "小食"),
        _item("D1", "可口可乐", 9.5, "饮料"),
    ]
    nutrition = {
        "巨无霸": {"kcal": 550, "protein": 26, "fat": 28, "carbs": 45, "sodium": 1010},
        "板烧鸡腿堡": {"kcal": 460, "protein": 25, "fat": 19, "carbs": 42, "sodium": 830},
        "麦辣鸡腿堡": {"kcal": 570, "protein": 24, "fat": 30, "carbs": 49, "sodium": 890},
        "中薯条": {"kcal": 330, "protein": 4, "fat": 16, "carbs": 42, "sodium": 210},
        "麦乐鸡": {"kcal": 250, "protein": 13, "fat": 14, "carbs": 17, "sodium": 480},
        "可口可乐": {"kcal": 150, "protein": 0, "fat": 0, "carbs": 39, "sodium": 0},
    }
    return Snapshot(store_code="1000001", menu=menu, nutrition=nutrition)


def test_v2_budget_is_hard_constraint():
    d = decide(_base_snapshot(), budget=25.0, engine="v2")
    est_pay = d.menu_price - d.est_saving
    assert est_pay <= 25.0 + 1e-9


def test_v2_sodium_hard_cap_filters():
    snap = _base_snapshot()
    salty = _item("M9", "双层吉士堡", 26.0, "汉堡")
    snap.menu.append(salty)
    snap.nutrition["双层吉士堡"] = {"kcal": 600, "protein": 27, "fat": 30, "carbs": 46, "sodium": SODIUM_HARD_CAP + 100}
    d = decide(snap, budget=40.0, engine="v2")
    names = [it.name for it in d.items]
    assert "双层吉士堡" not in names


def test_v2_coupon_draws_choice():
    snap = _base_snapshot()
    d_plain = decide(snap, budget=40.0, engine="v2")
    assert d_plain.coupon is None

    snap.coupons = [Coupon(
        coupon_id="C1", coupon_code="CC1", title="板烧鸡腿堡买一送一",
        product_codes=["M2"], valid_text="2026-10-01 00:00:00-2026-10-20 23:59:59",
    )]
    d = decide(snap, budget=40.0, engine="v2")
    assert d.coupon is not None and "板烧鸡腿堡" in [it.name for it in d.items]
    assert d.est_saving > 0


def test_v2_repetition_pushes_variety():
    snap = _base_snapshot()
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    snap.history = [HistoryOrder(date=yesterday, items=["板烧鸡腿堡"], total=23.0)]
    d = decide(snap, budget=40.0, engine="v2")
    assert "板烧鸡腿堡" not in [it.name for it in d.items]


def test_v2_breakdown_explainable_with_numbers():
    d = decide(_base_snapshot(), budget=40.0, engine="v2")
    assert d.engine == "v2"
    assert d.breakdown, "v2 决策必须带分数构成"
    for label, contrib, detail in d.breakdown:
        assert label
        assert any(ch.isdigit() for ch in detail), f"明细缺数字: {label} -> {detail}"
    assert sum(c for _, c, _ in d.breakdown) == d.score


def test_v2_deterministic():
    snap = _base_snapshot()
    d1 = decide(snap, budget=40.0, engine="v2")
    d2 = decide(snap, budget=40.0, engine="v2")
    assert [it.code for it in d1.items] == [it.code for it in d2.items]
    assert d1.score == d2.score


def test_v1_engine_unchanged():
    d = decide(_base_snapshot(), budget=40.0, engine="v1")
    assert d.engine == "v1"
    assert d.breakdown == []
    assert d.reasons


def test_unknown_engine_falls_back_to_v1():
    d = decide(_base_snapshot(), budget=40.0, engine="bogus")
    assert d.engine == "v1"
