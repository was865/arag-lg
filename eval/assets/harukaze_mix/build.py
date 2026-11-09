# 資料の本文を文字列で持つため、長い行を許す
# ruff: noqa: E501
"""評価用資料 harukaze_mix を作る（specs/018-eval-corpus-mix）。

架空の会社「株式会社ハルカゼ精工」（ポンプ製造、浜松第二工場・ペナン工場）1 社分の資料を、
Word・Excel・PowerPoint・文字のある PDF・走査 PDF（画像だけ）・英語資料で作る。
内容はこのファイルに直接書いてあり、何度流しても同じ内容になる（Office の作成日時などの付帯情報は除く）。

実行（リポジトリの直下で）:
    cd api && uv run --group assets python ../eval/assets/harukaze_mix/build.py

走査 PDF の文字は日本語の TrueType で描く。既定は macOS の Hiragino Sans GB。
別の環境では ARAG_ASSET_FONT に日本語を含むフォントのパスを渡す。
"""

import os
import random
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from PIL import Image, ImageDraw, ImageFilter, ImageFont
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
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

OUT = Path(__file__).resolve().parent / "docs"
FONT_PATH = os.environ.get("ARAG_ASSET_FONT", "/System/Library/Fonts/Hiragino Sans GB.ttc")
COMPANY = "株式会社ハルカゼ精工"


# ── Word ─────────────────────────────────────────────────────────────


def _docx(title: str, blocks: list[tuple[str, object]], name: str, lang: str = "ja") -> None:
    """blocks は (種類, 内容)。種類は h1 / h2 / p / list / table。"""
    d = Document()
    style = d.styles["Normal"]
    style.font.size = Pt(10.5)
    if lang == "ja":
        style.element.get_or_add_rPr().get_or_add_rFonts().set(
            "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}eastAsia", "Yu Gothic"
        )
    d.add_heading(title, level=0)
    for kind, body in blocks:
        if kind == "h1":
            d.add_heading(str(body), level=1)
        elif kind == "h2":
            d.add_heading(str(body), level=2)
        elif kind == "p":
            d.add_paragraph(str(body))
        elif kind == "right":
            para = d.add_paragraph(str(body))
            para.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        elif kind == "list":
            for item in body:  # type: ignore[attr-defined]
                d.add_paragraph(str(item), style="List Number")
        elif kind == "bullets":
            for item in body:  # type: ignore[attr-defined]
                d.add_paragraph(str(item), style="List Bullet")
        elif kind == "table":
            rows: list[list[str]] = body  # type: ignore[assignment]
            t = d.add_table(rows=len(rows), cols=len(rows[0]))
            t.style = "Table Grid"
            for i, row in enumerate(rows):
                for j, cell in enumerate(row):
                    t.cell(i, j).text = cell
    d.save(OUT / name)


