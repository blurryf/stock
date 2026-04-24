#!/usr/bin/env python3
from __future__ import annotations

import os

from flask import Flask, render_template, request, url_for

from stock_analyzer import (
    _is_yahoo_only_symbol,
    analyze_prices,
    fetch_stooq_prices,
    fetch_yahoo_prices,
    generate_demo_prices,
    generate_price_chart,
    resolve_symbol,
)

app = Flask(__name__)


def fetch_prices(symbol: str, source: str, timeout: float, limit: int):
    if source == "demo":
        return generate_demo_prices(limit), "demo"

    resolved, force_yahoo, suggestions = resolve_symbol(symbol, timeout=timeout)
    if not resolved:
        raise ValueError("未识别的股票名称/代码")

    if source == "yahoo" or force_yahoo or _is_yahoo_only_symbol(resolved):
        return fetch_yahoo_prices(resolved, limit, timeout=timeout), resolved

    return fetch_stooq_prices(resolved, limit, timeout=timeout), resolved


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/analyze", methods=["POST"])
def analyze():
    symbol = request.form.get("symbol", "").strip()
    source = request.form.get("source", "auto")
    form_source = source
    try:
        timeout = float(request.form.get("timeout", "10"))
    except ValueError:
        timeout = 10.0

    try:
        limit = int(request.form.get("limit", "180"))
    except ValueError:
        limit = 180

    chart = request.form.get("chart") == "on"

    if source not in ("auto", "stooq", "yahoo", "demo"):
        form_source = source = "auto"

    fetch_source = "stooq" if source == "auto" else source

    if fetch_source != "demo" and not symbol:
        return render_template(
            "index.html",
            error="请输入股票代码或名称，或者选择 demo 模式。",
            form_values={"symbol": symbol, "source": form_source, "timeout": timeout, "limit": limit, "chart": chart},
        )

    try:
        prices, resolved_symbol = fetch_prices(symbol, fetch_source, timeout, limit)

        chart_url = None
        if chart and prices:
            chart_dir = os.path.join(app.static_folder, "charts")
            os.makedirs(chart_dir, exist_ok=True)
            chart_file = generate_price_chart(symbol or resolved_symbol, prices, output_dir=chart_dir)
            if chart_file:
                chart_url = url_for("static", filename=f"charts/{os.path.basename(chart_file)}")

        result = analyze_prices(
            resolved_symbol,
            prices,
            generate_chart=False,
            chart_name=symbol or resolved_symbol,
        )
        return render_template(
            "index.html",
            result=result,
            chart_url=chart_url,
            form_values={"symbol": symbol, "source": form_source, "timeout": timeout, "limit": limit, "chart": chart},
        )
    except Exception as exc:
        return render_template(
            "index.html",
            error=f"错误: {exc}",
            form_values={"symbol": symbol, "source": source, "timeout": timeout, "limit": limit, "chart": chart},
        )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
