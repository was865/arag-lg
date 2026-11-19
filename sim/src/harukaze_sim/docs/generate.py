"""ある時点の文書を world.db から作る（specs/034 R8・R10）。

文書の数字は facts.py の問い合わせで数える（答えの計算と同じ）。今の harukaze_mix の文書は作り直さない。
作るもの（新しいファイルだけ）:
- g01 部品台帳（第二工場、10 月末）xlsx
- g02 月次報告 10 月 pptx
- g03 在庫の報告（11 月の週ごと）xlsx
- g04・g05 品質会議の議事録 10 月・11 月 docx
- g06 仕入先の評価（上期）pdf
手で書く文書（h01・h02、docs/manual.py）も同じフォルダに置く。
"""

import sqlite3
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.worksheet.worksheet import Worksheet
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE
from pptx.util import Inches
from pptx.util import Pt as PPt
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Flowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from harukaze_sim import facts

COMPANY = "株式会社ハルカゼ精工"
LEDGER_DAY = date(2026, 10, 31)
REPORT_WEEKS = [date(2026, 11, 2), date(2026, 11, 9), date(2026, 11, 16)]
MEETINGS = [date(2026, 10, 16), date(2026, 11, 13)]  # 9 月の議事録の「次回」が 10/16
PRODUCT_NAMES = {"FG-250": "HP-250", "FG-300": "HP-300", "FG-320": "HP-320", "FG-400": "HP-400"}

_HEAD = Font(bold=True)
_FILL = PatternFill("solid", fgColor="DDEBF7")


def _num(x: float) -> int | float:
    return int(x) if float(x).is_integer() else round(x, 2)


def _header(ws: Worksheet, row: list[str]) -> None:
    ws.append(row)
    for c in ws[ws.max_row]:
        c.font = _HEAD
        c.fill = _FILL


def _widths(ws: Worksheet, widths: list[int]) -> None:
    for i, w in enumerate(widths):
        ws.column_dimensions[chr(ord("A") + i)].width = w


# ── g01 部品台帳 ──


def g01_ledger(con: sqlite3.Connection, out: Path) -> Path:
    parts = facts.parts_at(con, LEDGER_DAY)
    stock = facts.stock_at(con, LEDGER_DAY, ["WH2"])
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "部品"
    ws.append([f"部品台帳（{LEDGER_DAY.year}年{LEDGER_DAY.month}月{LEDGER_DAY.day}日現在）　浜松第二工場 資材係"])
    _header(
        ws, ["部品番号", "名称", "適用機種", "標準単価（円）", "在庫", "単位", "発注点", "仕入先コード", "状態", "後継"]
    )
    for p in parts.values():
        if p.category == "製品":
            continue
        ws.append(
            [p.part_no, p.name, p.models, p.std_price, _num(stock.get(p.part_no, 0.0)), p.uom, p.reorder_point,
             p.supplier_code, p.status, p.successor]
        )  # fmt: skip
    ws.append([])
    ws.append(["注: 在庫は第二工場 資材倉庫（WH2）だけの数。第一工場の倉庫・呆滞品置場・見本は含まない。"])
    ws.append(["注: 標準単価は 2026年10月1日に下期の値へ改めた。"])
    _widths(ws, [10, 30, 20, 14, 8, 12, 8, 12, 6, 10])
    s = wb.create_sheet("仕入先")
    _header(s, ["仕入先コード", "仕入先名", "所在地", "リードタイム（日）", "担当者"])
    for r in con.execute("SELECT code, name, location, lead_days, contact FROM suppliers ORDER BY code"):
        s.append(list(r))
    _widths(s, [12, 36, 24, 16, 14])
    path = out / "g01-部品台帳_第二工場_2026-10末.xlsx"
    wb.save(path)
    return path


# ── g02 月次報告 ──


def _slide(prs: Any, title: str, bullets: list[str]) -> None:
    s = prs.slides.add_slide(prs.slide_layouts[1])
    s.shapes.title.text = title
    tf = s.placeholders[1].text_frame
    tf.text = bullets[0]
    for b in bullets[1:]:
        tf.add_paragraph().text = b
    for para in tf.paragraphs:
        for run in para.runs:
            run.font.size = PPt(18)


