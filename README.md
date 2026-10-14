# McAutoPilot 🍟 — 我把午饭外包给了 AI

> 每天 11:30，一个 GitHub Actions 会自己醒来：看看今天有什么券、回顾我最近吃过什么、检查我的营养缺口和预算，然后**替我决定午饭吃什么**——领券、算出最优组合、生成订单草稿，并把这一切写进一本公开的《AI 吃饭日记》。
>
> 我唯一要做的，是吃饭。

[![autopilot](https://img.shields.io/badge/daily-11:30%20%E5%8C%97%E4%BA%AC%E6%97%B6%E9%97%B4-autopilot-red)](.github/workflows/autopilot.yml)
[![dry-run](https://img.shields.io/badge/default-dry--run-green)](agent/config.py)
[![MCP](https://img.shields.io/badge/McDonald's-MCP-gold)](https://mcp.mcd.cn)

## 为什么做这个

打工人每天都要回答人类历史上最难的问题之一：**中午吃什么？**

这个问题的痛点不在"没得选"，而在：
- 有 30 张优惠券，但不知道今天哪张最划算；
- 想吃点好的，又不想连续五天麦辣鸡腿堡；
- 昨天吃太咸了，今天其实该补点蔬菜——但谁会记得呢？

McAutoPilot 把这些决策全部交给一个每天自动运行的 Agent。它有记忆（你的点餐历史）、有约束（预算/营养）、有目标（好吃、划算、别重样），还有一本公开的决策日志——**每一次"它为什么这么选"都有据可查**。

## 它每天怎么思考

```
11:30 (cron) ──▶ 感知 ──▶ 决策 ──▶ 执行 ──▶ 记录
                 │         │        │        │
                 │         │        │        └─ DECISIONS.md + 营养台账
                 │         │        │           自动 commit（活仓库）
                 │         │        ├─ 领券 + 订单草稿（默认 dry-run）
                 │         │        └─ 可选 webhook 通知
                 │         ├─ 营养缺口 + 预算 + 券 + 别重样 + 理由
                 │         └─ 规则打分引擎（v2 计划换求解器）
                 └─ 可用优惠券 / 历史订单 / 当日菜单（麦当劳 MCP）
```

每天一篇决策记录长这样（示意，见 [DECISIONS.md](DECISIONS.md)）：

```markdown
## Day 12 · 2026-10-14 · ☀️ 周三

**今日决策**：板烧鸡腿堡 + 蔬菜沙拉 + 鲜煮咖啡 —— 实付 ¥27.0

**为什么**：
1. 连续 2 天麦辣鸡腿堡，辣度疲劳，引擎给出"换口味"加权 +0.3
2. 近 3 天钠摄入均值超标 18%，沙拉与咖啡的组合把今天拉回均衡
3. 「板烧买一送一」券今天到期，不用就浪费 —— 折上再省 ¥23
4. 预算 ¥35 以内达标，蛋白质 42g 达标

**营养台账**：kcal 562/2000 · 蛋白 42/60g · 钠 1050/2000mg
```

## 快速开始（fork-and-run）

1. **Fork 本仓库**
2. 在 [open.mcd.cn](https://open.mcd.cn) 申请麦当劳 MCP Token（免费，需审核）
3. 仓库 **Settings → Secrets and variables → Actions → New repository secret**：
   - Name: `MCD_MCP_TOKEN`，Value: 你的 Token
4. 到 **Actions** 页启用 workflow（fork 默认禁用），手动点一次 `Run workflow` 验证

默认 `dry-run`：Agent 只决策、只写日记、只生成订单草稿，**不会真实下单**。想让它动真格，在仓库 **Settings → Secrets and variables → Actions → Variables** 里加 `MCD_DRY_RUN=false`。

没有 Token 也能玩：不配置 Secret 时自动进入**离线 Mock 模式**，用模拟数据跑完整决策循环，先看效果再决定要不要 Token。

## 项目结构

```
.github/workflows/autopilot.yml   # 每日 11:30 自动驾驶循环（含日记自动 commit）
agent/
  main.py                         # 主循环入口（python -m agent.main）
  config.py                       # 配置：Token 只从环境变量读，永不落仓库
  perceive.py                     # 感知层：菜单/券/历史订单/营养/积分 归一化
  brain.py                        # 决策引擎 v1：规则打分（券+营养+预算+换口味）
  ledger.py                       # 营养台账：滚动 7 天摄入与花费
  report.py                       # 日记渲染：DECISIONS.md 每日条目
  mcp_client/
    base.py                       # 客户端统一接口 + 返回文本 JSON 提取
    http_client.py                # 真实 MCP 客户端（Streamable HTTP + Bearer + 断连重试）
    mock_client.py                # 离线 Mock（工具名与返回结构对齐真实服务）
    fixtures/                     # 模拟菜单/券/订单数据
scripts/
  probe_mcp.py                    # MCP 探针：摸清工具返回结构（内置脱敏）
docs/mcp-tool-samples/            # 真实 MCP 返回结构脱敏样例（决策引擎设计依据）
state/                            # 营养台账 / 决策状态 / commit 消息（随决策 commit）
DECISIONS.md                      # AI 吃饭日记（核心产出）
MCP_INTEGRATION.md                # 麦当劳 MCP 集成说明
CONTEST_DECLARATION.md            # 参赛声明（官方要求，不可改动）
```

## 配置项（全部可选，走环境变量 / Actions Variables）

| 变量 | 默认 | 说明 |
|---|---|---|
| `MCD_MCP_TOKEN` | 空 | 麦当劳 MCP Token；不设则自动进入离线 Mock 模式 |
| `MCD_DRY_RUN` | `true` | true = 只决策+算价草稿；false 才会真实领券/下单（v2 实装） |
| `MCD_BUDGET` | `40` | 单餐预算上限（元） |
| `MCD_PREVIEW` | `false` | true = 真实数据跑完整决策但只写预览，不落 DECISIONS.md（fork 试跑推荐先开这个） |

## 设计原则

- **默认不动真格**：dry-run 是默认值，真实下单需要显式开启；
- **隐私不落仓库**：订单数据经字段白名单过滤后才写入决策日志，探针输出自动脱敏；
- **决策可解释**：不吃"黑盒推荐"，每一条决策附编号理由，日志就是审计记录；
- **活仓库即产品**：commit 历史就是这本日记的连载，star 它 = 订阅一个 AI 的午饭人生。

## 路线图

- [x] D1 感知链路：MCP 客户端 + Mock 模式 + Actions 定时任务
- [x] D2 决策引擎 v1（规则打分）+ DECISIONS.md 自动渲染与 commit + 营养台账
- [ ] D3 演示 GIF + fork 指南完善 + 首波发布
- [ ] v2 求解器（多约束优化替代规则打分）+ 真实下单执行链
- [ ] webhook 实时推送"今日决策卡"

## 大赛

本项目参加 **WorkBuddy × 麦当劳 程序员创意开发大赛**（基于[麦当劳官方 MCP](https://mcp.mcd.cn)）。参赛声明见 [CONTEST_DECLARATION.md](CONTEST_DECLARATION.md)，MCP 集成说明见 [MCP_INTEGRATION.md](MCP_INTEGRATION.md)。

## 免责与致谢

- 本项目为独立开发的参赛作品，与麦当劳官方无关；
- Mock 模式中的菜单价格与营养数据为演示用近似值，非官方数据；
- 感谢 [M-China](https://github.com/M-China) 提供的官方 MCP 服务与大赛机会。

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=Green1989/McAutoPilot&type=Date)](https://star-history.com)
