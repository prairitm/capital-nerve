# services/pipeline/formula

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Safe expression evaluator for `MetricDefinition.formula_text`. The metric
engine reads a user-authored formula like `(revenue - revenue_py) /
revenue_py * 100` and evaluates it against a dict of named inputs. Built on
Python's `ast` module with an explicit allowlist; never calls `eval()` or
`exec()`.

## Source

- Path: `backend/app/services/pipeline/formula.py`
- Layer: backend-service

## Contract

- `evaluate(formula: str, inputs: Mapping[str, Any]) -> FormulaResult` —
  parses, validates, and evaluates the formula. `FormulaResult.value` is
  `None` when any referenced input is `None` (treated as "missing input,
  drop the metric"); raises `FormulaError` for any other problem.
- `FormulaError` — raised on syntax errors, disallowed AST nodes, unknown
  function names, references to undeclared inputs, oversized exponents.

## Allowed AST nodes

- Literals (`Constant`).
- `Name` (resolved against `inputs` + the helper allowlist).
- `BinOp`: `+ - * / // % **`.
- `UnaryOp`: `+ - not`.
- `BoolOp`: `and / or`.
- `Compare` (chained): `< <= > >= == !=`.
- `IfExp`: `a if cond else b`.
- `Call` to whitelisted helpers only: `min`, `max`, `abs`, `avg`.

Anything else (attribute access, subscript, lambda, comprehension, import,
assignment, augassign, function def, etc.) → `FormulaError`. Exponents are
capped at `|exponent| <= 16` so a malicious metric definition can't burn a
worker.

## Dependencies

- May import: only `ast`, stdlib `dataclasses`, `logging`.
- Must not import: any other pipeline stage, SQLAlchemy, models, FastAPI.

## Patterns (symmetry)

- The `_safe_avg` helper ignores `None` arguments — callers can pass a list
  of TTM-style values and let the helper drop missing quarters.
- Division by zero returns `None` (not a crash). The metrics engine treats
  this the same as a missing input.
- Boolean comparisons return `1.0` / `0.0` so the engine can store the
  result as a numeric metric value when needed.

## Verification checklist

- [ ] `evaluate("a + b", {"a": 1})` raises `FormulaError` (typo guard).
- [ ] `evaluate("a / b", {"a": 1, "b": 0}).value is None`.
- [ ] `evaluate("a.__class__", {"a": 1})` raises `FormulaError`.
- [ ] `evaluate("pow(a, b)", ...)` raises `FormulaError` (`pow` not in allowlist).
- [ ] `evaluate("a ** b", {"a": 2, "b": 100})` raises `FormulaError` (exponent cap).
- [ ] `evaluate("a if a > 0 else b", {"a": -1, "b": 5}).value == 5.0`.
- [ ] All formulas in `seed_catalog.METRIC_DEFS` parse — covered by
      `tests/test_seed_config.py::test_every_metric_formula_parses`.
