# mcp-tool-samples — 真实 MCP 工具返回结构（脱敏样例）

本目录存放 `python scripts/probe_mcp.py --list --sample` 对**真实**麦当劳 MCP 服务的探针输出（自动脱敏：电话/地址/证件号等隐私字段打码，超长数组截断），作为决策引擎设计的结构参考。

- 仅存放真实服务样例，Mock 数据不落此目录（避免与真实结构混淆）；
- 原始未脱敏输出在 `state/probe/`，已被 .gitignore 排除，绝不提交；
- 示例命令：

```bash
export MCD_MCP_TOKEN=xxx   # 或写入 .env（已 gitignore）
python scripts/probe_mcp.py --list
python scripts/probe_mcp.py --sample --limit 5
python scripts/probe_mcp.py --tool get_menu --args '{"category":"汉堡"}'
```
