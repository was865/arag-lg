"""模擬の社内システムの問い合わせ（MCP の層から切り離した純粋な部分。specs/032 design §2）。

どの関数も (読み取り専用の接続, 利用者の身元, 引数) → 結果の dict。権限で列・行を絞るのはここ（R4・R13）。
"""

import sqlite3
from typing import Any

from mock_systems.common import Identity, current_basis, forbidden, like, table, today
from mock_systems.seed import WORK_ORDER_DEPTS

ERP = "ERP"
CMMS = "保全システム"
DIRECTORY = "社員名簿"
TICKETS = "課題の管理"

# 仕入単価を見られる部門（R4）
COST_DEPTS = frozenset({"資材係", "購買課"})


def _day(s: str | None, default: str) -> str:
    return (s or "").strip() or default


# ── ERP ──


def _match_parts(con: sqlite3.Connection, term: str) -> list[sqlite3.Row]:
    q = like(term)
    return list(
        con.execute(
            "SELECT * FROM parts WHERE part_no LIKE ? OR name LIKE ? OR models LIKE ? ORDER BY part_no",
            (q, q, q),
        )
    )


def find_parts(con: sqlite3.Connection, ident: Identity, term: str) -> dict[str, Any]:
    rows = _match_parts(con, term) if term.strip() else list(con.execute("SELECT * FROM parts ORDER BY part_no"))
    return table(
        ERP,
        "部品",
        ["部品番号", "名称", "適用機種", "標準単価（円）", "発注点", "仕入先コード", "状態"],
        [
            [r["part_no"], r["name"], r["models"], r["std_price"], r["reorder_point"], r["supplier_code"], r["status"]]
            for r in rows
        ],
        basis=current_basis(ERP),
        note=None if rows else f"「{term}」に当たる部品はありません",
    )


def get_stock(con: sqlite3.Connection, ident: Identity, part: str) -> dict[str, Any]:
    d = today().isoformat()
    rows = []
    for p in _match_parts(con, part):
        qty = con.execute(
            "SELECT COALESCE(SUM(qty), 0) FROM stock_moves WHERE part_no = ? AND date <= ?", (p["part_no"], d)
        ).fetchone()[0]
        on_order = con.execute(
            "SELECT COALESCE(SUM(qty), 0) FROM purchase_orders WHERE part_no = ? AND status = '発注済み'",
            (p["part_no"],),
        ).fetchone()[0]
        last = con.execute(
            "SELECT date, kind, qty FROM stock_moves WHERE part_no = ? AND date <= ? ORDER BY date DESC LIMIT 1",
            (p["part_no"], d),
        ).fetchone()
        rop = p["reorder_point"]
        if p["status"] == "廃止":
            judge = "廃止（発注しない）"
        else:
            judge = "発注点を下回っている" if qty < rop else "発注点を満たしている"
        rows.append(
            [
                p["part_no"],
                p["name"],
                qty,
                rop,
                judge,
                on_order,
                f"{last['date']} {last['kind']} {last['qty']:+d}" if last else "",
            ]
        )
    return table(
        ERP,
        "在庫",
        ["部品番号", "名称", "現在庫", "発注点", "発注点との比較", "未入荷の発注数", "最後の入出庫"],
        rows,
        basis=current_basis(ERP),
        note=None if rows else f"「{part}」に当たる部品はありません",
    )


def list_stock_moves(
    con: sqlite3.Connection, ident: Identity, part: str, since: str | None = None, until: str | None = None
) -> dict[str, Any]:
    parts = [p["part_no"] for p in _match_parts(con, part)]
    if not parts:
        return table(ERP, "入出庫", [], [], basis=current_basis(ERP), note=f"「{part}」に当たる部品はありません")
    marks = ",".join("?" for _ in parts)
    rows = con.execute(
        "SELECT m.date, m.part_no, p.name, m.kind, m.qty, m.ref, m.note"
        f" FROM stock_moves m JOIN parts p USING (part_no) WHERE m.part_no IN ({marks})"
        " AND m.date BETWEEN ? AND ? ORDER BY m.date, m.part_no",
        (*parts, _day(since, "0000-01-01"), _day(until, today().isoformat())),
    )
    return table(
        ERP,
        "入出庫",
        ["日付", "部品番号", "名称", "種類", "数量", "参照", "備考"],
        [list(r) for r in rows],
        basis=current_basis(ERP),
    )


