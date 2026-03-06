#!/usr/bin/env python3
"""
Finance MCP Server
------------------
Tools:
  A股历史:    get_stock_history (Tushare)
  A股实时行情: get_realtime_quote (Tushare)
  A股基本信息: get_stock_info (Tushare)
  A股估值指标: get_daily_basic (Tushare)
  A股财务指标: get_financial_indicators (Tushare)
  A股利润表:  get_income_statement (Tushare)
  A股排行:    get_realtime_list_top (新浪)
  A股实时资金: get_realtime_moneyflow (东方财富 fflow)
  A股大盘:    get_market_overview (东方财富)
  板块排行:   get_sector_ranking (新浪)
  北向资金:   get_hsgt_top10 (Tushare)
  龙虎榜:    get_top_list (Tushare)
  融资融券:   get_margin_detail (Tushare)
  股东人数:   get_stk_holdernumber (Tushare)
  资产负债表: get_balance_sheet (Tushare)
  现金流量表: get_cashflow (Tushare)
  限售股解禁: get_share_float (Tushare)
  券商研报:   get_research_report (Tushare)
  同行业对比: get_peer_comparison (Tushare)
  分钟K线:   get_stock_mins (Tushare)
  宏观数据:   get_macro_data (Tushare CPI/PPI/M2/GDP/SHIBOR)
  美股历史:   get_us_stock_history
  美股分析:   get_fundamental_analysis, get_technical_analysis,
              get_sentiment_analysis, get_comprehensive_analysis

Transport:
  stdio (default) — for local / Claude Desktop use
  sse             — set MCP_TRANSPORT=sse for Docker HTTP mode
"""
import os
import json
import logging
from typing import Optional
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv()
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

# ── Service singletons ───────────────────────────────────────────────────────

from services.eastmoney import EastMoneyService
from services.sina_sector import SinaSectorService
from services.us_stock import USStockService
from services.tushare import TushareService

_eastmoney = EastMoneyService()
_sina_sector = SinaSectorService()
_us_stock = USStockService()
_tushare = TushareService()

# ── MCP server ───────────────────────────────────────────────────────────────

_port = int(os.getenv("MCP_PORT", "8000"))

mcp = FastMCP(
    "finance-mcp",
    instructions=(
        "Financial analysis tools for A-shares (China) and US stocks.\n"
        "A-share capabilities: historical K-line with technical indicators (MA/MACD/RSI), "
        "real-time quote, stock info, daily valuation (PE/PB/PS), "
        "financial indicators (ROE/margins/growth), income statement, "
        "real-time market ranking, real-time money flow (via East Money), "
        "market overview, sector ranking (via Sina Finance), "
        "HSGT top10 (northbound capital), dragon-tiger list, "
        "margin trading detail, shareholder count, "
        "balance sheet, cashflow statement, share float (lock-up expiry), "
        "research reports (analyst ratings/target price), peer comparison (industry valuation ranking), "
        "minute K-line (1/5/15/30/60min), macro economic data (CPI/PPI/M2/GDP/SHIBOR).\n"
        "US stock capabilities: historical K-line (get_us_stock_history), "
        "fundamental, technical, and sentiment analysis.\n"
        "A-share sector ranking: industry and concept sector performance ranking (via Sina Finance).\n"
        "All A-share data sources are free and require no API key."
    ),
    host="0.0.0.0",
    port=_port,
)


# ── A股历史K线 ───────────────────────────────────────────────────────────────

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

    数据源: Tushare Pro（需要 TUSHARE_TOKEN）
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


# ── A股实时排行 ──────────────────────────────────────────────────────────────

@mcp.tool()
async def get_realtime_list_top(
    top_n: int = 20,
    sort_by: str = "pct_change",
    ascending: bool = False,
) -> str:
    """
    获取A股全市场实时排行榜

    数据源: 新浪财经实时行情API,免费无需配置。
    适用场景: 快速获取全市场涨幅榜/跌幅榜/成交额榜/换手率榜等排行。

    Args:
        top_n: 返回前N条,默认20
        sort_by: 排序字段,常用: 'pct_change'(涨跌幅,默认), 'amount'(成交额),
                 'volume'(成交量), 'turnover_rate'(换手率), 'total_mv'(总市值),
                 'pe'(市盈率), 'pb'(市净率)
        ascending: False=降序(默认,取涨幅榜), True=升序(取跌幅榜)
    Returns:
        JSON: 排名前N的股票实时行情数据
    """
    result = await _eastmoney.get_realtime_list_top(top_n, sort_by, ascending)
    return json.dumps(result, ensure_ascii=False)


