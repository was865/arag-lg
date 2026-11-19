"""題の正しい答えをスナップショット（world.db）から計算する（specs/034 R12）。

題ごとに問い合わせ（facts.py）を流し、key_facts と根拠（どの表のどの行か）を出す。
`main` は題集の下書き（YAML）を書き、根拠を # の注として添える。確かめてから golden.yaml に写す。
手で書いた数字は使わない（固定の値は文書の記述＝食い違いの側だけ）。
"""

import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from harukaze_sim import facts

TODAY = date(2026, 11, 18)
DOCS = [
    "g01-部品台帳_第二工場_2026-10末.xlsx",
    "g02-月次報告_2026-10.pptx",
    "g03-在庫の報告_2026-11.xlsx",
    "g04-品質会議議事録_2026-10.docx",
    "g05-品質会議議事録_2026-11.docx",
    "g06-仕入先の評価_2026上期.pdf",
    "h01-資材管理の手引き_第二工場.docx",
    "h02-倉庫の使い分けの決まり.docx",
]

Facts = list[list[str]]


@dataclass
class Answer:
    key_facts: Facts
    evidence: list[str]
    wrong_facts: Facts = field(default_factory=list)
    expect_caveat: Facts = field(default_factory=list)


@dataclass
class Case:
    id: str
    query: str
    tags: list[str]
    as_user: str
    compute: Callable[[sqlite3.Connection], Answer]
    expect_tools: list[str] = field(default_factory=list)
    relevant_documents: list[str] = field(default_factory=list)


def day_forms(d: str | date) -> list[str]:
    x = date.fromisoformat(d) if isinstance(d, str) else d
    return [f"{x.month}月{x.day}日", f"{x.month}/{x.day}", x.isoformat()]


def n(x: float) -> str:
    return str(int(x)) if float(x).is_integer() else str(round(x, 2))


def yen(x: int) -> list[str]:
    return [f"{x:,}", str(x)]


def _row(con: sqlite3.Connection, sql: str, *args: object) -> sqlite3.Row:
    r: sqlite3.Row | None = con.execute(sql, args).fetchone()
    assert r is not None, sql
    return r


def _part(con: sqlite3.Connection, no: str) -> sqlite3.Row:
    return _row(con, "SELECT * FROM parts WHERE part_no = ?", no)


def _usable(con: sqlite3.Connection, day: date = TODAY) -> dict[str, float]:
    return facts.stock_at(con, day, facts.usable_warehouses(con))


NOW = [["時点", "現在", "今", "11月18日", "11/18", "2026-11-18"]]

CASES: list[Case] = []


def case(
    id: str, query: str, tags: list[str], as_user: str, *, tools: list[str] | None = None, docs: list[str] | None = None
) -> Callable[[Callable[[sqlite3.Connection], Answer]], Callable[[sqlite3.Connection], Answer]]:
    def wrap(fn: Callable[[sqlite3.Connection], Answer]) -> Callable[[sqlite3.Connection], Answer]:
        CASES.append(Case(id, query, tags, as_user, fn, tools or [], docs or []))
        return fn

    return wrap


# ── 文書だけ ──


@case("hp01-docs-production", "10月の HP-300 の生産台数は何台でしたか？", ["ja", "docs"], "seizo", docs=[DOCS[1]])
def _hp01(con: sqlite3.Connection) -> Answer:
    made = facts.production(con, 2026, 10)
    return Answer([[str(made["FG-300"])]], [f"stock_moves 製造入庫 FG-300 2026-10: {made['FG-300']}"])


@case(
    "hp02-docs-supplier-grade",
    "上期の仕入先の評価で、Aster Seals の納期遵守率と評価はどうでしたか？",
    ["ja", "docs"],
    "kobai",
    docs=[DOCS[5]],
)
def _hp02(con: sqlite3.Connection) -> Answer:
    s = next(x for x in facts.supplier_scores(con, date(2026, 4, 1), date(2026, 10, 1)) if x.code == "S-07")
    pct = f"{s.rate * 100:.1f}"
    return Answer([[pct], [s.grade]], [f"S-07: {s.on_time}/{s.orders} = {pct}% → {s.grade}"])


