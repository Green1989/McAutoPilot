"""MCP 探针：摸清真实服务的工具清单与返回结构。

用法（Token 到手后）:
    python scripts/probe_mcp.py --list                 # 列出全部工具
    python scripts/probe_mcp.py --sample --limit 5     # 逐个空参调用前 5 个工具
    python scripts/probe_mcp.py --tool get_menu --args '{"category":"汉堡"}'
    python scripts/probe_mcp.py --mock --list          # 离线模式（Mock）

输出:
    原始结果 → state/probe/（已 gitignore，可能含个人数据，绝不提交）
    脱敏副本 → docs/mcp-tool-samples/（可提交，供决策引擎设计参考）
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.config import REPO_ROOT, Settings
from agent.mcp_client import make_client

# 隐私字段黑名单（大小写不敏感、忽略 -_ 分隔）：命中即打码，绝不写进可提交文件
PRIVACY_KEY_RE = re.compile(
    r"(phone|mobile|telephone|tel|contact|address|email|receiver|customer|"
    r"realname|username|nickname|avatar|cardnum|idcard|idnumber|location|gps|"
    r"latitude|longitude|token|session|accountid|memberid|userid|openid)",
    re.IGNORECASE,
)


def sanitize(obj, depth: int = 0):
    """递归脱敏：隐私键值打码；超长数组截断并标注。"""
    if depth > 24:
        return "..."
    if isinstance(obj, dict):
        out = {}
        for key, value in obj.items():
            if PRIVACY_KEY_RE.search(str(key)):
                out[key] = "***MASKED***"
            else:
                out[key] = sanitize(value, depth + 1)
        return out
    if isinstance(obj, list):
        if len(obj) > 30:
            return sanitize(obj[:30], depth + 1) + [f"...共 {len(obj)} 条，已截断"]
        return [sanitize(v, depth + 1) for v in obj]
    return obj


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


async def probe(args) -> int:
    settings = Settings.from_env()
    if args.mock:
        settings.mcp_token = ""  # 强制 Mock
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    probe_dir = REPO_ROOT / "state" / "probe"
    sample_dir = REPO_ROOT / "docs" / "mcp-tool-samples"

    async with make_client(settings) as client:
        tools = await client.list_tools()
        print(f"[probe] 模式: {settings.mode}，发现 {len(tools)} 个工具")
        write_json(probe_dir / f"{stamp}-tools.json", tools)

        if args.list:
            for tool in tools:
                desc = (tool.get("description") or "")[:60]
                print(f"  - {tool['name']}: {desc}")
            print(f"[probe] 工具清单已存 {probe_dir / (stamp + '-tools.json')}")

        targets: list[tuple[str, dict]] = []
        if args.tool:
            targets.append((args.tool, json.loads(args.args or "{}")))
        elif args.sample:
            for tool in tools[: args.limit]:
                targets.append((tool["name"], {}))

        for name, call_args in targets:
            result = await client.call_tool(name, call_args)
            status = "ERROR" if result.is_error else "OK"
            payload = {
                "tool": name,
                "arguments": call_args,
                "isError": result.is_error,
                "text": result.text,
                "parsed": result.data,
            }
            raw_path = probe_dir / f"{stamp}-{name}.json"
            safe_path = sample_dir / f"{name}.json"
            write_json(raw_path, payload)
            write_json(safe_path, sanitize(payload))
            preview = result.text[:100].replace("\n", " ")
            print(f"  [{status}] {name}({json.dumps(call_args, ensure_ascii=False)}) -> {preview}")
            print(f"        raw: {raw_path}  |  脱敏: {safe_path}")

    print("[probe] 完成。docs/mcp-tool-samples/ 下为脱敏样例，可安全提交。")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="麦当劳 MCP 探针")
    parser.add_argument("--list", action="store_true", help="列出全部工具")
    parser.add_argument("--sample", action="store_true", help="空参逐个调用工具")
    parser.add_argument("--limit", type=int, default=3, help="--sample 时调用的工具数上限")
    parser.add_argument("--tool", help="指定工具名调用")
    parser.add_argument("--args", help="工具参数 JSON 字符串")
    parser.add_argument("--mock", action="store_true", help="强制离线 Mock 模式")
    args = parser.parse_args()
    if not (args.list or args.sample or args.tool):
        parser.error("至少指定 --list / --sample / --tool 之一")
    sys.exit(asyncio.run(probe(args)))


if __name__ == "__main__":
    main()
