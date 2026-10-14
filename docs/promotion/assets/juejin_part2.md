
没有人类编辑过它。昨天下午 14:26，一个跑在 GitHub Actions 上的 Agent 醒来，连上麦当劳官方 MCP，看了看我收藏门店的在售菜单、卡包里的券、最近的历史订单和营养缺口，然后替我做了今天的午饭决策，连理由一起写进了 `DECISIONS.md` 并 commit 回仓库。

项目在这里：[github.com/Green1989/McAutoPilot](https://github.com/Green1989/McAutoPilot)（McAutoPilot，麦麦自动驾驶）。从今天起它每天北京时间 10:00 自动运行，日记公开连载，commit 历史就是连载本身。

## 为什么做这个

打工人每天都要回答人类历史上最难的问题之一：**中午吃什么？**

这个问题的痛点不在“没得选”，而在：

- 有 30 张优惠券，但不知道今天哪张最划算；
- 想吃点好的，又不想连续五天麦辣鸡腿堡；
- 昨天吃太咸了，今天其实该补点蔬菜——但谁会记得呢？

所以我把这个决策外包了出去。它有记忆（我的点餐历史）、有约束（预算/营养）、有目标（好吃、划算、别重样），还有一本公开的决策日志——**每一次“它为什么这么选”都有据可查**。

顺便说个真实发现：接入历史订单接口后它告诉我，我最后一次下单停在 8 月 8 日，是个「精选超值随心配」钉子户，单餐常年在 ¥13.9 徘徊——省钱意识满分，蛋白质摄入堪忧。Day 1 它就据此把“补蛋白”加权提了上去。

## 它每天怎么思考

```
10:00 (cron) ──▶ 感知 ──▶ 决策 ──▶ 执行 ──▶ 记录
                 │         │        │        │
                 │         │        │        └─ DECISIONS.md + 营养台账
                 │         │        │           自动 commit（活仓库）
                 │         │        ├─ 领券 + 订单草稿（默认 dry-run）
                 │         │        └─ 可选 webhook 通知
                 │         ├─ 营养缺口 + 预算 + 券 + 别重样 + 理由
                 │         └─ 规则打分引擎（v2 计划换求解器）
                 └─ 可用优惠券 / 历史订单 / 当日菜单（麦当劳 MCP）
```

**感知层**：基于麦当劳官方 MCP Server（`https://mcp.mcd.cn`，Streamable HTTP + Bearer Token）。实测发现 35 个工具，主链路用到 7 个：`query-nearby-stores`（收藏门店）、`query-meals`（在售菜单）、`query-store-coupons`（可用券）、`order-list`（历史订单画像）、`list-nutrition-foods`（营养库）、`query-my-account`（积分）、`calculate-price`（含优惠真实算价）。

**决策层**：规则打分引擎 v1，六条规则每条带数字——营养缺口（7 天滚动均值找短板）、单餐预算（默认 ¥40）、券有效期（不用就浪费）、近期重复度（换口味惩罚）、性价比、蛋白质密度。Day 1 的输出长这样：

> **今日决策**：芝士安格斯厚牛堡 —— 实测算价 ¥31.5
> 1. 蛋白质 32g 达标（目标 ≥30g），下午写码不困
> 2. 热量 696kcal 落在 480-820 的午餐甜区
> 3. 性价比 1.02g 蛋白/元，高于 1.0 的及格线
> 数据源：广州长兴路餐厅 · 123 个在售餐品 · 2 张可用券

**执行层**：默认 dry-run——执行链止步于 `calculate-price`，这是一个纯计算接口，不下单、不领券、不动账户。真实下单需要显式设置 `MCD_DRY_RUN=false`，且 v1 尚未实装下单代码，双重保险。

**记录层**：每天一篇决策记录自动渲染进 `DECISIONS.md` 并 commit 回仓库。附带滚动 7 天的营养台账（kcal/蛋白/钠）。

## 踩坑实录（读者老爷们要的干货）

接入官方 MCP 的过程不算平滑，四个印象最深的坑：

1. **返回是 markdown 包裹的 JSON**。多数工具返回「字段说明 + `## Original Response` + 原始 JSON」，直接 `json.loads` 必挂。适配做在 `mcp_client/base.py::extract_json`：截取 Original Response 段再解析。
2. **营养表是 CSV 文本**。`list-nutrition-foods` 返回 `[160]{productName,...,energyKcal,...}:` 加 CSV 行——LLM 友好但程序不友好，得按表格解析。
3. **金额单位是分**。`calculate-price` 返回的 price/discount 都是分，渲染前记得除以 100，不然日记里会出现 ¥3150 的巨堡。
4. **限流与断连**。上游 600 req/min，客户端做了串行调用 + 0.15s 间隔 + 断连重建会话重试一次。公网抖动不炸主流程。

## 安全设计

- Token 只走 GitHub Secrets → 环境变量，代码零硬编码，仓库做过全文扫描；
- 订单等个人数据经字段白名单过滤后才落地，探针脚本输出自动脱敏；
- 默认 dry-run，不乱下单不乱扣钱；
- fork 后没有 Token 会自动降级离线 Mock 模式，用模拟数据走完整个决策循环。

## fork-and-run：五分钟私有部署你自己的“午饭自动驾驶”

1. Fork 仓库（什么都不配也能跑——无 Token 自动进 Mock 模式先看效果）；
2. 在 open.mcd.cn 申请 MCP Token（免费，需审核，建议尽早）；
3. 你的 fork → Settings → Secrets and variables → Actions → New repository secret：`MCD_MCP_TOKEN`；
4. Actions 页启用 workflow（fork 默认禁用）；
5. 建议先加 Variable `MCD_PREVIEW=true` 手动跑一次，用真实数据出决策预览确认一切正常；
6. 删掉 `MCD_PREVIEW`，之后每天北京时间 10:00 它自动醒来写日记。

想调预算加 `MCD_BUDGET`（默认 40 元）。

## 最后

这个项目正在参加 WorkBuddy × 麦当劳 1024 程序员创意开发大赛（已通过官方报名审核）。它想证明的事情很简单：MCP 把“点餐”从 App 里的交互行为变成了可编程的开放能力，而“中午吃什么”这种高频、低愉悦、信息过载的决策，正适合交给一个有记忆、有约束、理由带数字的 Agent。

它不猜口味玄学。每条理由都带数字。

仓库：[github.com/Green1989/McAutoPilot](https://github.com/Green1989/McAutoPilot)
日记连载：DECISIONS.md（commit 历史即连载）

Star 它 = 订阅一个 AI 的午饭人生 🍟