def w01_regulation() -> None:
    _docx(
        "設備保全規程",
        [
            ("right", f"{COMPANY}　規程番号 HS-MR-003　制定 2023年4月1日　改定 2026年7月1日"),
            ("h1", "第1条（目的）"),
            (
                "p",
                "この規程は、浜松第二工場およびペナン工場の生産設備を安全かつ安定して稼働させるため、点検・保全の方法と責任を定める。",
            ),
            ("h1", "第2条（適用範囲）"),
            (
                "p",
                "全社の生産設備・検査装置・付帯設備に適用する。事務所の空調・照明は総務部の管理とし、この規程の対象外とする。",
            ),
            ("h1", "第3条（責任者）"),
            (
                "p",
                "設備保全の責任者は各工場の保全課長とする。浜松第二工場の保全課長は高梨 誠とする。保全課長が不在のときは保全係長が代行する。",
            ),
            ("h1", "第4条（点検の周期）"),
            ("p", "点検は次の周期で行う。"),
            (
                "table",
                [
                    ["区分", "周期", "実施者", "記録"],
                    ["日常点検", "毎日（始業前）", "設備の担当作業者", "日常点検表"],
                    ["月次点検", "毎月1回", "保全課員", "月次点検票（様式 MR-7）"],
                    ["年次点検", "毎年1回（8月の夏季休業中）", "保全課員と製造元", "年次点検報告書"],
                ],
            ),
            ("h1", "第5条（異常時の対応）"),
            (
                "p",
                "点検で異常を見つけた者は、直ちに設備を停止し、保全課（内線 2417）に連絡する。夜間・休日は当番の保全係長の携帯電話に連絡する。",
            ),
            ("p", "判定が「要注意」のときは、7日以内に再点検を行い、結果を月次点検票の備考欄に記入する。"),
            ("h1", "第6条（記録の保存）"),
            (
                "p",
                "点検の記録は5年間保存する。法令で定めのあるもの（圧力容器・クレーン等）は法令の期間に従う。",
            ),
            ("h1", "第7条（外部委託）"),
            (
                "p",
                "保全作業を外部に委託するときは、作業前に安全教育を行い、作業許可書を発行する。委託先への支払条件は購買規程による。",
            ),
            ("h1", "第12条（クリーンルーム設備の特例）"),
            (
                "p",
                "クリーンルーム内の設備は、第4条の規定にかかわらず、月次点検を2週間ごとに行う。年次点検はクリーンルームの停止日に合わせて行う。",
            ),
            ("h1", "附則"),
            (
                "p",
                "2026年7月1日の改定で、第12条を追加し、第5条の連絡先を内線 2417 に改めた（旧 内線 2410）。",
            ),
        ],
        "w01-設備保全規程.docx",
    )


_PROC_COMMON = [
    "電源を遮断し、ロックアウト・タグアウトを行う。",
    "吸込側・吐出側の弁を閉じ、ポンプ内の液を抜く。",
    "カップリングガードを外し、電動機とポンプの軸を切り離す。",
    "ケーシングボルトを外し、羽根車を取り出す。",
]


def w02_procedure_old() -> None:
    _docx(
        "HP-300 ポンプ分解・組立手順書（第2版）",
        [
            ("right", f"{COMPANY} 浜松第二工場 保全課　文書番号 HS-PR-021　第2版　2025年4月10日"),
            ("p", "対象機種: HP-300（渦巻ポンプ）。所要時間の目安は 90 分（2名作業）。"),
            ("h1", "1. 準備"),
            (
                "bullets",
                ["工具: トルクレンチ（20〜100 N·m）、軸受プーラー", "消耗品: グリス KG-2、ガスケット一式"],
            ),
            ("h1", "2. 分解"),
            ("list", _PROC_COMMON),
            ("h1", "3. 組立"),
            (
                "list",
                [
                    "軸受にグリス KG-2 を充填する。",
                    "羽根車を組み付け、ケーシングボルトを対角の順に締め付ける。締付トルクは 45 N·m とする。",
                    "カップリングの芯出しを行う（許容値 0.10 mm 以内）。",
                    "試運転を10分行い、漏れと異音がないことを確認する。",
                ],
            ),
            ("h1", "4. 記録"),
            ("p", "作業後、保守記録（Excel）に作業内容と停止時間を記入する。"),
        ],
        "w02-HP-300分解手順書_第2版.docx",
    )


