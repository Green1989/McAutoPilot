"""决策卡渲染与平台适配测试（不碰网络）。"""
from agent.notify import MAX_TEXT, build_payload, render_text

CARD = {
    "day": 3,
    "date": "2026-10-16",
    "mode": "live-dryrun",
    "engine": "v2",
    "items": [{"code": "M1", "name": "巨无霸"}, {"code": "S1", "name": "中薯条"}],
    "coupon": "板烧鸡腿堡买一送一",
    "pay": 31.5,
    "score": 7.42,
    "reasons": ["命中优惠券「板烧鸡腿堡买一送一」，省 约 ¥11.5", "蛋白质 38g 达标（目标 ≥30g）"],
}


def test_render_text_has_numbers_and_items():
    text = render_text(CARD)
    assert "Day 3" in text
    assert "巨无霸 + 中薯条" in text
    assert "¥31.5" in text
    assert "score 7.42" in text


def test_render_text_truncates():
    fat = dict(CARD, reasons=["理由" * 500])
    assert len(render_text(fat)) <= MAX_TEXT


def test_payload_wecom_markdown():
    p = build_payload("https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=x", CARD)
    assert p["msgtype"] == "markdown" and "content" in p["markdown"]


def test_payload_feishu_text():
    p = build_payload("https://open.feishu.cn/open-apis/bot/v2/hook/xxx", CARD)
    assert p["msg_type"] == "text" and "text" in p["content"]


def test_payload_discord_content():
    p = build_payload("https://discord.com/api/webhooks/123/abc", CARD)
    assert "content" in p


def test_payload_generic_json_card():
    p = build_payload("https://example.com/hook", CARD)
    assert p["source"] == "McAutoPilot" and p["card"]["day"] == 3 and p["text"]


def test_notify_main_without_url_exits_zero(monkeypatch, capsys):
    monkeypatch.delenv("MCD_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("MCD_WEBHOOK_URL".lower(), raising=False)
    from agent import notify

    assert notify.main() == 0
    assert "跳过" in capsys.readouterr().out