# ── A股实时资金流向 ──────────────────────────────────────────────────────────

@mcp.tool()
async def get_realtime_moneyflow(stock_names: str) -> str:
    """
    获取A股个股实时资金流向（盘中实时数据）

    数据源: 东方财富 fflow 接口（免费，盘中实时更新）
    适用场景: 交易时段查看当日主力/散户资金净流入流出。
    非交易时段返回最近一个交易日的数据。

    资金分级（东方财富标准）:
      小单 ≤ 5万 | 中单 5~20万 | 大单 20~100万 | 超大单 ≥ 100万

    Args:
        stock_names: 股票名称，多个用逗号分隔，最多50只。
                     例: '湖南黄金' 或 '贵州茅台,宁德时代,比亚迪'
    Returns:
        JSON: 每只股票的实时资金流向，包含:
              - summary: 主力净流入(万元) + 主力净占比(%)
              - detail: 超大单/大单/中单/小单各自净流入(万元)及净占比(%)
    """
    names = [n.strip() for n in stock_names.split(",") if n.strip()]
    if not names:
        return json.dumps({"success": False, "error": "未提供股票名称"}, ensure_ascii=False)

    # 用 Tushare 的名称解析拿到 secid
    name_code = await _tushare._names_to_codes(names)
    if not name_code:
        return json.dumps({"success": False, "error": f"无法解析股票名称: {stock_names}"}, ensure_ascii=False)

    # ts_code (如 002733.SZ) -> secid (如 0.002733)
    pairs = []
    for name, ts_code in name_code.items():
        code = ts_code.split(".")[0]
        market = "1" if ts_code.endswith(".SH") else "0"
        pairs.append((f"{market}.{code}", name))

    result = await _eastmoney.get_realtime_moneyflow(pairs)
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
async def get_market_overview() -> str:
    """
    获取A股大盘实时概览（主要指数行情 + 全市场涨跌统计）

    数据源: 东方财富实时行情API，免费无需配置。
    适用场景: 快速了解当前大盘走势、主要指数表现、市场涨跌家数。

    Returns:
        JSON:
          indices: 上证指数/深证成指/创业板指/沪深300/上证50/中证500/中证1000/科创50
                   每个含 price/change_pct/volume/amount/up_count/down_count
          market_stats: 全市场涨跌家数统计 + 涨跌比
    """
    result = await _eastmoney.get_market_overview()
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
async def get_sector_ranking(sector_type: str = "industry", top_n: int = 30) -> str:
    """
    获取A股板块涨跌幅排行（行业板块 / 概念板块）

    数据源: 新浪财经，免费无需配置。
    适用场景: 查看当日各板块涨跌幅排名、领涨股，快速定位市场热点方向。

    Args:
        sector_type: 板块类型，'industry'(行业板块,默认) 或 'concept'(概念板块)
        top_n: 返回涨幅前N个板块，默认30。同时返回跌幅后5个板块。
    Returns:
        JSON:
          type: 行业板块/概念板块
          total_sectors: 板块总数
          up_count/down_count: 上涨/下跌板块数
          top: 涨幅前N板块，每个含 name/change_pct/stock_count/leader(领涨股)
          bottom: 跌幅后5板块
    """
    result = await _sina_sector.get_sector_ranking(sector_type, top_n)
    return json.dumps(result, ensure_ascii=False)


# ── A股实时行情 ──────────────────────────────────────────────────────────────

@mcp.tool()
async def get_realtime_quote(stock_names: str) -> str:
    """
    获取A股实时行情报价（盘中实时数据）

    数据源: Tushare realtime_quote（免费，盘中实时）
    适用场景: 查看个股当前价格、涨跌幅、成交量等实时数据。

    Args:
        stock_names: 股票名称，多个用逗号分隔，最多50只。
                     例: '湖南黄金' 或 '贵州茅台,宁德时代,比亚迪'
    Returns:
        JSON: 每只股票的实时行情，含 price/open/high/low/pre_close/volume/amount
    """
    result = await _tushare.get_realtime_by_name(stock_names)
    return json.dumps(result, ensure_ascii=False)


# ── A股基本信息 ──────────────────────────────────────────────────────────────

@mcp.tool()
async def get_stock_info(stock_names: str) -> str:
    """
    获取A股基本信息（行业/地区/上市日期/市场类型）

    数据源: Tushare Pro
    适用场景: 查看股票所属行业、地区、上市时间等基础信息。

    Args:
        stock_names: 股票名称，多个用逗号分隔。
                     例: '湖南黄金' 或 '贵州茅台,宁德时代'
    Returns:
        JSON: 每只股票的基本信息，含 ts_code/name/area/industry/market/list_date
    """
    result = await _tushare.get_stock_info(stock_names)
    return json.dumps(result, ensure_ascii=False)


