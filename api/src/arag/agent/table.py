"""表の集計（specs/026 R12・R13）。資料の Markdown の表を読み、条件に合う行と合計を計算で求める。

小さいモデルは表の行を目で比べて誤る（harukaze_mix hm17: 在庫 4・発注点 4 を「下回る」と答える）。
条件と式だけをモデルに書かせ、行の選択と計算はここで行う。式は ast で読み、許した節だけを評価する。
"""

import ast
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal, DivisionByZero, InvalidOperation
from typing import Any

MAX_ROWS_SHOWN = 50
MAX_EXPR = 300
CALC_COLUMN = "計算"

Value = Decimal | str | None


class TableError(ValueError):
    """条件・式・表の指定の誤り。メッセージはモデルに返す。"""


@dataclass
class Table:
    title: str
    header: list[str]
    rows: list[list[str]]
    # 表に書かれた「合計」「小計」の行。データの行ではないので、条件・集計の対象から外す
    totals: list[list[str]] = field(default_factory=list)
    # 表の下の「注:」「※」などの注記の行（先頭のセルだけに文がある）。データの行から外して注記として残す
    notes: list[str] = field(default_factory=list)
    # 式で使える名前 → 列の位置（元の見出しと、括弧の単位を除いた別名）
    names: dict[str, int] = field(default_factory=dict)

    def aliases(self) -> list[str]:
        """列ごとの、式で使う名前（列の順）。"""
        best: dict[int, str] = {}
        for name, i in self.names.items():
            if i not in best or len(name) < len(best[i]):
                best[i] = name
        return [best[i] for i in sorted(best)]


_SEP = re.compile(r"^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?$")
_PAREN = re.compile(r"[（(][^）)]*[）)]")
_NOT_IDENT = re.compile(r"[^\w]+")


def _cells(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in re.split(r"(?<!\\)\|", s)]


def _ident(header: str) -> str:
    s = unicodedata.normalize("NFKC", header)
    s = _NOT_IDENT.sub("_", _PAREN.sub("", s)).strip("_")
    if not s or s[0].isdigit():
        s = f"列{s}"
    return s


def _name_map(header: list[str]) -> dict[str, int]:
    names: dict[str, int] = {}
    for i, h in enumerate(header):
        alias = _ident(h)
        k, n = alias, 2
        while k in names:
            k, n = f"{alias}_{n}", n + 1
        names[k] = i
    return names


_TOTAL = re.compile(r"^(合計|総計|総合計|小計|計|total|subtotal|grandtotal|sum)$", re.IGNORECASE)


def is_total_row(cells: list[str]) -> bool:
    """先頭の（空でない）セルが「合計」「小計」などの行。足し込むと二重に数えてしまう。"""
    first = next((c for c in cells if c.strip()), "")
    return bool(_TOTAL.match(re.sub(r"\s+", "", unicodedata.normalize("NFKC", first))))


_NOTE = re.compile(r"^(注|※|備考|note)", re.IGNORECASE)


def note_text(cells: list[str]) -> str | None:
    """先頭のセルだけに文があり、注記の言い方で始まる行なら、その文。"""
    if not cells or not cells[0].strip() or any(c.strip() for c in cells[1:]):
        return None
    first = cells[0].strip()
    return first if _NOTE.match(unicodedata.normalize("NFKC", first)) else None


def parse_tables(text: str) -> list[Table]:
    """本文から Markdown の表を取り出す。1 セルだけの題名行は題名にし、次の行を見出しにする。"""
    lines = text.split("\n")
    tables: list[Table] = []
    i = 0
    while i < len(lines) - 1:
        if lines[i].lstrip().startswith("|") and _SEP.match(lines[i + 1].strip()):
            header = _cells(lines[i])
            j = i + 2
            rows: list[list[str]] = []
            while j < len(lines) and lines[j].lstrip().startswith("|"):
                # 表の途中の区切りの行（注記が 1 列の表として続くときなど）はデータの行にしない
                if not _SEP.match(lines[j].strip()):
                    rows.append(_cells(lines[j]))
                j += 1
            title = ""
            if sum(1 for c in header if c) <= 1 and len(rows) >= 2:
                title = next((c for c in header if c), "")
                header, rows = rows[0], rows[1:]
            width = len(header)
            # すべてのセルが空の行は捨てる。注記の行は合計の行と同じくデータの行から外す（specs/026 T30）
            rows = [(r + [""] * width)[:width] for r in rows if any(c.strip() for c in r)]
            notes = [n for r in rows if (n := note_text(r)) is not None]
            rows = [r for r in rows if note_text(r) is None]
            totals = [r for r in rows if is_total_row(r)]
            rows = [r for r in rows if not is_total_row(r)]
            if header and rows:
                tables.append(
                    Table(
                        title=title,
                        header=header,
                        rows=rows,
                        totals=totals,
                        notes=notes,
                        names=_name_map(header),
                    )
                )
            i = j
        else:
            i += 1
    return tables