def w03_procedure_new() -> None:
    _docx(
        "HP-300 ポンプ分解・組立手順書（第3版）",
        [
            ("right", f"{COMPANY} 浜松第二工場 保全課　文書番号 HS-PR-021　第3版　2026年8月20日"),
            ("p", "対象機種: HP-300（渦巻ポンプ）。所要時間の目安は 75 分（2名作業）。"),
            (
                "p",
                "第2版からの主な変更: シール部からの漏れ対策として、締付トルクを 45 N·m から 52 N·m に上げ、グリスを KG-5 に変更し、Oリングの交換を必須とした。",
            ),
            ("h1", "1. 準備"),
            (
                "bullets",
                [
                    "工具: トルクレンチ（20〜100 N·m）、軸受プーラー、Oリング挿入治具 J-14",
                    "消耗品: グリス KG-5、シールキット SK-300（部品番号 P-1042）",
                ],
            ),
            ("h1", "2. 分解"),
            ("list", [*_PROC_COMMON, "Oリングとメカニカルシールを取り外し、廃棄する（再使用禁止）。"]),
            ("h1", "3. 組立"),
            (
                "list",
                [
                    "軸受にグリス KG-5 を充填する。",
                    "シールキット SK-300 の新しいOリングとメカニカルシールを、治具 J-14 を使って取り付ける。",
                    "羽根車を組み付け、ケーシングボルトを対角の順に2回に分けて締め付ける。締付トルクは 52 N·m とする。",
                    "カップリングの芯出しを行う（許容値 0.05 mm 以内）。",
                    "試運転を15分行い、漏れと異音がないこと、軸受温度が 70℃ 以下であることを確認する。",
                ],
            ),
            ("h1", "4. 記録"),
            (
                "p",
                "作業後、保守記録（Excel）に作業内容と停止時間を記入する。シールキットを使ったときは部品台帳の在庫を1減らす。",
            ),
        ],
        "w03-HP-300分解手順書_第3版.docx",
    )


def w04_minutes() -> None:
    _docx(
        "品質会議 議事録（2026年9月）",
        [
            ("right", f"{COMPANY} 品質保証部　2026年9月18日（金）14:00〜15:30　第二工場 会議室B"),
            (
                "p",
                "出席者: 品質保証部長 三浦 遥（議長）、保全課長 高梨 誠、製造課長 江口 拓也、購買課 佐伯 美穂、記録 品質保証部 森下 葵",
            ),
            ("h1", "1. 8月の品質実績"),
            (
                "p",
                "出荷検査の不良率は 0.8%（7月 0.6%）。主な不良は HP-300 のシール部からの漏れで、8月の発生件数は 7 件だった。",
            ),
            ("h1", "2. HP-300 シール漏れの対策"),
            (
                "p",
                "保全課長より、分解手順書を第3版に改訂した旨の報告があった（締付トルク変更、Oリングの交換を必須化）。",
            ),
            ("p", "製造課長より、組立ラインでも同じ締付トルクに揃えるべきとの意見があり、了承された。"),
            ("h1", "3. 決定事項"),
            (
                "table",
                [
                    ["No.", "内容", "担当", "期限"],
                    ["1", "組立ラインの締付トルク基準を手順書第3版に合わせる", "江口", "2026年10月15日"],
                    ["2", "シールキット SK-300 の在庫を発注点まで補充する", "佐伯", "2026年10月31日"],
                    ["3", "不良率の目標を 0.5% 以下とし、毎月の会議で確認する", "三浦", "継続"],
                ],
            ),
            ("h1", "4. 次回"),
            ("p", "次回は 2026年10月16日（金）14:00 から、同じ会議室で行う。"),
        ],
        "w04-品質会議議事録_2026-09.docx",
    )


def e01_penang_procedure() -> None:
    _docx(
        "HP-300 Pump Overhaul Procedure — Penang Plant",
        [
            ("right", "Harukaze Seiko (Penang) Sdn. Bhd. — Document PN-PR-021, Rev. B, 2026-09-05"),
            (
                "p",
                "This procedure localizes HS-PR-021 (3rd edition) for the Penang plant. Where this document is silent, the Hamamatsu procedure applies.",
            ),
            ("h1", "1. Local requirements"),
            (
                "bullets",
                [
                    "Work only when the workshop humidity is below 70% RH. If humidity is higher, run the dehumidifier for at least 30 minutes before opening the casing.",
                    "Use grease KG-5 and seal kit SK-300. Seal kits are stored in cabinet C-3 of the spare parts room.",
                    "Casing bolts are tightened to 52 N·m in two passes, in a cross pattern.",
                    "The shift lead must sign off the job before the pump is returned to service.",
                ],
            ),
            ("h1", "2. Records"),
            (
                "p",
                "Record the job on form PN-QF-12 and enter downtime in the maintenance log within 24 hours.",
            ),
            ("h1", "3. Contacts"),
            (
                "p",
                "Maintenance supervisor: Lim Wei Ling (ext. 315). For seal kit shortages, contact the purchasing team in Hamamatsu.",
            ),
        ],
        "e01-Penang-HP-300-overhaul-procedure.docx",
        lang="en",
    )


