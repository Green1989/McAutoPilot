"""流水线加固三件套测试：同日幂等 / 决策记忆 / 北京时间（纯离线，不碰网络）。"""
import asyncio
import json
from datetime import date, timedelta
from pathlib import Path

from agent import main as autopilot
from agent import report
from agent.brain import Decision, decide
from agent.config import BJ_TZ, Settings, bj_now, bj_today
from agent.memory import DecisionMemory, parse_diary
from agent.perceive import HistoryOrder, MenuItem, Snapshot

# 模拟真实 DECISIONS.md 的条目形态（含 Day 0 占位、决策失败条目、多品组合）。
# 日期取远离"今天"的历史段，避免与同日覆盖逻辑相撞。
DIARY_SAMPLE = """# DECISIONS.md — AI 吃饭日记

<!-- 格式说明注释块，不会被替换 -->

## Day 3 · 2026-09-03 · 周四

**今日决策**：板烧鸡腿堡 + 麦乐鸡 —— 实测算价 ¥25.0（原价 ¥30.0，优惠 ¥5.0）

**为什么**：
1. 蛋白质 38g 达标（目标 ≥30g），下午写码不困

<sub>score 5.01 · 由 McAutoPilot 求解器引擎 v2 于 10:02（北京时间）自动生成</sub>

---

## Day 2 · 2026-09-02 · 周三

**今日决策**：芝士安格斯厚牛堡 —— 实测算价 ¥31.5（原价 ¥31.5，优惠 ¥0.0）

---

## Day 1 · 2026-09-01 · 周二

**今日决策**：芝士安格斯厚牛堡 —— 实测算价 ¥31.5（原价 ¥31.5，优惠 ¥0.0）

---

## Day 0 · 2026-09-01 · 🚀 系统初始化

**今日决策**：（无——今天我刚刚出生）

---

## Day 4 · 2026-09-04 · 周五

**今日决策**：（无——引擎故障日）

---

"""


# ---- 同日幂等 ----

def test_has_entry_for_today_matches_exact_date(tmp_path):
    diary = tmp_path / "DECISIONS.md"
    diary.write_text("## Day 2 · 2026-10-15 · 周四\n\n**今日决策**：某堡 —— 实测算价 ¥31.5\n", encoding="utf-8")
    assert report.has_entry_for_today(diary, "2026-10-15") is True
    assert report.has_entry_for_today(diary, "2026-10-16") is False  # 其他日期不挡


def test_has_entry_for_today_ignores_failure_entries(tmp_path):
    diary = tmp_path / "DECISIONS.md"
    diary.write_text("## Day 5 · 2026-10-15 · ⚠️ 决策失败\n\n今天没能做出决定：菜单为空\n", encoding="utf-8")
    assert report.has_entry_for_today(diary, "2026-10-15") is False  # 失败占位允许同日重试


def test_has_entry_for_today_missing_file(tmp_path):
    assert report.has_entry_for_today(tmp_path / "nope.md", bj_today()) is False