_NUMBER = re.compile(r"^(-?\d[\d,]*(?:\.\d+)?)\s*(%|[^\d\s.,]{0,4})$")


def to_value(cell: str) -> Value:
    """セルの値。数（単位付きも可）は Decimal、ほかは文字列、空は None。"""
    s = unicodedata.normalize("NFKC", cell).strip()
    if not s or s in {"-", "—", "–"}:
        return None
    m = _NUMBER.match(s)
    if m:
        try:
            return Decimal(m.group(1).replace(",", ""))
        except InvalidOperation:
            return s
    return s


def normalize_expr(expr: str, table: Table) -> str:
    """モデルが書きがちな書き方（全角・＝・≦・AND・かつ・contains・元の見出し）を式の書き方にそろえる。"""
    s = unicodedata.normalize("NFKC", expr).strip()
    for a, b in (("≦", "<="), ("≧", ">="), ("≠", "!="), ("<>", "!="), ("×", "*"), ("÷", "/")):
        s = s.replace(a, b)
    # 元の見出し（括弧付きなど）を式で使える名前に置き換える。長いものから
    originals = sorted(
        ((unicodedata.normalize("NFKC", h), i) for i, h in enumerate(table.header) if h),
        key=lambda x: -len(x[0]),
    )
    alias = {i: n for n, i in table.names.items()}
    for h, i in originals:
        if h != alias[i] and h in s:
            s = s.replace(h, alias[i])
    s = re.sub(r"\s+(AND|かつ|且つ|&&)\s+", " and ", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+(OR|または|又は|\|\|)\s+", " or ", s, flags=re.IGNORECASE)
    s = re.sub(r"\bNOT\b", "not", s)
    s = re.sub(r"(\w+)\s+contains\s+(\"[^\"]*\"|'[^']*')", r"\2 in \1", s, flags=re.IGNORECASE)
    s = re.sub(r"(?<![<>=!])=(?!=)", "==", s)
    return re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "", s)


_CMP: dict[type[ast.cmpop], Callable[[Decimal, Decimal], bool]] = {
    ast.Lt: lambda a, b: a < b,
    ast.LtE: lambda a, b: a <= b,
    ast.Gt: lambda a, b: a > b,
    ast.GtE: lambda a, b: a >= b,
}
_ARITH: dict[type[ast.operator], Callable[[Decimal, Decimal], Decimal]] = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
}


def _eval(node: ast.expr, row: dict[str, Value], names: list[str]) -> Any:
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        return Decimal(str(node.value))
    if isinstance(node, ast.Constant) and isinstance(node.value, str | bool):
        return node.value
    if isinstance(node, ast.Name):
        if node.id not in row:
            raise TableError(f"列「{node.id}」はありません。使える列: {', '.join(names)}")
        return row[node.id]
    if isinstance(node, ast.BoolOp):
        vals = (_eval(v, row, names) for v in node.values)
        return all(vals) if isinstance(node.op, ast.And) else any(vals)
    if isinstance(node, ast.UnaryOp):
        v = _eval(node.operand, row, names)
        if isinstance(node.op, ast.Not):
            return not v
        if isinstance(node.op, ast.USub) and isinstance(v, Decimal):
            return -v
        if isinstance(node.op, ast.UAdd) and isinstance(v, Decimal):
            return v
        return None
    if isinstance(node, ast.BinOp) and type(node.op) in _ARITH:
        a, b = _eval(node.left, row, names), _eval(node.right, row, names)
        if not isinstance(a, Decimal) or not isinstance(b, Decimal):
            return None  # 数でない・空のセルを含む行は計算できない
        try:
            return _ARITH[type(node.op)](a, b)
        except (DivisionByZero, InvalidOperation, ZeroDivisionError):
            return None
    if isinstance(node, ast.Compare):
        left = _eval(node.left, row, names)
        for op, right_node in zip(node.ops, node.comparators, strict=True):
            right = _eval(right_node, row, names)
            if not _compare(op, left, right):
                return False
            left = right
        return True
    raise TableError(
        '読めない式です。比較（< <= > >= == !=）・and・or・not・四則・"語" in 列 が使えます'
        "（集計関数 max・min・sum・avg・count は compute だけで使えます）"
    )


