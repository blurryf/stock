#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import socket
import statistics
import sys
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class PriceBar:
    date: datetime
    close: float


def _parse_price_rows(rows: list[dict[str, str]]) -> list[PriceBar]:
    prices: list[PriceBar] = []
    for row in rows:
        try:
            prices.append(
                PriceBar(
                    date=datetime.strptime(row["Date"], "%Y-%m-%d"),
                    close=float(row["Close"]),
                )
            )
        except (KeyError, ValueError):
            continue
    return [item for item in prices if item.close > 0]


def _normalize_yahoo_symbol(symbol: str) -> list[str]:
    normalized = symbol.strip()
    if not normalized:
        return []

    lower = normalized.lower()
    if "." not in lower:
        return [normalized.upper()]

    base, suffix = lower.rsplit(".", 1)
    if suffix == "us":
        return [base.upper()]
    if suffix == "hk":
        return [f"{base.upper()}.HK"]
    if suffix == "cn":
        return [f"{base}.SS", f"{base}.SZ", base.upper()]
    return [normalized.upper()]


def fetch_yahoo_prices(symbol: str, limit: int = 180, timeout: float = 10.0) -> list[PriceBar]:
    candidates = _normalize_yahoo_symbol(symbol)
    if not candidates:
        raise ValueError("股票代码不能为空")

    last_error: Exception | None = None
    for yahoo_symbol in candidates:
        query = urllib.parse.urlencode(
            {
                "range": "1y",
                "interval": "1d",
                "includePrePost": "false",
                "events": "div,splits",
            }
        )
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(yahoo_symbol)}?{query}"
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; StockAnalyzer/1.0; +https://example.local)"
            },
        )

        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, json.JSONDecodeError) as exc:
            last_error = exc
            continue

        chart = payload.get("chart", {})
        if chart.get("error"):
            last_error = RuntimeError(str(chart["error"]))
            continue

        results = chart.get("result") or []
        if not results:
            last_error = RuntimeError("Yahoo Finance 返回空结果")
            continue

        result = results[0]
        timestamps = result.get("timestamp") or []
        quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
        closes = quote.get("close") or []

        prices: list[PriceBar] = []
        for ts, close in zip(timestamps, closes):
            if close is None:
                continue
            try:
                prices.append(PriceBar(date=datetime.fromtimestamp(ts), close=float(close)))
            except (TypeError, ValueError, OSError):
                continue

        prices = [item for item in prices if item.close > 0]
        if prices:
            return prices[-limit:]

        last_error = RuntimeError("Yahoo Finance 返回的价格数据无效")

    if last_error is not None:
        raise RuntimeError(f"无法获取在线行情: {last_error}") from last_error
    raise RuntimeError("无法获取在线行情")


def fetch_stooq_prices(symbol: str, limit: int = 180, timeout: float = 10.0) -> list[PriceBar]:
    normalized = symbol.strip().lower()
    if not normalized:
        raise ValueError("股票代码不能为空")

    query = urllib.parse.urlencode({"s": normalized, "i": "d"})
    url = f"https://stooq.com/q/d/l/?{query}"

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; StockAnalyzer/1.0; +https://example.local)"
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except KeyboardInterrupt:
        raise
    except (urllib.error.URLError, TimeoutError, socket.timeout, ssl.SSLError):
        return fetch_yahoo_prices(symbol, limit, timeout=timeout)

    rows = list(csv.DictReader(raw.splitlines()))
    prices = _parse_price_rows(rows)
    if not prices:
        return fetch_yahoo_prices(symbol, limit, timeout=timeout)

    return prices[-limit:]


def generate_demo_prices(limit: int = 180) -> list[PriceBar]:
    start = datetime.now() - timedelta(days=limit * 2)
    prices: list[PriceBar] = []
    price = 100.0

    for idx in range(limit):
        current_day = start + timedelta(days=idx)
        drift = 0.18
        seasonality = math.sin(idx / 8) * 1.2
        pullback = math.cos(idx / 19) * 0.7
        price = max(10.0, price + drift + seasonality + pullback)
        prices.append(PriceBar(date=current_day, close=round(price, 2)))

    return prices