def g02_monthly(con: sqlite3.Connection, out: Path, year: int = 2026, month: int = 10) -> Path:
    made = facts.production(con, year, month)
    n_so, q_ship = facts.shipped(con, year, month)
    n_po, amount = facts.ordered(con, year, month)
    end = facts.month_range(year, month)[1]
    last = date.fromisoformat(end) - timedelta(days=1)
    late = facts.overdue_pos(con, last)
    up = facts.upkeep(con, year, month)
    top = facts.issued_top(con, year, month)
    prs = Presentation()
    s0 = prs.slides.add_slide(prs.slide_layouts[0])
    s0.shapes.title.text = f"浜松第二工場 月次報告（{year}年{month}月）"
    s0.placeholders[1].text = f"{COMPANY} 製造部　{year}年{month + 1}月5日"
    total = sum(made.values())
    _slide(
        prs,
        "生産実績",
        [f"生産台数: {total} 台"] + [f"{PRODUCT_NAMES.get(k, k)}: {v} 台" for k, v in made.items()],
    )
    _slide(
        prs,
        "出荷と購買",
        [
            f"出荷した受注: {n_so} 件（数量の合計 {_num(q_ship)}）",
            f"出した発注: {n_po} 件（金額の合計 {amount:,} 円、取消を除く）",
            f"月末に納期を過ぎて入荷し終えていない発注: {len(late)} 件",
        ],
    )
    _slide(
        prs,
        "保全",
        [
            f"保全の作業: {up.records} 件（うち故障修理 {up.breakdowns} 件）",
            f"設備の停止時間の合計: {up.downtime_min:,} 分",
        ],
    )
    s = prs.slides.add_slide(prs.slide_layouts[5])
    s.shapes.title.text = f"ラインへの払出しの多い部品（{month}月・上位 {len(top)}）"
    data = CategoryChartData()
    data.categories = [f"{no} {name}" for no, name, _q in top]
    data.add_series("払出し数", [q for _no, _name, q in top])
    s.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, Inches(1), Inches(1.6), Inches(8), Inches(4.8), data)
    path = out / f"g02-月次報告_{year}-{month:02d}.pptx"
    prs.save(str(path))
    return path


# ── g03 在庫の報告 ──


def g03_stock_report(con: sqlite3.Connection, out: Path) -> Path:
    wb = Workbook()
    first = wb.active
    assert first is not None
    wb.remove(first)
    for day in REPORT_WEEKS:
        ws = wb.create_sheet(f"{day.month}月{day.day}日")
        ws.append([f"発注点を下回っている部品（{day.year}年{day.month}月{day.day}日 朝の時点）　資材係"])
        _header(ws, ["部品番号", "名称", "在庫（使える倉庫の合計）", "発注点", "不足"])
        for sh in facts.below_reorder(con, day - timedelta(days=1)):
            ws.append([sh.part_no, sh.name, _num(sh.stock), sh.reorder_point, _num(sh.reorder_point - sh.stock)])
        ws.append([])
        ws.append(["注: 使える倉庫は第二工場 資材倉庫（WH2）と第一工場 資材倉庫（WH1）。廃止の部品は載せない。"])
        _widths(ws, [10, 32, 22, 8, 8])
    path = out / "g03-在庫の報告_2026-11.xlsx"
    wb.save(path)
    return path


# ── g04・g05 品質会議の議事録 ──


def _docx(title: str, blocks: list[tuple[str, object]], path: Path) -> Path:
    d = Document()
    style = d.styles["Normal"]
    style.font.size = Pt(10.5)
    style.element.get_or_add_rPr().get_or_add_rFonts().set(
        "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}eastAsia", "Yu Gothic"
    )
    d.add_heading(title, level=0)
    for kind, body in blocks:
        if kind == "h1":
            d.add_heading(str(body), level=1)
        elif kind == "p":
            d.add_paragraph(str(body))
        elif kind == "right":
            d.add_paragraph(str(body)).alignment = WD_ALIGN_PARAGRAPH.RIGHT
        elif kind == "table":
            rows: list[list[str]] = body  # type: ignore[assignment]
            t = d.add_table(rows=len(rows), cols=len(rows[0]))
            t.style = "Table Grid"
            for i, row in enumerate(rows):
                for j, cell in enumerate(row):
                    t.cell(i, j).text = cell
    d.save(str(path))
    return path