def _compare(op: ast.cmpop, a: Any, b: Any) -> bool:
    if isinstance(op, ast.In | ast.NotIn):
        hit = a is not None and b is not None and str(a) in str(b)
        return hit if isinstance(op, ast.In) else not hit
    if isinstance(op, ast.Eq | ast.NotEq):
        same = a == b if type(a) is type(b) else (a is not None and b is not None and str(a) == str(b))
        return same if isinstance(op, ast.Eq) else not same
    fn = _CMP.get(type(op))
    if fn is None:
        raise TableError("使えない比較です")
    # 大小は数どうしだけ（空・文字の行は当てはまらない扱い）
    return isinstance(a, Decimal) and isinstance(b, Decimal) and bool(fn(a, b))


def _parse(expr: str, table: Table, what: str) -> ast.expr:
    if len(expr) > MAX_EXPR:
        raise TableError(f"{what}が長すぎます（{MAX_EXPR} 文字まで）")
    try:
        return ast.parse(normalize_expr(expr, table), mode="eval").body
    except SyntaxError as e:
        raise TableError(
            f'{what}「{expr}」を読めませんでした。例: 在庫 < 発注点、単価 >= 10000 and "HP-300" in 適用機種。'
            f"使える列: {', '.join(table.aliases())}"
        ) from e


# ── 集計関数（compute で max(列)・min(列)・sum(式)・avg(式)・count()。大文字も可） ──

AGGREGATES = {"max", "min", "sum", "avg", "count"}


def _agg_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords:
        name = node.func.id.lower()
        return name if name in AGGREGATES else None
    return None


def _has_aggregate(node: ast.AST) -> bool:
    return any(_agg_name(n) is not None for n in ast.walk(node))


@dataclass
class Pick:
    """max / min の値と、その値を持つ行（該当行の中の位置）。"""

    expr: str
    value: Decimal
    rows: list[int]


def _eval_aggregate(
    node: ast.expr, rows: list[dict[str, Value]], names: list[str], picks: list[Pick]
) -> Decimal | None:
    """集計関数を含む式を、該当行全体に対して 1 つの値として計算する。"""
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        return Decimal(str(node.value))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub | ast.UAdd):
        v = _eval_aggregate(node.operand, rows, names, picks)
        return v if v is None or isinstance(node.op, ast.UAdd) else -v
    if isinstance(node, ast.BinOp) and type(node.op) in _ARITH:
        a = _eval_aggregate(node.left, rows, names, picks)
        b = _eval_aggregate(node.right, rows, names, picks)
        if a is None or b is None:
            return None
        try:
            return _ARITH[type(node.op)](a, b)
        except (DivisionByZero, InvalidOperation, ZeroDivisionError):
            return None
    fn = _agg_name(node)
    if fn is None or not isinstance(node, ast.Call):
        if isinstance(node, ast.Name):
            raise TableError(
                f"集計の式では、列「{node.id}」は集計関数の中に書いてください"
                "（例 max(単価)・sum(在庫 * 単価)）"
            )
        raise TableError("集計の式で使えるのは max・min・sum・avg・count と四則だけです")
    if fn == "count" and not node.args:
        return Decimal(len(rows))
    if len(node.args) != 1:
        raise TableError(f"{fn} には式を 1 つだけ書いてください（例 {fn}(単価)。count は count()）")
    arg = node.args[0]
    if _has_aggregate(arg):
        raise TableError("集計関数の中に集計関数は書けません")
    vals = [(i, v) for i, row in enumerate(rows) if isinstance(v := _eval(arg, row, names), Decimal)]
    if fn == "count":
        return Decimal(len(vals))
    if not vals:
        return None
    nums = [v for _, v in vals]
    if fn == "sum":
        return sum(nums, Decimal(0))
    if fn == "avg":
        return sum(nums, Decimal(0)) / len(nums)
    best = max(nums) if fn == "max" else min(nums)
    picks.append(Pick(f"{fn}({ast.unparse(arg)})", best, [i for i, v in vals if v == best]))
    return best


