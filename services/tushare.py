"""
A股实时行情服务 - 基于 Tushare Pro API
工具: get_realtime_by_name, get_realtime_tick_by_name, get_realtime_list_top
"""
import os
import json
import time
import asyncio
import logging
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

try:
    import tushare as ts
    TUSHARE_AVAILABLE = True
except ImportError:
    TUSHARE_AVAILABLE = False
    logger.warning("tushare not installed")


class TushareService:
    CACHE_DIR = Path("/tmp/mcp_cache/tushare")
    CACHE_EXPIRE_HOURS = 24

    def __init__(self):
        self.token = os.getenv("TUSHARE_TOKEN")
        self.pro = None
        self.CACHE_DIR.mkdir(parents=True, exist_ok=True)

        if TUSHARE_AVAILABLE and self.token:
            try:
                ts.set_token(self.token)
                self.pro = ts.pro_api(self.token)
                logger.info("TushareService initialized")
            except Exception as e:
                logger.error(f"Tushare init failed: {e}")

    # ── Cache helpers ────────────────────────────────────────────────────────

    def _load_cache(self, key: str) -> Optional[Any]:
        f = self.CACHE_DIR / f"{key}.json"
        if f.exists():
            try:
                d = json.loads(f.read_text())
                if time.time() - d["ts"] < self.CACHE_EXPIRE_HOURS * 3600:
                    return d["data"]
            except Exception:
                pass
        return None

    def _save_cache(self, key: str, data: Any):
        try:
            (self.CACHE_DIR / f"{key}.json").write_text(
                json.dumps({"ts": time.time(), "data": data}, ensure_ascii=False)
            )
        except Exception:
            pass

    # ── Stock basic (name <-> code mapping) ──────────────────────────────────

    async def _stock_basic_df(self) -> Optional[pd.DataFrame]:
        cached = self._load_cache("stock_basic")
        if cached:
            return pd.DataFrame(cached)
        if not self.pro:
            return None
        loop = asyncio.get_running_loop()
        df = await loop.run_in_executor(
            None,
            lambda: self.pro.stock_basic(exchange="", list_status="L",
                                          fields="ts_code,symbol,name"),
        )
        if df is not None and not df.empty:
            self._save_cache("stock_basic", df.to_dict("records"))
        return df

    async def _names_to_codes(self, names: List[str]) -> Dict[str, str]:
        df = await self._stock_basic_df()
        if df is None or df.empty:
            return {}
        return {n: df[df["name"] == n].iloc[0]["ts_code"]
                for n in names if not df[df["name"] == n].empty}

    async def _codes_to_names(self, codes: List[str]) -> Dict[str, str]:
        df = await self._stock_basic_df()
        if df is None or df.empty:
            return {}
        return {c: df[df["ts_code"] == c].iloc[0]["name"]
                for c in codes if not df[df["ts_code"] == c].empty}

    # ── Tool: get_realtime_by_name ───────────────────────────────────────────

    async def get_realtime_by_name(self, stock_names: str) -> Dict[str, Any]:
        """获取A股实时报价（按股票名称批量查询，最多50只）"""
        names = [n.strip() for n in stock_names.split(",") if n.strip()]
        if not names:
            return {"success": False, "error": "No stock names provided"}
        if len(names) > 50:
            return {"success": False, "error": "Maximum 50 stocks per request"}

        name_code = await self._names_to_codes(names)
        if not name_code:
            return {"success": False, "error": f"Could not resolve names: {stock_names}"}

        not_found = [n for n in names if n not in name_code]
        ts_codes = ",".join(name_code.values())

        if not TUSHARE_AVAILABLE:
            return {"success": False, "error": "Tushare not available"}

        try:
            loop = asyncio.get_running_loop()
            df = await loop.run_in_executor(
                None, lambda: ts.realtime_quote(ts_code=ts_codes, src="sina")
            )
            if df is None or df.empty:
                return {"success": True, "data": [], "metadata": {"count": 0}}

            records = []
            for _, row in df.iterrows():
                pre = float(row["PRE_CLOSE"]) if pd.notna(row.get("PRE_CLOSE")) else None
                price = float(row["PRICE"]) if pd.notna(row.get("PRICE")) else None
                records.append({
                    "ts_code": str(row.get("TS_CODE", "")),
                    "name": str(row.get("NAME", "")),
                    "price": price,
                    "change": round(price - pre, 2) if price and pre else None,
                    "pct_change": round((price - pre) / pre * 100, 2) if price and pre and pre != 0 else None,
                    "open": float(row["OPEN"]) if pd.notna(row.get("OPEN")) else None,
                    "high": float(row["HIGH"]) if pd.notna(row.get("HIGH")) else None,
                    "low": float(row["LOW"]) if pd.notna(row.get("LOW")) else None,
                    "pre_close": pre,
                    "volume": int(row["VOLUME"]) if pd.notna(row.get("VOLUME")) else None,
                    "amount": float(row["AMOUNT"]) if pd.notna(row.get("AMOUNT")) else None,
                    "bid": float(row["BID"]) if pd.notna(row.get("BID")) else None,
                    "ask": float(row["ASK"]) if pd.notna(row.get("ASK")) else None,
                    "date": str(row.get("DATE", "")),
                    "time": str(row.get("TIME", "")),
                })
            meta = {"count": len(records), "query_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
            if not_found:
                meta["not_found"] = not_found
            return {"success": True, "data": records, "metadata": meta}

        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── Tool: get_realtime_tick_by_name ──────────────────────────────────────

    async def get_realtime_tick_by_name(self, stock_name: str, src: str = "sina") -> Dict[str, Any]:
        """获取单只A股当日全部分笔成交明细"""
        name_code = await self._names_to_codes([stock_name.strip()])
        if not name_code:
            return {"success": False, "error": f"Could not resolve: {stock_name}"}

        ts_code = name_code[stock_name.strip()]
        if not TUSHARE_AVAILABLE:
            return {"success": False, "error": "Tushare not available"}

        try:
            loop = asyncio.get_running_loop()
            df = await loop.run_in_executor(
                None, lambda: ts.realtime_tick(ts_code=ts_code, src=src)
            )
            if df is None or df.empty:
                return {"success": True, "data": [], "metadata": {"ts_code": ts_code, "count": 0}}

            def val(row, *keys):
                for k in keys:
                    v = row.get(k, row.get(k.lower()))
                    if v is not None and pd.notna(v):
                        return v
                return None

            records = [{
                "time": str(val(row, "TIME") or ""),
                "price": float(val(row, "PRICE") or 0),
                "change": float(val(row, "CHANGE") or 0),
                "volume": int(val(row, "VOLUME") or 0),
                "amount": float(val(row, "AMOUNT") or 0),
                "type": str(val(row, "TYPE") or ""),
            } for _, row in df.iterrows()]

            return {
                "success": True,
                "data": records,
                "metadata": {
                    "ts_code": ts_code,
                    "name": stock_name,
                    "src": src,
                    "count": len(records),
                    "query_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                },
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── Tool: get_moneyflow ──────────────────────────────────────────────────

    async def get_moneyflow(
        self,
        stock_names: Optional[str] = None,
        trade_date: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """获取A股个股资金流向（大单/中单/小单买卖明细）"""
        if not self.pro:
            return {"success": False, "error": "Tushare Pro not available"}
        if not stock_names and not trade_date:
            return {"success": False, "error": "stock_names 或 trade_date 至少提供一个"}

        # 日期格式统一为 YYYYMMDD
        def fmt_date(d: Optional[str]) -> Optional[str]:
            if not d:
                return None
            return d.replace("-", "")

        trade_date = fmt_date(trade_date)
        start_date = fmt_date(start_date)
        end_date = fmt_date(end_date)

        # 名称 -> ts_code
        ts_code: Optional[str] = None
        if stock_names:
            names = [n.strip() for n in stock_names.split(",") if n.strip()]
            name_code = await self._names_to_codes(names)
            if not name_code:
                return {"success": False, "error": f"无法解析股票名称: {stock_names}"}
            ts_code = ",".join(name_code.values())

        try:
            loop = asyncio.get_running_loop()
            kwargs: Dict[str, Any] = {}
            if ts_code:
                kwargs["ts_code"] = ts_code
            if trade_date:
                kwargs["trade_date"] = trade_date
            if start_date:
                kwargs["start_date"] = start_date
            if end_date:
                kwargs["end_date"] = end_date

            df = await loop.run_in_executor(None, lambda: self.pro.moneyflow(**kwargs))
            if df is None or df.empty:
                return {"success": True, "data": [], "metadata": {"count": 0}}

            # 补充股票名称
            code_name: Dict[str, str] = {}
            if ts_code:
                codes = ts_code.split(",")
                code_name = await self._codes_to_names(codes)

            records = []
            for _, row in df.iterrows():
                def fv(col: str) -> Optional[float]:
                    v = row.get(col)
                    return round(float(v), 4) if v is not None and pd.notna(v) else None

                code = str(row.get("ts_code", ""))
                records.append({
                    "ts_code": code,
                    "name": code_name.get(code, ""),
                    "trade_date": str(row.get("trade_date", "")),
                    # 小单（≤50万）
                    "buy_sm_vol": fv("buy_sm_vol"),
                    "buy_sm_amount": fv("buy_sm_amount"),
                    "sell_sm_vol": fv("sell_sm_vol"),
                    "sell_sm_amount": fv("sell_sm_amount"),
                    # 中单（50~200万）
                    "buy_md_vol": fv("buy_md_vol"),
                    "buy_md_amount": fv("buy_md_amount"),
                    "sell_md_vol": fv("sell_md_vol"),
                    "sell_md_amount": fv("sell_md_amount"),
                    # 大单（200~1000万）
                    "buy_lg_vol": fv("buy_lg_vol"),
                    "buy_lg_amount": fv("buy_lg_amount"),
                    "sell_lg_vol": fv("sell_lg_vol"),
                    "sell_lg_amount": fv("sell_lg_amount"),
                    # 特大单（≥1000万）
                    "buy_elg_vol": fv("buy_elg_vol"),
                    "buy_elg_amount": fv("buy_elg_amount"),
                    "sell_elg_vol": fv("sell_elg_vol"),
                    "sell_elg_amount": fv("sell_elg_amount"),
                    # 净流入
                    "net_mf_vol": fv("net_mf_vol"),
                    "net_mf_amount": fv("net_mf_amount"),
                })

            return {
                "success": True,
                "data": records,
                "metadata": {
                    "count": len(records),
                    "query_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                },
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── Tool: get_stock_info ─────────────────────────────────────────────────

    async def _stock_detail_df(self) -> Optional[pd.DataFrame]:
        """获取带行业/地区信息的股票基础数据（带24h缓存）"""
        cached = self._load_cache("stock_detail")
        if cached:
            return pd.DataFrame(cached)
        if not self.pro:
            return None
        loop = asyncio.get_running_loop()
        df = await loop.run_in_executor(
            None,
            lambda: self.pro.stock_basic(
                exchange="", list_status="L",
                fields="ts_code,symbol,name,area,industry,market,list_date,is_hs",
            ),
        )
        if df is not None and not df.empty:
            self._save_cache("stock_detail", df.to_dict("records"))
        return df

    async def get_stock_info(self, stock_names: str) -> Dict[str, Any]:
        """获取A股基本信息（行业/地区/上市日期/市场类型）"""
        names = [n.strip() for n in stock_names.split(",") if n.strip()]
        df = await self._stock_detail_df()
        if df is None or df.empty:
            return {"success": False, "error": "无法获取股票基础数据"}

        results, not_found = [], []
        for name in names:
            match = df[df["name"] == name]
            if match.empty:
                not_found.append(name)
            else:
                row = match.iloc[0]
                results.append({k: (None if pd.isna(v) else str(v)) for k, v in row.items()})

        return {
            "success": True,
            "data": results,
            "not_found": not_found,
            "query_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    # ── Tool: get_stock_history ──────────────────────────────────────────────

    async def get_stock_history(
        self,
        stock_names: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        adj: str = "qfq",
        limit: Optional[int] = None,
    ) -> Dict[str, Any]:
        """获取A股历史日K线（含前/后复权及 MA/MACD/RSI 技术指标）"""
        if not self.pro:
            return {"success": False, "error": "Tushare Pro not available"}

        names = [n.strip() for n in stock_names.split(",") if n.strip()]
        name_code = await self._names_to_codes(names)
        if not name_code:
            return {"success": False, "error": f"无法解析股票名称: {stock_names}"}

        def fmt(d: Optional[str]) -> Optional[str]:
            return d.replace("-", "") if d else None

        start = fmt(start_date)
        end = fmt(end_date)
        loop = asyncio.get_running_loop()
        results: Dict[str, Any] = {}

        for name, ts_code in name_code.items():
            try:
                kw: Dict[str, Any] = {"ts_code": ts_code}
                if start:
                    kw["start_date"] = start
                if end:
                    kw["end_date"] = end

                df = await loop.run_in_executor(None, lambda k=kw: self.pro.daily(**k))
                if df is None or df.empty:
                    results[name] = {"ts_code": ts_code, "data": [], "count": 0}
                    continue

                df = df.sort_values("trade_date").reset_index(drop=True)

                # Adjustment factors
                if adj in ("qfq", "hfq"):
                    af_kw: Dict[str, Any] = {"ts_code": ts_code}
                    if start:
                        af_kw["start_date"] = start
                    if end:
                        af_kw["end_date"] = end
                    af_df = await loop.run_in_executor(
                        None, lambda k=af_kw: self.pro.adj_factor(**k)
                    )
                    if af_df is not None and not af_df.empty:
                        af_df = af_df.sort_values("trade_date")
                        df = df.merge(af_df[["trade_date", "adj_factor"]], on="trade_date", how="left")
                        df["adj_factor"] = df["adj_factor"].ffill().fillna(1.0)
                        if adj == "qfq":
                            lf = df["adj_factor"].iloc[-1]
                            for col in ["open", "high", "low", "close", "pre_close"]:
                                if col in df.columns:
                                    df[col] = (df[col] * df["adj_factor"] / lf).round(3)
                        else:
                            for col in ["open", "high", "low", "close", "pre_close"]:
                                if col in df.columns:
                                    df[col] = (df[col] * df["adj_factor"]).round(3)

                # Technical indicators
                c = df["close"]
                df["ma5"]  = c.rolling(5).mean().round(3)
                df["ma10"] = c.rolling(10).mean().round(3)
                df["ma20"] = c.rolling(20).mean().round(3)
                df["ma60"] = c.rolling(60).mean().round(3)
                ema12 = c.ewm(span=12, adjust=False).mean()
                ema26 = c.ewm(span=26, adjust=False).mean()
                dif = ema12 - ema26
                dea = dif.ewm(span=9, adjust=False).mean()
                df["macd_dif"] = dif.round(4)
                df["macd_dea"] = dea.round(4)
                df["macd_bar"] = ((dif - dea) * 2).round(4)
                delta = c.diff()
                gain  = delta.clip(lower=0).rolling(14).mean()
                loss  = (-delta.clip(upper=0)).rolling(14).mean()
                rs    = gain / loss.where(loss != 0, other=float("nan"))
                df["rsi14"] = (100 - 100 / (1 + rs)).round(2)

                # Apply limit: return only the last N records (indicators already warmed up)
                if limit and limit > 0:
                    df = df.iloc[-limit:]

                keep_cols = [col for col in df.columns if col != "adj_factor"]
                records = [{k: (None if pd.isna(v) else v) for k, v in row.items()}
                           for row in df[keep_cols].to_dict("records")]
                results[name] = {"ts_code": ts_code, "adj": adj, "data": records, "count": len(records)}

            except Exception as e:
                results[name] = {"ts_code": ts_code, "error": str(e)}

        return {
            "success": True,
            "results": results,
            "query_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    # ── Tool: get_daily_basic ────────────────────────────────────────────────

    async def get_daily_basic(
        self,
        stock_names: Optional[str] = None,
        trade_date: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """获取A股每日估值指标（PE/PB/PS/换手率/市值）"""
        if not self.pro:
            return {"success": False, "error": "Tushare Pro not available"}
        if not stock_names and not trade_date:
            return {"success": False, "error": "stock_names 或 trade_date 至少提供一个"}

        def fmt(d: Optional[str]) -> Optional[str]:
            return d.replace("-", "") if d else None

        ts_code: Optional[str] = None
        if stock_names:
            names = [n.strip() for n in stock_names.split(",") if n.strip()]
            name_code = await self._names_to_codes(names)
            if not name_code:
                return {"success": False, "error": f"无法解析股票名称: {stock_names}"}
            ts_code = ",".join(name_code.values())

        kw: Dict[str, Any] = {
            "fields": (
                "ts_code,trade_date,close,turnover_rate,turnover_rate_f,volume_ratio,"
                "pe,pe_ttm,pb,ps,ps_ttm,dv_ratio,dv_ttm,"
                "total_share,float_share,free_share,total_mv,circ_mv"
            )
        }
        if ts_code:
            kw["ts_code"] = ts_code
        if fmt(trade_date):
            kw["trade_date"] = fmt(trade_date)
        if fmt(start_date):
            kw["start_date"] = fmt(start_date)
        if fmt(end_date):
            kw["end_date"] = fmt(end_date)

        try:
            loop = asyncio.get_running_loop()
            df = await loop.run_in_executor(None, lambda: self.pro.daily_basic(**kw))
            if df is None or df.empty:
                return {"success": True, "data": [], "count": 0}

            if ts_code:
                code_name = await self._codes_to_names(ts_code.split(","))
                df.insert(1, "name", df["ts_code"].map(code_name))

            records = [{k: (None if pd.isna(v) else v) for k, v in row.items()}
                       for row in df.to_dict("records")]
            return {
                "success": True,
                "data": records,
                "count": len(records),
                "query_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── Tool: get_financial_indicators ───────────────────────────────────────

    async def get_financial_indicators(
        self,
        stock_names: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 8,
    ) -> Dict[str, Any]:
        """获取A股关键财务指标（ROE/净利率/成长率/偿债能力，最近N报告期）"""
        if not self.pro:
            return {"success": False, "error": "Tushare Pro not available"}

        names = [n.strip() for n in stock_names.split(",") if n.strip()]
        name_code = await self._names_to_codes(names)
        if not name_code:
            return {"success": False, "error": f"无法解析股票名称: {stock_names}"}

        def fmt(d: Optional[str]) -> Optional[str]:
            return d.replace("-", "") if d else None

        loop = asyncio.get_running_loop()
        results: Dict[str, Any] = {}
        FIELDS = (
            "ts_code,ann_date,end_date,eps,dt_eps,bps,"
            "roe,roe_dt,roa,roic,"
            "netprofit_margin,grossprofit_margin,"
            "current_ratio,quick_ratio,debt_to_assets,debt_to_eqt,"
            "basic_eps_yoy,netprofit_yoy,tr_yoy,or_yoy,"
            "fcff,fcfe,ocf_to_profit"
        )

        for name, ts_code in name_code.items():
            try:
                kw: Dict[str, Any] = {"ts_code": ts_code, "fields": FIELDS}
                if fmt(start_date):
                    kw["start_date"] = fmt(start_date)
                if fmt(end_date):
                    kw["end_date"] = fmt(end_date)

                df = await loop.run_in_executor(None, lambda k=kw: self.pro.fina_indicator(**k))
                if df is None or df.empty:
                    results[name] = {"ts_code": ts_code, "data": [], "count": 0}
                    continue

                df = df.sort_values("end_date", ascending=False).head(limit)
                records = [{k: (None if pd.isna(v) else v) for k, v in row.items()}
                           for row in df.to_dict("records")]
                results[name] = {"ts_code": ts_code, "data": records, "count": len(records)}
            except Exception as e:
                results[name] = {"ts_code": ts_code, "error": str(e)}

        return {
            "success": True,
            "results": results,
            "query_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    # ── Tool: get_income_statement ───────────────────────────────────────────

    async def get_income_statement(
        self,
        stock_names: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 8,
    ) -> Dict[str, Any]:
        """获取A股利润表（营收/净利润/毛利/三费/EPS，最近N报告期）"""
        if not self.pro:
            return {"success": False, "error": "Tushare Pro not available"}

        names = [n.strip() for n in stock_names.split(",") if n.strip()]
        name_code = await self._names_to_codes(names)
        if not name_code:
            return {"success": False, "error": f"无法解析股票名称: {stock_names}"}

        def fmt(d: Optional[str]) -> Optional[str]:
            return d.replace("-", "") if d else None

        loop = asyncio.get_running_loop()
        results: Dict[str, Any] = {}
        FIELDS = (
            "ts_code,ann_date,f_ann_date,end_date,report_type,end_type,"
            "basic_eps,diluted_eps,total_revenue,revenue,total_cogs,oper_cost,"
            "sell_exp,admin_exp,fin_exp,assets_impair_loss,"
            "operate_profit,total_profit,income_tax,n_income,n_income_attr_p,"
            "ebit,ebitda,rd_exp"
        )

        for name, ts_code in name_code.items():
            try:
                kw: Dict[str, Any] = {"ts_code": ts_code, "report_type": "1", "fields": FIELDS}
                if fmt(start_date):
                    kw["start_date"] = fmt(start_date)
                if fmt(end_date):
                    kw["end_date"] = fmt(end_date)

                df = await loop.run_in_executor(None, lambda k=kw: self.pro.income(**k))
                if df is None or df.empty:
                    results[name] = {"ts_code": ts_code, "data": [], "count": 0}
                    continue

                df = df.sort_values("end_date", ascending=False).head(limit)
                records = [{k: (None if pd.isna(v) else v) for k, v in row.items()}
                           for row in df.to_dict("records")]
                results[name] = {"ts_code": ts_code, "data": records, "count": len(records)}
            except Exception as e:
                results[name] = {"ts_code": ts_code, "error": str(e)}

        return {
            "success": True,
            "results": results,
            "query_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    # ── Tool: get_hsgt_top10 ─────────────────────────────────────────────────

    async def get_hsgt_top10(
        self,
        trade_date: Optional[str] = None,
        market_type: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """获取沪深港通十大成交股（北向/南向资金 Top10）"""
        if not self.pro:
            return {"success": False, "error": "Tushare Pro not available"}

        def fmt(d: Optional[str]) -> Optional[str]:
            return d.replace("-", "") if d else None

        kw: Dict[str, Any] = {}
        if fmt(trade_date):
            kw["trade_date"] = fmt(trade_date)
        if market_type:
            kw["market_type"] = market_type
        if fmt(start_date):
            kw["start_date"] = fmt(start_date)
        if fmt(end_date):
            kw["end_date"] = fmt(end_date)

        if not kw:
            return {"success": False, "error": "请提供 trade_date 或日期范围"}

        try:
            loop = asyncio.get_running_loop()
            df = await loop.run_in_executor(None, lambda: self.pro.hsgt_top10(**kw))
            if df is None or df.empty:
                return {"success": True, "data": [], "count": 0}

            market_map = {"1": "沪股通", "2": "港股通(沪)", "3": "深股通", "4": "港股通(深)"}
            df["market_label"] = df["market_type"].astype(str).map(market_map)

            records = [{k: (None if pd.isna(v) else v) for k, v in row.items()}
                       for row in df.to_dict("records")]
            return {
                "success": True,
                "data": records,
                "count": len(records),
                "query_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── Tool: get_realtime_list_top ──────────────────────────────────────────

    async def get_realtime_list_top(
        self,
        src: str = "dc",
        top_n: int = 20,
        sort_by: str = "pct_change",
        ascending: bool = False,
    ) -> Dict[str, Any]:
        """获取A股全市场实时涨跌幅排行榜"""
        if not TUSHARE_AVAILABLE:
            return {"success": False, "error": "Tushare not available"}

        try:
            loop = asyncio.get_running_loop()
            df = await loop.run_in_executor(None, lambda: ts.realtime_list(src=src))
            if df is None or df.empty:
                return {"success": True, "data": [], "metadata": {"count": 0}}

            # Clean NaN
            records = [{k: (None if pd.isna(v) else v) for k, v in row.items()}
                       for row in df.to_dict("records")]

            df2 = pd.DataFrame(records)
            if sort_by in df2.columns:
                df2 = df2.sort_values(sort_by, ascending=ascending, na_position="last")
            top = df2.head(top_n).to_dict("records")

            return {
                "success": True,
                "data": top,
                "metadata": {
                    "src": src,
                    "top_n": top_n,
                    "sort_by": sort_by,
                    "ascending": ascending,
                    "count": len(top),
                    "total_stocks": len(records),
                    "query_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                },
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
