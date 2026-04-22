import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
from unittest import mock

import stock_analyzer


class _FakeHTTPResponse:
    def __init__(self, body: str):
        self._body = body.encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def _run_main(argv: list[str]) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with mock.patch.object(stock_analyzer.sys, "argv", argv), redirect_stdout(stdout), redirect_stderr(stderr):
        rc = stock_analyzer.main()
    return rc, stdout.getvalue(), stderr.getvalue()


class TestHelpers(unittest.TestCase):
    def test_parse_price_rows_skips_invalid(self):
        rows = [
            {"Date": "2026-01-01", "Close": "100"},
            {"Date": "bad", "Close": "101"},
            {"Date": "2026-01-03", "Close": "-1"},
            {"X": "y"},
        ]
        prices = stock_analyzer._parse_price_rows(rows)
        self.assertEqual(len(prices), 1)
        self.assertEqual(prices[0].close, 100.0)

    def test_normalize_yahoo_symbol_variants(self):
        self.assertEqual(stock_analyzer._normalize_yahoo_symbol(""), [])
        self.assertEqual(stock_analyzer._normalize_yahoo_symbol("AAPL"), ["AAPL"])
        self.assertEqual(stock_analyzer._normalize_yahoo_symbol("aapl.us"), ["AAPL"])
        self.assertEqual(stock_analyzer._normalize_yahoo_symbol("0700.hk"), ["0700.HK"])
        self.assertEqual(
            stock_analyzer._normalize_yahoo_symbol("600519.cn"),
            ["600519.SS", "600519.SZ", "600519"],
        )
        self.assertEqual(stock_analyzer._normalize_yahoo_symbol("foo.bar"), ["FOO.BAR"])


class TestIndicators(unittest.TestCase):
    def test_moving_average_none_then_value(self):
        self.assertIsNone(stock_analyzer.moving_average([1.0, 2.0], 3))
        self.assertAlmostEqual(stock_analyzer.moving_average([1.0, 2.0, 3.0], 3), 2.0)

    def test_ema_and_series_none_then_value(self):
        self.assertIsNone(stock_analyzer.exponential_moving_average([1.0, 2.0], 3))
        self.assertEqual(stock_analyzer.ema_series([1.0, 2.0], 3), [])
        series = stock_analyzer.ema_series([1.0, 2.0, 3.0], 3)
        self.assertEqual(len(series), 1)
        self.assertAlmostEqual(series[0], 2.0)

    def test_rsi_branches(self):
        self.assertIsNone(stock_analyzer.compute_rsi([1.0] * 10, 14))
        values = list(range(1, 40))
        self.assertEqual(stock_analyzer.compute_rsi(values, 14), 100.0)

    def test_macd_branches(self):
        self.assertEqual(stock_analyzer.compute_macd([1.0] * 10), (None, None, None))
        demo = stock_analyzer.generate_demo_prices(120)
        closes = [p.close for p in demo]
        macd, signal, hist = stock_analyzer.compute_macd(closes)
        self.assertIsNotNone(macd)
        self.assertIsNotNone(signal)
        self.assertIsNotNone(hist)

    def test_change_volatility_format(self):
        self.assertIsNone(stock_analyzer.annualized_volatility([1.0]))
        self.assertIsNone(stock_analyzer.percent_change([1.0, 2.0], 2))
        self.assertEqual(stock_analyzer.format_pct(None), "N/A")
        self.assertEqual(stock_analyzer.format_num(None), "N/A")

    def test_score_signal_branches(self):
        stance, _ = stock_analyzer.score_signal(
            latest=110.0,
            sma20=100.0,
            sma60=90.0,
            rsi=25.0,
            macd_hist=1.0,
            change20=-0.10,
        )
        self.assertEqual(stance, "偏多")

        stance, _ = stock_analyzer.score_signal(
            latest=90.0,
            sma20=100.0,
            sma60=110.0,
            rsi=80.0,
            macd_hist=-1.0,
            change20=0.10,
        )
        self.assertEqual(stance, "偏空")

        stance, _ = stock_analyzer.score_signal(
            latest=100.0,
            sma20=None,
            sma60=None,
            rsi=None,
            macd_hist=None,
            change20=None,
        )
        self.assertEqual(stance, "中性")

    def test_analyze_prices_no_indicators_reason_branch(self):
        prices = [stock_analyzer.PriceBar(date=datetime(2026, 1, 1), close=100.0)]
        report = stock_analyzer.analyze_prices("x", prices)
        self.assertIn("结论:", report)
        self.assertIn("指标数据不足", report)

    def test_analyze_prices_empty_raises(self):
        with self.assertRaises(ValueError):
            stock_analyzer.analyze_prices("x", [])


