# MCP_INTEGRATION.md — 麦当劳 MCP 集成说明

本项目基于**麦当劳中国官方 MCP Server**（[M-China/mcd-mcp-server](https://github.com/M-China/mcd-mcp-server)）构建，符合大赛技术要求。

## 接入信息

| 项 | 值 |
|---|---|
| Endpoint | `https://mcp.mcd.cn` |
| 传输协议 | Streamable HTTP（MCP 规范） |
| 认证方式 | `Authorization: Bearer <MCP_TOKEN>` |
| 频率限制 | 600 请求/分钟 |
| Token 申请 | [open.mcd.cn](https://open.mcd.cn)（免费，需审核） |

## 客户端接入配置

参考 [mcp-config.example.json](mcp-config.example.json)（占位符 `${MCD_MCP_TOKEN}` 仅作示例，真实 Token 通过环境变量注入，**永不写入仓库**）：

```json
{
  "mcpServers": {
    "mcd": {
      "type": "streamablehttp",
      "url": "https://mcp.mcd.cn",
      "headers": {
        "Authorization": "Bearer ${MCD_MCP_TOKEN}"
      }
    }
  }
}
```

本项目在 Python 侧通过官方 `mcp` SDK（`mcp.client.streamable_http`）接入，见 `agent/mcp_client/http_client.py`。客户端实现要点：

- **限流自律**：串行调用 + 请求间隔（默认 0.15s，对齐 600 req/min 上限并留余量）；
- **断连重试**：公网偶发抖动时重建会话重试一次，关闭阶段网络异常不炸主流程；
- **懒加载**：无 Token 场景自动降级到 `MockMcpClient`（工具名与返回结构逐字段对齐真实服务），离线也能跑完整链路；
- **归一化返回**：markdown 包裹文本自动提取 JSON，上层决策引擎不感知协议细节。

## 实际用到的 MCP 工具（2026-10-14 实测，共发现 35 个工具）

| 决策阶段 | 工具 | 说明 |
|---|---|---|
| 感知 | `query-nearby-stores` | 收藏门店 → storeCode（后续工具的必要入参） |
| 感知 | `query-meals` | 门店在售餐品：categories + meals{code: {name, currentPrice, originalPrice}} |
| 感知 | `query-store-coupons` | 门店+订单类型维度的可用券（couponId/couponCode/适用商品/有效期） |
| 感知 | `order-list` | 历史订单（仅取菜品名/数量/金额做画像，隐私字段不落地） |
| 感知 | `list-nutrition-foods` | 营养成分库（`[N]{列名}: CSV行` 表格文本） |
| 感知 | `query-my-account` | 麦享会积分余额 |
| 执行(dry-run) | `calculate-price` | 含优惠真实算价（纯计算无副作用）——"订单草稿"的核心 |

> 完整返回结构样例见 [docs/mcp-tool-samples/](docs/mcp-tool-samples/)（已脱敏）。
> 写操作类工具（`create-order` / `auto-bind-coupons` / `cancel-order` 等）仅在
> `MCD_DRY_RUN=false` 的 live 模式才会被调用，v1 默认永不触碰。

### 返回格式的两个坑（适配都做在了 `agent/mcp_client/base.py::extract_json`）

1. **LLM 友好文本包裹**：多数工具返回「markdown 字段说明 + `## Original Response` + 原始 JSON」，需要截取 Original Response 段再解析；
2. **营养表是 CSV 文本**：`list-nutrition-foods` 返回 `[160]{productName,...,energyKcal,...}:` + CSV 行，按表格解析（`agent/perceive.py::parse_nutrition_table`）；
3. **金额单位是分**：`calculate-price` 返回的 price/discount 均为分，渲染前除以 100。

## 业务价值

麦当劳 MCP 把"点餐"从 App 内的交互行为，变成了可编程的开放能力。本项目展示的价值方向：

1. **决策自动化**：把高频、低愉悦度、信息过载的日常决策（吃什么/怎么凑单）交给有记忆、有约束的 Agent；
2. **券的利用率**：人守着 30 张券会过期，Agent 把"今天最优券"当作每日约束求解的一部分，让权益不被浪费；
3. **可解释的消费**：每笔决策附结构化理由与营养台账，消费记录从流水变成可回溯的决策日志；
4. **无服务器的常驻 Agent**：GitHub Actions 即运行时，fork 即私有部署，Token 走 Secrets，零基础设施门槛。

## 合规要点

- Token 仅从环境变量 / GitHub Secrets 读取，仓库内零硬编码；
- 订单等个人数据经字段白名单过滤后才进入任何可提交文件；探针脚本默认输出脱敏副本；
- 默认 dry-run，真实下单需显式开启；
- 项目措辞不贬损品牌、不与竞品做对比（详见 [CONTEST_DECLARATION.md](CONTEST_DECLARATION.md)）。