# ── Excel ────────────────────────────────────────────────────────────

_HEAD = Font(bold=True)
_FILL = PatternFill("solid", fgColor="DDEBF7")


def _header(ws: object, row: list[str]) -> None:
    ws.append(row)  # type: ignore[attr-defined]
    for c in ws[ws.max_row]:  # type: ignore[attr-defined,index]
        c.font = _HEAD
        c.fill = _FILL


def x01_parts() -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "部品"
    ws.append(["部品台帳（2026年9月30日現在）　浜松第二工場 資材係"])
    _header(ws, ["部品番号", "名称", "適用機種", "単価（円）", "在庫", "発注点", "仕入先コード"])
    rows = [
        ["P-1042", "シールキット SK-300", "HP-300 / HP-320", 18400, 6, 10, "S-07"],
        ["P-1043", "メカニカルシール MS-30", "HP-300 / HP-320", 24800, 4, 4, "S-07"],
        ["P-2010", "軸受 6308ZZ", "HP-300", 3150, 22, 12, "S-02"],
        ["P-2011", "軸受 6309ZZ", "HP-320", 3980, 9, 12, "S-02"],
        ["P-3100", "羽根車 IM-300", "HP-300", 56000, 2, 1, "S-11"],
        ["P-3120", "羽根車 IM-320", "HP-320", 61500, 1, 1, "S-11"],
        ["P-4001", "グリス KG-5（400g）", "共通", 2200, 35, 20, "S-02"],
        ["P-4002", "グリス KG-2（400g）", "共通（廃止予定）", 1800, 12, 0, "S-02"],
    ]
    for r in rows:
        ws.append(r)
    # 適用機種が同じ行を結合する（結合セルの読み取りを試すため）
    ws.merge_cells("C3:C4")
    ws["C3"].alignment = Alignment(vertical="center")
    ws.append([])
    ws.append(["注: 在庫が発注点を下回ったら、資材係が仕入先に発注する。廃止予定の部品は発注点を 0 とする。"])

    s = wb.create_sheet("仕入先")
    _header(s, ["仕入先コード", "仕入先名", "所在地", "リードタイム（日）", "担当者"])
    for r in [
        ["S-02", "東雲ベアリング販売株式会社", "静岡県浜松市", 7, "大川"],
        ["S-07", "Aster Seals Ltd.", "英国 バーミンガム", 21, "J. Carter"],
        ["S-11", "有限会社 白砂鋳造", "愛知県豊橋市", 30, "白砂"],
    ]:
        s.append(r)
    for sheet in (ws, s):
        for col in sheet.columns:
            sheet.column_dimensions[col[1].column_letter].width = 18
    wb.save(OUT / "x01-部品台帳.xlsx")