@case(
    "hp03-docs-warehouses",
    "発注点と比べる在庫には、どの倉庫の在庫を含めますか？",
    ["ja", "docs"],
    "seizo",
    docs=[DOCS[7]],
)
def _hp03(con: sqlite3.Connection) -> Answer:
    return Answer(
        [["WH2", "第二工場 資材倉庫"], ["WH1", "第一工場 資材倉庫"], ["DEAD", "呆滞品"]],
        ["h02 の 2.: WH2 と WH1 の合計。DEAD と SMPL は含めない（含めないことに触れる）"],
    )


@case(
    "hp04-docs-minutes-late",
    "11月の品質会議で、納期遅れとして挙がったシール部品の発注は？",
    ["ja", "docs"],
    "hinsho",
    docs=[DOCS[4]],
)
def _hp04(con: sqlite3.Connection) -> Answer:
    parts = facts.parts_at(con, date(2026, 11, 13))
    seals = [p for p in facts.overdue_pos(con, date(2026, 11, 12)) if parts[p.part_no].category == "シール"]
    return Answer(
        [[s.po_no] for s in seals], [f"{s.po_no} {s.part_no} {s.supplier_code} 納期 {s.due_on}" for s in seals]
    )


@case(
    "hp05-docs-top-issued",
    "10月にラインへの払出しがいちばん多かった部品は何ですか？",
    ["ja", "docs"],
    "seizo",
    docs=[DOCS[1]],
)
def _hp05(con: sqlite3.Connection) -> Answer:
    no, name, q = facts.issued_top(con, 2026, 10, 1)[0]
    return Answer([[no, name]], [f"出庫 IS- 2026-10: {no} {name} {n(q)}"])


# ── システムだけ ──


@case(
    "hp06-below-count",
    "今、在庫が発注点を下回っている部品は何件ありますか？",
    ["ja", "system", "time", "many"],
    "seizo",
    tools=["erp"],
)
def _hp06(con: sqlite3.Connection) -> Answer:
    b = facts.below_reorder(con, TODAY)
    return Answer(
        [[str(len(b))], [b[0].part_no, b[0].name]],
        [f"使える倉庫の在庫 < 発注点（廃止を除く）: {len(b)} 件。先頭 {b[0].part_no}"],
        expect_caveat=NOW,
    )


@case(
    "hp07-overdue-all",
    "納期を過ぎても入荷し終えていない発注を全部挙げてください。",
    ["ja", "system", "many"],
    "kobai",
    tools=["erp"],
)
def _hp07(con: sqlite3.Connection) -> Answer:
    o = facts.overdue_pos(con, TODAY)
    oldest = min(o, key=lambda x: x.due_on)
    return Answer(
        [[str(len(o))], [o[0].po_no], [oldest.po_no]],
        [f"{x.po_no} {x.part_no} 納期 {x.due_on} 入荷 {n(x.received)}/{x.qty}" for x in o],
    )


@case("hp08-partial", "PO-2026-2241 は今どうなっていますか？", ["ja", "system", "partial"], "kobai", tools=["erp"])
def _hp08(con: sqlite3.Connection) -> Answer:
    r = _row(con, "SELECT * FROM purchase_orders WHERE po_no = 'PO-2026-2241'")
    left = r["qty"] - r["received_qty"]
    return Answer(
        [["一部入荷", "一部"], [n(r["received_qty"])], [n(r["qty"])], [n(left)]],
        [f"{r['po_no']} {r['part_no']} {n(r['received_qty'])}/{r['qty']} 納期 {r['due_on']} 状態 {r['status']}"],
    )


@case(
    "hp09-unit",
    "Oリング P20 の今の在庫と、発注するときの単位を教えてください。",
    ["ja", "system", "unit"],
    "seizo",
    tools=["erp"],
)
def _hp09(con: sqlite3.Connection) -> Answer:
    p = _part(con, "P-5052")
    q = _usable(con)["P-5052"]
    return Answer(
        [[n(q)], [p["purchase_uom"], "袋"]], [f"P-5052 使える在庫 {n(q)} {p['uom']}・発注の単位 {p['purchase_uom']}"]
    )


