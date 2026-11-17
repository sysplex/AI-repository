"""单元测试：提醒规则评估器（Price, Technical, Earnings, ThesisBreakers）（M10-T03）。"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from app.modules.notify.enums import AlertType, ComparisonOperator, PriceDirection
from app.modules.notify.evaluators import (
    EarningsDateEvaluator,
    PriceAlertEvaluator,
    TechnicalSignalEvaluator,
    ThesisBreakerEvaluator,
    get_evaluator,
)
from app.modules.notify.models import Alert


def _make_alert(
    alert_type: AlertType,
    conditions: dict[str, Any],
    symbol: str = "AAPL",
    title: str = "Test Alert",
) -> Alert:
    return Alert(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        symbol=symbol,
        alert_type=alert_type.value,
        title=title,
        conditions=conditions,
        status="active",
        cooldown_minutes=1440,
    )


class TestPriceAlertEvaluator:
    """价格突破提醒评估器测试。"""

    def setup_method(self) -> None:
        self.evaluator = PriceAlertEvaluator()

    def test_cross_above_triggered_with_previous(self) -> None:
        alert = _make_alert(
            AlertType.PRICE,
            {"direction": PriceDirection.CROSS_ABOVE.value, "target_price": "230.00"},
        )
        context = {"current_price": Decimal("232.50"), "previous_price": Decimal("228.00")}
        res = self.evaluator.evaluate(alert, context)
        assert res.triggered is True
        assert "向上突破" in res.message
        assert res.triggered_value["current_price"] == "232.50"
        assert res.triggered_value["target_price"] == "230.00"

    def test_cross_above_not_triggered(self) -> None:
        alert = _make_alert(
            AlertType.PRICE,
            {"direction": PriceDirection.CROSS_ABOVE.value, "target_price": "230.00"},
        )
        context = {"current_price": Decimal("229.50"), "previous_price": Decimal("225.00")}
        res = self.evaluator.evaluate(alert, context)
        assert res.triggered is False

    def test_cross_above_without_previous(self) -> None:
        alert = _make_alert(
            AlertType.PRICE,
            {"direction": PriceDirection.CROSS_ABOVE.value, "target_price": "230.00"},
        )
        context = {"current_price": Decimal("235.00")}
        res = self.evaluator.evaluate(alert, context)
        assert res.triggered is True

    def test_cross_below_triggered_with_previous(self) -> None:
        alert = _make_alert(
            AlertType.PRICE,
            {"direction": PriceDirection.CROSS_BELOW.value, "target_price": "180.00"},
        )
        context = {"current_price": Decimal("178.50"), "previous_price": Decimal("182.00")}
        res = self.evaluator.evaluate(alert, context)
        assert res.triggered is True
        assert "向下跌破" in res.message

    def test_cross_below_not_triggered(self) -> None:
        alert = _make_alert(
            AlertType.PRICE,
            {"direction": PriceDirection.CROSS_BELOW.value, "target_price": "180.00"},
        )
        context = {"current_price": Decimal("185.00"), "previous_price": Decimal("190.00")}
        res = self.evaluator.evaluate(alert, context)
        assert res.triggered is False

    def test_missing_price_returns_false(self) -> None:
        alert = _make_alert(
            AlertType.PRICE,
            {"direction": PriceDirection.CROSS_ABOVE.value, "target_price": "230.00"},
        )
        res = self.evaluator.evaluate(alert, {})
        assert res.triggered is False

    def test_invalid_target_price_returns_false(self) -> None:
        alert = _make_alert(
            AlertType.PRICE,
            {"direction": PriceDirection.CROSS_ABOVE.value, "target_price": "-10"},
        )
        res = self.evaluator.evaluate(alert, {"current_price": 200})
        assert res.triggered is False


class TestTechnicalSignalEvaluator:
    """技术指标提醒评估器测试。"""

    def setup_method(self) -> None:
        self.evaluator = TechnicalSignalEvaluator()

    def test_rsi_oversold_triggered(self) -> None:
        alert = _make_alert(
            AlertType.TECHNICAL_SIGNAL,
            {
                "indicator": "RSI",
                "operator": ComparisonOperator.LT.value,
                "threshold": "30.0",
            },
        )
        context = {"indicators": {"RSI": Decimal("24.5")}}
        res = self.evaluator.evaluate(alert, context)
        assert res.triggered is True
        assert "RSI" in res.message
        assert res.triggered_value["actual_value"] == "24.5"

    def test_rsi_oversold_not_triggered(self) -> None:
        alert = _make_alert(
            AlertType.TECHNICAL_SIGNAL,
            {
                "indicator": "RSI",
                "operator": ComparisonOperator.LT.value,
                "threshold": "30.0",
            },
        )
        context = {"indicators": {"RSI": Decimal("35.0")}}
        res = self.evaluator.evaluate(alert, context)
        assert res.triggered is False

    def test_operator_variations_and_flat_context(self) -> None:
        alert = _make_alert(
            AlertType.TECHNICAL_SIGNAL,
            {
                "indicator": "SMA_20",
                "operator": ">=",
                "threshold": "150.0",
            },
        )
        context = {"SMA_20": Decimal("150.0")}
        res = self.evaluator.evaluate(alert, context)
        assert res.triggered is True

    def test_missing_indicator_returns_false(self) -> None:
        alert = _make_alert(
            AlertType.TECHNICAL_SIGNAL,
            {
                "indicator": "MACD",
                "operator": "gt",
                "threshold": "0",
            },
        )
        res = self.evaluator.evaluate(alert, {"indicators": {"RSI": 50}})
        assert res.triggered is False


class TestEarningsDateEvaluator:
    """财报日倒计时提醒评估器测试。"""

    def setup_method(self) -> None:
        self.evaluator = EarningsDateEvaluator()

    def test_earnings_date_in_range_triggered(self) -> None:
        alert = _make_alert(
            AlertType.EARNINGS_DATE,
            {"days_before": 3},
        )
        context = {
            "earnings_date": "2026-11-20",
            "as_of_date": date(2026, 11, 18),
        }
        res = self.evaluator.evaluate(alert, context)
        assert res.triggered is True
        assert "2 天后" in res.message
        assert res.triggered_value["days_remaining"] == 2

    def test_earnings_date_today_triggered(self) -> None:
        alert = _make_alert(
            AlertType.EARNINGS_DATE,
            {"days_before": 1},
        )
        context = {
            "earnings_date": "2026-11-18",
            "as_of_date": date(2026, 11, 18),
        }
        res = self.evaluator.evaluate(alert, context)
        assert res.triggered is True
        assert "将于今日" in res.message
        assert res.triggered_value["days_remaining"] == 0

    def test_earnings_date_too_far_not_triggered(self) -> None:
        alert = _make_alert(
            AlertType.EARNINGS_DATE,
            {"days_before": 2},
        )
        context = {
            "earnings_date": "2026-11-25",
            "as_of_date": date(2026, 11, 18),
        }
        res = self.evaluator.evaluate(alert, context)
        assert res.triggered is False

    def test_past_earnings_date_not_triggered(self) -> None:
        alert = _make_alert(
            AlertType.EARNINGS_DATE,
            {"days_before": 3},
        )
        context = {
            "earnings_date": "2026-11-10",
            "as_of_date": date(2026, 11, 18),
        }
        res = self.evaluator.evaluate(alert, context)
        assert res.triggered is False

    def test_missing_earnings_date_returns_false(self) -> None:
        alert = _make_alert(
            AlertType.EARNINGS_DATE,
            {"days_before": 3},
        )
        res = self.evaluator.evaluate(alert, {})
        assert res.triggered is False


class TestThesisBreakerEvaluator:
    """长期持有论文破裂（Thesis Breakers）评估器测试（对齐 M7 投资研究）。"""

    def setup_method(self) -> None:
        self.evaluator = ThesisBreakerEvaluator()

    def test_net_margin_breached_nested_context(self) -> None:
        alert = _make_alert(
            AlertType.THESIS_BREAKER,
            {
                "metric": "net_margin",
                "operator": "lt",
                "threshold": "0.15",
                "data_field": "fundamentals.net_margin",
                "description": "净利润率跌破 15% 说明竞争优势衰退",
            },
        )
        context = {
            "fundamentals": {
                "net_margin": Decimal("0.115"),
                "pe_trailing": Decimal("28.0"),
            }
        }
        res = self.evaluator.evaluate(alert, context)
        assert res.triggered is True
        assert "论文破裂预警" in res.message
        assert "净利润率跌破 15%" in res.message
        assert res.triggered_value["actual_value"] == "0.115"
        assert res.triggered_value["threshold"] == "0.15"

    def test_net_margin_healthy_not_triggered(self) -> None:
        alert = _make_alert(
            AlertType.THESIS_BREAKER,
            {
                "metric": "net_margin",
                "operator": "lt",
                "threshold": "0.15",
                "data_field": "fundamentals.net_margin",
            },
        )
        context = {
            "fundamentals": {
                "net_margin": Decimal("0.22"),
            }
        }
        res = self.evaluator.evaluate(alert, context)
        assert res.triggered is False

    def test_string_threshold_parsing(self) -> None:
        alert = _make_alert(
            AlertType.THESIS_BREAKER,
            {
                "metric": "pe_trailing",
                "threshold": "> 45.0",
                "data_field": "fundamentals.pe_trailing",
            },
        )
        context = {
            "fundamentals": {
                "pe_trailing": Decimal("52.4"),
            }
        }
        res = self.evaluator.evaluate(alert, context)
        assert res.triggered is True
        assert res.triggered_value["operator"] == "gt"
        assert res.triggered_value["threshold"] == "45.0"

    def test_percentage_format_tolerance(self) -> None:
        alert = _make_alert(
            AlertType.THESIS_BREAKER,
            {
                "metric": "revenue_growth",
                "operator": "lt",
                "threshold": "10%",
                "data_field": "fundamentals.revenue_growth",
            },
        )
        context = {"fundamentals": {"revenue_growth": "8.5%"}}
        res = self.evaluator.evaluate(alert, context)
        assert res.triggered is True

    def test_missing_data_field_returns_false(self) -> None:
        alert = _make_alert(
            AlertType.THESIS_BREAKER,
            {
                "metric": "debt_to_equity",
                "operator": "gt",
                "threshold": "2.0",
                "data_field": "fundamentals.debt_to_equity",
            },
        )
        context: dict[str, Any] = {"fundamentals": {}}
        res = self.evaluator.evaluate(alert, context)
        assert res.triggered is False


class TestEvaluatorFactory:
    """工厂方法测试。"""

    def test_get_evaluator_all_types(self) -> None:
        assert isinstance(get_evaluator(AlertType.PRICE), PriceAlertEvaluator)
        assert isinstance(get_evaluator(AlertType.TECHNICAL_SIGNAL), TechnicalSignalEvaluator)
        assert isinstance(get_evaluator(AlertType.EARNINGS_DATE), EarningsDateEvaluator)
        assert isinstance(get_evaluator(AlertType.THESIS_BREAKER), ThesisBreakerEvaluator)
        assert isinstance(get_evaluator("price"), PriceAlertEvaluator)
        assert get_evaluator("unknown_type") is None
