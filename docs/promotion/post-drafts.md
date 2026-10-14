# D3 首波传播文案草稿

> 使用说明：以下为五个平台的首发文案草稿，发布时机建议在报名 Issue 提交并收到成功通知之后（进入 RANKING.md 排行榜，Star 才开始"计票"）。发布节奏建议：第一天 掘金+V2EX+即刻，第二天看数据补 腾讯云社区+X。所有文案遵循合规红线：不刷星、不贬损品牌、不与他牌对比、不夸大（默认 dry-run 如实说明）。

## 1. 掘金（技术向，主战场）

**标题备选**：
- 我把午饭外包给了 AI：用麦当劳官方 MCP 造了个每天自己写日记的 GitHub 仓库
- 1024 程序员节整活：让 GitHub Actions 每天替我决定午饭吃什么

**正文结构**：
1. 开头钩子：贴 DECISIONS.md Day 1 截图（真实决策 + 编号理由），"这是一个 GitHub 仓库自己写的日记"
2. 痛点：30 张券不知道用哪张 / 连续五天麦辣鸡腿堡 / 昨天吃太咸今天该吃什么
3. 架构讲透（技术读者要干货）：
   - 每天 10:00 cron → 感知（35 个 MCP 工具实测：菜单/券/历史订单/营养库/积分）→ 决策（规则打分引擎，6 条规则每条带数字）→ 执行（calculate-price 真实算价，默认 dry-run）→ 记录（DECISIONS.md 自动 commit）
   - 踩坑实录（读者最爱）：返回是 markdown 包裹 JSON、营养表是 CSV 文本、金额单位是分、mcp SDK 1.x/2.x 兼容
4. 安全设计：Token 只走 Secrets、默认 dry-run、隐私字段脱敏
5. fork-and-run 五分钟教程
6. 结尾：仓库链接 + "Star 它 = 订阅一个 AI 的午饭人生"
**标签**：GitHub、MCP、AI Agent、自动化、程序员节

## 2. V2EX（geek 向，标题克制）

**标题**：把午饭决策外包给了一个每天自动跑的 GitHub Actions（麦当劳 MCP）
**节点**：分享创造
**正文**：三段以内。是什么（每天 10:00 自动看券/看历史/算营养缺口，替我决定午饭并写公开日记）、亮点（决策全带理由和数字、commit 历史即连载、fork 即私有部署、默认 dry-run 不会乱下单）、链接。评论区准备好回答技术细节（限流/cron 延迟/为什么不用 LLM 做决策）。

## 3. 即刻（麦门圈 + AI 探索站）

**正文**：手机拍屏 DECISIONS.md 的 Day 1 + 一句话："给麦当劳 1024 大赛做了个东西：一个 AI 每天早上 10 点替我决定午饭吃什么，理由写得很认真，日记公开连载中 🍟" 评论区放仓库链接。

## 4. 腾讯云社区（大赛关联方，正式一些）

**标题**：WorkBuddy × 麦当劳 1024 参赛作品：McAutoPilot——基于官方 MCP 的"午饭自动驾驶"
**正文**：按技术分享格式，突出 MCP 集成深度（35 工具实测、格式坑、限流处理）与 WorkBuddy/Actions 生态结合。（注：如大赛有社区加群/加精通道，优先投稿到指定专题。）

## 5. X/Twitter（英文短打）

> I outsourced my lunch to a GitHub repo. Every day at 10am it wakes up, checks my McDonald's coupons & order history & nutrition gaps via the official MCP, decides lunch, and writes a public diary with numbered reasons. 🍟
> Star it = subscribe to an AI's lunch life.
> github.com/Green1989/McAutoPilot

## 发布纪律

- 所有平台首发时间避开周末，选工作日 10:00-12:00 或 20:00-22:00
- 评论区 2 小时内必回（算法权重）
- 不发"求 Star"私信，不做互赞群，Star 必须自然获取（大赛合规红线）