class TestFetchOnline(unittest.TestCase):
    def test_fetch_stooq_urlerror_falls_back_to_yahoo(self):
        sentinel = [stock_analyzer.PriceBar(date=datetime(2026, 1, 1), close=1.0)]
        with mock.patch.object(stock_analyzer.urllib.request, "urlopen", side_effect=stock_analyzer.urllib.error.URLError("x")):
            with mock.patch.object(stock_analyzer, "fetch_yahoo_prices", return_value=sentinel) as fy:
                prices = stock_analyzer.fetch_stooq_prices("aapl.us", 5)
        fy.assert_called()
        self.assertIs(prices, sentinel)

    def test_fetch_stooq_invalid_csv_falls_back_to_yahoo(self):
        sentinel = [stock_analyzer.PriceBar(date=datetime(2026, 1, 1), close=1.0)]
        with mock.patch.object(stock_analyzer.urllib.request, "urlopen", return_value=_FakeHTTPResponse("Get your apikey:\n...")):
            with mock.patch.object(stock_analyzer, "fetch_yahoo_prices", return_value=sentinel) as fy:
                prices = stock_analyzer.fetch_stooq_prices("aapl.us", 5)
        fy.assert_called()
        self.assertIs(prices, sentinel)

    def test_fetch_stooq_valid_csv_no_fallback(self):
        csv_body = "Date,Open,High,Low,Close,Volume\n2026-01-01,1,1,1,100,0\n2026-01-02,1,1,1,101,0\n"
        with mock.patch.object(stock_analyzer.urllib.request, "urlopen", return_value=_FakeHTTPResponse(csv_body)):
            with mock.patch.object(stock_analyzer, "fetch_yahoo_prices") as fy:
                prices = stock_analyzer.fetch_stooq_prices("aapl.us", 10)
        fy.assert_not_called()
        self.assertEqual([p.close for p in prices], [100.0, 101.0])

    def test_fetch_yahoo_empty_symbol_raises(self):
        with self.assertRaises(ValueError):
            stock_analyzer.fetch_yahoo_prices("   ", 10)

    def test_fetch_yahoo_multiple_candidates_and_success(self):
        # 1) URLError -> try next candidate
        # 2) chart error -> try next candidate
        # 3) success -> returns prices
        payload_error = {"chart": {"result": None, "error": {"code": "Bad", "description": "bad"}}}
        now = int(datetime(2026, 1, 2).timestamp())
        payload_ok = {
            "chart": {
                "result": [
                    {
                        "timestamp": [now - 86400, now],
                        "indicators": {"quote": [{"close": [100.0, None]}]},
                    }
                ],
                "error": None,
            }
        }

        responses = [
            stock_analyzer.urllib.error.URLError("x"),
            _FakeHTTPResponse(json.dumps(payload_error)),
            _FakeHTTPResponse(json.dumps(payload_ok)),
        ]

        def _urlopen_side_effect(*args, **kwargs):
            item = responses.pop(0)
            if isinstance(item, Exception):
                raise item
            return item

        with mock.patch.object(stock_analyzer, "_normalize_yahoo_symbol", return_value=["A", "B", "C"]):
            with mock.patch.object(stock_analyzer.urllib.request, "urlopen", side_effect=_urlopen_side_effect):
                prices = stock_analyzer.fetch_yahoo_prices("x", 10)
        self.assertEqual(len(prices), 1)
        self.assertEqual(prices[0].close, 100.0)

    def test_fetch_yahoo_all_candidates_fail(self):
        with mock.patch.object(stock_analyzer, "_normalize_yahoo_symbol", return_value=["A", "B"]):
            with mock.patch.object(stock_analyzer.urllib.request, "urlopen", side_effect=stock_analyzer.urllib.error.URLError("x")):
                with self.assertRaises(RuntimeError):
                    stock_analyzer.fetch_yahoo_prices("x", 10)


class TestCLI(unittest.TestCase):
    def test_main_self_test_branch(self):
        rc, out, err = _run_main(["stock_analyzer.py", "--self-test"])
        self.assertEqual(rc, 0)
        self.assertIn("自检通过", out)
        self.assertEqual(err, "")

    def test_main_limit_invalid_branch(self):
        rc, out, err = _run_main(["stock_analyzer.py", "--source", "demo", "--limit", "0"])
        self.assertEqual(rc, 1)
        self.assertIn("--limit 必须大于 0", err)
        self.assertEqual(out, "")

    def test_main_timeout_invalid_branch(self):
        rc, out, err = _run_main(["stock_analyzer.py", "aapl.us", "--timeout", "0"])
        self.assertEqual(rc, 1)
        self.assertIn("--timeout 必须大于 0", err)
        self.assertEqual(out, "")

    def test_main_missing_symbol_branch(self):
        rc, out, err = _run_main(["stock_analyzer.py"])
        self.assertEqual(rc, 1)
        self.assertIn("在线模式必须提供股票代码", err)
        self.assertEqual(out, "")

    def test_main_demo_positive(self):
        rc, out, err = _run_main(["stock_analyzer.py", "--source", "demo", "--limit", "10"])
        self.assertEqual(rc, 0)
        self.assertIn("股票代码:", out)
        self.assertEqual(err, "")

    def test_main_online_positive_via_mock(self):
        sentinel = stock_analyzer.generate_demo_prices(50)
        with mock.patch.object(stock_analyzer, "fetch_stooq_prices", return_value=sentinel):
            rc, out, err = _run_main(["stock_analyzer.py", "aapl.us", "--limit", "50"])
        self.assertEqual(rc, 0)
        self.assertIn("股票代码: aapl.us", out)
        self.assertEqual(err, "")

    def test_main_yahoo_source_branch(self):
        sentinel = stock_analyzer.generate_demo_prices(50)
        with mock.patch.object(stock_analyzer, "fetch_yahoo_prices", return_value=sentinel) as fy:
            rc, out, err = _run_main(["stock_analyzer.py", "aapl.us", "--source", "yahoo", "--limit", "50"])
        self.assertEqual(rc, 0)
        self.assertIn("股票代码: aapl.us", out)
        self.assertEqual(err, "")
        fy.assert_called()

    def test_main_online_fetch_exception_branch(self):
        with mock.patch.object(stock_analyzer, "fetch_stooq_prices", side_effect=RuntimeError("boom")):
            rc, out, err = _run_main(["stock_analyzer.py", "aapl.us"])
        self.assertEqual(rc, 1)
        self.assertIn("错误:", err)
        self.assertEqual(out, "")


if __name__ == "__main__":
    unittest.main()
