# DEVLOG — McAutoPilot 开发日志

## D4 · 2026-10-14 晚 · v2 开发（分支 v2，待 Day 2 验证后合并）

### 完成内容
- **求解器决策引擎 v2**（`brain.py`）：同一枚举空间上先过硬约束（预算 / 钠≤1500mg / 热量≤1200kcal），再按公开权重的归一化目标求最大值（蛋白 2.5 / 热量甜区 1.5 / 钠余量 0.8 / 券价值 2.0 / 新鲜度 1.5 / 品类 0.8 / 性价比 1.0）；日记新增「分数构成」行，逐项带真实数字。`MCD_ENGINE` 切换（默认 v1，渐进发布，改环境变量即回滚）
- **真实下单执行链**（`executor.py`）：`auto-bind-coupons` 领券（`MCD_AUTO_CLAIM`，默认关）+ `create-order` 下单，三重护栏=双开关（MCD_DRY_RUN=false + MCD_CONFIRM_ORDER=当天日期，日期每天变所以陈旧配置无法持续授权）+ 预算硬上限（以 calculate-price 实付为准）+ 支付留人（订单只到"待支付"，支付链接只落本地 state/last-order.json 不进仓库）。`price_check` 补采 takeWayList（create-order 必填项来源）
- **webhook 决策卡**（`notify.py` + workflow 增量步骤）：企业微信 markdown / 飞书 text / Discord content / 通用 JSON 按 URL 自动适配；未配置 Secret 时静默跳过、退出码恒 0，绝不让流水线变红
- **测试**：`tests/` 22 个单测（求解器约束与可解释性 / 执行链三重护栏全走 Mock / 决策卡渲染），全绿
- **验证**：mock 全链路 ✓；live 预览 v1 回归 ✓（芝士安格斯厚牛堡 ¥31.5，与合并前行为一致）；live 预览 v2 ✓（真实数据：双层吉士汉堡+麦乐鸡 ¥37.0，蛋白 39g 达标，分数构成 7 项完整，钠 1439mg 触发"未破硬上限"提醒——可解释性符合设计）
- **文档**：README（架构图/配置表 8 项/FAQ 四层保险/路线图勾选 v2）+ MCP_INTEGRATION（写操作工具表 + 三重护栏专节）

### 关键决策
- v2 只上分支，**明天 Day 2 验证 PASS 后才合并 main**：10-15 10:00 是首次无人值守定时运行（评分演示点），不能让新引擎首秀扛这个风险；合并后 `MCD_ENGINE` 仓库变量切 v2，再出问题撤变量即回滚（无需回滚代码）
- create-order 不做 live 实测：会创建真实订单（外向动作，无授权路径），以单测 + mock 模拟覆盖；首次真实调用由用户显式开启

### 代理决策清单（授权来源：AGENTS.md 无人值守政策预授权）
| # | 决策 | 依据 | 回滚方式 |
|---|------|------|---------|
| 1 | v2 开发在分支、Day 2 PASS 后合并 | 硬性红线"不得碰坏每天 10:00 流水线" + 首次无人值守运行是关键演示 | 合并一步 `git merge v2` 随时可做/可逆 |
| 2 | MCD_ENGINE 默认 v1、用仓库变量切 v2 | 渐进发布；变量级回滚秒级生效 | 撤变量即回 v1 |
| 3 | MCD_AUTO_CLAIM 默认关 | 保持 dry-run 语义纯净（日记"未领券"承诺不变） | 设变量即开 |
| 4 | 二次确认用"当日日期令牌"而非静态口令 | 无人值守场景下唯一能防止陈旧配置持续授权的形态 | 无需回滚 |
| 5 | 支付链接/订单号只落 gitignore 的 state/last-order.json | 链接含账号上下文，公开仓库不可见 | 无需回滚 |
| 6 | mock 客户端补 create-order/auto-bind 模拟 | 执行链单测需要；mock 主流程永不触达写操作 | 删两段分支即可 |

---

## D3 · 2026-10-14 · 上线打磨