def _minutes(con: sqlite3.Connection, out: Path, day: date, nxt: date | None) -> Path:
    prev_m = day.month - 1
    up = facts.upkeep(con, day.year, prev_m)
    scraps = facts.scrapped(con, date(day.year, prev_m, 1), day)
    stock = facts.stock_at(con, day - timedelta(days=1), facts.usable_warehouses(con))
    parts = facts.parts_at(con, day)
    sk = parts["P-1042"]
    sk_now = stock.get("P-1042", 0.0)
    seals = [p for p in facts.overdue_pos(con, day - timedelta(days=1)) if parts[p.part_no].category == "シール"]
    blocks: list[tuple[str, object]] = [
        ("right", f"{COMPANY} 品質保証部　{day.year}年{day.month}月{day.day}日（金）14:00〜15:30　第二工場 会議室B"),
        ("p", "出席者: 品質保証部長 三浦 遥（議長）、保全課長 高梨 誠、製造課長 江口 拓也、購買課 佐伯 美穂、記録 品質保証部 森下 葵"),
        ("h1", f"1. {prev_m}月の保全の実績"),
        (
            "p",
            f"{prev_m}月の保全の作業は {up.records} 件（うち故障修理 {up.breakdowns} 件）、"
            f"設備の停止時間は合計 {up.downtime_min:,} 分だった。",
        ),
        ("h1", "2. 前回の決定事項の確認"),
        (
            "p",
            f"シールキット SK-300（P-1042）の在庫は会議の前日の終わりで {_num(sk_now)} 個、発注点は {sk.reorder_point} 個。"
            + ("発注点を満たしている。" if sk_now >= sk.reorder_point else "発注点を下回っているため、購買課が引き続き手配する。"),
        ),
        ("h1", "3. 廃棄"),
        ("p", f"{prev_m}月1日から会議の前日までの廃棄（呆滞品置場の廃止品を含む）。"),
    ]  # fmt: skip
    if scraps:
        blocks.append(
            ("table", [["部品番号", "名称", "数量", "倉庫"]] + [[a, b, str(_num(q)), w] for a, b, q, w in scraps])
        )
    else:
        blocks.append(("p", "期間中の廃棄は無かった。"))
    blocks.append(("h1", "4. シール部品の納期遅れ"))
    if seals:
        blocks.append(
            (
                "table",
                [["発注番号", "部品番号", "仕入先", "数量", "入荷済み", "納期"]]
                + [
                    [s.po_no, s.part_no, s.supplier_code, f"{s.qty} {s.uom}", f"{_num(s.received)} {s.uom}", s.due_on]
                    for s in seals
                ],
            )
        )
        blocks.append(("p", "購買課より、遅れている発注は仕入先に督促済みとの報告があった。"))
    else:
        blocks.append(("p", "納期を過ぎたシール部品の発注は無い。"))
    blocks.append(("h1", "5. 次回"))
    blocks.append(
        (
            "p",
            f"次回は {nxt.year}年{nxt.month}月{nxt.day}日（金）14:00 から、同じ会議室で行う。"
            if nxt
            else "次回は追って連絡する。",
        )
    )
    name = f"g0{4 + MEETINGS.index(day)}-品質会議議事録_{day.year}-{day.month:02d}.docx"
    return _docx(f"品質会議 議事録（{day.year}年{day.month}月）", blocks, out / name)


# ── g06 仕入先の評価 ──

_FONT = "HeiseiKakuGo-W5"


def g06_suppliers(con: sqlite3.Connection, out: Path) -> Path:
    pdfmetrics.registerFont(UnicodeCIDFont(_FONT))
    body = ParagraphStyle("jp", fontName=_FONT, fontSize=10, leading=15)
    head = ParagraphStyle("jph", parent=body, fontSize=15, leading=22, spaceAfter=6)
    scores = facts.supplier_scores(con, date(2026, 4, 1), date(2026, 10, 1))
    rows = [["コード", "仕入先名", "件数", "納期どおり", "納期遵守率", "平均の遅れ（日）", "評価"]]
    for s in scores:
        rows.append(
            [s.code, s.name, str(s.orders), str(s.on_time), f"{s.rate * 100:.1f}%", f"{s.late_days_avg:.1f}", s.grade]
        )
    path = out / "g06-仕入先の評価_2026上期.pdf"
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm)
    t = Table(rows, colWidths=[16 * mm, 70 * mm, 12 * mm, 20 * mm, 22 * mm, 26 * mm, 12 * mm], repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (-1, -1), _FONT, 8.5),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DDEBF7")),
            ]
        )
    )
    flow: list[Flowable] = [
        Paragraph("仕入先の評価（2026年度 上期）", head),
        Paragraph(f"{COMPANY} 購買課　2026年10月20日", body),
        Paragraph(
            "対象: 納期が 2026年4月1日〜9月30日の発注のうち、入荷し終えたもの。納期どおり = 最後の入荷の日が納期以前。"
            "評価: 納期遵守率 85% 以上を A、70% 以上を B、それ未満を C とする。平均の遅れは遅れた発注だけで平均した。",
            body,
        ),
        Spacer(1, 5 * mm),
        t,
        Spacer(1, 5 * mm),
        Paragraph("C の仕入先には、下期の最初の発注の前に納期の見直しを依頼する。", body),
    ]
    doc.build(flow)
    return path


def all_docs(db: Path, out: Path) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    con = facts.connect(db)
    try:
        made = [g01_ledger(con, out), g02_monthly(con, out), g03_stock_report(con, out)]
        for i, day in enumerate(MEETINGS):
            made.append(_minutes(con, out, day, MEETINGS[i + 1] if i + 1 < len(MEETINGS) else None))
        made.append(g06_suppliers(con, out))
        from harukaze_sim.docs import manual

        return made + manual.all_manual(out)
    finally:
        con.close()
