# 报名 Issue 草稿（待发布）

> 提交方式：在 https://github.com/M-China/mcd-developer-innovation-challenge 仓库创建 Issue
> 格式要求：标题自定义；正文为下方模板，**不超过 1000 字，不能带图片**
> 时机：D3 材料（README 润色 + 演示 GIF）上线并自查后提交
> 提交后确认：系统会在 Issue 下回复成功通知；Star>0 后出现在 RANKING.md

---

**Issue 标题**：McAutoPilot 参赛申请 —— 我把午饭外包给了 AI

**Issue 正文**：

【参赛申请】
项目名称：McAutoPilot（麦麦自动驾驶）
项目地址：https://github.com/Green1989/McAutoPilot
项目简介：一个每天自动运行的"午饭自动驾驶"Agent。基于麦当劳官方 MCP（https://mcp.mcd.cn），GitHub Actions 每天北京时间 10:00 自动执行完整决策循环：感知（收藏门店在售菜单、可用优惠券、历史订单、营养数据库、会员积分）→ 决策（规则打分引擎综合优惠券有效期、营养缺口、单餐预算、近期重复度打分，每条决策附编号理由与营养台账）→ 执行（调用 calculate-price 真实算价生成订单草稿，默认 dry-run 不真实下单）→ 记录（自动写入公开的《AI 吃饭日记》DECISIONS.md 并 commit 回仓库，commit 历史即连载）。技术特点：35 个 MCP 工具实测接入（含 markdown 包裹 JSON 解析、CSV 营养表解析、金额分单位换算、600 req/min 限流自律与断连重连）；无 Token 自动降级离线 Mock 模式，fork 后 5 分钟即可私有部署（Token 仅走 GitHub Secrets）；隐私字段自动脱敏，参赛声明等必备文件齐全。作品目标：把"中午吃什么"这类高频低愉悦决策交给可解释、可审计的 Agent——它不猜口味玄学，每条理由都带数字。
