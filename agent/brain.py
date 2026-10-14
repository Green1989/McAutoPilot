"""决策引擎 v1：规则打分。

设计目标不是"最优解"而是"可解释的好决定"——每个分数项都会产出
带真实数字的理由，最终进 DECISIONS.md。求解器版优化留 v2。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .perceive import Coupon, HistoryOrder, MenuItem, Snapshot

# 午餐营养目标（单人单餐）
KCAL_IDEAL = 650.0
KCAL_RANGE = (480.0, 820.0)
PROTEIN_TARGET = 30.0
SODIUM_CAP = 1100.0

MAIN_PAT = re.compile(r"堡|卷|麦满分|三明治|饭|满碗|套餐|巨无霸")
SIDE_PAT = re.compile(r"薯|麦乐鸡|鸡块|派|玉米|沙拉|蛋挞|鸡翅|鸡排|小食")
DRINK_PAT = re.compile(r"可乐|雪碧|茶|咖啡|奶|矿泉水|汁|柠檬|圣代|圆筒|阳光橙")

MAX_MAINS = 30
MAX_SIDES = 10
MAX_DRINKS = 8


@dataclass
class Decision:
    items: list[MenuItem] = field(default_factory=list)
    coupon: Coupon | None = None
    menu_price: float = 0.0           # 菜单价合计
    est_saving: float = 0.0           # 券优惠估值（真实值以 calculate-price 为准）
    score: float = 0.0
    reasons: list[str] = field(default_factory=list)
    nutrition: dict[str, float] | None = None
    nutrition_matched: bool = False


def _is_main(m: MenuItem) -> bool:
    return bool(MAIN_PAT.search(m.name)) and not DRINK_PAT.search(m.name)


def _is_side(m: MenuItem) -> bool:
    return bool(SIDE_PAT.search(m.name)) and not MAIN_PAT.search(m.name)


def _is_drink(m: MenuItem) -> bool:
    return bool(DRINK_PAT.search(m.name)) and not MAIN_PAT.search(m.name)


def _match_nutrition(name: str, nutrition: dict[str, dict]) -> dict | None:
    if name in nutrition:
        return nutrition[name]
    best = None
    for nutr_name, values in nutrition.items():
        if len(nutr_name) >= 2 and (nutr_name in name or name in nutr_name):
            if best is None or len(nutr_name) > len(best):
                best = nutr_name
    return nutrition.get(best) if best else None


def _coupon_est_saving(coupon: Coupon, combo: list[MenuItem]) -> float:
    """券优惠估值：买一送一≈半价，立减N 元按 N；其余 0（真实值走算价）。"""
    coupon_price = sum(it.price for it in combo if it.code in coupon.product_codes)
    if "买一送一" in coupon.title or "BOGO" in coupon.title:
        return round(coupon_price / 2, 1)
    m = re.search(r"减\s*(\d+(?:\.\d+)?)", coupon.title)
    if m:
        return min(float(m.group(1)), coupon_price)
    m = re.search(r"半价", coupon.title)
    if m:
        return round(coupon_price / 2, 1)
    return 0.0


def decide(snap: Snapshot, budget: float = 40.0, days_history: int = 14) -> Decision:
    if not snap.menu:
        raise ValueError("菜单为空，无法决策")

    mains = [m for m in snap.menu if _is_main(m) and 5 <= m.price <= budget][:MAX_MAINS]
    sides = [m for m in snap.menu if _is_side(m)][:MAX_SIDES]
    drinks = [m for m in snap.menu if _is_drink(m)][:MAX_DRINKS]
    if not mains:  # 兜底：关键词全落空时按价格取较贵的一半当主食
        priced = sorted(snap.menu, key=lambda m: -m.price)
        mains = priced[: max(1, len(priced) // 3)]

    recent_names = {name for h in snap.history[:2] for name in h.items} if snap.history else set()
    fortnight_names = {name for h in snap.history[:days_history] for name in h.items} if snap.history else set()

    best: Decision | None = None
    for main in mains:
        for side in [None, *sides]:
            for drink in [None, *drinks]:
                if (side or drink) and sum(1 for x in (side, drink) if x) > 1 and main.name.endswith("套餐"):
                    continue  # 套餐自带小食饮料，不叠加
                combo = [x for x in (main, side, drink) if x]
                d = _score_combo(combo, snap, budget, recent_names, fortnight_names)
                if d is not None and (best is None or d.score > best.score or (d.score == best.score and d.menu_price < best.menu_price)):
                    best = d
    if best is None:
        raise ValueError(f"预算 ¥{budget} 内无可行组合（最便宜主食 ¥{min(m.price for m in mains)}）")
    return best


def _score_combo(
    combo: list[MenuItem],
    snap: Snapshot,
    budget: float,
    recent_names: set[str],
    fortnight_names: set[str],
) -> Decision | None:
    menu_price = round(sum(it.price for it in combo), 1)

    # 券匹配（取估值最高的一张）
    coupon, est_saving = None, 0.0
    for c in snap.coupons:
        if any(it.code in c.product_codes for it in combo):
            s = _coupon_est_saving(c, combo)
            if s >= est_saving:
                coupon, est_saving = c, s
    est_pay = round(menu_price - est_saving, 1)
    if est_pay > budget:
        return None

    reasons: list[str] = []
    score = 0.0

    # 1. 券
    if coupon is not None:
        score += 2.0
        saving_txt = f"约 ¥{est_saving}" if est_saving > 0 else "以实测算价为准"
        expire_dates = re.findall(r"\d{4}-\d{2}-\d{2}", coupon.valid_text)
        expiry = f"{expire_dates[-1]} 到期" if expire_dates else "有效期见券详情"
        reasons.append(f"命中优惠券「{coupon.title}」（{expiry}，不用就浪费），省 {saving_txt}")

    # 2. 营养
    nutr_sum = {"kcal": 0.0, "protein": 0.0, "fat": 0.0, "carbs": 0.0, "sodium": 0.0}
    matched = True
    for it in combo:
        n = _match_nutrition(it.name, snap.nutrition)
        if n is None:
            matched = False
            continue
        for k in nutr_sum:
            nutr_sum[k] += n.get(k, 0.0)
    d = Decision(items=combo, coupon=coupon, menu_price=menu_price, est_saving=est_saving, nutrition=nutr_sum if matched else None, nutrition_matched=matched)

    if matched:
        protein, kcal, sodium = nutr_sum["protein"], nutr_sum["kcal"], nutr_sum["sodium"]
        score += min(protein / PROTEIN_TARGET, 1.25) * 2.0
        if protein >= PROTEIN_TARGET:
            reasons.append(f"蛋白质 {protein:.0f}g 达标（目标 ≥{PROTEIN_TARGET:.0f}g），下午写码不困")
        if KCAL_RANGE[0] <= kcal <= KCAL_RANGE[1]:
            score += 1.0
        elif kcal < KCAL_RANGE[0]:
            score += max(0.0, 1.0 - (KCAL_RANGE[0] - kcal) / 300)
        else:
            score += max(0.0, 1.0 - (kcal - KCAL_RANGE[1]) / 300)
        if sodium <= SODIUM_CAP:
            score += 0.5
        else:
            penalty = min((sodium - SODIUM_CAP) / 300, 1.5)
            score -= penalty
            reasons.append(f"钠 {sodium:.0f}mg 超单餐上限 {SODIUM_CAP:.0f}mg，扣 {penalty:.1f} 分（提醒：今晚吃清淡点）")
        if KCAL_RANGE[0] <= kcal <= KCAL_RANGE[1] and PROTEIN_TARGET <= protein and sodium > SODIUM_CAP * 0.8:
            reasons.append(f"热量 {kcal:.0f}kcal 落在 {KCAL_RANGE[0]:.0f}-{KCAL_RANGE[1]:.0f} 的午餐甜区")
    else:
        reasons.append("营养库未能完全匹配该组合，按中性评分（热量/蛋白未知不加分不扣分）")

    # 3. 换口味
    repeats = [it.name for it in combo if it.name in recent_names or any(it.name in rn or rn in it.name for rn in recent_names)]
    if repeats:
        penalty = min(1.5 * len(repeats), 3.0)
        score -= penalty
        reasons.append(f"「{'、'.join(repeats)}」最近刚吃过，连吃会腻，扣 {penalty:.1f} 分")
    fresh = [it.name for it in combo if it.name not in fortnight_names and not any(it.name in fn or fn in it.name for fn in fortnight_names)]
    if fresh:
        score += min(0.3 * len(fresh), 0.6)

    # 4. 性价比（蛋白/元）
    if matched and est_pay > 0:
        ppy = nutr_sum["protein"] / est_pay
        if ppy >= 1.0:
            score += 0.5
            reasons.append(f"性价比 {ppy:.2f}g 蛋白/元，高于 1.0 的及格线")

    d.score = round(score, 2)
    d.reasons = reasons or ["各项中规中矩，价格在预算内（这已经打败了选择困难）"]
    return d
