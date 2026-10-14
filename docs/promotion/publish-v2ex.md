# V2EX 发布稿（定稿）

- 节点：分享创造
- 标题：把午饭决策外包给了一个每天自动跑的 GitHub Actions（麦当劳官方 MCP）
- 发布状态：待发布（2026-10-14 晚窗口）
- 备注：无图（V2EX 正文不支持图片）；评论区准备回答 限流/cron 延迟/为什么不用 LLM 做决策 等技术问题

---

## 正文

做了一个实验性的小项目 McAutoPilot：一个跑在 GitHub Actions 上的 Agent，每天北京时间 10:00 自动醒来，通过麦当劳官方 MCP（mcp.mcd.cn，Streamable HTTP + Bearer Token）读取收藏门店的在售菜单、可用优惠券、我的历史订单和营养库，用规则打分引擎（营养缺口/预算/券有效期/近期重复度）替我决定午饭吃什么，调用 calculate-price 真实算价生成订单草稿，然后把决策和编号理由写进公开的 DECISIONS.md 并 commit 回仓库——commit 历史就是这本日记的连载。

几个设计取舍：

- 执行链默认 dry-run，止步于 calculate-price（纯计算接口），不下单不领券；真实下单需要显式开启且 v1 未实装
- 不用 LLM 做决策：每条理由都要带数字（蛋白质克数/热量区间/性价比），规则引擎可解释可审计
- Token 只走 GitHub Secrets；无 Token 自动降级离线 Mock 模式，fork 后五分钟可私有部署
- 接入过程踩了几个官方 MCP 的格式坑：返回是 markdown 包裹 JSON、营养表是 CSV 文本、金额单位是分

仓库：https://github.com/Green1989/McAutoPilot

正在参加 WorkBuddy × 麦当劳 1024 大赛（已过官方报名审核）。欢迎拍砖，技术细节知无不言。
