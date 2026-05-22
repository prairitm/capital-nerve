"""Unit tests for the safe AST formula evaluator.

These tests run without a database — they only exercise pure expression
evaluation. Run with::

    cd backend && pytest tests/test_formula.py
"""
from __future__ import annotations

import pytest

from app.services.pipeline.formula import FormulaError, evaluate


def test_simple_arithmetic():
    res = evaluate("(a - b) / b * 100", {"a": 110.0, "b": 100.0})
    assert res.value == pytest.approx(10.0)


def test_short_circuits_on_none():
    res = evaluate("(a - b) / b * 100", {"a": None, "b": 100.0})
    assert res.value is None


def test_unknown_input_raises():
    with pytest.raises(FormulaError):
        evaluate("a + b", {"a": 1.0})


def test_division_by_zero_returns_none():
    # We treat / 0 as a missing metric, not a crash, so partial documents
    # don't kill the whole pipeline run.
    res = evaluate("a / b", {"a": 10.0, "b": 0.0})
    assert res.value is None


def test_calls_only_whitelisted_funcs():
    res = evaluate("min(a, b) * abs(c)", {"a": 4, "b": 7, "c": -3})
    assert res.value == pytest.approx(12.0)


def test_avg_helper():
    res = evaluate("avg(a, b, c)", {"a": 10, "b": 20, "c": 30})
    assert res.value == pytest.approx(20.0)


def test_rejects_attribute_access():
    with pytest.raises(FormulaError):
        evaluate("a.__class__", {"a": 1})


def test_rejects_unknown_function():
    with pytest.raises(FormulaError):
        evaluate("pow(a, b)", {"a": 2, "b": 3})


def test_rejects_lambda():
    with pytest.raises(FormulaError):
        evaluate("(lambda: 1)()", {})


def test_rejects_subscript():
    with pytest.raises(FormulaError):
        evaluate("a[0]", {"a": 1})


def test_rejects_huge_exponent():
    with pytest.raises(FormulaError):
        evaluate("a ** b", {"a": 2, "b": 100})


def test_compare_returns_bool_as_float():
    res = evaluate("a > b", {"a": 5, "b": 1})
    assert res.value == 1.0


def test_chained_compare():
    res = evaluate("a < b < c", {"a": 1, "b": 2, "c": 3})
    assert res.value == 1.0


def test_bool_op():
    res = evaluate("(a > 0) and (b > 0)", {"a": 1, "b": -1})
    assert res.value == 0.0


def test_ifexp():
    res = evaluate("a if a > 0 else b", {"a": -1, "b": 5})
    assert res.value == pytest.approx(5.0)


def test_negative_number():
    res = evaluate("-a + b", {"a": 5, "b": 10})
    assert res.value == pytest.approx(5.0)