@dataclass
class QueryResult:
    table: Table
    matched: list[list[str]]
    computed: list[Decimal | None]  # compute の結果（行ごと。compute が無い・集計関数のときは空）
    totals: dict[str, Decimal]  # 数値列の合計（該当行）
    is_aggregate: bool = False  # compute が集計関数の式か
    aggregate: Decimal | None = None  # 集計関数の式の値
    picks: list[Pick] = field(default_factory=list)


def run_query(table: Table, where: str = "", compute: str = "") -> QueryResult:
    names = table.aliases()
    cond = _parse(where, table, "条件") if where.strip() else None
    calc = _parse(compute, table, "計算式") if compute.strip() else None
    is_agg = calc is not None and _has_aggregate(calc)
    matched: list[list[str]] = []
    matched_rows: list[dict[str, Value]] = []
    computed: list[Decimal | None] = []
    sums: dict[int, Decimal] = {}
    for cells in table.rows:
        row = {name: to_value(cells[i]) for name, i in table.names.items()}
        if cond is not None and not _eval(cond, row, names):
            continue
        matched.append(cells)
        matched_rows.append(row)
        if calc is not None and not is_agg:
            v = _eval(calc, row, names)
            computed.append(v if isinstance(v, Decimal) else None)
        for i, cell in enumerate(cells):
            v = to_value(cell)
            if isinstance(v, Decimal):
                sums[i] = sums.get(i, Decimal(0)) + v
    # どの該当行でも数だった列だけ合計を出す（型番の列などを足さない）
    numeric = [
        i for i in sums if all(isinstance(to_value(r[i]), Decimal) or not r[i].strip() for r in matched)
    ]
    alias = {i: n for n, i in zip(names, sorted(set(table.names.values())), strict=True)}
    picks: list[Pick] = []
    aggregate = _eval_aggregate(calc, matched_rows, names, picks) if calc is not None and is_agg else None
    return QueryResult(
        table,
        matched,
        computed,
        {alias[i]: sums[i] for i in sorted(numeric)},
        is_aggregate=is_agg,
        aggregate=aggregate,
        picks=picks,
    )


def fmt(v: Decimal) -> str:
    out = format(v.normalize(), "f")
    return "0" if out == "-0" else out