def x02_maintenance_log() -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "2026年9月"
    _header(ws, ["日付", "設備ID", "設備名", "作業内容", "担当", "停止時間（分）"])
    for r in [
        ["2026-09-02", "PM-04", "冷却水ポンプ（HP-300）", "月次点検", "小野寺", 30],
        ["2026-09-05", "AL-01", "組立ライン1号", "コンベヤベルト交換", "田村", 120],
        ["2026-09-12", "PM-04", "冷却水ポンプ（HP-300）", "月次点検（再点検）", "小野寺", 25],
        ["2026-09-16", "XR-9", "X線検査装置", "校正", "製造元", 240],
        [
            "2026-09-19",
            "PM-04",
            "冷却水ポンプ（HP-300）",
            "軸受交換・分解整備（手順書第3版）",
            "小野寺・田村",
            80,
        ],
        ["2026-09-24", "CR-02", "クリーンルーム空調機", "フィルタ交換", "田村", 60],
        ["2026-09-29", "AL-01", "組立ライン1号", "非常停止回路の点検", "高梨", 45],
    ]:
        ws.append(r)
    ws.append([])
    ws.append(["合計", "", "", "", "", 600])
    s = wb.create_sheet("設備一覧")
    _header(s, ["設備ID", "設備名", "設置場所", "導入年"])
    for r in [
        ["PM-04", "冷却水ポンプ（HP-300）", "第二工場 機械室", 2019],
        ["AL-01", "組立ライン1号", "第二工場 1階", 2021],
        ["XR-9", "X線検査装置", "第二工場 検査室", 2024],
        ["CR-02", "クリーンルーム空調機", "第二工場 2階", 2022],
    ]:
        s.append(r)
    for sheet in (ws, s):
        for col in sheet.columns:
            sheet.column_dimensions[col[0].column_letter].width = 20
    wb.save(OUT / "x02-保守記録_2026-09.xlsx")


def x03_price_list() -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "価格表"
    ws.append([f"{COMPANY} 標準価格表（2026年度下期：2026年10月1日〜2027年3月31日）"])
    _header(ws, ["機種", "標準価格（円・税別）", "保守契約 年額（円・税別）", "納期（週）"])
    for r in [
        ["HP-300", 1280000, 96000, 6],
        ["HP-320", 1490000, 112000, 8],
        ["HP-300 シール更新パック", 52000, None, 2],
    ]:
        ws.append(r)
    ws.append([])
    ws.append(["割引条件"])
    ws.append(["・同一機種を10台以上まとめて注文した場合、標準価格から 8% 引き"])
    ws.append(["・保守契約を3年分一括で前払いした場合、保守契約の年額から 5% 引き"])
    ws.append(["・割引は併用できる。ただし HP-300 シール更新パックは割引の対象外"])
    for col in "ABCD":
        ws.column_dimensions[col].width = 30
    wb.save(OUT / "x03-価格表_2026下期.xlsx")


# ── PowerPoint ───────────────────────────────────────────────────────


def _slide(prs: Presentation, title: str, bullets: list[str]) -> object:
    s = prs.slides.add_slide(prs.slide_layouts[1])
    s.shapes.title.text = title
    tf = s.placeholders[1].text_frame
    tf.text = bullets[0]
    for b in bullets[1:]:
        tf.add_paragraph().text = b
    for p in tf.paragraphs:
        for r in p.runs:
            r.font.size = PPt(20)
    return s


def _title(prs: Presentation, title: str, sub: str) -> None:
    s = prs.slides.add_slide(prs.slide_layouts[0])
    s.shapes.title.text = title
    s.placeholders[1].text = sub


def p01_monthly_report() -> None:
    prs = Presentation()
    _title(prs, "浜松第二工場 月次報告（2026年9月）", f"{COMPANY} 製造部　2026年10月5日")
    _slide(
        prs,
        "生産実績",
        [
            "生産台数: 1,284 台（計画 1,320 台、計画比 97%）",
            "HP-300: 836 台 / HP-320: 448 台",
            "残業時間: 1人あたり月 14.2 時間",
        ],
    )
    s = prs.slides.add_slide(prs.slide_layouts[5])
    s.shapes.title.text = "設備停止の要因（9月・分）"
    data = CategoryChartData()
    data.categories = ["金型・治具の交換", "計画保全", "材料待ち", "故障"]
    data.add_series("停止時間（分）", (410, 330, 180, 95))
    s.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, Inches(1), Inches(1.6), Inches(8), Inches(4.8), data)
    _slide(
        prs,
        "安全",
        [
            "休業災害: 0 件（無災害の連続日数 412 日）",
            "ヒヤリハットの報告: 9 件（うちフォークリフト関連 4 件）",
            "10月の重点: 機械室の通路の整理",
        ],
    )
    _slide(
        prs,
        "10月の計画",
        [
            "生産計画: 1,350 台",
            "組立ラインの締付トルク基準の見直し（品質会議の決定事項）",
            "XR-9 の校正結果を受けた検査条件の更新",
        ],
    )
    prs.save(OUT / "p01-月次報告_2026-09.pptx")


