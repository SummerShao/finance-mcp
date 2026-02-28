# Finance MCP Server

A [Model Context Protocol (MCP)](https://modelcontextprotocol.io) server that gives AI assistants (Claude, etc.) real financial data capabilities — covering A-shares, US stocks, and market intelligence tools.

## Features

### A股实时行情
| Tool | Description |
|------|-------------|
| `get_realtime_by_name` | 实时报价：价格、涨跌幅、成交量、买一卖一盘口（最多50只）|
| `get_realtime_tick_by_name` | 当日全部逐笔成交明细（时间、价格、方向、成交量）|
| `get_realtime_list_top` | 全市场实时排行榜（涨幅榜/跌幅榜/成交额/换手率等）|

### A股历史行情与估值
| Tool | Description |
|------|-------------|
| `get_stock_history` | 历史日K线（前/后复权）+ MA5/10/20/60 + MACD + RSI14 |
| `get_daily_basic` | 每日估值指标：PE/PB/PS/股息率/换手率/量比/总市值/流通市值 |
| `get_moneyflow` | 个股资金流向：大单/中单/小单买卖净流入（覆盖2010年至今）|

### A股基本面
| Tool | Description |
|------|-------------|
| `get_stock_info` | 股票基本信息：行业/地区/上市日期/市场/沪深港通标识 |
| `get_financial_indicators` | 财务指标：ROE/ROA/净利率/毛利率/流动比率/资产负债率/净利润增速/FCF |
| `get_income_statement` | 利润表：营收/净利润/归母净利/三费/EPS/EBIT/EBITDA/研发费用 |

### A股资金与情绪
| Tool | Description |
|------|-------------|
| `get_hsgt_top10` | 沪深港通十大成交股（北向/南向资金流入 Top10）|
| `get_daban_indicators` | 涨停板核心因子：封板时间/质量、封单力度、筹码分布、游资动向等20+维度 |
| `get_market_sentiment_report` | 市场涨停板情绪复盘：连板梯队、热门板块 Top20、情绪评级 |

### 美股分析
| Tool | Description |
|------|-------------|
| `get_fundamental_analysis` | 基本面：公司概况、财务指标、股权结构、高管、SEC 文件 |
| `get_technical_analysis` | 技术面：SMA/EMA/RSI/MACD/支撑阻力位/综合信号 |
| `get_sentiment_analysis` | 情绪面：新闻情绪、社交情绪、内部人交易、分析师评级变化 |
| `get_comprehensive_analysis` | 全维度综合分析（基本面 + 技术面 + 情绪面一次返回）|

### 搜索
| Tool | Description |
|------|-------------|
| `search_x_posts` | X (Twitter) 热帖搜索（按热度+时间衰减排序）|

---

## Prerequisites

申请以下 API Key（按需，只需要用到的功能对应的 Key）：

| 服务 | 用途 | 申请地址 | 费用 |
|------|------|----------|------|
| **Tushare Pro** | A股全部功能 | [tushare.pro](https://tushare.pro/register?reg=700000) | 免费注册，部分接口需积分 |
| **Finnhub** | 美股基本面/情绪 | [finnhub.io](https://finnhub.io) | 免费套餐可用 |
| **Polygon.io** | 美股技术指标 | [polygon.io](https://polygon.io) | 免费套餐可用 |
| **X API** | Twitter 搜索 | [developer.x.com](https://developer.x.com) | 免费套餐可用 |

---

## Installation

### 方式一：本地直接运行（stdio，适合 Claude Desktop）

```bash
# 1. 克隆项目
git clone https://github.com/your-username/finance-mcp-server.git
cd finance-mcp-server

# 2. 安装依赖（建议 Python 3.11+）
pip install -r requirements.txt

# 3. 配置 API Key
cp .env.example .env
# 编辑 .env，填入你的 API Key

# 4. 启动（stdio 模式）
python server.py
```

### 方式二：Docker 运行（SSE，适合 Claude Code / 远程访问）

```bash
# 1. 克隆项目
git clone https://github.com/your-username/finance-mcp-server.git
cd finance-mcp-server

# 2. 配置 API Key
cp .env.example .env
# 编辑 .env，填入你的 API Key

# 3. 构建并启动
docker compose up -d

# 验证服务正常
curl http://localhost:8000/sse
# 看到 event: endpoint 即为成功
```

---

## Configuration

编辑 `.env` 文件：

```env
# A股行情 & 涨停板分析（必填，用于所有 A股工具）
TUSHARE_TOKEN=your_tushare_token_here

# 美股基本面 & 情绪分析（可选）
FINNHUB_API_KEY=your_finnhub_api_key_here

# 美股技术指标（可选）
POLYGON_API_KEY=your_polygon_api_key_here

# X (Twitter) 搜索（可选）
X_API_KEY=your_x_bearer_token_here

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
      "args": ["/absolute/path/to/finance-mcp-server/server.py"],
      "env": {
        "TUSHARE_TOKEN": "your_token_here"
      }
    }
  }
}
```

重启 Claude Desktop 后即可使用。

---

### Claude Code（SSE 模式）

Docker 启动后，在项目的 `.claude/mcp.json` 中配置（或 `~/.claude/mcp.json` 全局配置）：

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

配置完成后，直接用自然语言提问即可，AI 会自动调用合适的工具组合：

```
帮我分析贵州茅台，包括基本面、估值和近期走势

对比宁德时代和比亚迪最近两年的财务指标

今天北向资金重点买入了哪些股票？

分析一下浦发银行的涨停板情况

NVDA 最近的综合分析怎么样？
```

---

## Project Structure

```
finance-mcp-server/
├── server.py              # MCP 服务入口，所有 tool 注册
├── services/
│   ├── tushare.py         # A股行情、历史K线、财务数据（Tushare Pro）
│   ├── daban.py           # 涨停板分析（同花顺 via Tushare Pro）
│   ├── us_stock.py        # 美股分析（Finnhub + Polygon.io）
│   └── x_search.py        # X/Twitter 搜索
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── .env.example
```

---

## Tushare 积分说明

部分接口需要一定积分，常用接口的最低要求：

| 接口 | 最低积分 |
|------|----------|
| `stock_basic` / `daily` / `adj_factor` | 免费 |
| `daily_basic`（PE/PB/市值）| 120 |
| `moneyflow`（资金流向）| 120 |
| `fina_indicator`（财务指标）| 2000 |
| `income`（利润表）| 2000 |
| `hsgt_top10`（北向资金）| 600 |
| 涨停板相关（ths_* 系列）| 2000+ |

免费注册后默认有 100 积分，可通过实名认证、邀请等方式提升。

---

## License

MIT
