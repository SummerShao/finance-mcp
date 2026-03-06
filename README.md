# Finance MCP Server

A [Model Context Protocol (MCP)](https://modelcontextprotocol.io) server that gives AI assistants (Claude, etc.) real financial data capabilities — covering A-shares, US stocks, and market intelligence tools.

**A股数据全部免费，无需 API Key。**

## Features

### A股行情与K线
| Tool | Description | 数据源 |
|------|-------------|--------|
| `get_stock_history` | 历史日K线（前/后复权）+ MA5/10/20/60 + MACD + RSI14 | 东方财富 |
| `get_realtime_list_top` | 全市场实时排行榜（涨幅/跌幅/成交额/换手率/主力净流入等） | 东方财富 |
| `get_baidu_stock_quote` | 多维度股票数据（行情/资金/财务/公司/资讯，5个tab） | 百度股市通 |

### A股资金与市场
| Tool | Description | 数据源 |
|------|-------------|--------|
| `get_realtime_moneyflow` | 个股实时资金流向：超大/大/中/小单买卖净流入 | 东方财富 |
| `get_market_overview` | 大盘实时概览：主要指数行情 + 全市场涨跌统计 | 东方财富 |
| `get_sector_ranking` | 板块涨跌幅排行（行业板块/概念板块）+ 领涨股 | 新浪财经 |

### 美股分析
| Tool | Description |
|------|-------------|
| `get_us_stock_history` | 美股历史K线（OHLCV） |
| `get_fundamental_analysis` | 基本面：公司概况、财务指标、股权结构、高管、SEC 文件 |
| `get_technical_analysis` | 技术面：SMA/EMA/RSI/MACD/支撑阻力位/综合信号 |
| `get_sentiment_analysis` | 情绪面：新闻情绪、社交情绪、内部人交易、分析师评级变化 |
| `get_comprehensive_analysis` | 全维度综合分析（基本面 + 技术面 + 情绪面一次返回）|

---

## Prerequisites

| 服务 | 用途 | 费用 |
|------|------|------|
| **东方财富 / 百度股市通 / 新浪财经** | A股全部功能 | **免费，无需申请** |
| **Finnhub** | 美股基本面/情绪（可选） | 免费套餐可用，[finnhub.io](https://finnhub.io) |
| **Polygon.io** | 美股技术指标（可选） | 免费套餐可用，[polygon.io](https://polygon.io) |

---

## Installation

### 方式一：本地直接运行（stdio，适合 Claude Desktop）

```bash
# 1. 克隆项目
git clone https://github.com/your-username/finance-mcp-server.git
cd finance-mcp-server

# 2. 安装依赖（建议 Python 3.11+）
pip install -r requirements.txt

# 3. 配置 API Key（仅美股功能需要，A股无需配置）
cp .env.example .env
# 编辑 .env，填入美股 API Key（可选）

# 4. 启动（stdio 模式）
python server.py
```

### 方式二：Docker 运行（SSE，适合 Claude Code / 远程访问）

```bash
# 1. 克隆项目
git clone https://github.com/your-username/finance-mcp-server.git
cd finance-mcp-server

# 2. 配置 API Key（仅美股功能需要）
cp .env.example .env

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
# 美股基本面 & 情绪分析（可选）
FINNHUB_API_KEY=your_finnhub_api_key_here

# 美股技术指标（可选）
POLYGON_API_KEY=your_polygon_api_key_here

# 传输方式：stdio（本地）| sse（Docker/远程）
MCP_TRANSPORT=stdio
MCP_PORT=8000
```

> A股数据全部来自免费公开 API（东方财富、百度股市通、新浪财经），无需任何 API Key。

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
帮我看看贵州茅台最近的K线走势和技术指标

今天涨幅前20的股票有哪些？

贵州茅台的实时资金流向怎么样？

帮我查一下 600519 的财务数据和公司信息

今天哪些板块涨得好？概念板块排行呢？

NVDA 最近的综合分析怎么样？
```

---

## Project Structure

```
finance-mcp-server/
├── server.py              # MCP 服务入口，所有 tool 注册
├── services/
│   ├── stock_resolver.py  # 股票名称↔代码解析（东方财富）
│   ├── eastmoney.py       # K线/排行/资金流/大盘（东方财富）
│   ├── baidu_stock.py     # 多维度股票数据（百度股市通）
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