def p02_plant_intro() -> None:
    prs = Presentation()
    _title(prs, "浜松第二工場のご紹介", f"{COMPANY}　見学者向け資料")
    _slide(
        prs,
        "工場の概要",
        [
            "所在地: 静岡県浜松市（架空の住所は省略）",
            "稼働開始: 2018年",
            "従業員: 214 名（2026年9月現在）",
            "主な製品: 渦巻ポンプ HP-300・HP-320",
        ],
    )
    _slide(
        prs,
        "主な設備",
        [
            "組立ライン1号（AL-01）: 自動化率 68%",
            "X線検査装置（XR-9）: 鋳物の内部欠陥を全数検査",
            "クリーンルーム: クラス 10,000（ISO クラス 7 相当）、2階に 120 m²",
        ],
    )
    _slide(
        prs,
        "見学時のお願い",
        [
            "黄色の線の内側には入らないでください",
            "写真撮影は会議室の中だけとします",
            "クリーンルームは窓越しの見学となります",
        ],
    )
    prs.save(OUT / "p02-工場紹介_浜松第二工場.pptx")


def p03_safety_training() -> None:
    prs = Presentation()
    _title(prs, "新人安全教育", "浜松第二工場　2026年度版")
    _slide(
        prs,
        "5つの禁止事項",
        [
            "回転中の機械に手を入れない",
            "ロックアウトをせずに保全作業をしない",
            "安全装置を外さない・無効にしない",
            "フォークリフトの作業範囲に立ち入らない",
            "許可なく他部署の設備を操作しない",
        ],
    )
    _slide(
        prs,
        "保護具",
        [
            "安全靴（JIS T 8101 適合品）は工場内で常に着用",
            "保護めがねは機械加工エリアで着用",
            "クリーンルームでは専用の防塵服と帽子を着用",
        ],
    )
    _slide(
        prs,
        "非常時",
        [
            "非常停止ボタンは赤色のきのこ形。設備ごとに2か所以上",
            "火災・地震のときの集合場所は南駐車場",
            "けが人が出たら、まず上長と守衛室（内線 1100）に連絡",
        ],
    )
    prs.save(OUT / "p03-新人安全教育.pptx")


# ── 文字のある PDF ────────────────────────────────────────────────────

pdfmetrics.registerFont(UnicodeCIDFont("HeiseiKakuGo-W5"))
_JP = ParagraphStyle("jp", fontName="HeiseiKakuGo-W5", fontSize=10.5, leading=16)
_JPH = ParagraphStyle("jph", parent=_JP, fontSize=16, leading=24, spaceAfter=6)
_EN = ParagraphStyle("en", fontName="Helvetica", fontSize=10.5, leading=15)
_ENH = ParagraphStyle("enh", parent=_EN, fontName="Helvetica-Bold", fontSize=16, leading=22, spaceAfter=6)


