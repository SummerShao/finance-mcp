# Finance MCP Server

A [Model Context Protocol (MCP)](https://modelcontextprotocol.io) server that gives AI assistants (Claude, etc.) comprehensive financial data capabilities — covering A-shares (China), US stocks, and macro economics.

## Features

### A股行情与K线
| Tool | Description | 数据源 |
|------|-------------|--------|
| `get_stock_history` | 历史日K线（前/后复权）+ MA5/10/20/60 + MACD + RSI14 | Tushare Pro |
| `get_realtime_quote` | 个股实时行情（价格/涨跌幅/成交量） | Tushare |
| `get_stock_mins` | 分钟级K线（1/5/15/30/60min），日内交易分析 | Tushare Pro |
| `get_realtime_list_top` | 全市场实时排行榜（涨幅/跌幅/成交额/换手率） | 新浪财经 |

### A股基本面
| Tool | Description | 数据源 |
|------|-------------|--------|
| `get_stock_info` | 基本信息（行业/地区/上市日期/市场类型） | Tushare Pro |
| `get_daily_basic` | 每日估值指标（PE/PB/PS/换手率/市值） | Tushare Pro |
| `get_financial_indicators` | 关键财务指标（ROE/净利率/毛利率/成长率/偿债能力） | Tushare Pro |
| `get_income_statement` | 利润表（营收/净利润/三费/EPS/EBITDA） | Tushare Pro |
| `get_balance_sheet` | 资产负债表（资产/负债/权益结构） | Tushare Pro |
| `get_cashflow` | 现金流量表（经营/投资/筹资现金流） | Tushare Pro |
| `get_peer_comparison` | 同行业估值横向对比（PE/PB百分位排名） | Tushare Pro |
| `get_research_report` | 券商研报（评级/目标价/盈利预测） | Tushare Pro |

### A股资金与博弈
| Tool | Description | 数据源 |
|------|-------------|--------|
| `get_realtime_moneyflow` | 个股实时资金流向（超大/大/中/小单净流入） | 东方财富 |
| `get_market_overview` | 大盘实时概览（主要指数 + 涨跌家数） | 东方财富 |
| `get_sector_ranking` | 板块涨跌幅排行（行业/概念板块 + 领涨股） | 新浪财经 |
| `get_hsgt_top10` | 沪深港通十大成交股（北向/南向资金动向） | Tushare Pro |
| `get_top_list` | 龙虎榜每日明细（上榜原因 + 机构席位） | Tushare Pro |
| `get_margin_detail` | 融资融券交易明细（杠杆情绪指标） | Tushare Pro |
| `get_stk_holdernumber` | 股东人数变化（筹码集中度参考） | Tushare Pro |
| `get_share_float` | 限售股解禁计划（抛压预期） | Tushare Pro |

### 宏观经济
| Tool | Description | 数据源 |
|------|-------------|--------|
| `get_macro_data` | 宏观经济指标（CPI/PPI/M2/GDP/SHIBOR） | Tushare Pro |

### 美股分析
| Tool | Description | 数据源 |
|------|-------------|--------|
| `get_us_stock_history` | 美股历史K线（OHLCV） | Finnhub |
| `get_fundamental_analysis` | 基本面（公司概况/财务指标/股权结构/SEC文件） | Finnhub |
| `get_technical_analysis` | 技术面（SMA/EMA/RSI/MACD/支撑阻力位） | Polygon.io |
| `get_sentiment_analysis` | 情绪面（新闻情绪/分析师评级/内部人交易） | Finnhub |
| `get_comprehensive_analysis` | 全维度综合分析（基本面+技术面+情绪面） | All |

---

## Prerequisites

| 服务 | 用途 | 费用 |
|------|------|------|
| **Tushare Pro** | A股全部功能（必需） | 免费注册，[tushare.pro](https://tushare.pro/register) |
| **东方财富 / 新浪财经** | 实时资金流/大盘/板块排行 | 免费，无需申请 |
| **Finnhub** | 美股分析（可选） | 免费套餐，[finnhub.io](https://finnhub.io) |
| **Polygon.io** | 美股技术指标（可选） | 免费套餐，[polygon.io](https://polygon.io) |

---

## Installation

### 方式一：本地直接运行（stdio）

```bash
# 1. 克隆项目
git clone <repo-url>
cd finance-mcp-server

# 2. 安装依赖（Python 3.11+）
pip install -r requirements.txt

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 TUSHARE_TOKEN（必需）和美股 API Key（可选）

# 4. 启动
python server.py
```

### 方式二：Docker 运行（SSE）

```bash
# 1. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 TUSHARE_TOKEN

# 2. 构建并启动
docker compose up -d

# 验证
curl http://localhost:8000/sse
```

---

## Configuration

编辑 `.env` 文件：

```env
# A股数据（必需 — 免费注册 https://tushare.pro/register）
TUSHARE_TOKEN=your_tushare_token_here

# 美股基本面 & 情绪分析（可选）
FINNHUB_API_KEY=your_finnhub_api_key_here

# 美股技术指标（可选）
POLYGON_API_KEY=your_polygon_api_key_here

# 传输方式：stdio（本地）| sse（Docker/远程）
MCP_TRANSPORT=stdio
MCP_PORT=8000
```

---

## Connect to Claude

### Claude Desktop（stdio 模式）

编辑 Claude Desktop 配置文件：

- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "finance-mcp": {
      "command": "python",
      "args": ["/absolute/path/to/finance-mcp-server/server.py"]
    }
  }
}
```

### Claude Code（SSE 模式）

在 `.claude/mcp.json` 或 `~/.claude/mcp.json` 中配置：

```json
{
  "mcpServers": {
    "finance-mcp": {
      "type": "sse",
      "url": "http://localhost:8000/sse"
    }
  }
}
```

---

## Usage Examples

```
帮我看看贵州茅台最近的K线走势和技术指标

今天涨幅前20的股票有哪些？

贵州茅台的实时资金流向怎么样？主力在买还是在卖？

看看宁德时代的财务指标和同行业对比

今天龙虎榜有哪些票？机构在买什么？

最近的宏观经济数据怎么样？CPI和M2趋势如何？

NVDA 最近的综合分析怎么样？
```

---

## Project Structure

```
finance-mcp-server/
├── server.py              # MCP 服务入口，所有 tool 注册
├── services/
│   ├── tushare.py         # A股核心数据（行情/财务/资金/宏观）
│   ├── eastmoney.py       # 实时资金流/大盘概览（东方财富）
│   ├── sina_sector.py     # 板块排行（新浪财经）
│   └── us_stock.py        # 美股分析（Finnhub + Polygon.io）
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── .env.example
```

---

## License

MIT