def render(result: QueryResult, where: str, compute: str) -> str:
    t = result.table
    total, n = len(t.rows), len(result.matched)
    head = f"表「{t.title}」" if t.title else "表"
    cond = f"条件 `{where.strip()}` に合う行: " if where.strip() else "全行: "
    lines = [f"{head}（{total} 行）。{cond}{n} 行。行の選択と計算はシステムが行った（正確）。"]
    if t.totals:
        # 表の合計の行は全行の合計。データの行としては数えず、参考として末尾に示す
        lines[0] += f" 表に書かれた合計の行 {len(t.totals)} つは、行の選択と集計から外した。"
    per_row = bool(compute.strip()) and not result.is_aggregate
    if n:
        header = t.header + ([CALC_COLUMN] if per_row else [])
        lines.append("| " + " | ".join(header) + " |")
        lines.append("|" + "---|" * len(header))
        for k, cells in enumerate(result.matched[:MAX_ROWS_SHOWN]):
            row = list(cells)
            if per_row:
                v = result.computed[k]
                row.append(fmt(v) if v is not None else "（計算不可）")
            lines.append("| " + " | ".join(row) + " |")
        if n > MAX_ROWS_SHOWN:
            lines.append(f"（ほか {n - MAX_ROWS_SHOWN} 行は省略。合計は全 {n} 行のもの）")
        sums = [f"{name} の合計 {fmt(v)}" for name, v in result.totals.items()]
        vals = [v for v in result.computed if v is not None]
        if vals:
            s = sum(vals, Decimal(0))
            sums.append(
                f"{CALC_COLUMN}（{compute.strip()}）の合計 {fmt(s)}・平均 {fmt(s / len(vals))}"
                f"・最大 {fmt(max(vals))}・最小 {fmt(min(vals))}"
            )
        if sums:
            lines.append(f"集計（該当 {n} 行）: " + " / ".join(sums))
    if result.is_aggregate:
        value = fmt(result.aggregate) if result.aggregate is not None else "（該当する数値なし）"
        lines.append(f"{CALC_COLUMN}（{compute.strip()}）の結果: {value}")
        for p in result.picks:
            lines.append(f"{p.expr} = {fmt(p.value)} の行（{len(p.rows)} 行）:")
            lines.append("| " + " | ".join(t.header) + " |")
            lines.append("|" + "---|" * len(t.header))
            lines += ["| " + " | ".join(result.matched[i]) + " |" for i in p.rows[:MAX_ROWS_SHOWN]]
    lines += [f"注記: {n}" for n in t.notes]
    return "\n".join(lines)


def _stats(vals: list[Decimal]) -> dict[str, str]:
    s = sum(vals, Decimal(0))
    return {"sum": fmt(s), "avg": fmt(s / len(vals)), "max": fmt(max(vals)), "min": fmt(min(vals))}


def summarize(result: QueryResult, compute: str) -> dict[str, Any]:
    """記録（ステップの output）に出す構造（specs/028 R10）。モデルに渡す文（render）とは別に作る。

    該当行（最大 MAX_ROWS_SHOWN 行）・行数・compute の列の名前と集計・数値の列ごとの合計・平均・最大・最小。
    """
    t = result.table
    per_row = bool(compute.strip()) and not result.is_aggregate
    label = f"{CALC_COLUMN}（{compute.strip()}）" if compute.strip() else None
    rows: list[list[str]] = []
    for k, cells in enumerate(result.matched[:MAX_ROWS_SHOWN]):
        row = list(cells)
        if per_row:
            v = result.computed[k]
            row.append(fmt(v) if v is not None else "")
        rows.append(row)
    aggregates: dict[str, dict[str, str]] = {}
    vals = [v for v in result.computed if v is not None]
    if per_row and vals and label:
        aggregates[label] = _stats(vals)
    for name in result.totals:  # 合計を出した列（どの該当行でも数だった列）。名前は式で使う名前
        i = t.names[name]
        col = [x for x in (to_value(cells[i]) for cells in result.matched) if isinstance(x, Decimal)]
        if col:
            aggregates[name] = _stats(col)
    out: dict[str, Any] = {
        "rows_total": len(t.rows),
        "rows_matched": len(result.matched),
        "columns": t.header + ([CALC_COLUMN] if per_row else []),
        "rows": rows,
        "compute_label": label,
        "aggregates": aggregates,
    }
    if t.notes:
        out["notes"] = list(t.notes)
    if result.is_aggregate:
        out["compute_value"] = fmt(result.aggregate) if result.aggregate is not None else None
    return out


EXAMPLES = (
    '書き方の例: where="在庫 < 発注点"・where="単価 >= 10000 and "HP-300" in 適用機種"・'
    'compute="(発注点 - 在庫) * 単価"（行ごと）・compute="max(単価)"・compute="sum(在庫 * 単価)"・'
    'compute="count()"（集計）'
)


def error_hint(table: Table) -> str:
    """誤りに必ず添える案内（使える列名と書き方の例。specs/026 R13）。"""
    return f"使える列: {', '.join(table.aliases())}\n{EXAMPLES}"


def describe_tables(tables: list[Table]) -> str:
    return "\n".join(
        f"- table={i}: {t.title or '（題名なし）'}（{len(t.rows)} 行）列: {', '.join(t.aliases())}"
        for i, t in enumerate(tables, 1)
    )
