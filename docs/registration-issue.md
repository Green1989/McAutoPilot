# 报名 Issue（已提交并通过审核 ✅）

> 状态：**2026-10-14 已报名成功**。Issue：https://github.com/M-China/mcd-developer-innovation-challenge/issues/701
> 官方机器人 M-China-Official 于 2026-10-14 12:59（UTC）回复："您的作品已成功参赛，您可以通过官方项目的排行榜.md查看排名"
> 以下为提交原文存档。

---

**Issue 标题**：McAutoPilot 参赛申请 —— 我把午饭外包给了 AI

**Issue 正文**：

【参赛申请】
项目名称：McAutoPilot（麦麦自动驾驶）
项目地址：https://github.com/Green1989/McAutoPilot
项目简介：一个每天自动运行的"午饭自动驾驶"Agent。基于麦当劳官方 MCP（https://mcp.mcd.cn），GitHub Actions 每天北京时间 10:00 自动执行完整决策循环：感知（收藏门店在售菜单、可用优惠券、历史订单、营养数据库、会员积分）→ 决策（规则打分引擎综合优惠券有效期、营养缺口、单餐预算、近期重复度打分，每条决策附编号理由与营养台账）→ 执行（调用 calculate-price 真实算价生成订单草稿，默认 dry-run 不真实下单）→ 记录（自动写入公开的《AI 吃饭日记》DECISIONS.md 并 commit 回仓库，commit 历史即连载）。技术特点：35 个 MCP 工具实测接入（含 markdown 包裹 JSON 解析、CSV 营养表解析、金额分单位换算、600 req/min 限流自律与断连重连）；无 Token 自动降级离线 Mock 模式，fork 后 5 分钟即可私有部署（Token 仅走 GitHub Secrets）；隐私字段自动脱敏，参赛声明等必备文件齐全。作品目标：把"中午吃什么"这类高频低愉悦决策交给可解释、可审计的 Agent——它不猜口味玄学，每条理由都带数字。
