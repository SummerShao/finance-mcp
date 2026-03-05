#!/usr/bin/env python3
"""
Finance MCP Server
------------------
Tools:
  A股实时:  get_realtime_by_name, get_realtime_tick_by_name, get_realtime_list_top
  A股历史:  get_stock_history, get_daily_basic, get_moneyflow
  A股实时资金: get_realtime_moneyflow
  A股基本面: get_stock_info, get_financial_indicators, get_income_statement
  A股资金:  get_hsgt_top10
  涨停板:   get_daban_indicators, get_market_sentiment_report
  美股历史: get_us_stock_history
  美股分析: get_fundamental_analysis, get_technical_analysis,
            get_sentiment_analysis, get_comprehensive_analysis
  搜索:     search_x_posts

Transport:
  stdio (default) — for local / Claude Desktop use
  sse             — set MCP_TRANSPORT=sse for Docker HTTP mode
"""
import os
import json
import logging
from datetime import date as _date
from typing import Optional
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv()
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

# ── Service singletons ───────────────────────────────────────────────────────

from services.tushare import TushareService
from services.daban import ThsDabanService
from services.us_stock import USStockService
from services.x_search import XSearchService
from services.eastmoney import EastMoneyService
from services.baidu_stock import BaiduStockService

_tushare = TushareService()
_eastmoney = EastMoneyService(_tushare)
_daban = ThsDabanService()
_us_stock = USStockService()
_x_search = XSearchService()
_baidu_stock = BaiduStockService()

# ── MCP server ───────────────────────────────────────────────────────────────

_port = int(os.getenv("MCP_PORT", "8000"))

mcp = FastMCP(
    "finance-mcp",
    instructions=(
        "Financial analysis tools for A-shares (China) and US stocks.\n"
        "A-share capabilities: real-time quotes, tick data, historical K-line with technical indicators "
        "(MA/MACD/RSI), daily valuation metrics (PE/PB/market cap), financial statements (income/ratios), "
        "money flow (historical via Tushare and real-time via East Money), "
        "northbound capital (HSGT top10), limit-up board analysis, and market sentiment.\n"
        "US stock capabilities: historical K-line (get_us_stock_history), fundamental, technical, and sentiment analysis.\n"
        "Also supports X/Twitter post search."
    ),
    host="0.0.0.0",
    port=_port,
)


# ── A股实时行情 ──────────────────────────────────────────────────────────────