def _pdf(
    name: str, title: str, intro: list[str], rows: list[list[str]], notes: list[str], en: bool = False
) -> None:
    body, head = (_EN, _ENH) if en else (_JP, _JPH)
    font = "Helvetica" if en else "HeiseiKakuGo-W5"
    doc = SimpleDocTemplate(str(OUT / name), pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm)
    flow: list[object] = [Paragraph(title, head)]
    flow += [Paragraph(t, body) for t in intro]
    flow.append(Spacer(1, 6 * mm))
    t = Table(rows, colWidths=[60 * mm, 90 * mm])
    t.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (-1, -1), font, 10),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DDEBF7")),
            ]
        )
    )
    flow.append(t)
    flow.append(Spacer(1, 6 * mm))
    flow += [Paragraph(t, body) for t in notes]
    doc.build(flow)  # type: ignore[arg-type]


def d01_spec_hp300() -> None:
    _pdf(
        "d01-仕様書_HP-300.pdf",
        "渦巻ポンプ HP-300 仕様書",
        [f"{COMPANY}　仕様書番号 SP-300-04　2026年6月改訂"],
        [
            ["項目", "仕様"],
            ["最大吐出量", "300 L/min"],
            ["全揚程", "42 m"],
            ["電動機出力", "5.5 kW（4極）"],
            ["質量", "86 kg"],
            ["使用液温", "0〜60 ℃"],
            ["接液部材質", "ステンレス鋼 SCS13"],
            ["軸封", "メカニカルシール MS-30"],
        ],
        ["注1: 液温が 60 ℃ を超える用途には HP-320 を選定すること。", "注2: 保証期間は納入後 18 か月。"],
    )


def d02_spec_hp320() -> None:
    _pdf(
        "d02-仕様書_HP-320.pdf",
        "渦巻ポンプ HP-320 仕様書",
        [f"{COMPANY}　仕様書番号 SP-320-02　2026年6月改訂"],
        [
            ["項目", "仕様"],
            ["最大吐出量", "320 L/min"],
            ["全揚程", "45 m"],
            ["電動機出力", "7.5 kW（4極）"],
            ["質量", "94 kg"],
            ["使用液温", "0〜80 ℃"],
            ["接液部材質", "ステンレス鋼 SCS14"],
            ["軸封", "メカニカルシール MS-30"],
        ],
        [
            "注1: HP-300 と取付寸法は同じだが、電動機の出力が異なるため配線の確認が必要。",
            "注2: 保証期間は納入後 18 か月。",
        ],
    )


def e02_supplier_spec() -> None:
    _pdf(
        "e02-Aster-Seals-SK-300-datasheet.pdf",
        "Seal Kit SK-300 — Product Data Sheet",
        ["Aster Seals Ltd., Birmingham, UK. Data sheet DS-SK300, issue 3 (2026-03)."],
        [
            ["Item", "Specification"],
            ["Compatible pumps", "Harukaze Seiko HP-300, HP-320"],
            ["O-ring material", "FKM (fluoroelastomer)"],
            ["Temperature range", "-20 to 200 °C"],
            ["Shelf life", "24 months from date of manufacture"],
            ["Storage", "Below 25 °C, away from direct sunlight and ozone sources"],
            ["Contents", "2 O-rings, 1 mechanical seal MS-30, 1 gasket"],
        ],
        [
            "Kits past their shelf life must not be installed.",
            "Minimum order quantity is 5 kits. Standard lead time is 21 days from order confirmation.",
        ],
        en=True,
    )


# ── 走査 PDF（画像だけ） ─────────────────────────────────────────────