# ── A股每日估值指标 ──────────────────────────────────────────────────────────

@mcp.tool()
async def get_daily_basic(
    stock_names: Optional[str] = None,
    trade_date: Optional[str] = None,
) -> str:
    """
    获取A股每日估值指标（PE/PB/PS/换手率/市值）

    数据源: Tushare Pro
    适用场景: 查看个股估值水平、换手率、总市值/流通市值。

    Args:
        stock_names: 股票名称，多个用逗号分隔。
                     例: '湖南黄金' 或 '贵州茅台,宁德时代'
        trade_date:  交易日期，格式 'YYYY-MM-DD' 或 'YYYYMMDD'（默认最近交易日）
        注: stock_names 和 trade_date 至少提供一个
    Returns:
        JSON: PE/PE_TTM/PB/PS/换手率/总市值/流通市值等
    """
    result = await _tushare.get_daily_basic(stock_names, trade_date)
    return json.dumps(result, ensure_ascii=False)


# ── A股财务指标 ──────────────────────────────────────────────────────────────

@mcp.tool()
async def get_financial_indicators(
    stock_names: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 8,
) -> str:
    """
    获取A股关键财务指标（ROE/净利率/毛利率/成长率/偿债能力）

    数据源: Tushare Pro (fina_indicator)
    适用场景: 基本面选股必看的核心财务指标，按报告期排列。

    Args:
        stock_names: 股票名称，多个用逗号分隔。例: '贵州茅台,宁德时代'
        start_date:  报告期开始日期，格式 'YYYY-MM-DD' 或 'YYYYMMDD'
        end_date:    报告期结束日期
        limit:       返回最近N个报告期，默认8
    Returns:
        JSON: ROE/ROA/ROIC/净利率/毛利率/EPS/BPS/资产负债率/
              净利润增速/营收增速/自由现金流等
    """
    result = await _tushare.get_financial_indicators(stock_names, start_date, end_date, limit)
    return json.dumps(result, ensure_ascii=False)


# ── A股利润表 ────────────────────────────────────────────────────────────────

@mcp.tool()
async def get_income_statement(
    stock_names: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 8,
) -> str:
    """
    获取A股利润表（营收/净利润/毛利/三费/EPS）

    数据源: Tushare Pro (income)
    适用场景: 查看公司盈利能力、费用结构、利润趋势。

    Args:
        stock_names: 股票名称，多个用逗号分隔。例: '贵州茅台,宁德时代'
        start_date:  报告期开始日期，格式 'YYYY-MM-DD' 或 'YYYYMMDD'
        end_date:    报告期结束日期
        limit:       返回最近N个报告期，默认8
    Returns:
        JSON: 营收/营业成本/销售费用/管理费用/财务费用/营业利润/
              净利润/归母净利润/EPS/EBITDA/研发费用等
    """
    result = await _tushare.get_income_statement(stock_names, start_date, end_date, limit)
    return json.dumps(result, ensure_ascii=False)


# ── 北向资金Top10 ────────────────────────────────────────────────────────────