@case(
    "hp10-similar-retired", "軸受 6308ZZ-C3 の在庫はありますか？", ["ja", "system", "similar"], "hozen", tools=["erp"]
)
def _hp10(con: sqlite3.Connection) -> Answer:
    p = _part(con, "P-5028")
    succ = _part(con, p["successor"])
    q = _usable(con).get(succ["part_no"], 0.0)
    q2010 = _usable(con)["P-2010"]
    return Answer(
        [["廃止"], [succ["part_no"], succ["name"].split()[-1]], [n(q)]],
        [
            f"P-5028 廃止 {p['retired_on']}、後継 {succ['part_no']} {succ['name']} 在庫 {n(q)}（6308ZZ P-2010 は {n(q2010)}）"
        ],
        wrong_facts=[[f"6308ZZ-C3 の在庫は {n(q2010)}"]],
    )


@case(
    "hp11-similar-ntn",
    "軸受 6309ZZ（NTN 指定）の今の在庫はいくつですか？",
    ["ja", "system", "similar"],
    "hozen",
    tools=["erp"],
)
def _hp11(con: sqlite3.Connection) -> Answer:
    q = _usable(con)["P-5033"]
    q2011 = _usable(con)["P-2011"]
    return Answer(
        [[n(q)], ["P-5033"]],
        [f"P-5033 使える在庫 {n(q)}（6309ZZ P-2011 は {n(q2011)}）"],
        wrong_facts=[[f"在庫は {n(q2011)} 個"]],
    )


@case("hp12-dead-stock", "軸受 6204ZZ-C3 は今いくつ使えますか？", ["ja", "system", "warehouse"], "seizo", tools=["erp"])
def _hp12(con: sqlite3.Connection) -> Answer:
    use = _usable(con)["P-5002"]
    dead = facts.stock_at(con, TODAY, ["DEAD"]).get("P-5002", 0.0)
    return Answer(
        [[n(use)]],
        [f"P-5002 WH2+WH1 {n(use)}、DEAD {n(dead)}（数えない）"],
        wrong_facts=[[f"{n(use + dead)} 個使え", f"{n(use + dead)}個使え"]],
    )


@case(
    "hp13-po-cost-change",
    "軸受 6204ZZ-C3 の発注の仕入単価は、上期と比べて変わりましたか？",
    ["ja", "system", "price"],
    "kobai",
    tools=["erp"],
)
def _hp13(con: sqlite3.Connection) -> Answer:
    rows = con.execute(
        "SELECT po_no, ordered_on, unit_cost FROM purchase_orders WHERE part_no = 'P-5002' AND status != '取消' ORDER BY ordered_on"
    ).fetchall()
    first = [r for r in rows if r["ordered_on"] < "2026-10-01"][-1]
    last = rows[-1]
    return Answer(
        [yen(first["unit_cost"]), yen(last["unit_cost"])],
        [f"{r['po_no']} {r['ordered_on']} {r['unit_cost']}" for r in rows],
    )


@case(
    "hp14-perm-cost-hidden",
    "軸受 6204ZZ-C3 の発注の仕入単価を教えてください。",
    ["ja", "system", "perm"],
    "seizo",
    tools=["erp"],
)
def _hp14(con: sqlite3.Connection) -> Answer:
    last = _row(con, "SELECT unit_cost FROM purchase_orders WHERE part_no = 'P-5002' ORDER BY ordered_on DESC")
    return Answer(
        [["権限", "見られません", "見る権限", "表示されません", "確認できません"]],
        ["製造課（erp-genba）は仕入単価が隠れる（restricted）"],
        wrong_facts=[yen(last["unit_cost"])],
    )