def _scan(name: str, lines: list[tuple[str, int]], stamp: str | None, seed: int) -> None:
    """A4・150dpi の紙を描き、わずかに傾けて汚して画像だけの PDF にする。lines は (文字, 大きさ)。"""
    rnd = random.Random(seed)
    w, h = 1240, 1754
    im = Image.new("L", (w, h), 250)
    d = ImageDraw.Draw(im)
    y = 120
    for text, size in lines:
        if text == "---":
            d.line((100, y + 10, w - 100, y + 10), fill=40, width=2)
            y += 40
            continue
        f = ImageFont.truetype(FONT_PATH, size)
        d.text((110, y), text, font=f, fill=25)
        y += int(size * 1.9)
    rgb = im.convert("RGB")
    if stamp:
        sd = ImageDraw.Draw(rgb)
        cx, cy, r = w - 260, 260, 75
        sd.ellipse((cx - r, cy - r, cx + r, cy + r), outline=(200, 40, 40), width=6)
        sf = ImageFont.truetype(FONT_PATH, 34)
        for i, ch in enumerate(stamp):
            sd.text((cx - 17, cy - 52 + i * 38), ch, font=sf, fill=(200, 40, 40))
    # 紙の汚れと傾き
    px = rgb.load()
    for _ in range(4000):
        x, yy = rnd.randrange(w), rnd.randrange(h)
        v = rnd.randrange(150, 230)
        px[x, yy] = (v, v, v)
    rgb = rgb.rotate(rnd.uniform(-0.8, 0.8), resample=Image.BICUBIC, fillcolor=(250, 250, 250))
    rgb = rgb.filter(ImageFilter.GaussianBlur(0.6))
    rgb.save(OUT / name, "PDF", resolution=150)


def s01_inspection_sheet() -> None:
    _scan(
        "s01-月次点検票_PM-04_走査.pdf",
        [
            ("月次点検票（様式 MR-7）", 44),
            (f"{COMPANY} 浜松第二工場 保全課", 26),
            ("---", 0),
            ("設備ID: PM-04　　設備名: 冷却水ポンプ（HP-300）", 28),
            ("点検日: 2026年9月12日（再点検）　　点検者: 小野寺 健", 28),
            ("---", 0),
            ("点検項目　　　　　測定値　　　　判定", 28),
            ("振動速度　　　　　2.8 mm/s　　　良", 28),
            ("軸受温度　　　　　61 ℃　　　　 要注意", 28),
            ("吐出圧力　　　　　0.39 MPa　　　良", 28),
            ("シール部の漏れ　　なし　　　　　良", 28),
            ("---", 0),
            ("備考: 9月2日の点検で軸受温度 64 ℃。再点検でも 61 ℃ と高め。", 26),
            ("軸受の交換を推奨する。交換は9月19日に予定（手順書第3版による）。", 26),
            ("確認: 保全課長 高梨", 26),
        ],
        stamp="高梨",
        seed=1,
    )


def s02_notice() -> None:
    _scan(
        "s02-支払条件変更のお知らせ_走査.pdf",
        [
            ("2026年10月1日", 26),
            ("協力会社 各位", 30),
            (f"{COMPANY}　購買部長 長谷部 透", 26),
            ("---", 0),
            ("支払条件変更のお知らせ", 44),
            ("拝啓 平素は格別のお引き立てをいただき、厚く御礼申し上げます。", 26),
            ("さて、当社は下記のとおり支払条件を変更いたします。", 26),
            ("記", 30),
            ("1. 変更内容: 支払サイトを 月末締め翌々月末払い（60日）から", 26),
            ("　　月末締め翌月15日払い（45日）に短縮します。", 26),
            ("2. 適用開始: 2026年11月締め分から", 26),
            ("3. 支払方法: 銀行振込（手形での支払いは廃止します）", 26),
            ("4. お問い合わせ: 購買課 佐伯（内線 2230）", 26),
            ("以上", 26),
        ],
        stamp="購買",
        seed=2,
    )


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for f in (
        w01_regulation, w02_procedure_old, w03_procedure_new, w04_minutes, e01_penang_procedure,
        x01_parts, x02_maintenance_log, x03_price_list,
        p01_monthly_report, p02_plant_intro, p03_safety_training,
        d01_spec_hp300, d02_spec_hp320, e02_supplier_spec,
        s01_inspection_sheet, s02_notice,
    ):  # fmt: skip
        f()
    for p in sorted(OUT.iterdir()):
        print(p.name)


if __name__ == "__main__":
    main()
