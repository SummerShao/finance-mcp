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
                                          fields="ts_code,symbol,name,industry,area,market,list_date"),
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

    # ── Tool: get_top_list (龙虎榜) ───────────────────────────────────────────

    async def get_top_list(
        self,
        trade_date: Optional[str] = None,
        stock_names: Optional[str] = None,
    ) -> Dict[str, Any]:
        """获取A股龙虎榜每日明细（上榜原因/买卖金额/净买入）"""
        if not self.pro:
            return {"success": False, "error": "Tushare Pro not available"}

        def fmt(d: Optional[str]) -> Optional[str]:
            return d.replace("-", "") if d else None

        kw: Dict[str, Any] = {}
        if fmt(trade_date):
            kw["trade_date"] = fmt(trade_date)

        ts_code_filter = None
        if stock_names:
            names = [n.strip() for n in stock_names.split(",") if n.strip()]
            name_code = await self._names_to_codes(names)
            if name_code:
                ts_code_filter = list(name_code.values())

        if not kw and not ts_code_filter:
            return {"success": False, "error": "请提供 trade_date 或 stock_names"}

        try:
            loop = asyncio.get_running_loop()

            if ts_code_filter and len(ts_code_filter) == 1:
                kw["ts_code"] = ts_code_filter[0]
            df = await loop.run_in_executor(None, lambda: self.pro.top_list(**kw))
            if df is None or df.empty:
                return {"success": True, "data": [], "count": 0}

            if ts_code_filter and "ts_code" not in kw:
                df = df[df["ts_code"].isin(ts_code_filter)]

            records = [{k: (None if pd.isna(v) else v) for k, v in row.items()}
                       for row in df.to_dict("records")]

            # 尝试获取龙虎榜机构明细
            inst_records = []
            try:
                df_inst = await loop.run_in_executor(None, lambda: self.pro.top_inst(**kw))
                if df_inst is not None and not df_inst.empty:
                    if ts_code_filter and "ts_code" not in kw:
                        df_inst = df_inst[df_inst["ts_code"].isin(ts_code_filter)]
                    inst_records = [{k: (None if pd.isna(v) else v) for k, v in row.items()}
                                    for row in df_inst.to_dict("records")]
            except Exception:
                pass

            result: Dict[str, Any] = {
                "success": True,
                "data": records,
                "count": len(records),
                "query_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            if inst_records:
                result["institutions"] = inst_records
                result["inst_count"] = len(inst_records)
            return result
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── Tool: get_margin_detail (融资融券) ────────────────────────────────────

    async def get_margin_detail(
        self,
        stock_names: Optional[str] = None,
        trade_date: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """获取A股融资融券交易明细（融资买入/融券卖出/余额）"""
        if not self.pro:
            return {"success": False, "error": "Tushare Pro not available"}

        def fmt(d: Optional[str]) -> Optional[str]:
            return d.replace("-", "") if d else None

        kw: Dict[str, Any] = {}
        if fmt(trade_date):
            kw["trade_date"] = fmt(trade_date)
        if fmt(start_date):
            kw["start_date"] = fmt(start_date)
        if fmt(end_date):
            kw["end_date"] = fmt(end_date)

        ts_code_filter = None
        if stock_names:
            names = [n.strip() for n in stock_names.split(",") if n.strip()]
            name_code = await self._names_to_codes(names)
            if name_code:
                if len(name_code) == 1:
                    kw["ts_code"] = list(name_code.values())[0]
                else:
                    ts_code_filter = list(name_code.values())

        if not kw:
            return {"success": False, "error": "请提供 trade_date/stock_names/日期范围 至少一个"}

        try:
            loop = asyncio.get_running_loop()
            df = await loop.run_in_executor(None, lambda: self.pro.margin_detail(**kw))
            if df is None or df.empty:
                return {"success": True, "data": [], "count": 0}

            if ts_code_filter:
                df = df[df["ts_code"].isin(ts_code_filter)]

            df = df.sort_values("trade_date", ascending=False)
            records = [{k: (None if pd.isna(v) else v) for k, v in row.items()}
                       for row in df.head(100).to_dict("records")]

            return {
                "success": True,
                "data": records,
                "count": len(records),
                "query_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── Tool: get_stk_holdernumber (股东人数) ─────────────────────────────────

    async def get_stk_holdernumber(
        self,
        stock_names: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """获取A股股东人数变化（筹码集中度参考）"""
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

        for name, ts_code in name_code.items():
            try:
                kw: Dict[str, Any] = {"ts_code": ts_code}
                if fmt(start_date):
                    kw["start_date"] = fmt(start_date)
                if fmt(end_date):
                    kw["end_date"] = fmt(end_date)

                df = await loop.run_in_executor(
                    None, lambda k=kw: self.pro.stk_holdernumber(**k)
                )
                if df is None or df.empty:
                    results[name] = {"ts_code": ts_code, "data": [], "count": 0}
                    continue

                df = df.sort_values("end_date", ascending=False).head(20)
                records = [{k: (None if pd.isna(v) else v) for k, v in row.items()}
                           for row in df.to_dict("records")]
                results[name] = {"ts_code": ts_code, "data": records, "count": len(records)}
            except Exception as e:
                results[name] = {"ts_code": ts_code, "error": str(e)}

        return {"success": True, "results": results,
                "query_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

    # ── Tool: get_balance_sheet (资产负债表) ──────────────────────────────────

    async def get_balance_sheet(
        self,
        stock_names: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 8,
    ) -> Dict[str, Any]:
        """获取A股资产负债表（资产/负债/所有者权益）"""
        if not self.pro:
            return {"success": False, "error": "Tushare Pro not available"}

        names = [n.strip() for n in stock_names.split(",") if n.strip()]
        name_code = await self._names_to_codes(names)
        if not name_code:
            return {"success": False, "error": f"无法解析股票名称: {stock_names}"}

        def fmt(d: Optional[str]) -> Optional[str]:
            return d.replace("-", "") if d else None

        loop = asyncio.get_running_loop()
        results_bs: Dict[str, Any] = {}
        FIELDS = (
            "ts_code,ann_date,f_ann_date,end_date,report_type,"
            "total_assets,total_liab,total_hldr_eqty_exc_min_int,"
            "cap_rese,surplus_rese,undistr_porfit,"
            "money_cap,trad_asset,notes_receiv,accounts_receiv,"
            "prepayment,inventories,fix_assets,cip,"
            "lt_borr,st_borr,bond_payable,accounts_payab,"
            "adv_receipts,goodwill,r_and_d"
        )

        for name, ts_code in name_code.items():
            try:
                kw: Dict[str, Any] = {"ts_code": ts_code, "report_type": "1", "fields": FIELDS}
                if fmt(start_date):
                    kw["start_date"] = fmt(start_date)
                if fmt(end_date):
                    kw["end_date"] = fmt(end_date)

                df = await loop.run_in_executor(None, lambda k=kw: self.pro.balancesheet(**k))
                if df is None or df.empty:
                    results_bs[name] = {"ts_code": ts_code, "data": [], "count": 0}
                    continue

                df = df.sort_values("end_date", ascending=False).head(limit)
                recs = [{k: (None if pd.isna(v) else v) for k, v in row.items()}
                        for row in df.to_dict("records")]
                results_bs[name] = {"ts_code": ts_code, "data": recs, "count": len(recs)}
            except Exception as e:
                results_bs[name] = {"ts_code": ts_code, "error": str(e)}

        return {"success": True, "results": results_bs,
                "query_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

    # ── Tool: get_cashflow (现金流量表) ───────────────────────────────────────

    async def get_cashflow(
        self,
        stock_names: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 8,
    ) -> Dict[str, Any]:
        """获取A股现金流量表（经营/投资/筹资活动现金流）"""
        if not self.pro:
            return {"success": False, "error": "Tushare Pro not available"}

        names = [n.strip() for n in stock_names.split(",") if n.strip()]
        name_code = await self._names_to_codes(names)
        if not name_code:
            return {"success": False, "error": f"无法解析股票名称: {stock_names}"}

        def fmt(d: Optional[str]) -> Optional[str]:
            return d.replace("-", "") if d else None

        loop = asyncio.get_running_loop()
        results_cf: Dict[str, Any] = {}
        FIELDS = (
            "ts_code,ann_date,f_ann_date,end_date,report_type,"
            "n_cashflow_act,n_cashflow_inv_act,n_cash_flows_fnc_act,"
            "c_fr_sale_sg,c_paid_goods_s,c_paid_to_for_empl,"
            "c_paid_for_taxes,c_pay_acq_const_fiam,c_paid_invest,"
            "c_recp_borrow,c_pay_dist_dpcp_int_exp,"
            "free_cashflow,c_cash_equ_end_period"
        )

        for name, ts_code in name_code.items():
            try:
                kw: Dict[str, Any] = {"ts_code": ts_code, "report_type": "1", "fields": FIELDS}
                if fmt(start_date):
                    kw["start_date"] = fmt(start_date)
                if fmt(end_date):
                    kw["end_date"] = fmt(end_date)

                df = await loop.run_in_executor(None, lambda k=kw: self.pro.cashflow(**k))
                if df is None or df.empty:
                    results_cf[name] = {"ts_code": ts_code, "data": [], "count": 0}
                    continue

                df = df.sort_values("end_date", ascending=False).head(limit)
                recs = [{k: (None if pd.isna(v) else v) for k, v in row.items()}
                        for row in df.to_dict("records")]
                results_cf[name] = {"ts_code": ts_code, "data": recs, "count": len(recs)}
            except Exception as e:
                results_cf[name] = {"ts_code": ts_code, "error": str(e)}

        return {"success": True, "results": results_cf,
                "query_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

    # ── Tool: get_share_float (限售股解禁) ────────────────────────────────────

    async def get_share_float(
        self,
        stock_names: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """获取A股限售股解禁计划"""
        if not self.pro:
            return {"success": False, "error": "Tushare Pro not available"}

        def fmt(d: Optional[str]) -> Optional[str]:
            return d.replace("-", "") if d else None

        kw: Dict[str, Any] = {}
        if fmt(start_date):
            kw["start_date"] = fmt(start_date)
        if fmt(end_date):
            kw["end_date"] = fmt(end_date)

        ts_code_filter = None
        if stock_names:
            names = [n.strip() for n in stock_names.split(",") if n.strip()]
            name_code = await self._names_to_codes(names)
            if name_code:
                if len(name_code) == 1:
                    kw["ts_code"] = list(name_code.values())[0]
                else:
                    ts_code_filter = list(name_code.values())

        if not kw:
            return {"success": False, "error": "请提供 stock_names 或日期范围"}

        try:
            loop = asyncio.get_running_loop()
            df = await loop.run_in_executor(None, lambda: self.pro.share_float(**kw))
            if df is None or df.empty:
                return {"success": True, "data": [], "count": 0}

            if ts_code_filter:
                df = df[df["ts_code"].isin(ts_code_filter)]

            df = df.sort_values("float_date", ascending=True)
            recs = [{k: (None if pd.isna(v) else v) for k, v in row.items()}
                    for row in df.head(100).to_dict("records")]

            return {"success": True, "data": recs, "count": len(recs),
                    "query_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── Tool: get_research_report (券商研报) ─────────────────────────────────

    async def get_research_report(
        self,
        stock_names: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """获取A股券商研报（评级/目标价/盈利预测）"""
        if not self.pro:
            return {"success": False, "error": "Tushare Pro not available"}

        def fmt(d: Optional[str]) -> Optional[str]:
            return d.replace("-", "") if d else None

        kw: Dict[str, Any] = {}
        if fmt(start_date):
            kw["start_date"] = fmt(start_date)
        if fmt(end_date):
            kw["end_date"] = fmt(end_date)

        ts_code_filter = None
        if stock_names:
            names = [n.strip() for n in stock_names.split(",") if n.strip()]
            name_code = await self._names_to_codes(names)
            if name_code:
                if len(name_code) == 1:
                    kw["ts_code"] = list(name_code.values())[0]
                else:
                    ts_code_filter = list(name_code.values())

        if not kw:
            return {"success": False, "error": "请提供 stock_names 或日期范围"}

        try:
            loop = asyncio.get_running_loop()
            df = await loop.run_in_executor(None, lambda: self.pro.report_rc(**kw))
            if df is None or df.empty:
                return {"success": True, "data": [], "count": 0}

            if ts_code_filter:
                df = df[df["ts_code"].isin(ts_code_filter)]

            df = df.sort_values("report_date", ascending=False).head(limit)
            recs = [{k: (None if pd.isna(v) else v) for k, v in row.items()}
                    for row in df.to_dict("records")]

            return {"success": True, "data": recs, "count": len(recs),
                    "query_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── Tool: get_peer_comparison (同行业对比) ────────────────────────────────

    async def get_peer_comparison(
        self,
        stock_names: str,
        trade_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        同行业公司估值横向对比。
        查目标股行业，拉同行业所有股票估值指标做排名。
        """
        if not self.pro:
            return {"success": False, "error": "Tushare Pro not available"}

        names = [n.strip() for n in stock_names.split(",") if n.strip()]
        name_code = await self._names_to_codes(names)
        if not name_code:
            return {"success": False, "error": f"无法解析股票名称: {stock_names}"}

        loop = asyncio.get_running_loop()
        basic_df = await self._stock_basic_df()
        if basic_df is None:
            return {"success": False, "error": "无法获取股票基础列表"}

        results_peer: Dict[str, Any] = {}

        for name, ts_code in name_code.items():
            try:
                target = basic_df[basic_df["ts_code"] == ts_code]
                if target.empty:
                    results_peer[name] = {"error": f"未找到 {ts_code} 的基本信息"}
                    continue
                industry = target.iloc[0].get("industry")
                if not industry:
                    results_peer[name] = {"error": "未找到行业信息"}
                    continue

                peers = basic_df[basic_df["industry"] == industry]["ts_code"].tolist()

                td = trade_date.replace("-", "") if trade_date else None
                if not td:
                    sample = await loop.run_in_executor(
                        None, lambda: self.pro.daily_basic(ts_code=ts_code)
                    )
                    if sample is not None and not sample.empty:
                        td = sample["trade_date"].max()
                    else:
                        results_peer[name] = {"error": "无法确定最近交易日"}
                        continue

                df = await loop.run_in_executor(
                    None, lambda d=td: self.pro.daily_basic(trade_date=d)
                )
                if df is None or df.empty:
                    results_peer[name] = {"error": "无法获取估值数据"}
                    continue

                df = df[df["ts_code"].isin(peers)].copy()
                if df.empty:
                    results_peer[name] = {"error": f"行业 '{industry}' 无估值数据"}
                    continue

                name_map = dict(zip(basic_df["ts_code"], basic_df["name"]))
                df["name"] = df["ts_code"].map(name_map)

                cols = ["ts_code", "name", "close", "pe", "pe_ttm", "pb",
                        "ps", "ps_ttm", "turnover_rate", "total_mv", "circ_mv"]
                cols = [c for c in cols if c in df.columns]
                df = df[cols].copy()

                recs = [{k: (None if pd.isna(v) else v) for k, v in rd.items()}
                        for rd in df.to_dict("records")]

                metric_cols = ["pe_ttm", "pb", "ps_ttm", "turnover_rate", "total_mv"]
                stats = {}
                for col in metric_cols:
                    if col in df.columns:
                        s = df[col].dropna()
                        if not s.empty:
                            stats[col] = {
                                "mean": round(float(s.mean()), 2),
                                "median": round(float(s.median()), 2),
                                "min": round(float(s.min()), 2),
                                "max": round(float(s.max()), 2),
                            }

                target_row = df[df["ts_code"] == ts_code]
                target_pos = {}
                if not target_row.empty:
                    for col in metric_cols:
                        if col in target_row.columns:
                            val = target_row.iloc[0][col]
                            if pd.notna(val):
                                total = int(df[col].dropna().count())
                                rank = int((df[col].dropna() <= val).sum())
                                target_pos[col] = {
                                    "value": round(float(val), 2),
                                    "rank": rank, "total": total,
                                    "percentile": round(rank / total * 100, 1) if total else None,
                                }

                results_peer[name] = {
                    "ts_code": ts_code, "industry": industry,
                    "peer_count": len(recs),
                    "target_position": target_pos,
                    "industry_stats": stats,
                    "peers": sorted(recs, key=lambda x: x.get("total_mv") or 0, reverse=True)[:20],
                }
            except Exception as e:
                results_peer[name] = {"ts_code": ts_code, "error": str(e)}

        return {"success": True, "results": results_peer,
                "query_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

    # ── Tool: get_stock_mins (分钟K线) ────────────────────────────────────────

    async def get_stock_mins(
        self,
        stock_names: str,
        freq: str = "5min",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 240,
    ) -> Dict[str, Any]:
        """获取A股分钟级K线数据（1/5/15/30/60分钟）"""
        if not self.pro:
            return {"success": False, "error": "Tushare Pro not available"}

        valid_freqs = {"1min", "5min", "15min", "30min", "60min"}
        if freq not in valid_freqs:
            return {"success": False, "error": f"freq 必须是 {valid_freqs} 之一"}

        names = [n.strip() for n in stock_names.split(",") if n.strip()]
        name_code = await self._names_to_codes(names)
        if not name_code:
            return {"success": False, "error": f"无法解析股票名称: {stock_names}"}

        def fmt(d: Optional[str]) -> Optional[str]:
            return d.replace("-", "") if d else None

        loop = asyncio.get_running_loop()
        results_mins: Dict[str, Any] = {}

        for name, ts_code in name_code.items():
            try:
                kw: Dict[str, Any] = {"ts_code": ts_code, "freq": freq}
                if fmt(start_date):
                    kw["start_date"] = fmt(start_date)
                if fmt(end_date):
                    kw["end_date"] = fmt(end_date)

                df = await loop.run_in_executor(None, lambda k=kw: self.pro.stk_mins(**k))
                if df is None or df.empty:
                    results_mins[name] = {"ts_code": ts_code, "data": [], "count": 0}
                    continue

                df = df.sort_values("trade_time", ascending=False).head(limit)
                df = df.sort_values("trade_time", ascending=True)
                recs = [{k: (None if pd.isna(v) else v) for k, v in row.items()}
                        for row in df.to_dict("records")]
                results_mins[name] = {"ts_code": ts_code, "data": recs, "count": len(recs)}
            except Exception as e:
                results_mins[name] = {"ts_code": ts_code, "error": str(e)}

        return {"success": True, "results": results_mins,
                "query_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

    # ── Tool: get_macro_data (宏观经济数据) ───────────────────────────────────

    async def get_macro_data(
        self,
        indicator: str = "all",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 12,
    ) -> Dict[str, Any]:
        """
        获取中国宏观经济数据（CPI/PPI/货币供应/GDP/SHIBOR）
        indicator: 'cpi','ppi','money','gdp','shibor','all'
        """
        if not self.pro:
            return {"success": False, "error": "Tushare Pro not available"}

        loop = asyncio.get_running_loop()
        results_macro: Dict[str, Any] = {}

        indicators = [indicator] if indicator != "all" else ["cpi", "ppi", "money", "gdp", "shibor"]

        for ind in indicators:
            try:
                if ind == "cpi":
                    kw: Dict[str, Any] = {}
                    if start_date:
                        kw["start_month"] = start_date.replace("-", "")[:6]
                    if end_date:
                        kw["end_month"] = end_date.replace("-", "")[:6]
                    df = await loop.run_in_executor(None, lambda k=kw: self.pro.cn_cpi(**k))
                    if df is not None and not df.empty:
                        df = df.sort_values("month", ascending=False).head(limit)
                        # 只保留关键列
                        key_cols = ["month", "nt_val", "nt_yoy", "nt_mom", "nt_accu"]
                        key_cols = [c for c in key_cols if c in df.columns]
                        df = df[key_cols]

                elif ind == "ppi":
                    kw = {}
                    if start_date:
                        kw["start_month"] = start_date.replace("-", "")[:6]
                    if end_date:
                        kw["end_month"] = end_date.replace("-", "")[:6]
                    df = await loop.run_in_executor(None, lambda k=kw: self.pro.cn_ppi(**k))
                    if df is not None and not df.empty:
                        df = df.sort_values("month", ascending=False).head(limit)
                        key_cols = ["month", "ppi_yoy", "ppi_mp_yoy", "ppi_cg_yoy"]
                        key_cols = [c for c in key_cols if c in df.columns]
                        df = df[key_cols]

                elif ind == "money":
                    kw = {}
                    if start_date:
                        kw["start_month"] = start_date.replace("-", "")[:6]
                    if end_date:
                        kw["end_month"] = end_date.replace("-", "")[:6]
                    df = await loop.run_in_executor(None, lambda k=kw: self.pro.cn_m(**k))
                    if df is not None and not df.empty:
                        df = df.sort_values("month", ascending=False).head(limit)
                        key_cols = ["month", "m0", "m0_yoy", "m1", "m1_yoy", "m2", "m2_yoy"]
                        key_cols = [c for c in key_cols if c in df.columns]
                        df = df[key_cols]

                elif ind == "gdp":
                    kw = {}
                    if start_date:
                        y = start_date[:4]
                        kw["start_q"] = f"{y}Q1"
                    if end_date:
                        y = end_date[:4]
                        kw["end_q"] = f"{y}Q4"
                    df = await loop.run_in_executor(None, lambda k=kw: self.pro.cn_gdp(**k))
                    if df is not None and not df.empty:
                        df = df.sort_values("quarter", ascending=False).head(limit)
                        key_cols = ["quarter", "gdp", "gdp_yoy", "pi", "si", "ti", "ti_yoy"]
                        key_cols = [c for c in key_cols if c in df.columns]
                        df = df[key_cols]

                elif ind == "shibor":
                    kw = {}
                    if start_date:
                        kw["start_date"] = start_date.replace("-", "")
                    if end_date:
                        kw["end_date"] = end_date.replace("-", "")
                    df = await loop.run_in_executor(None, lambda k=kw: self.pro.shibor(**k))
                    if df is not None and not df.empty:
                        df = df.sort_values("date", ascending=False).head(limit)

                else:
                    results_macro[ind] = {"error": f"未知指标: {ind}"}
                    continue

                if df is not None and not df.empty:
                    recs = [{k: (None if pd.isna(v) else v) for k, v in row.items()}
                            for row in df.to_dict("records")]
                    results_macro[ind] = {"data": recs, "count": len(recs)}
                else:
                    results_macro[ind] = {"data": [], "count": 0}
            except Exception as e:
                results_macro[ind] = {"error": str(e)}

        return {"success": True, "results": results_macro,
                "query_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