@case("hp15-perm-forbidden", "納期を過ぎた発注はありますか？", ["ja", "system", "perm"], "none", tools=["erp"])
def _hp15(con: sqlite3.Connection) -> Answer:
    o = facts.overdue_pos(con, TODAY)
    return Answer(
        [["権限", "見られません", "見る権限", "確認できません"]],
        ["部門の無い人（erp-viewer）は購買を見られない（forbidden）"],
        wrong_facts=[[o[0].po_no]],
    )


@case("hp16-po-month-total", "10月に出した発注は全部で何件ですか？", ["ja", "system", "many"], "kobai", tools=["erp"])
def _hp16(con: sqlite3.Connection) -> Answer:
    cnt, _amt = facts.ordered(con, 2026, 10)
    cancelled = _row(
        con,
        "SELECT COUNT(*) AS c FROM purchase_orders WHERE ordered_on >= '2026-10-01' AND ordered_on < '2026-11-01' AND status = '取消'",
    )["c"]
    alt = [str(cnt)] + ([str(cnt + cancelled)] if cancelled else [])
    return Answer([alt], [f"ordered_on 2026-10: 取消を除き {cnt} 件（取消 {cancelled} 件）"])


@case(
    "hp17-so-overdue",
    "納期を過ぎても出荷し終えていない受注はいくつありますか？",
    ["ja", "system"],
    "seizo",
    tools=["erp"],
)
def _hp17(con: sqlite3.Connection) -> Answer:
    rows = con.execute(
        "SELECT so_no, customer_code, due_on FROM sales_orders WHERE status IN ('受注済み', '一部出荷') AND due_on < ? ORDER BY due_on",
        (TODAY.isoformat(),),
    ).fetchall()
    return Answer(
        [[str(len(rows))], [rows[0]["so_no"]]], [f"{r['so_no']} {r['customer_code']} {r['due_on']}" for r in rows]
    )


@case(
    "hp18-customer-open",
    "静岡環境開発からの受注で、まだ出荷していないものを教えてください。",
    ["ja", "system"],
    "seizo",
    tools=["erp"],
)
def _hp18(con: sqlite3.Connection) -> Answer:
    code = _row(con, "SELECT code FROM customers WHERE name LIKE '静岡環境開発%'")["code"]
    rows = con.execute(
        "SELECT so_no, part_no, qty, shipped_qty, due_on FROM sales_orders WHERE customer_code = ? AND status IN ('受注済み', '一部出荷') ORDER BY so_no",
        (code,),
    ).fetchall()
    return Answer(
        [[str(len(rows)) + " 件", str(len(rows)) + "件"], [rows[0]["so_no"]], [rows[-1]["so_no"]]],
        [
            f"{code}: "
            + ", ".join(f"{r['so_no']} {r['part_no']} {n(r['shipped_qty'])}/{n(r['qty'])} {r['due_on']}" for r in rows)
        ],
    )


@case("hp19-moves", "Oリング P20 の 9 月以降の入出庫を教えてください。", ["ja", "system"], "seizo", tools=["erp"])
def _hp19(con: sqlite3.Connection) -> Answer:
    rows = con.execute(
        "SELECT date, kind, qty, ref FROM stock_moves WHERE part_no = 'P-5052' AND date >= '2026-09-01' ORDER BY date"
    ).fetchall()
    return Answer(
        [day_forms(r["date"]) for r in rows], [f"{r['date']} {r['kind']} {n(r['qty'])} {r['ref']}" for r in rows]
    )


@case(
    "hp20-bolt-box",
    "六角ボルト M12×40 SUS304 の発注で、まだ入荷していない数はいくつですか？",
    ["ja", "system", "unit", "partial"],
    "kobai",
    tools=["erp"],
)
def _hp20(con: sqlite3.Connection) -> Answer:
    p = _part(con, "P-5122")
    rows = con.execute(
        "SELECT po_no, qty, received_qty, uom FROM purchase_orders WHERE part_no = 'P-5122' AND status IN ('発注済み', '一部入荷')"
    ).fetchall()
    left = sum(r["qty"] - r["received_qty"] for r in rows)
    pieces = left * p["purchase_ratio"]
    return Answer(
        [[n(pieces) + " 個", n(pieces) + "個", f"{n(left)} 箱"]],
        [f"{r['po_no']} {n(r['received_qty'])}/{r['qty']} {r['uom']}" for r in rows]
        + [f"残り {n(left)} 箱 = {n(pieces)} 個"],
    )


