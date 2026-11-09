"""計算ツールの中身（specs/020 R4）。

小さなモデルは表の値の合計などを暗算で誤る（harukaze_mix hm22）ので、式を渡して値を返す。
eval は使わず、ast で数・四則演算・括弧・いくつかの関数だけを許して Decimal で計算する。
"""

import ast
import operator
import re
import unicodedata
from collections.abc import Callable
from decimal import Decimal, DivisionByZero, InvalidOperation, localcontext

MAX_LEN = 500
MAX_EXP = 100
MAX_DIGITS = 60


class CalcError(ValueError):
    """計算できない式。メッセージはモデルに返す。"""


_ALLOWED = "数・+ - * / ( ) と sum・avg・min・max・round・abs だけ使えます"


_BIN: dict[type[ast.operator], Callable[[Decimal, Decimal], Decimal]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
}


def _round(x: Decimal, n: Decimal = Decimal(0)) -> Decimal:
    return round(x, int(n))


_FUNCS: dict[str, Callable[..., Decimal]] = {
    "sum": lambda *a: sum(a, Decimal(0)),
    "min": min,
    "max": max,
    "abs": abs,
    "round": _round,
    "avg": lambda *a: sum(a, Decimal(0)) / len(a),
}

# 3 桁ごとのカンマ（1,200）だけを外す。関数の引数の区切り（sum(30, 25)）は残す
_THOUSANDS = re.compile(r"(?<=\d),(?=\d{3}(?!\d))")


def _normalize(expr: str) -> str:
    s = unicodedata.normalize("NFKC", expr).replace("×", "*").replace("÷", "/")
    return _THOUSANDS.sub("", s)


def evaluate(expr: str) -> str:
    """式を計算し、結果を文字列で返す（末尾の 0 は落とす）。"""
    if not expr.strip() or len(expr) > MAX_LEN:
        raise CalcError(f"式は 1〜{MAX_LEN} 文字にしてください")
    try:
        tree = ast.parse(_normalize(expr), mode="eval")
    except SyntaxError as e:
        raise CalcError(f"式を読めませんでした（{_ALLOWED}）") from e
    with localcontext() as ctx:
        ctx.prec = 28
        try:
            v = _eval(tree.body)
        except (DivisionByZero, InvalidOperation, ZeroDivisionError) as e:
            raise CalcError("計算できませんでした（0 での割り算など）") from e
    if v.adjusted() > MAX_DIGITS:
        raise CalcError("結果が大きすぎます")
    out = format(v.normalize(), "f")
    return "0" if out == "-0" else out


def _eval(node: ast.expr) -> Decimal:
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        return Decimal(str(node.value))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub | ast.UAdd):
        v = _eval(node.operand)
        return -v if isinstance(node.op, ast.USub) else v
    if isinstance(node, ast.BinOp):
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow):
            if abs(right) > MAX_EXP:
                raise CalcError(f"累乗の指数は {MAX_EXP} 以下にしてください")
            return left**right
        op = _BIN.get(type(node.op))
        if op is None:
            raise CalcError("使えない演算子があります")
        return op(left, right)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS:
        if node.keywords:
            raise CalcError(_ALLOWED)
        args = [_eval(a) for a in node.args]
        if not args:
            raise CalcError(f"{node.func.id} に値がありません")
        return _FUNCS[node.func.id](*args)
    raise CalcError(_ALLOWED)
