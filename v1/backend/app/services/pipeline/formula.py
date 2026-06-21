"""Safe AST-based expression evaluator for `MetricDefinition.formula_text`.

The metric engine reads a user-authored formula like
`(revenue - revenue_py) / revenue_py * 100` and evaluates it against a dict of
named inputs. We never call `eval()` or `exec()`; we walk the parsed AST and
allow only a small set of nodes:

- Literals (int / float / bool / None)
- Names (looked up in the input dict)
- BinOp:    + - * / // % **
- UnaryOp:  + - not
- BoolOp:   and / or
- Compare:  <  <=  >  >=  ==  !=  (chained)
- IfExp:    a if cond else b
- Calls to a small whitelist (`min`, `max`, `abs`, `avg`)

Anything else (attribute access, subscript, lambda, comprehension, import,
assignment, augassign, function def, etc.) raises `FormulaError`.

The evaluator is intentionally pure: no DB access, no IO. Inputs come in as a
plain `dict[str, float | int | None]`. A `None` input short-circuits the whole
evaluation to `None`, which the metrics engine treats as "skip this metric"
(consistent with the existing pipeline pattern of dropping metrics that lack
inputs rather than raising).
"""
from __future__ import annotations

import ast
import logging
from dataclasses import dataclass
from typing import Any, Mapping

logger = logging.getLogger(__name__)


class FormulaError(ValueError):
    """Raised when a formula contains a disallowed construct or fails to parse."""


@dataclass(frozen=True)
class FormulaResult:
    """Output of evaluating one formula. `value` is `None` if any input was None."""

    value: float | None
    inputs_used: dict[str, float | int | None]


# Single source of truth for whitelisted helper names. Extending this requires
# a code review; never accept a callable from the inputs dict.
def _safe_avg(*xs: Any) -> float | None:
    nums = [x for x in xs if x is not None]
    if not nums:
        return None
    return sum(nums) / len(nums)


_ALLOWED_FUNCS: dict[str, Any] = {
    "min": min,
    "max": max,
    "abs": abs,
    "avg": _safe_avg,
}


_ALLOWED_NODES: tuple[type[ast.AST], ...] = (
    ast.Expression,
    ast.Constant,
    ast.Name,
    ast.Load,
    ast.BinOp,
    ast.UnaryOp,
    ast.BoolOp,
    ast.Compare,
    ast.IfExp,
    ast.Call,
    # Operators
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Pow,
    ast.UAdd,
    ast.USub,
    ast.Not,
    ast.And,
    ast.Or,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
)


def evaluate(formula: str, inputs: Mapping[str, Any]) -> FormulaResult:
    """Parse `formula` and evaluate it against `inputs`.

    Returns `FormulaResult(value=None, ...)` if any referenced input is
    missing or `None`. Raises `FormulaError` on any other problem.
    """
    if not formula or not formula.strip():
        raise FormulaError("Empty formula")

    try:
        tree = ast.parse(formula, mode="eval")
    except SyntaxError as exc:
        raise FormulaError(f"Could not parse formula: {exc}") from exc

    referenced: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise FormulaError(
                f"Disallowed node {type(node).__name__} in formula `{formula}`"
            )
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise FormulaError("Only direct named-function calls are allowed")
            if node.func.id not in _ALLOWED_FUNCS:
                raise FormulaError(f"Function `{node.func.id}` is not whitelisted")
            if node.keywords:
                raise FormulaError("Keyword arguments are not allowed in formulas")
        if isinstance(node, ast.Name):
            referenced.add(node.id)

    # Resolve inputs. Any reference that is neither a whitelisted function nor
    # provided in `inputs` is an error (typo guard). Missing-but-declared inputs
    # become `None` and short-circuit the result.
    resolved: dict[str, float | int | None] = {}
    for name in referenced:
        if name in _ALLOWED_FUNCS:
            continue
        if name not in inputs:
            raise FormulaError(
                f"Formula references unknown input `{name}` (formula: `{formula}`)"
            )
        resolved[name] = inputs[name]

    if any(v is None for v in resolved.values()):
        return FormulaResult(value=None, inputs_used=resolved)

    namespace: dict[str, Any] = {**_ALLOWED_FUNCS, **resolved}
    try:
        result = _eval(tree.body, namespace)
    except ZeroDivisionError:
        # Treat division by zero as a missing metric (same as a None input).
        return FormulaResult(value=None, inputs_used=resolved)
    except FormulaError:
        raise
    except Exception as exc:  # noqa: BLE001 — surface every other failure clearly
        raise FormulaError(f"Formula evaluation failed for `{formula}`: {exc}") from exc

    if isinstance(result, bool):
        # Boolean comparators stay boolean (used by signal engine when it
        # leans on this evaluator). Metrics callers always want a number, so
        # they see 1.0 / 0.0 — keep both contracts.
        return FormulaResult(value=float(result), inputs_used=resolved)
    if isinstance(result, (int, float)):
        return FormulaResult(value=float(result), inputs_used=resolved)
    raise FormulaError(
        f"Formula `{formula}` produced non-numeric value of type {type(result).__name__}"
    )