### 完成内容
- **发车时间调整**：11:30 → 10:00（北京，cron `0 2 * * *`）——GitHub cron 高峰期可能延迟几分钟到几十分钟，提前给午饭决策留缓冲（用户决策）；全仓引用同步清理，仓库描述同步更新
- **演示 GIF**：IAB 真实截取仓库三视图（首页 README 区 / DECISIONS.md / Actions 运行列表），Pillow 合成 docs/demo.gif（含字幕条与结尾卡），脚本 scripts/make_demo_gif.py 可复现
- **README 打磨**：演示区 + 上线状态徽章 + "已上线运行"链接、fork 指南扩成 6 步（含 MCD_PREVIEW 试跑建议）、FAQ 四问（Token 安全/会不会乱下单/怎么懂口味/为什么用 Actions）
- **仓库运营**：topics 打标（mcp/mcdonalds/ai-agent/github-actions/automation/model-context-protocol/hackathon/python/mcp-server/lunch）
- **传播与报名**：docs/promotion/post-drafts.md（掘金/V2EX/即刻/腾讯云/X 五平台首发文案 + 发布纪律）；docs/registration-issue.md（官方标准格式报名草稿，≤1000 字无图）
- **截图工程发现**：GitHub Actions 运行日志匿名访客不可见（Sign in to view logs）→ 第三帧改用运行列表页；GitHub 新版界面用嵌套滚动容器，window.scrollTo 无效 → 改 CUA 滚轮/整页截图+DOM 定位裁剪；整页截图按视口分块拼接，固定导航栏在分块边界重复渲染 → 裁剪带须完全落在单个分块内；**shields 静态徽章不支持 %20 空格编码，且以 HTTP 200 返回"404 badge"SVG（判活不能只看状态码，要看 SVG 内容）**；多模态子智能体多轮验收截图

### 代理决策清单（授权来源：AGENTS.md 无人值守政策预授权）
| # | 决策 | 依据 | 回滚方式 |
|---|------|------|---------|
| 1 | 发车 11:30 → 10:00 | 用户明确指示（cron 延迟缓冲） | 改 cron 一行 |
| 2 | 报名押后到 D3 材料就绪后，只备草稿不提交 | 用户明确指示 | docs/registration-issue.md 随时可发 |
| 3 | 演示 GIF 第三帧用 Actions 运行列表页而非日志页 | 匿名访客看不到日志（实测），列表页的 ✅ 历史同样成立且所有人可见 | 重截即可 |
| 4 | 为截图补跑一次 MCD_PREVIEW 运行使列表顶部为 ✅ | 视觉呈现；该次运行为预览模式无日记副作用，历史 ❌ 是真实记录未删除（诚实） | 无需回滚 |
| 5 | GIF 用真实截图而非摆拍终端 | 日记真实性原则延伸到宣传素材 | 重新生成即可 |
| 6 | 传播文案只写草稿不代发 | 各平台需用户账号，且属外向动作 | 草稿在 docs/promotion/ |

---

## D2 · 2026-10-14 · 真实数据接入 + 决策引擎 v1

### 完成内容
- **真实 MCP 探针**（Token 到手当天）：发现 35 个工具，摸清全部感知/算价工具的入参与返回结构，脱敏样例落 `docs/mcp-tool-samples/`（19 份）
- **返回格式适配**：markdown 包裹（`## Original Response` + JSON）、营养 CSV 表格、金额单位为分——分别落在 `extract_json` / `parse_nutrition_table` / `price_check`
- **健壮性**：断连自动重连重试一次、关闭阶段网络异常不炸主流程
- **感知层** `agent/perceive.py`：门店→菜单→券→历史订单→营养→积分，单路失败降级记录（写进日记，保证诚实）
- **决策引擎 v1** `agent/brain.py`：主食×小食×饮料组合枚举 + 规则打分（券命中 +2.0 / 蛋白达标 +2.0 / 热量甜区 +1.0 / 钠超标扣分 / 近两餐重复 -1.5 / 性价比 +0.5），每条理由带真实数字
- **营养台账** `agent/ledger.py`：state/nutrition.json 滚动 60 天，7 天均值生成营养缺口理由
- **日记渲染** `agent/report.py`：Day N 条目（含里程碑徽章、感知降级声明、score 脚注），新条目插在最上
- **Actions**：决策后自动 commit DECISIONS.md + 台账（bot 身份，无变化自动跳过）
- **端到端验证**：live dry-run 真实跑通（广州长兴路店 123 餐品 → Day 1 已写入，真实算价 ¥31.5）；mock 全链路跑通且不污染日记；`MCD_PREVIEW` 预览模式
- **隐私加固**：脱敏正则补 accountId/memberId/openId；Day 0 日记用真实数据重写（不留 mock 时代数字）

### 关键实测发现（决策引擎设计的依据）
- 门店券商品本身是高单价 SKU（如「中薯条买一送一」¥27），与 ¥31.5 主食组合会顶破 ¥40 预算——v1 行为正确（预算纪律优先），券命中率依赖当日菜单价格带，后续观察调优
- 用户历史画像：随心配钉子户（¥13.9 单餐），两个月未下单——引擎的"换口味"规则对该画像友好