def test_main_skips_when_today_already_written(tmp_path, monkeypatch):
    diary = tmp_path / "DECISIONS.md"
    diary.write_text(
        f"## Day 2 · {bj_today()} · 周四\n\n**今日决策**：某堡 —— 实测算价 ¥31.5\n",
        encoding="utf-8",
    )
    state = tmp_path / "state"
    monkeypatch.setattr(autopilot, "DIARY", diary)
    monkeypatch.setattr(autopilot, "STATE_DIR", state)
    for key in ("MCD_MCP_TOKEN", "MCD_PREVIEW", "MCD_FORCE", "MCD_DRY_RUN", "MCD_ENGINE", "MCD_BUDGET"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("MCD_MCP_TOKEN", "fake-token")  # live-dryrun：会写日记的模式

    rc = asyncio.run(autopilot.run())
    assert rc == 0
    assert not state.exists(), "幂等命中应整条流水线跳过，连 state 目录都不产生"
    assert diary.read_text(encoding="utf-8").count("## Day") == 1, "日记不得重复插入"


def test_mcd_force_env_parsed(monkeypatch):
    monkeypatch.delenv("MCD_FORCE", raising=False)
    assert Settings.from_env().force is False
    monkeypatch.setenv("MCD_FORCE", "true")
    assert Settings.from_env().force is True


# ---- 决策记忆 ----

def test_parse_diary_extracts_days_and_skips_placeholders():
    days = parse_diary(DIARY_SAMPLE)
    assert [d["date"] for d in days] == ["2026-09-01", "2026-09-02", "2026-09-03"]
    assert days[0]["items"] == ["芝士安格斯厚牛堡"] and days[0]["pay"] == 31.5
    assert days[2]["items"] == ["板烧鸡腿堡", "麦乐鸡"] and days[2]["pay"] == 25.0
    # Day 0 占位与 Day 4 失败日都不进决策序列


def test_memory_record_rolling_and_overwrite(tmp_path):
    path = tmp_path / "decision-history.json"
    mem = DecisionMemory(path)
    base = date.fromisoformat(bj_today()) - timedelta(days=69)
    for i in range(70):  # 69 天前 ~ 今天，共 70 条
        mem.record((base + timedelta(days=i)).isoformat(), [f"堡{i}"], 20.0 + i)
    mem.record(bj_today(), ["今天的堡"], 30.0)  # 同日重写 = 覆盖
    mem.save()

    reloaded = DecisionMemory(path)
    # 滚动窗口与营养台账同语义：保留 date >= today-60（闭区间 61 条）
    oldest = (date.fromisoformat(bj_today()) - timedelta(days=60)).isoformat()
    assert len(reloaded.days) == 61, "滚动窗口 60 天"
    assert reloaded.days[0]["date"] == oldest
    assert reloaded.days[-1] == {"date": bj_today(), "items": ["今天的堡"], "pay": 30.0}


def test_memory_merge_dedups_real_orders_and_marks_source(tmp_path):
    mem = DecisionMemory(tmp_path / "decision-history.json", days=[
        {"date": "2026-10-10", "items": ["巨无霸"], "pay": 25.5},
        {"date": "2026-10-11", "items": ["板烧鸡腿堡"], "pay": 23.0},
    ])
    history = [HistoryOrder(date="2026-10-10", items=["巨无霸（真实下单）"], total=25.5)]  # 真实订单优先
    merged = mem.merge_into(history)
    assert merged == 1, "同日已有真实订单的决策记忆不重复并入"
    assert [h.date for h in history] == ["2026-10-11", "2026-10-10"], "倒序（最新在前）"
    assert history[0].source == "decision-history" and history[1].source == "order-list"


def _two_burger_snapshot() -> Snapshot:
    menu = [
        MenuItem(code="M1", name="巨无霸", price=25.5, category="汉堡"),
        MenuItem(code="M2", name="板烧鸡腿堡", price=23.0, category="汉堡"),
    ]
    nutrition = {  # 两堡营养完全一致：分差只能来自"昨天吃过什么"
        "巨无霸": {"kcal": 550, "protein": 26, "fat": 28, "carbs": 45, "sodium": 1010},
        "板烧鸡腿堡": {"kcal": 550, "protein": 26, "fat": 28, "carbs": 45, "sodium": 1010},
    }
    return Snapshot(store_code="1000001", menu=menu, nutrition=nutrition)


def _memory_with_yesterday(burger: str) -> DecisionMemory:
    yesterday = (date.fromisoformat(bj_today()) - timedelta(days=1)).isoformat()
    return DecisionMemory(Path("N/A"), days=[{"date": yesterday, "items": [burger], "pay": 25.0}])


def test_v1_penalizes_yesterday_choice_from_memory():
    snap = _two_burger_snapshot()
    _memory_with_yesterday("巨无霸").merge_into(snap.history)
    d = decide(snap, budget=40.0, engine="v1")
    assert [it.name for it in d.items] == ["板烧鸡腿堡"], "v1 应惩罚昨天吃过的巨无霸"


def test_v2_avoids_yesterday_choice_from_memory():
    snap = _two_burger_snapshot()
    _memory_with_yesterday("巨无霸").merge_into(snap.history)
    d = decide(snap, budget=40.0, engine="v2")
    assert [it.name for it in d.items] == ["板烧鸡腿堡"], "v2 新鲜度应避开昨天吃过的巨无霸"


def test_load_or_seed_reads_diary_when_file_missing(tmp_path):
    diary = tmp_path / "DECISIONS.md"
    diary.write_text(DIARY_SAMPLE, encoding="utf-8")
    mem = DecisionMemory.load_or_seed(tmp_path / "state" / "decision-history.json", diary)
    assert mem.seeded and len(mem.days) == 3
    assert not (tmp_path / "state").exists(), "种子惰性：不落盘，mock/preview 零写副作用"

    mem.record(bj_today(), ["新决策"], 28.0)
    mem.save()
    disk = json.loads((tmp_path / "state" / "decision-history.json").read_text(encoding="utf-8"))
    assert len(disk) == 4 and disk[-1]["items"] == ["新决策"], "record 时种子随记忆一起落盘"


# ---- 北京时间 ----

def test_beijing_timezone_fixed_offset():
    assert BJ_TZ.utcoffset(None).total_seconds() == 8 * 3600
    assert bj_now().utcoffset().total_seconds() == 8 * 3600


def test_render_entry_uses_beijing_time():
    decision = Decision(
        items=[MenuItem(code="M1", name="巨无霸", price=25.5, category="汉堡")],
        menu_price=25.5, score=4.2, reasons=["测试理由"], engine="v1",
    )
    entry = report.render_entry(1, decision, Snapshot(), None, "mock", [])
    assert "北京时间" in entry
    assert f"## Day 1 · {bj_today()}" in entry, "日记日期按北京口径（runner 是 UTC）"