def _eval(node: ast.AST, ns: dict[str, Any]) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return ns[node.id]
    if isinstance(node, ast.BinOp):
        left = _eval(node.left, ns)
        right = _eval(node.right, ns)
        return _binop(node.op, left, right)
    if isinstance(node, ast.UnaryOp):
        operand = _eval(node.operand, ns)
        return _unaryop(node.op, operand)
    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            for v in node.values:
                ev = _eval(v, ns)
                if not ev:
                    return ev
            return ev
        if isinstance(node.op, ast.Or):
            ev = False
            for v in node.values:
                ev = _eval(v, ns)
                if ev:
                    return ev
            return ev
        raise FormulaError(f"Unsupported bool op {type(node.op).__name__}")
    if isinstance(node, ast.Compare):
        left = _eval(node.left, ns)
        for op, comparator in zip(node.ops, node.comparators):
            right = _eval(comparator, ns)
            if not _compare(op, left, right):
                return False
            left = right
        return True
    if isinstance(node, ast.IfExp):
        return _eval(node.body, ns) if _eval(node.test, ns) else _eval(node.orelse, ns)
    if isinstance(node, ast.Call):
        func = ns[node.func.id]  # type: ignore[union-attr]
        args = [_eval(a, ns) for a in node.args]
        return func(*args)
    raise FormulaError(f"Unsupported node {type(node).__name__}")


def _binop(op: ast.AST, left: Any, right: Any) -> Any:
    if isinstance(op, ast.Add):
        return left + right
    if isinstance(op, ast.Sub):
        return left - right
    if isinstance(op, ast.Mult):
        return left * right
    if isinstance(op, ast.Div):
        return left / right
    if isinstance(op, ast.FloorDiv):
        return left // right
    if isinstance(op, ast.Mod):
        return left % right
    if isinstance(op, ast.Pow):
        # Cap exponent magnitude to keep formulas from DOS-ing the worker.
        if isinstance(right, (int, float)) and abs(right) > 16:
            raise FormulaError("Exponent too large in formula")
        return left ** right
    raise FormulaError(f"Unsupported binary op {type(op).__name__}")


def _unaryop(op: ast.AST, operand: Any) -> Any:
    if isinstance(op, ast.UAdd):
        return +operand
    if isinstance(op, ast.USub):
        return -operand
    if isinstance(op, ast.Not):
        return not operand
    raise FormulaError(f"Unsupported unary op {type(op).__name__}")


def _compare(op: ast.AST, left: Any, right: Any) -> bool:
    if isinstance(op, ast.Eq):
        return left == right
    if isinstance(op, ast.NotEq):
        return left != right
    if isinstance(op, ast.Lt):
        return left < right
    if isinstance(op, ast.LtE):
        return left <= right
    if isinstance(op, ast.Gt):
        return left > right
    if isinstance(op, ast.GtE):
        return left >= right
    raise FormulaError(f"Unsupported compare op {type(op).__name__}")