def list_purchase_orders(
    con: sqlite3.Connection,
    ident: Identity,
    part: str | None = None,
    status: str | None = None,
    since: str | None = None,
    until: str | None = None,
) -> dict[str, Any]:
    sql = (
        "SELECT o.*, p.name, s.name AS supplier FROM purchase_orders o JOIN parts p USING (part_no)"
        " JOIN suppliers s ON s.code = p.supplier_code WHERE o.ordered_on BETWEEN ? AND ?"
    )
    args: list[Any] = [_day(since, "0000-01-01"), _day(until, today().isoformat())]
    if part and part.strip():
        parts = [p["part_no"] for p in _match_parts(con, part)] or ["-"]
        sql += f" AND o.part_no IN ({','.join('?' for _ in parts)})"
        args += parts
    if status and status.strip():
        # 「未入荷」「未完了」も発注済みとして扱う
        st = "発注済み" if status.strip() in {"未入荷", "未完了", "発注中"} else status.strip()
        sql += " AND o.status = ?"
        args.append(st)
    rows = list(con.execute(sql + " ORDER BY o.ordered_on", args))
    see_cost = ident.in_any(COST_DEPTS)
    cols = ["発注番号", "部品番号", "名称", "仕入先", "数量", "発注日", "納期", "入荷日", "状態"]
    if see_cost:
        cols.insert(5, "仕入単価（円）")
    out = []
    for r in rows:
        row = [
            r["po_no"],
            r["part_no"],
            r["name"],
            r["supplier"],
            r["qty"],
            r["ordered_on"],
            r["due_on"],
            r["received_on"] or "",
            r["status"],
        ]
        if see_cost:
            row.insert(5, r["unit_cost"])
        if r["status"] == "発注済み" and r["due_on"] < today().isoformat():
            row[-1] = "発注済み（納期を過ぎて未入荷）"
        out.append(row)
    return table(
        ERP,
        "発注",
        cols,
        out,
        basis=current_basis(ERP),
        restricted=None if see_cost else ["仕入単価（円）"],
        note=None if see_cost else "仕入単価は資材係・購買課の人だけが見られます。この利用者には見る権限がありません。",
    )


# ── 保全システム ──


def list_equipment(con: sqlite3.Connection, ident: Identity) -> dict[str, Any]:
    rows = con.execute("SELECT id, name, location, installed FROM equipment ORDER BY id")
    return table(
        CMMS, "設備", ["設備ID", "設備名", "設置場所", "導入年"], [list(r) for r in rows], basis=current_basis(CMMS)
    )


def list_work_records(
    con: sqlite3.Connection,
    ident: Identity,
    equipment: str | None = None,
    since: str | None = None,
    until: str | None = None,
) -> dict[str, Any]:
    sql = (
        "SELECT w.date, w.equipment_id, e.name, w.work, w.staff, w.downtime_min, w.procedure"
        " FROM work_records w JOIN equipment e ON e.id = w.equipment_id WHERE w.date BETWEEN ? AND ?"
    )
    args: list[Any] = [_day(since, "0000-01-01"), _day(until, today().isoformat())]
    if equipment and equipment.strip():
        sql += " AND (w.equipment_id LIKE ? OR e.name LIKE ?)"
        args += [like(equipment), like(equipment)]
    rows = con.execute(sql + " ORDER BY w.date", args)
    return table(
        CMMS,
        "作業の記録",
        ["日付", "設備ID", "設備名", "作業内容", "担当", "停止時間（分）", "使った手順書"],
        [list(r) for r in rows],
        basis=current_basis(CMMS),
    )


def list_work_orders(
    con: sqlite3.Connection, ident: Identity, equipment: str | None = None, status: str | None = None
) -> dict[str, Any]:
    if not ident.in_any(WORK_ORDER_DEPTS):
        return forbidden(CMMS, "作業指示は保全課・製造課の人だけが見られます。この利用者には見る権限がありません。")
    sql = "SELECT * FROM work_orders WHERE 1=1"
    args: list[Any] = []
    if equipment and equipment.strip():
        sql += " AND equipment_id LIKE ?"
        args.append(like(equipment))
    if status and status.strip():
        if status.strip() in {"未完了", "未完", "open"}:
            sql += " AND status <> '完了'"
        else:
            sql += " AND status = ?"
            args.append(status.strip())
    rows = con.execute(sql + " ORDER BY opened_on", args)
    return table(
        CMMS,
        "作業指示",
        ["作業指示番号", "設備ID", "内容", "状態", "担当", "起票日", "期限", "完了日"],
        [
            [
                r["wo_no"],
                r["equipment_id"],
                r["title"],
                r["status"],
                r["assignee"],
                r["opened_on"],
                r["due_on"],
                r["closed_on"] or "",
            ]
            for r in rows
        ],
        basis=current_basis(CMMS),
    )