# ── 時点の違い・文書とシステムをまたぐ ──


@case(
    "hp21-ledger-vs-now",
    "10月末の部品台帳と今とで、軸受 6208ZZ の在庫はいくつ違いますか？",
    ["ja", "cross", "time"],
    "seizo",
    tools=["erp"],
    docs=[DOCS[0]],
)
def _hp21(con: sqlite3.Connection) -> Answer:
    then = facts.stock_at(con, date(2026, 10, 31), ["WH2"])["P-5010"]
    now = _usable(con)["P-5010"]
    return Answer(
        [[n(then)], [n(now)], [f"{n(abs(then - now))} 個", f"{n(abs(then - now))}個"]],
        [f"P-5010 10/31 WH2 {n(then)} → 今 {n(now)}"],
        expect_caveat=[["10月31日", "10/31", "10月末", "2026-10-31"]],
    )


@case(
    "hp22-report-vs-now",
    "11月16日の在庫の報告に載っていた軸受 6204ZZ-C3 は、今も発注点を下回っていますか？",
    ["ja", "cross", "time"],
    "seizo",
    tools=["erp"],
    docs=[DOCS[2]],
)
def _hp22(con: sqlite3.Connection) -> Answer:
    then = _usable(con, date(2026, 11, 15))["P-5002"]
    now = _usable(con)["P-5002"]
    rp = _part(con, "P-5002")["reorder_point"]
    assert then < rp <= now
    return Answer(
        [[n(now)], [str(rp)], ["満たして", "上回って", "下回っていません", "解消"]],
        [f"P-5002 11/15 終わり {n(then)} < {rp} → 今 {n(now)}"],
    )


@case(
    "hp23-minutes-follow",
    "11月の品質会議で納期遅れとして挙がった Aster Seals の発注は、今どうなっていますか？",
    ["ja", "cross", "time"],
    "kobai",
    tools=["erp"],
    docs=[DOCS[4]],
)
def _hp23(con: sqlite3.Connection) -> Answer:
    o = next(x for x in facts.overdue_pos(con, TODAY) if x.supplier_code == "S-07")
    return Answer(
        [[o.po_no], ["未入荷", "入荷していない", "まだ", "入っていない"]],
        [f"{o.po_no} {o.part_no} 入荷 {n(o.received)}/{o.qty} 納期 {o.due_on}"],
    )


@case(
    "hp24-conflict-extension",
    "資材管理の手引きにある発注の問い合わせ先の内線番号は、今も正しいですか？",
    ["ja", "cross", "conflict"],
    "seizo",
    tools=["directory"],
    docs=[DOCS[6]],
)
def _hp24(con: sqlite3.Connection) -> Answer:
    ext = _row(con, "SELECT extension FROM employees WHERE name = '佐伯 美穂'")["extension"]
    return Answer([["佐伯"], [ext], ["2201"]], [f"名簿 佐伯 美穂 {ext}、手引き 2201（conflicts c1）"])


@case(
    "hp25-conflict-reorder",
    "軸受 6309ZZ の発注点はいくつですか？今の在庫はそれを下回っていますか？",
    ["ja", "cross", "conflict"],
    "seizo",
    tools=["erp"],
    docs=[DOCS[6]],
)
def _hp25(con: sqlite3.Connection) -> Answer:
    rp = _part(con, "P-2011")["reorder_point"]
    q = _usable(con)["P-2011"]
    return Answer(
        [[str(rp)], [n(q)], ["下回って"]],
        [f"ERP P-2011 発注点 {rp}、在庫 {n(q)}（手引きは 10、conflicts c2）"],
        wrong_facts=[["発注点は 10 "]],
    )