def moving_average(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def exponential_moving_average(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None

    multiplier = 2 / (period + 1)
    ema = sum(values[:period]) / period
    for value in values[period:]:
        ema = (value - ema) * multiplier + ema
    return ema


def ema_series(values: list[float], period: int) -> list[float]:
    if len(values) < period:
        return []

    multiplier = 2 / (period + 1)
    series: list[float] = []
    ema = sum(values[:period]) / period
    series.append(ema)
    for value in values[period:]:
        ema = (value - ema) * multiplier + ema
        series.append(ema)
    return series


def compute_rsi(values: list[float], period: int = 14) -> float | None:
    if len(values) <= period:
        return None

    gains: list[float] = []
    losses: list[float] = []
    for idx in range(1, len(values)):
        delta = values[idx] - values[idx - 1]
        gains.append(max(delta, 0.0))
        losses.append(abs(min(delta, 0.0)))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for idx in range(period, len(gains)):
        avg_gain = ((avg_gain * (period - 1)) + gains[idx]) / period
        avg_loss = ((avg_loss * (period - 1)) + losses[idx]) / period

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def compute_macd(values: list[float]) -> tuple[float | None, float | None, float | None]:
    if len(values) < 35:
        return None, None, None

    ema12_values = ema_series(values, 12)
    ema26_values = ema_series(values, 26)
    if not ema12_values or not ema26_values:
        return None, None, None

    macd_series = ema12_values[-len(ema26_values):]
    macd_series = [short - long for short, long in zip(macd_series, ema26_values)]
    signal_series = ema_series(macd_series, 9)
    if not signal_series:
        return None, None, None

    signal = signal_series[-1]
    macd = macd_series[-1]
    histogram = macd - signal
    return macd, signal, histogram


def compute_returns(values: list[float]) -> list[float]:
    returns: list[float] = []
    for idx in range(1, len(values)):
        previous = values[idx - 1]
        current = values[idx]
        returns.append((current - previous) / previous)
    return returns


def annualized_volatility(values: list[float]) -> float | None:
    returns = compute_returns(values)
    if len(returns) < 2:
        return None
    return statistics.stdev(returns) * math.sqrt(252)


def percent_change(values: list[float], period: int) -> float | None:
    if len(values) <= period:
        return None
    return (values[-1] - values[-1 - period]) / values[-1 - period]


def score_signal(
    latest: float,
    sma20: float | None,
    sma60: float | None,
    rsi: float | None,
    macd_hist: float | None,
    change20: float | None,
) -> tuple[str, list[str]]:
    score = 0
    reasons: list[str] = []

    if sma20 is not None and latest > sma20:
        score += 1
        reasons.append("价格位于 20 日均线上方")
    elif sma20 is not None:
        score -= 1
        reasons.append("价格跌破 20 日均线")

    if sma20 is not None and sma60 is not None and sma20 > sma60:
        score += 1
        reasons.append("20 日均线高于 60 日均线")
    elif sma20 is not None and sma60 is not None:
        score -= 1
        reasons.append("20 日均线低于 60 日均线")

    if rsi is not None and rsi < 30:
        score += 1
        reasons.append("RSI 低于 30，可能超卖")
    elif rsi is not None and rsi > 70:
        score -= 1
        reasons.append("RSI 高于 70，可能过热")

    if macd_hist is not None and macd_hist > 0:
        score += 1
        reasons.append("MACD 柱状图为正")
    elif macd_hist is not None:
        score -= 1
        reasons.append("MACD 柱状图为负")

    if change20 is not None and change20 > 0.08:
        score -= 1
        reasons.append("近 20 日涨幅较大，短线追高风险增加")
    elif change20 is not None and change20 < -0.08:
        score += 1
        reasons.append("近 20 日回撤较大，需观察企稳迹象")

    if score >= 3:
        return "偏多", reasons
    if score <= -2:
        return "偏空", reasons
    return "中性", reasons


def format_pct(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value * 100:.2f}%"


def format_num(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:.2f}"


def analyze_prices(symbol: str, prices: list[PriceBar]) -> str:
    if not prices:
        raise ValueError("没有可分析的价格数据")

    closes = [item.close for item in prices]
    latest = closes[-1]
    sma20 = moving_average(closes, 20)
    sma60 = moving_average(closes, 60)
    ema20 = exponential_moving_average(closes, 20)
    rsi14 = compute_rsi(closes, 14)
    macd, signal, histogram = compute_macd(closes)
    change5 = percent_change(closes, 5)
    change20 = percent_change(closes, 20)
    volatility = annualized_volatility(closes)
    stance, reasons = score_signal(latest, sma20, sma60, rsi14, histogram, change20)

    lines = [
        f"股票代码: {symbol}",
        f"数据区间: {prices[0].date.strftime('%Y-%m-%d')} -> {prices[-1].date.strftime('%Y-%m-%d')}",
        f"最新收盘价: {latest:.2f}",
        "",
        "关键指标",
        f"- SMA20: {format_num(sma20)}",
        f"- SMA60: {format_num(sma60)}",
        f"- EMA20: {format_num(ema20)}",
        f"- RSI14: {format_num(rsi14)}",
        f"- MACD: {format_num(macd)}",
        f"- Signal: {format_num(signal)}",
        f"- Histogram: {format_num(histogram)}",
        f"- 5日涨跌幅: {format_pct(change5)}",
        f"- 20日涨跌幅: {format_pct(change20)}",
        f"- 年化波动率: {format_pct(volatility)}",
        "",
        f"结论: {stance}",
        "依据:",
    ]
    if reasons:
        lines.extend(f"- {reason}" for reason in reasons)
    else:
        lines.append("- 指标数据不足，当前仅返回基础信息")
    lines.append("")
    lines.append("风险提示: 该工具基于历史价格和技术指标，不构成投资建议。")
    return "\n".join(lines)


def run_self_test() -> None:
    demo = generate_demo_prices(120)
    closes = [item.close for item in demo]

    assert moving_average(closes, 20) is not None
    assert exponential_moving_average(closes, 20) is not None
    assert compute_rsi(closes, 14) is not None

    macd = compute_macd(closes)
    assert all(value is not None for value in macd)

    report = analyze_prices("demo", demo)
    assert "股票代码: demo" in report
    assert "结论:" in report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="命令行股票分析工具")
    parser.add_argument(
        "symbol",
        nargs="?",
        default=None,
        help="股票代码，例如 aapl.us、msft.us、0700.hk；demo 模式可省略",
    )
    parser.add_argument(
        "--source",
        choices=("auto", "stooq", "yahoo", "demo"),
        default="auto",
        help="行情来源：auto(默认，优先 stooq 失败回退 yahoo)、stooq、yahoo、demo",
    )
    parser.add_argument("--limit", type=int, default=180, help="拉取或生成的数据条数，默认 180")
    parser.add_argument("--timeout", type=float, default=10.0, help="在线请求超时时间(秒)，默认 10")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="运行内置自检并退出",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.self_test:
        try:
            run_self_test()
        except AssertionError:
            print("错误: 自检失败", file=sys.stderr)
            return 1
        print("自检通过")
        return 0

    if args.limit <= 0:
        print("错误: --limit 必须大于 0", file=sys.stderr)
        return 1

    if args.timeout <= 0:
        print("错误: --timeout 必须大于 0", file=sys.stderr)
        return 1

    if args.source != "demo" and not args.symbol:
        print("错误: 在线模式必须提供股票代码", file=sys.stderr)
        return 1

    try:
        if args.source == "demo":
            prices = generate_demo_prices(args.limit)
            symbol = args.symbol or "demo"
        elif args.source == "yahoo":
            prices = fetch_yahoo_prices(args.symbol, args.limit, timeout=args.timeout)
            symbol = args.symbol
        else:
            # auto / stooq 都走 stooq，失败会在函数内部回退到 yahoo
            prices = fetch_stooq_prices(args.symbol, args.limit, timeout=args.timeout)
            symbol = args.symbol
    except Exception as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1

    print(analyze_prices(symbol, prices))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