# ── 社員名簿 ──


def find_people(con: sqlite3.Connection, ident: Identity, term: str) -> dict[str, Any]:
    flat = term.replace(" ", "").replace("　", "")
    q = like(term)
    # 「保全課長」→ 部署「保全課」・役職「課長」（部署名の末尾の字と役職の頭の字が重なる）
    dept, title = "-", "-"
    for t in ("課長", "部長", "係長"):
        if flat.endswith(t) and len(flat) > len(t):
            dept, title = flat[: -len(t)] + t[0], t
    # 私用の連絡先（private_phone）は誰にも出さない（R4）
    rows = con.execute(
        "SELECT emp_no, name, dept, title, extension FROM employees"
        " WHERE name LIKE ? OR replace(name, ' ', '') LIKE ? OR dept LIKE ? OR title LIKE ? OR (dept = ? AND title = ?)"
        " ORDER BY dept, emp_no",
        (q, like(flat), q, q, dept, title),
    )
    out = [list(r) for r in rows]
    return table(
        DIRECTORY,
        "社員",
        ["社員番号", "氏名", "部署", "役職", "内線"],
        out,
        basis=current_basis(DIRECTORY),
        note=None if out else f"「{term}」に当たる人はいません",
    )


# ── 課題の管理 ──


def search_issues(
    con: sqlite3.Connection, ident: Identity, term: str = "", status: str | None = None
) -> dict[str, Any]:
    sql = "SELECT * FROM issues WHERE (title LIKE ? OR source LIKE ? OR no LIKE ?)"
    q = like(term)
    args: list[Any] = [q, q, q]
    if status and status.strip():
        if status.strip() in {"未完了", "未完", "open"}:
            sql += " AND status <> '完了'"
        else:
            sql += " AND status = ?"
            args.append(status.strip())
    rows = con.execute(sql + " ORDER BY no", args).fetchall()

    def latest(no: str) -> str:
        """最新の経過（一覧の画面と同じく、最後のコメントを 1 件だけ出す）。"""
        c = con.execute(
            "SELECT at, author, body FROM comments WHERE issue_no = ? ORDER BY at DESC LIMIT 1", (no,)
        ).fetchone()
        return f"{c['at']} {c['author']}: {c['body']}" if c else ""

    return table(
        TICKETS,
        "課題",
        ["課題番号", "件名", "出どころ", "担当", "期限", "状態", "起票日", "完了日", "最新の経過"],
        [
            [
                r["no"],
                r["title"],
                r["source"],
                r["assignee"],
                r["due"],
                r["status"],
                r["opened_on"],
                r["closed_on"] or "",
                latest(r["no"]),
            ]
            for r in rows
        ],
        basis=current_basis(TICKETS),
    )


def get_issue(con: sqlite3.Connection, ident: Identity, issue: str) -> dict[str, Any]:
    r = con.execute("SELECT * FROM issues WHERE no = ?", (issue.strip().upper(),)).fetchone()
    if r is None:
        return table(TICKETS, "課題の経過", [], [], basis=current_basis(TICKETS), note=f"課題 {issue} はありません")
    comments = con.execute("SELECT at, author, body FROM comments WHERE issue_no = ? ORDER BY at", (r["no"],))
    out = table(
        TICKETS,
        f"課題 {r['no']} の経過",
        ["日時", "書いた人", "本文"],
        [list(c) for c in comments],
        basis=current_basis(TICKETS),
    )
    out["issue"] = {
        "課題番号": r["no"],
        "件名": r["title"],
        "出どころ": r["source"],
        "担当": r["assignee"],
        "期限": r["due"],
        "状態": r["status"],
        "起票日": r["opened_on"],
        "完了日": r["closed_on"] or "",
    }
    return out