@case(
    "hp26-conflict-leadtime",
    "Aster Seals に発注すると、届くまで何日かかりますか？",
    ["ja", "cross", "conflict"],
    "kobai",
    tools=["erp"],
    docs=[DOCS[6]],
)
def _hp26(con: sqlite3.Connection) -> Answer:
    lead = _row(con, "SELECT lead_days FROM suppliers WHERE code = 'S-07'")["lead_days"]
    return Answer(
        [[str(lead)]],
        [f"ERP S-07 リードタイム {lead} 日（手引きは 14 日、conflicts c3）"],
        wrong_facts=[["14日です", "14 日です"]],
    )


@case(
    "hp27-conflict-retired",
    "試験装置の軸受の交換に使う 6206ZZ（NTN 指定）は、今も発注できますか？",
    ["ja", "cross", "conflict"],
    "hozen",
    tools=["erp"],
    docs=[DOCS[6]],
)
def _hp27(con: sqlite3.Connection) -> Answer:
    p = _part(con, "P-5009")
    s = _part(con, p["successor"])
    q = _usable(con)[s["part_no"]]
    return Answer(
        [["廃止"], [s["part_no"], "6208ZZ"], [n(q)]],
        [f"P-5009 廃止 {p['retired_on']} → {s['part_no']} {s['name']} 在庫 {n(q)}（conflicts c4）"],
    )


@case(
    "hp28-conflict-price",
    "軸受 6204ZZ-C3 の標準単価はいくらですか？",
    ["ja", "cross", "conflict", "price"],
    "kobai",
    tools=["erp"],
    docs=[DOCS[6]],
)
def _hp28(con: sqlite3.Connection) -> Answer:
    p = _part(con, "P-5002")
    return Answer(
        [yen(p["std_price"])],
        [f"ERP P-5002 標準単価 {p['std_price']}（上期 {p['old_std_price']}、手引きの値、conflicts c5）"],
        wrong_facts=[[f"標準単価は {p['old_std_price']:,}", f"標準単価は{p['old_std_price']:,}"]],
    )


@case(
    "hp29-grade-c-overdue",
    "上期の評価が C だった仕入先で、今も納期を過ぎた発注が残っているのはどこですか？",
    ["ja", "cross"],
    "kobai",
    tools=["erp"],
    docs=[DOCS[5]],
)
def _hp29(con: sqlite3.Connection) -> Answer:
    c = {s.code: s.name for s in facts.supplier_scores(con, date(2026, 4, 1), date(2026, 10, 1)) if s.grade == "C"}
    hit = sorted({o.supplier_code for o in facts.overdue_pos(con, TODAY) if o.supplier_code in c})
    return Answer([[code, c[code]] for code in hit], [f"C: {sorted(c)}; 今の遅れの仕入先のうち C: {hit}"])


@case(
    "hp30-report-overdue-change",
    "10月の月次報告にある『納期を過ぎて入荷し終えていない発注』の件数と、今の件数を比べてください。",
    ["ja", "cross", "time"],
    "kobai",
    tools=["erp"],
    docs=[DOCS[1]],
)
def _hp30(con: sqlite3.Connection) -> Answer:
    then = len(facts.overdue_pos(con, date(2026, 10, 31)))
    now = len(facts.overdue_pos(con, TODAY))
    return Answer([[str(then)], [str(now)]], [f"10/31 {then} 件 → 今 {now} 件"])


@case(
    "hp31-scrapped-sensor",
    "近接センサ PX-120 はどこにいくつありますか？",
    ["ja", "system", "warehouse"],
    "hozen",
    tools=["erp"],
)
def _hp31(con: sqlite3.Connection) -> Answer:
    p = _part(con, "P-5324")
    all_wh = facts.stock_at(con, TODAY, ["WH2", "WH1", "DEAD", "SMPL"]).get("P-5324", 0.0)
    return Answer(
        [["0", "ありません", "無い", "ない"], ["廃止", "廃棄"]],
        [f"P-5324 {p['status']}・全倉庫の在庫 {n(all_wh)}（10/20 DEAD へ移動、11/06 廃棄）"],
    )


