# 运行时状态目录

随每日决策 commit 回仓库的（跨 Actions run 存活，见 .github/workflows/autopilot.yml 的 git add 列表）：

- `nutrition.json` —— 营养台账（滚动 60 天，7 天均值生成营养缺口理由）
- `decision-history.json` —— 决策记忆（滚动 60 天的每日决策摘要；dry-run 下的
  决策不是订单、order-list 看不见，换口味规则靠它感知"昨天吃过什么"）
- `last-decision.json` —— 最近一次决策摘要（决策卡推送的数据源）
- `commit-msg.txt` —— 当日 commit 消息

不进仓库的运行时产物：`probe/`、`cache/`、`preview.md`（.gitignore）；
`last-order.json` 含支付链接（账号上下文），不在 workflow 的 git add 列表里，
仅存本地——切勿手动提交。
