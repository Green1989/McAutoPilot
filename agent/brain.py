"""决策引擎：v1 规则打分 / v2 求解器（硬约束 + 加权目标）。

设计目标不是"最优解"而是"可解释的好决定"——每个分数项都会产出
带真实数字的理由，最终进 DECISIONS.md。

- v1：主食×小食×饮料枚举 + 6 条规则打分（券/蛋白/热量/钠/重复/性价比）；
- v2：同一枚举空间上先过**硬约束**（预算、钠、热量上限），再按**公开权重的
  归一化目标**求最大值，并输出逐项分数构成（label + 贡献 + 带数字的明细）。
  通过 MCD_ENGINE=v2 启用，默认仍是 v1（渐进发布，出问题改环境变量即回滚）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

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

# ---- 求解器 v2 参数 ----
SODIUM_HARD_CAP = 1500.0   # 钠硬上限（mg）：超过直接不可行
KCAL_HARD_CAP = 1200.0     # 热量硬上限（kcal）
# 目标权重（公开、可审计；每项归一化到 [0,1]，理论满分 ≈ 10.1）
WEIGHTS = {
    "protein": 2.5,      # 蛋白充足
    "kcal": 1.5,         # 热量甜区
    "sodium": 0.8,       # 钠余量（离上限越远越好）
    "coupon": 2.0,       # 券价值
    "freshness": 1.5,    # 换口味（近 14 天没吃过）
    "completeness": 0.8, # 品类完整（主食+小食+饮料）
    "value": 1.0,        # 性价比（蛋白/元）
}


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
    engine: str = "v1"
    # v2 求解器的逐项分数构成：(标签, 贡献分, 带数字的明细)，渲染进日记
    breakdown: list[tuple[str, float, str]] = field(default_factory=list)


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


def decide(snap: Snapshot, budget: float = 40.0, days_history: int = 14, engine: str = "v1") -> Decision:
    """决策入口。engine: v1 = 规则打分（默认），v2 = 求解器；非法值回落 v1。"""
    if engine == "v2":
        return decide_v2(snap, budget, days_history)
    return decide_v1(snap, budget, days_history)


def _candidates(snap: Snapshot, budget: float):
    """枚举空间：主食 × (小食∪∅) × (饮料∪∅)，套餐自带小食饮料的不叠加。"""
    mains = [m for m in snap.menu if _is_main(m) and 5 <= m.price <= budget][:MAX_MAINS]
    sides = [m for m in snap.menu if _is_side(m)][:MAX_SIDES]
    drinks = [m for m in snap.menu if _is_drink(m)][:MAX_DRINKS]
    if not mains:  # 兜底：关键词全落空时按价格取较贵的一半当主食
        priced = sorted(snap.menu, key=lambda m: -m.price)
        mains = priced[: max(1, len(priced) // 3)]
    for main in mains:
        for side in [None, *sides]:
            for drink in [None, *drinks]:
                if (side or drink) and sum(1 for x in (side, drink) if x) > 1 and main.name.endswith("套餐"):
                    continue
                yield [x for x in (main, side, drink) if x]


def decide_v1(snap: Snapshot, budget: float = 40.0, days_history: int = 14) -> Decision:
    if not snap.menu:
        raise ValueError("菜单为空，无法决策")

    recent_names = {name for h in snap.history[:2] for name in h.items} if snap.history else set()
    fortnight_names = {name for h in snap.history[:days_history] for name in h.items} if snap.history else set()

    best: Decision | None = None
    for combo in _candidates(snap, budget):
        d = _score_combo(combo, snap, budget, recent_names, fortnight_names)
        if d is not None and (best is None or d.score > best.score or (d.score == best.score and d.menu_price < best.menu_price)):
            best = d
    if best is None:
        mains = [m for m in snap.menu if _is_main(m) and 5 <= m.price <= budget]
        raise ValueError(f"预算 ¥{budget} 内无可行组合（最便宜主食 ¥{min(m.price for m in mains)}）")
    return best


# ---- 求解器 v2 ----

def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _days_since_eaten(item_name: str, history: list[HistoryOrder]) -> int | None:
    """该商品距上次出现在历史订单的天数；从未吃过返回 None。history 需按日期倒序。"""
    today = date.today()
    for h in history:
        for it in h.items:
            base = it.split("x")[0]
            if not base:
                continue
            if base in item_name or item_name in base:
                try:
                    return (today - date.fromisoformat(h.date)).days
                except ValueError:
                    return None
    return None


def _freshness(item_name: str, history: list[HistoryOrder]) -> float:
    """新鲜度 ∈ [0,1]：近 2 天吃过 = 0，≥14 天没吃或没吃过 = 1，中间线性过渡。"""
    days = _days_since_eaten(item_name, history)
    if days is None or days >= 14:
        return 1.0
    if days <= 2:
        return 0.0
    return round(0.3 + 0.7 * (days - 2) / 12.0, 4)


def _code_num(code: str) -> int:
    digits = "".join(ch for ch in code if ch.isdigit())
    return int(digits) if digits else 0


def decide_v2(snap: Snapshot, budget: float = 40.0, days_history: int = 14) -> Decision:
    if not snap.menu:
        raise ValueError("菜单为空，无法决策")

    history = snap.history[:days_history]
    best: Decision | None = None
    best_key: tuple | None = None
    for combo in _candidates(snap, budget):
        d = _solve_combo(combo, snap, budget, history)
        if d is None:
            continue
        # 决胜规则：分数 → 价格低者 → 件数多者 → 编号序（确定性输出）
        key = (d.score, -d.menu_price, len(d.items), tuple(-_code_num(it.code) for it in d.items))
        if best_key is None or key > best_key:
            best, best_key = d, key
    if best is None:
        raise ValueError(f"预算 ¥{budget} 内无可行组合（硬约束过滤后为空）")
    best.engine = "v2"
    return best


def _solve_combo(
    combo: list[MenuItem],
    snap: Snapshot,
    budget: float,
    history: list[HistoryOrder],
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

    # 硬约束（不可行直接丢弃）
    if est_pay > budget:
        return None

    # 营养合计（匹配同 v1）
    nutr_sum = {"kcal": 0.0, "protein": 0.0, "fat": 0.0, "carbs": 0.0, "sodium": 0.0}
    matched = True
    for it in combo:
        n = _match_nutrition(it.name, snap.nutrition)
        if n is None:
            matched = False
            continue
        for k in nutr_sum:
            nutr_sum[k] += n.get(k, 0.0)
    if matched:
        if nutr_sum["sodium"] > SODIUM_HARD_CAP:
            return None
        if nutr_sum["kcal"] > KCAL_HARD_CAP:
            return None

    # 归一化目标项（[0,1] × 公开权重）；营养未匹配时四项取中性 0.5
    protein, kcal, sodium = nutr_sum["protein"], nutr_sum["kcal"], nutr_sum["sodium"]
    if matched:
        s_protein = _clamp(protein / PROTEIN_TARGET)
        if KCAL_RANGE[0] <= kcal <= KCAL_RANGE[1]:
            s_kcal = 1.0
        elif kcal < KCAL_RANGE[0]:
            s_kcal = _clamp(1.0 - (KCAL_RANGE[0] - kcal) / 300)
        else:
            s_kcal = _clamp(1.0 - (kcal - KCAL_RANGE[1]) / 300)
        s_sodium = _clamp(1.0 - sodium / SODIUM_CAP)
        ppy = protein / est_pay if est_pay > 0 else 0.0
        s_value = _clamp(ppy / 2.0)
    else:
        s_protein = s_kcal = s_sodium = s_value = 0.5
        ppy = 0.0
    s_coupon = _clamp(est_saving / max(budget * 0.5, 1.0))
    freshness_per_item = [_freshness(it.name, history) for it in combo]
    s_freshness = sum(freshness_per_item) / len(freshness_per_item)
    s_completeness = {1: 0.3, 2: 0.6, 3: 1.0}[min(len(combo), 3)]

    W = WEIGHTS
    score = round(
        W["protein"] * s_protein + W["kcal"] * s_kcal + W["sodium"] * s_sodium
        + W["coupon"] * s_coupon + W["freshness"] * s_freshness
        + W["completeness"] * s_completeness + W["value"] * s_value,
        2,
    )

    # 分数构成（每条明细带真实数字）
    breakdown = [
        ("券价值", round(W["coupon"] * s_coupon, 2),
         f"命中「{coupon.title}」估值省 ¥{est_saving}" if coupon else "未命中券（本组合匹配 0 张）"),
        ("蛋白质", round(W["protein"] * s_protein, 2),
         f"蛋白质 {protein:.0f}g / 目标 {PROTEIN_TARGET:.0f}g" if matched else "营养未匹配，中性 0.5"),
        ("热量", round(W["kcal"] * s_kcal, 2),
         f"热量 {kcal:.0f}kcal（甜区 {KCAL_RANGE[0]:.0f}-{KCAL_RANGE[1]:.0f}）" if matched else "营养未匹配，中性 0.5"),
        ("钠余量", round(W["sodium"] * s_sodium, 2),
         f"钠 {sodium:.0f}mg / 上限 {SODIUM_CAP:.0f}mg" if matched else "营养未匹配，中性 0.5"),
        ("新鲜度", round(W["freshness"] * s_freshness, 2),
         f"组合新鲜度 {s_freshness * 100:.0f}%（近{14}天口径）"),
        ("品类", round(W["completeness"] * s_completeness, 2),
         f"{len(combo)} 件套（主食+小食+饮料 越全越好）"),
        ("性价比", round(W["value"] * s_value, 2),
         f"{ppy:.2f}g 蛋白/元（2.0 满分线）" if matched else "营养未匹配，中性 0.5"),
    ]

    # 人话理由（保持 v1 的日记文风，数字说话）
    reasons: list[str] = []
    if coupon is not None:
        expire_dates = re.findall(r"\d{4}-\d{2}-\d{2}", coupon.valid_text)
        expiry = f"{expire_dates[-1]} 到期" if expire_dates else "有效期见券详情"
        saving_txt = f"约 ¥{est_saving}" if est_saving > 0 else "以实测算价为准"
        reasons.append(f"命中优惠券「{coupon.title}」（{expiry}，不用就浪费），省 {saving_txt}")
    if matched:
        if protein >= PROTEIN_TARGET:
            reasons.append(f"蛋白质 {protein:.0f}g 达标（目标 ≥{PROTEIN_TARGET:.0f}g），下午写码不困")
        if KCAL_RANGE[0] <= kcal <= KCAL_RANGE[1]:
            reasons.append(f"热量 {kcal:.0f}kcal 落在 {KCAL_RANGE[0]:.0f}-{KCAL_RANGE[1]:.0f} 的午餐甜区")
        if sodium > SODIUM_CAP:
            reasons.append(f"钠 {sodium:.0f}mg 超单餐参考 {SODIUM_CAP:.0f}mg（未破 {SODIUM_HARD_CAP:.0f} 硬上限，提醒今晚吃清淡点）")
        if ppy >= 1.0:
            reasons.append(f"性价比 {ppy:.2f}g 蛋白/元，高于 1.0 的及格线")
    else:
        reasons.append("营养库未能完全匹配该组合，四项营养得分按中性 0.5 处理")
    repeats = [it.name for it, f in zip(combo, freshness_per_item) if f == 0.0]
    if repeats:
        reasons.append(f"「{'、'.join(repeats)}」最近刚吃过（新鲜度记 0），本次入选是其他项分数压过了换口味偏好")

    return Decision(
        items=combo, coupon=coupon, menu_price=menu_price, est_saving=est_saving,
        score=score, reasons=reasons or ["各项中规中矩，价格在预算内（这已经打败了选择困难）"],
        nutrition=nutr_sum if matched else None, nutrition_matched=matched,
        engine="v2", breakdown=breakdown,
    )


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
