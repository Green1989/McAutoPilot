"""今日决策卡：把 state/last-decision.json 推送到群机器人（可选功能）。

用法（Actions 里作为独立步骤，在日记 commit 之后）：
    MCD_WEBHOOK_URL=... python -m agent.notify

平台适配（按 URL 特征自动识别，无需额外配置）：
- 企业微信群机器人 qyapi.weixin.qq.com → markdown 消息
- 飞书自定义机器人 open.feishu.cn      → text 消息
- Discord discord.com/api/webhooks      → content 消息
- 其余 → 通用 JSON（完整决策卡字段 + 文本版）

纪律：未配置 MCD_WEBHOOK_URL、无 last-decision.json、网络失败——一律打印后
退出码 0，绝不影响日记流水线。
"""
from __future__ import annotations

import json
import sys
import urllib.request

from .config import REPO_ROOT, Settings

MAX_TEXT = 1800  # Discord 2000 字符上限，留余量


def _item_name(it) -> str:
    if isinstance(it, dict):
        return str(it.get("name") or it.get("code") or "")
    return str(it)


def render_text(card: dict) -> str:
    items = " + ".join(_item_name(it) for it in card.get("items") or [])
    pay = card.get("pay")
    pay_txt = f" —— ¥{pay:.1f}" if isinstance(pay, (int, float)) else ""
    lines = [
        f"🍱 McAutoPilot Day {card.get('day', '?')} · {card.get('date', '')}",
        f"今日决策：{items}{pay_txt}",
    ]
    if card.get("coupon"):
        lines.append(f"用券：{card['coupon']}")
    for i, reason in enumerate((card.get("reasons") or [])[:3], 1):
        lines.append(f"{i}. {reason}")
    lines.append(f"score {card.get('score', '?')} · 日记 github.com/Green1989/McAutoPilot/blob/main/DECISIONS.md")
    return "\n".join(lines)[:MAX_TEXT]


def build_payload(url: str, card: dict) -> dict:
    text = render_text(card)
    if "qyapi.weixin.qq.com" in url:
        return {"msgtype": "markdown", "markdown": {"content": text}}
    if "open.feishu.cn" in url:
        return {"msg_type": "text", "content": {"text": text}}
    if "discord.com" in url or "discordapp.com" in url:
        return {"content": text}
    return {"source": "McAutoPilot", "text": text, "card": card}


def send(url: str, payload: dict, timeout: float = 10.0) -> tuple[bool, str]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= resp.status < 300, f"HTTP {resp.status}"
    except Exception as exc:  # 推送失败不影响流水线
        return False, str(exc)[:200]


def main() -> int:
    settings = Settings.from_env()
    if not settings.webhook_url:
        print("[notify] MCD_WEBHOOK_URL 未配置，跳过（不影响流水线）")
        return 0
    path = REPO_ROOT / "state" / "last-decision.json"
    if not path.exists():
        print("[notify] 无 state/last-decision.json（mock/预览模式），跳过")
        return 0
    try:
        card = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[notify] last-decision.json 读取失败: {exc}，跳过")
        return 0
    ok, note = send(settings.webhook_url, build_payload(settings.webhook_url, card))
    print(f"[notify] 决策卡推送{'成功' if ok else '失败'}: {note}")
    return 0  # 推送失败也不让步骤红掉


if __name__ == "__main__":
    sys.exit(main())