@case(
    "hp32-ledger-retired-count",
    "10月末の部品台帳で、状態が廃止になっている部品はいくつありますか？",
    ["ja", "docs"],
    "seizo",
    docs=[DOCS[0]],
)
def _hp32(con: sqlite3.Connection) -> Answer:
    parts = facts.parts_at(con, date(2026, 10, 31))
    ret = [p.part_no for p in parts.values() if p.status == "廃止"]
    return Answer([[str(len(ret))]], [f"10/31 時点の廃止: {ret}"])


@case(
    "hp33-en-stock",
    "How many mechanical seals MS-30 do we have in stock right now?",
    ["en", "system"],
    "seizo",
    tools=["erp"],
)
def _hp33(con: sqlite3.Connection) -> Answer:
    q = _usable(con)["P-1043"]
    rp = _part(con, "P-1043")["reorder_point"]
    return Answer([[n(q)], ["reorder", "below", "発注点"]], [f"P-1043 在庫 {n(q)}、発注点 {rp}"])


@case(
    "hp34-week-new",
    "11月16日の在庫の報告のあとで、新しく発注点を下回った部品はいくつありますか？",
    ["ja", "cross", "time", "many"],
    "seizo",
    tools=["erp"],
    docs=[DOCS[2]],
)
def _hp34(con: sqlite3.Connection) -> Answer:
    before = {s.part_no for s in facts.below_reorder(con, date(2026, 11, 15))}
    now = {s.part_no for s in facts.below_reorder(con, TODAY)}
    new = sorted(now - before)
    return Answer([[str(len(new))], [new[0]]], [f"報告 {len(before)} 件・今 {len(now)} 件・新しく {new}"])


@case(
    "hp35-maintenance-oct",
    "10月の保全の作業は何件で、設備の停止時間は合計何分でしたか？",
    ["ja", "docs"],
    "hozen",
    docs=[DOCS[1], DOCS[4]],
)
def _hp35(con: sqlite3.Connection) -> Answer:
    u = facts.upkeep(con, 2026, 10)
    return Answer(
        [[str(u.records)], yen(u.downtime_min)], [f"work_records 2026-10: {u.records} 件・{u.downtime_min} 分"]
    )


# ── 出力 ──


def compute_all(db: Path) -> list[tuple[Case, Answer]]:
    con = facts.connect(db)
    try:
        return [(c, c.compute(con)) for c in CASES]
    finally:
        con.close()


def _flow(xs: list[str]) -> str:
    return "[" + ", ".join(json.dumps(x, ensure_ascii=False) for x in xs) + "]"


def _facts(name: str, fs: Facts) -> list[str]:
    if not fs:
        return []
    return [f"  {name}:"] + [f"  - any: {_flow(f)}" for f in fs]


def draft(results: list[tuple[Case, Answer]]) -> str:
    out: list[str] = []
    for c, a in results:
        out += [f"# 根拠: {e}" for e in a.evidence]
        out.append(f"- id: {c.id}")
        out.append(f"  query: {json.dumps(c.query, ensure_ascii=False)}")
        out.append(f"  tags: {_flow(c.tags)}")
        out.append(f"  as_user: {c.as_user}")
        if c.relevant_documents:
            out.append(f"  relevant_documents: {_flow(c.relevant_documents)}")
        if c.expect_tools:
            out.append(f"  expect_tools: {_flow(c.expect_tools)}")
        out += _facts("key_facts", a.key_facts)
        out += _facts("wrong_facts", a.wrong_facts)
        out += _facts("expect_caveat", a.expect_caveat)
    return "\n".join(out) + "\n"


def main(db: Path, out: Path | None) -> int:
    text = draft(compute_all(db))
    if out is None:
        print(text, end="")
    else:
        out.write_text(text)
        print(out)
    return 0


__all__ = ["CASES", "TODAY", "Answer", "Case", "compute_all", "day_forms", "draft", "main", "timedelta"]