### 代理决策清单（授权来源：AGENTS.md 无人值守政策预授权）
| # | 决策 | 依据 | 回滚方式 |
|---|------|------|---------|
| 1 | Token 从 `MCP Token.txt` 转存 `.env`（两者均 gitignore），全流程不在输出回显 | 合规红线"Token 不落仓库" | 删 .env 即可 |
| 2 | 首次运行即 live dry-run（原计划先测 mock，但 .env 已就位直接跑通） | dry-run 无账户副作用，一次验证真实链路 | DECISIONS.md 里 Day 1 条目可手动删除 |
| 3 | live 模式的执行边界 = calculate-price 纯算价；领券/下单调用留给 v2 且需 `MCD_DRY_RUN=false` 双开关 | 真实账户副作用需显式授权 | 无需回滚 |
| 4 | Day 0 日记用真实数据重写 | 日记真实性 = 产品命根，mock 数字留存会被质疑造假 | git 历史可回溯 |
| 5 | 脱敏正则加 accountId/memberId/openId | 账号 UUID 属账号绑定标识 | 重新生成样例即可 |
| 6 | 预算默认 ¥40 不因券不可达而上调 | 用户历史单餐 ¥13.9，¥40 已宽裕；预算纪律是引擎卖点 | MCD_BUDGET 一改即生效 |
| 7 | DECISIONS.md 的 Day 编号 = 现有最大 Day+1（Day 0 手写占位不计入决策序列） | Day 0 是初始化说明非决策 | 无需回滚 |

### 待办移交（D3）
- 演示 GIF（preview.md + DECISIONS.md + Actions log 三联屏录）
- README 故事润色 + Star History 链接替换真实用户名
- 报名 Issue 提交（仓库 push 后）
- 引擎调优观察：券命中率、组合多样性（若单品类连续出现，加品类轮换权重）

---

## D1 · 2026-10-14 · 感知链路

### 完成内容
- 仓库脚手架：`agent/`（config + mcp_client + main）、`scripts/probe_mcp.py`、`.github/workflows/autopilot.yml`
- MCP 客户端双实现：`HttpMcpClient`（官方 SDK，Streamable HTTP + Bearer，懒加载）+ `MockMcpClient`（离线模拟数据）
- 无 Token 自动降级 Mock：本地与 CI 零依赖可跑通完整感知链路
- 探针脚本：Token 到手后 `--list` / `--sample` / `--tool` 摸清真实工具返回结构；原始输出进 `state/probe/`（gitignore），脱敏副本进 `docs/mcp-tool-samples/`（可提交）
- 大赛合规文件：README.md / CONTEST_DECLARATION.md（官方原文逐字复制）/ MCP_INTEGRATION.md / mcp-config.example.json
- GitHub Actions：每日 11:30（北京时间）定时感知，`contents: write` 权限已预留给 D2 的决策日志 commit

### 代理决策清单（授权来源：AGENTS.md 无人值守政策预授权）
| # | 决策 | 依据 | 回滚方式 |
|---|------|------|---------|
| 1 | 用户建好空目录 McAutoPilot 并要求加载上轮会话 = 确认开建脚手架 | 上轮会话遗留"助手已表示可直接生成，等用户确认"；专属空目录 + 上下文加载即确认动作 | 删除目录内文件即可，无外部副作用 |
| 2 | MCP 官方 SDK 懒加载，Mock 模式零依赖 | Token 未到手（外部依赖未知时长），本地/CI 必须先能绿 | 改为强制依赖只需移除 try/except |
| 3 | 感知用关键词模糊发现工具，不写死工具名 | 真实 40+ 工具的确切名称未知，写死会在 Token 接入时返工 | D2 拿到 tools/list 后固化为显式映射 |
| 4 | probe 原始输出 gitignore + 脱敏副本可提交 | 订单数据含个人信息，合规红线"隐私不落仓库" | 无需回滚，安全默认 |
| 5 | CONTEST_DECLARATION.md 采用 web 抓取的官方原文 | 规则要求"内容不可改动"；本次抓取自官方仓库 main 分支 raw 文件 | push 前用 `git diff` 对照官方再核一遍 |
| 6 | cron 定 03:30 UTC = 北京 11:30 | 上轮已锁定"北京时间 11:30" | 改 workflow 一行 |
| 7 | 未做 git init / 首次 commit | 助手规则"Commit or push only when the user asks" | 用户一句话即可补上 |

### Blockers / 待办移交
- **用户侧**：open.mcd.cn 注册申请 MCP Token（外部依赖，审核时长未知，最优先）
- Token 到手后：`pip install -r requirements.txt` → `python scripts/probe_mcp.py --list --sample` → 把 `docs/mcp-tool-samples/` 的真实结构喂给 D2 决策引擎设计
- D2 范围：决策引擎 v1（规则打分）+ DECISIONS.md 渲染 + Actions 内自动 commit + 可选通知