@mcp.tool()
async def get_hsgt_top10(
    trade_date: Optional[str] = None,
    market_type: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> str:
    """
    获取沪深港通十大成交股（北向/南向资金 Top10）

    数据源: Tushare Pro (hsgt_top10)
    适用场景: 追踪外资/北向资金动向，查看外资重点买卖标的。

    Args:
        trade_date:  交易日期，格式 'YYYY-MM-DD' 或 'YYYYMMDD'
        market_type: '1'=沪股通, '2'=港股通(沪), '3'=深股通, '4'=港股通(深)
                     不填返回全部
        start_date:  开始日期（与end_date配合查范围）
        end_date:    结束日期
        注: trade_date 或 start_date/end_date 至少提供一个
    Returns:
        JSON: 股票名/买入金额/卖出金额/净买入/市场类型等
    """
    result = await _tushare.get_hsgt_top10(trade_date, market_type, start_date, end_date)
    return json.dumps(result, ensure_ascii=False)


# ── A股龙虎榜 ────────────────────────────────────────────────────────────────

@mcp.tool()
async def get_top_list(
    trade_date: Optional[str] = None,
    stock_names: Optional[str] = None,
) -> str:
    """
    获取A股龙虎榜每日明细（上榜原因/买卖金额/机构动向）

    数据源: Tushare Pro (top_list + top_inst)
    适用场景: 短线博弈核心参考，查看游资/机构买卖席位及金额。

    Args:
        trade_date:  交易日期，格式 'YYYY-MM-DD' 或 'YYYYMMDD'
        stock_names: 股票名称，多个用逗号分隔（可选，按个股过滤）
        注: trade_date 或 stock_names 至少提供一个
    Returns:
        JSON: 上榜原因/买入额/卖出额/净买入/收盘价/涨跌幅 +
              机构买卖明细(如有)
    """
    result = await _tushare.get_top_list(trade_date, stock_names)
    return json.dumps(result, ensure_ascii=False)


# ── A股融资融券 ──────────────────────────────────────────────────────────────

@mcp.tool()
async def get_margin_detail(
    stock_names: Optional[str] = None,
    trade_date: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> str:
    """
    获取A股融资融券交易明细（杠杆情绪指标）

    数据源: Tushare Pro (margin_detail)
    适用场景: 判断市场杠杆情绪，观察融资买入/融券卖出趋势。

    Args:
        stock_names: 股票名称，多个用逗号分隔
        trade_date:  交易日期，格式 'YYYY-MM-DD' 或 'YYYYMMDD'
        start_date:  开始日期
        end_date:    结束日期
        注: 至少提供一个参数
    Returns:
        JSON: 融资余额/融资买入额/融券余额/融券卖出量/融资融券余额等
    """
    result = await _tushare.get_margin_detail(stock_names, trade_date, start_date, end_date)
    return json.dumps(result, ensure_ascii=False)


# ── A股股东人数 ──────────────────────────────────────────────────────────────

@mcp.tool()
async def get_stk_holdernumber(
    stock_names: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> str:
    """
    获取A股股东人数变化（筹码集中度参考）

    数据源: Tushare Pro (stk_holdernumber)
    适用场景: 股东人数减少→筹码集中→主力吸筹信号。

    Args:
        stock_names: 股票名称，多个用逗号分隔。例: '贵州茅台,宁德时代'
        start_date:  开始日期，格式 'YYYY-MM-DD' 或 'YYYYMMDD'
        end_date:    结束日期
    Returns:
        JSON: 每期股东总数/A股股东数/B股股东数/变化幅度等
    """
    result = await _tushare.get_stk_holdernumber(stock_names, start_date, end_date)
    return json.dumps(result, ensure_ascii=False)


# ── A股资产负债表 ────────────────────────────────────────────────────────────

@mcp.tool()
async def get_balance_sheet(
    stock_names: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 8,
) -> str:
    """
    获取A股资产负债表（资产/负债/所有者权益结构）

    数据源: Tushare Pro (balancesheet)
    适用场景: 分析公司资产质量、负债结构、有息负债率，判断财务健康度。

    Args:
        stock_names: 股票名称，多个用逗号分隔。例: '贵州茅台,宁德时代'
        start_date:  报告期开始日期，格式 'YYYY-MM-DD' 或 'YYYYMMDD'
        end_date:    报告期结束日期
        limit:       返回最近N个报告期，默认8
    Returns:
        JSON: 总资产/总负债/所有者权益/货币资金/应收账款/存货/
              固定资产/短期借款/长期借款/商誉等
    """
    result = await _tushare.get_balance_sheet(stock_names, start_date, end_date, limit)
    return json.dumps(result, ensure_ascii=False)


# ── A股现金流量表 ────────────────────────────────────────────────────────────

@mcp.tool()
async def get_cashflow(
    stock_names: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 8,
) -> str:
    """
    获取A股现金流量表（经营/投资/筹资三大活动现金流）

    数据源: Tushare Pro (cashflow)
    适用场景: 判断公司造血能力（经营现金流vs净利润）、投资扩张力度、筹资依赖度。

    Args:
        stock_names: 股票名称，多个用逗号分隔。例: '贵州茅台,宁德时代'
        start_date:  报告期开始日期，格式 'YYYY-MM-DD' 或 'YYYYMMDD'
        end_date:    报告期结束日期
        limit:       返回最近N个报告期，默认8
    Returns:
        JSON: 经营活动净现金流/投资活动净现金流/筹资活动净现金流/
              销售收到现金/购买支付现金/自由现金流/期末现金余额等
    """
    result = await _tushare.get_cashflow(stock_names, start_date, end_date, limit)
    return json.dumps(result, ensure_ascii=False)


# ── A股限售股解禁 ────────────────────────────────────────────────────────────

@mcp.tool()
async def get_share_float(
    stock_names: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> str:
    """
    获取A股限售股解禁计划（抛压预期）

    数据源: Tushare Pro (share_float)
    适用场景: 提前预判解禁抛压，规避大额解禁风险期。

    Args:
        stock_names: 股票名称，多个用逗号分隔
        start_date:  解禁日期范围开始，格式 'YYYY-MM-DD' 或 'YYYYMMDD'
        end_date:    解禁日期范围结束
        注: stock_names 或日期范围至少提供一个
    Returns:
        JSON: 解禁日期/解禁数量(万股)/解禁比例/解禁类型/持有人等
    """
    result = await _tushare.get_share_float(stock_names, start_date, end_date)
    return json.dumps(result, ensure_ascii=False)


# ── A股券商研报 ──────────────────────────────────────────────────────────────

@mcp.tool()
async def get_research_report(
    stock_names: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 20,
) -> str:
    """
    获取A股券商研报（评级/目标价/盈利预测）

    数据源: Tushare Pro (report_rc)
    适用场景: 查看机构观点、一致预期盈利、目标价，作为估值锚参考。

    Args:
        stock_names: 股票名称，多个用逗号分隔
        start_date:  研报日期范围开始，格式 'YYYY-MM-DD' 或 'YYYYMMDD'
        end_date:    研报日期范围结束
        limit:       返回最近N条研报，默认20
        注: stock_names 或日期范围至少提供一个
    Returns:
        JSON: 研报日期/标题/机构/作者/评级/目标价/
              营收预测/净利润预测/EPS/PE/ROE等
    """
    result = await _tushare.get_research_report(stock_names, start_date, end_date, limit)
    return json.dumps(result, ensure_ascii=False)


# ── A股同行业对比 ────────────────────────────────────────────────────────────

@mcp.tool()
async def get_peer_comparison(
    stock_names: str,
    trade_date: Optional[str] = None,
) -> str:
    """
    获取同行业公司估值横向对比（相对估值分析）

    数据源: Tushare Pro (daily_basic + stock_basic)
    适用场景: 判断个股估值在行业中的位置，识别估值偏高/偏低的标的。

    Args:
        stock_names: 股票名称，多个用逗号分隔。例: '贵州茅台'
        trade_date:  交易日期，格式 'YYYY-MM-DD'（默认最近交易日）
    Returns:
        JSON: 目标股在行业中的PE/PB/PS排名百分位 + 行业统计(均值/中位数/极值)
              + 同行业Top20公司估值明细
    """
    result = await _tushare.get_peer_comparison(stock_names, trade_date)
    return json.dumps(result, ensure_ascii=False)


# ── A股分钟K线 ──────────────────────────────────────────────────────────────

@mcp.tool()
async def get_stock_mins(
    stock_names: str,
    freq: str = "5min",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 240,
) -> str:
    """
    获取A股分钟级K线数据（日内交易分析）

    数据源: Tushare Pro (stk_mins)
    适用场景: 日内交易分析、分时走势、短线买卖点判断。

    Args:
        stock_names: 股票名称，多个用逗号分隔。例: '贵州茅台,宁德时代'
        freq:        K线频率，'1min'/'5min'(默认)/'15min'/'30min'/'60min'
        start_date:  开始日期，格式 'YYYY-MM-DD' 或 'YYYYMMDD'
        end_date:    结束日期
        limit:       返回最近N条K线，默认240（一个交易日的1min数据量）
    Returns:
        JSON: 每只股票的分钟K线，含 trade_time/open/high/low/close/vol/amount
    """
    result = await _tushare.get_stock_mins(stock_names, freq, start_date, end_date, limit)
    return json.dumps(result, ensure_ascii=False)


# ── 宏观经济数据 ─────────────────────────────────────────────────────────────

@mcp.tool()
async def get_macro_data(
    indicator: str = "all",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 12,
) -> str:
    """
    获取中国宏观经济数据（判断经济周期和货币政策方向）

    数据源: Tushare Pro
    适用场景: 判断"该不该入场" — 经济周期位置、通胀趋势、流动性环境。

    Args:
        indicator: 指标类型:
                   'cpi'    — 居民消费价格指数（通胀）
                   'ppi'    — 工业品出厂价格指数（上游通胀）
                   'money'  — 货币供应量（M0/M1/M2，流动性）
                   'gdp'    — 国内生产总值（经济增长）
                   'shibor' — 上海银行间同业拆放利率（资金面松紧）
                   'all'    — 全部指标（默认）
        start_date: 开始日期，格式 'YYYY-MM-DD' 或 'YYYYMMDD'
        end_date:   结束日期
        limit:      返回最近N期数据，默认12
    Returns:
        JSON: 各项宏观经济指标的时间序列数据
    """
    result = await _tushare.get_macro_data(indicator, start_date, end_date, limit)
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


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    mcp.run(transport=transport)