@mcp.tool()
async def get_realtime_by_name(stock_names: str) -> str:
    """
    获取A股实时报价（按股票名称批量查询）

    Args:
        stock_names: 股票名称，多个用逗号分隔，最多50只。
                     例: '浦发银行' 或 '浦发银行,平安银行,贵州茅台'
    Returns:
        JSON: 每只股票的实时价格、涨跌幅、成交量、买一卖一盘口等
    """
    result = await _tushare.get_realtime_by_name(stock_names)
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
async def get_realtime_tick_by_name(stock_name: str, src: str = "sina") -> str:
    """
    获取单只A股当日全部分笔成交明细

    Args:
        stock_name: 股票名称，仅支持单只。例: '浦发银行'
        src: 数据源，'sina'(新浪,默认) 或 'dc'(东方财富)
    Returns:
        JSON: 从开盘至今的所有逐笔成交记录（时间、价格、方向、成交量）
    """
    result = await _tushare.get_realtime_tick_by_name(stock_name, src)
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
async def get_realtime_list_top(
    src: str = "dc",
    top_n: int = 20,
    sort_by: str = "pct_change",
    ascending: bool = False,
) -> str:
    """
    获取A股全市场实时排行榜

    Args:
        src: 数据源，'dc'(东方财富,默认,字段更丰富) 或 'sina'(新浪)
        top_n: 返回前N条，默认20
        sort_by: 排序字段，常用: 'pct_change'(涨跌幅,默认), 'amount'(成交额),
                 'volume'(成交量), 'turnover_rate'(换手率), 'vol_ratio'(量比),
                 'swing'(振幅), 'rise'(涨速), 'total_mv'(总市值)
        ascending: False=降序(默认，取涨幅榜), True=升序(取跌幅榜)
    Returns:
        JSON: 排名前N的股票实时行情数据
    """
    result = await _tushare.get_realtime_list_top(src, top_n, sort_by, ascending)
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
async def get_moneyflow(
    stock_names: Optional[str] = None,
    trade_date: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> str:
    """
    获取A股个股资金流向（大单/中单/小单买卖明细）

    数据来源: Tushare Pro moneyflow 接口，覆盖2010年至今。
    订单分级:
      小单 ≤ 50万 | 中单 50~200万 | 大单 200~1000万 | 特大单 ≥ 1000万

    Args:
        stock_names: 股票名称，多个用逗号分隔。例: '兴业银锡' 或 '贵州茅台,宁德时代'
                     与 trade_date 至少提供一个
        trade_date:  查询单日，格式 'YYYY-MM-DD' 或 'YYYYMMDD'
        start_date:  日期范围起始，格式 'YYYY-MM-DD' 或 'YYYYMMDD'
        end_date:    日期范围结束，格式 'YYYY-MM-DD' 或 'YYYYMMDD'
    Returns:
        JSON: 每条记录包含各级别买卖量/额及净流入量/额（万元）
    """
    result = await _tushare.get_moneyflow(stock_names, trade_date, start_date, end_date)
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
async def get_realtime_moneyflow(stock_names: str) -> str:
    """
    获取A股个股实时资金流向（盘中实时数据，来源东方财富）

    数据源: 东方财富实时资金流API，免费无需配置。
    适用场景: 交易时段(9:30-15:00)查看当日实时主力/散户资金流入流出。
    非交易时段返回最近一个交易日的累计数据。

    资金分级（东方财富标准）:
      小单 ≤ 5万 | 中单 5~20万 | 大单 20~100万 | 超大单 ≥ 100万
    注: 与 get_moneyflow(Tushare) 的分级标准不同，不宜直接对比。

    Args:
        stock_names: 股票名称，多个用逗号分隔，最多50只。
                     例: '湖南黄金' 或 '贵州茅台,宁德时代,比亚迪'
    Returns:
        JSON: 每只股票的实时资金流向，包含:
              - summary: 主力(大单+超大单) vs 散户(中单+小单) 流入/流出/净流入
              - detail: 超大单/大单/中单/小单各自的买入、卖出、净流入
              金额单位: 万元
    """
    result = await _eastmoney.get_realtime_moneyflow(stock_names)
    return json.dumps(result, ensure_ascii=False)


# ── A股历史行情 & 基本面 ─────────────────────────────────────────────────────

@mcp.tool()
async def get_stock_info(stock_names: str) -> str:
    """
    获取A股股票基本信息（行业/地区/上市日期/市场类型）

    Args:
        stock_names: 股票名称，多个用逗号分隔。例: '贵州茅台' 或 '贵州茅台,宁德时代'
    Returns:
        JSON: ts_code/symbol/name/area(省份)/industry(行业)/market/list_date/is_hs(是否沪深港通)
    """
    result = await _tushare.get_stock_info(stock_names)
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
async def get_stock_history(
    stock_names: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    adj: str = "qfq",
    limit: int = 120,
) -> str:
    """
    获取A股历史日K线行情（含复权价格及 MA/MACD/RSI 技术指标）

    数据源: Tushare Pro + 复权因子，覆盖上市至今全部历史。
    技术指标在返回前基于完整历史计算，因此即使 limit=20 也能拿到准确的 MA/MACD/RSI。

    Args:
        stock_names: 股票名称，多个用逗号分隔。例: '贵州茅台' 或 '贵州茅台,宁德时代'
        start_date:  开始日期，格式 'YYYY-MM-DD' 或 'YYYYMMDD'
        end_date:    结束日期，格式 'YYYY-MM-DD' 或 'YYYYMMDD'
        adj:         复权类型，'qfq'=前复权(默认), 'hfq'=后复权, 'none'=不复权
        limit:       返回最近N条记录，默认120。设为0返回全部。
                     技术指标基于完整历史计算后再截取，保证指标值准确。
    Returns:
        JSON: 每只股票的日线数据，含 open/high/low/close/vol/amount +
              MA5/10/20/60 + MACD(dif/dea/bar) + RSI14，按日期升序排列
    """
    result = await _tushare.get_stock_history(stock_names, start_date, end_date, adj, limit)
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
async def get_daily_basic(
    stock_names: Optional[str] = None,
    trade_date: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> str:
    """
    获取A股每日估值指标（PE/PB/PS/换手率/市值）

    数据源: Tushare Pro daily_basic，覆盖2012年至今。
    订阅需求: 至少120积分。

    Args:
        stock_names: 股票名称，多个用逗号分隔。与 trade_date 至少提供一个
        trade_date:  查询单日，格式 'YYYY-MM-DD' 或 'YYYYMMDD'
        start_date:  日期范围起始
        end_date:    日期范围结束
    Returns:
        JSON: PE/PE_TTM/PB/PS/PS_TTM/股息率/换手率/量比/总市值/流通市值 等
    """
    result = await _tushare.get_daily_basic(stock_names, trade_date, start_date, end_date)
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
async def get_financial_indicators(
    stock_names: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 8,
) -> str:
    """
    获取A股关键财务指标（ROE/净利率/成长率/偿债能力）

    数据源: Tushare Pro fina_indicator，覆盖历年季报/半年报/年报。

    Args:
        stock_names: 股票名称，多个用逗号分隔。例: '贵州茅台,宁德时代'
        start_date:  报告期起始，格式 'YYYY-MM-DD' 或 'YYYYMMDD'
        end_date:    报告期结束
        limit:       最近N个报告期，默认8（约2年含季报）
    Returns:
        JSON: EPS/BPS/ROE/ROA/净利率/毛利率/流动比率/资产负债率/净利润增速/营收增速/FCF 等
    """
    result = await _tushare.get_financial_indicators(stock_names, start_date, end_date, limit)
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
async def get_income_statement(
    stock_names: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 8,
) -> str:
    """
    获取A股利润表（营业收入/净利润/毛利/三费/EPS）

    数据源: Tushare Pro income，覆盖历年季报/半年报/年报。

    Args:
        stock_names: 股票名称，多个用逗号分隔。例: '贵州茅台'
        start_date:  报告期起始，格式 'YYYY-MM-DD' 或 'YYYYMMDD'
        end_date:    报告期结束
        limit:       最近N个报告期，默认8
    Returns:
        JSON: 营收/营业成本/营业利润/利润总额/净利润/归母净利润/EPS/EBIT/EBITDA/研发费用 等
    """
    result = await _tushare.get_income_statement(stock_names, start_date, end_date, limit)
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
async def get_hsgt_top10(
    trade_date: Optional[str] = None,
    market_type: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> str:
    """
    获取沪深港通十大成交股（北向/南向资金 Top10）

    每交易日18~20点更新，反映外资对A股的关注重点和资金流向。

    Args:
        trade_date:  查询单日，格式 'YYYY-MM-DD' 或 'YYYYMMDD'
        market_type: 市场类型，'1'=沪股通, '3'=深股通（不填=全部）
        start_date:  日期范围起始
        end_date:    日期范围结束
    Returns:
        JSON: 排名/ts_code/名称/收盘价/涨跌/买入金额/卖出金额/净流入金额 等
    """
    result = await _tushare.get_hsgt_top10(trade_date, market_type, start_date, end_date)
    return json.dumps(result, ensure_ascii=False)


# ── 涨停板分析 ───────────────────────────────────────────────────────────────

@mcp.tool()
async def get_daban_indicators(stock_names: str, date: str) -> str:
    """
    获取A股打板核心因子（涨停板决策指标）

    分析维度包括：封板时间/质量、封单力度、筹码分布、资金流向、
    游资动向、板块地位、市场情绪等20+个关键因子。

    Args:
        stock_names: 股票名称，多个用逗号分隔。例: '利欧股份,中信证券'
        date: 查询日期，格式 'YYYY-MM-DD' 或 'YYYYMMDD'
    Returns:
        JSON: 每只股票的详细打板因子数据
    """
    result = await _daban.get_daban_indicators(stock_names, date)
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
async def get_market_sentiment_report(date: str = "") -> str:
    """
    获取A股市场涨停板情绪复盘报告

    返回连板梯队（N板、首板）、热门板块 Top20、市场情绪评级等，
    格式紧凑，适合LLM快速理解当日市场结构。

    Args:
        date: 查询日期，格式 'YYYY-MM-DD' 或 'YYYYMMDD'，不传则默认当天
    Returns:
        JSON: {date, summary, ladder:{N板:[...],...}, hot_sectors:[...]}
    """
    if not date:
        date = _date.today().strftime("%Y%m%d")
    result = await _daban.get_market_sentiment_report(date)
    return json.dumps(result, ensure_ascii=False)


# ── 美股分析 ─────────────────────────────────────────────────────────────────

@mcp.tool()
async def get_us_stock_history(
    symbol: str,
    start_date: str,
    end_date: str,
    resolution: str = "D",
) -> str:
    """
    获取美股历史K线行情（OHLCV）

    Args:
        symbol: 股票代码，如 'AAPL', 'TSLA', 'BIDU', 'NVDA'
        start_date: 开始日期，格式 'YYYY-MM-DD'
        end_date: 结束日期，格式 'YYYY-MM-DD'
        resolution: K线周期，'D'=日(默认),'W'=周,'M'=月,'1'/'5'/'15'/'30'/'60'=分钟
    Returns:
        JSON: {c:收盘, o:开盘, h:最高, l:最低, v:成交量, t:时间戳, s:状态}
    """
    result = await _us_stock.get_stock_history(symbol, start_date, end_date, resolution)
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
async def get_fundamental_analysis(symbol: str, start_date: str, end_date: str) -> str:
    """
    美股基本面分析

    包含：公司概况、财务指标(PE/PB/ROE等)、股权结构、高管信息、
    SEC文件、财报电话会议摘要。

    Args:
        symbol: 股票代码，如 'AAPL', 'TSLA', 'NVDA'
        start_date: 开始日期，格式 'YYYY-MM-DD'
        end_date: 结束日期，格式 'YYYY-MM-DD'
    Returns:
        JSON: 完整基本面分析数据
    """
    result = await _us_stock.get_fundamental_analysis(symbol, start_date, end_date)
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
async def get_technical_analysis(symbol: str, start_date: str, end_date: str) -> str:
    """
    美股技术分析

    包含：均线(SMA 20/50/200, EMA 12/26)、动量指标(RSI-14, MACD)、
    形态识别、支撑/阻力位、综合技术信号。

    Args:
        symbol: 股票代码，如 'AAPL', 'TSLA', 'NVDA'
        start_date: 开始日期，格式 'YYYY-MM-DD'
        end_date: 结束日期，格式 'YYYY-MM-DD'
    Returns:
        JSON: 技术指标数据
    """
    result = await _us_stock.get_technical_analysis(symbol, start_date, end_date)
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
async def get_sentiment_analysis(symbol: str, start_date: str, end_date: str) -> str:
    """
    美股情绪分析

    包含：新闻情绪评分、社交媒体情绪、内部人交易情绪、
    分析师评级变化(升/降级)、推荐趋势。

    Args:
        symbol: 股票代码，如 'AAPL', 'TSLA', 'NVDA'
        start_date: 开始日期，格式 'YYYY-MM-DD'
        end_date: 结束日期，格式 'YYYY-MM-DD'
    Returns:
        JSON: 情绪分析数据
    """
    result = await _us_stock.get_sentiment_analysis(symbol, start_date, end_date)
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
async def get_comprehensive_analysis(symbol: str, start_date: str, end_date: str) -> str:
    """
    美股全维度综合分析（基本面 + 技术面 + 情绪面）

    一次性返回完整分析报告，适合全面研究某只股票。

    Args:
        symbol: 股票代码，如 'AAPL', 'TSLA', 'NVDA'
        start_date: 开始日期，格式 'YYYY-MM-DD'
        end_date: 结束日期，格式 'YYYY-MM-DD'
    Returns:
        JSON: {fundamental:{...}, technical:{...}, sentiment:{...}}
    """
    result = await _us_stock.get_comprehensive_analysis(symbol, start_date, end_date)
    return json.dumps(result, ensure_ascii=False)


# ── 搜索工具 ─────────────────────────────────────────────────────────────────

@mcp.tool()
def search_x_posts(
    query: str,
    max_results: int = 20,
    exclude_retweets: bool = True,
    exclude_replies: bool = True,
    require_links: bool = True,
    language: str = "en",
    min_engagement: int = 5,
) -> str:
    """
    搜索 X (Twitter) 帖子，按热度+时间衰减排序

    适合市场情绪分析、新闻追踪。

    Args:
        query: 搜索词。例: 'NVDA earnings' 或 'Tesla deliveries'
        max_results: 最大返回数量，默认20
        exclude_retweets: 过滤转发，默认True
        exclude_replies: 过滤回复，默认True
        require_links: 只要含链接的帖子（更高质量），默认True
        language: 语言过滤，默认 'en'
        min_engagement: 最低互动量(点赞+转发+回复)，默认5
    Returns:
        JSON: 按热度分数排序的帖子列表
    """
    result = _x_search.search_x_posts(
        query, max_results, exclude_retweets, exclude_replies,
        require_links, language, min_engagement,
    )
    return json.dumps(result, ensure_ascii=False)


# ── 百度股市通 ──────────────────────────────────────────────────────────────

@mcp.tool()
async def get_baidu_stock_quote(stock_input: str, tab: str = "quote") -> str:
    """
    获取百度股市通(FinScope)股票数据（行情/资金/财务/公司/资讯）

    数据源: 百度股市通（免费，无需 API Key）
    适用场景: 通过百度股市通 URL 或股票代码获取多维度股票数据。

    Args:
        stock_input: 百度股市通 URL 或股票代码
                     URL 示例: https://gushitong.baidu.com/stock/ab-000630
                     代码示例: 000630, 600519
        tab: 数据类型，默认 'quote'
             'quote'   — 实时行情（价格/涨跌/盘口指标/五档买卖）
             'capital' — 资金流向（日/周/月主力散户流入流出 + 超大/大/中/小单分布）
             'finance' — 财务数据（关键指标ROE/ROA/EPS + 利润表/资产负债表/现金流 + 主营构成 + 估值）
             'company' — 公司信息（行业/概念板块/公司资料/高管）
             'news'    — 最新资讯（新闻/快讯/研报/公告）
    Returns:
        JSON: 对应 tab 的结构化数据
    """
    result = await _baidu_stock.get_stock_quote(stock_input, tab)
    return json.dumps(result, ensure_ascii=False)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    mcp.run(transport=transport)
