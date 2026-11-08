"""テスト用の小さな DoclingDocument を組み立てる（docling-serve を使わない）。"""

from typing import Any

from docling_core.transforms.chunker.tokenizer.base import BaseTokenizer
from docling_core.types.doc import (
    BoundingBox,
    DocItemLabel,
    DoclingDocument,
    ProvenanceItem,
    Size,
    TableCell,
    TableData,
)


class CharTokenizer(BaseTokenizer):
    """1 文字 = 1 トークンの偽トークナイザ。"""

    max_tokens: int = 80

    def count_tokens(self, text: str) -> int:
        return len(text)

    def get_max_tokens(self) -> int:
        return self.max_tokens

    def get_tokenizer(self) -> Any:
        return len


def prov(page: int) -> ProvenanceItem:
    return ProvenanceItem(page_no=page, bbox=BoundingBox(l=10, t=700, r=300, b=680), charspan=(0, 1))


def table(rows: list[list[str]], page: int, *, header: bool = True) -> tuple[TableData, ProvenanceItem]:
    cells = [
        TableCell(
            text=v,
            start_row_offset_idx=i,
            end_row_offset_idx=i + 1,
            start_col_offset_idx=j,
            end_col_offset_idx=j + 1,
            column_header=header and i == 0,
        )
        for i, r in enumerate(rows)
        for j, v in enumerate(r)
    ]
    return TableData(num_rows=len(rows), num_cols=len(rows[0]), table_cells=cells), prov(page)


def regulation_doc() -> DoclingDocument:
    """見出し 2 段・本文・表・リストを持つ規程文書（3 ページ）。"""
    doc = DoclingDocument(name="情報セキュリティ規程")
    for p in (1, 2, 3):
        doc.add_page(page_no=p, size=Size(width=600, height=800))
    doc.add_heading("第1章 総則", level=1, prov=prov(1))
    doc.add_heading("第1条 目的", level=2, prov=prov(1))
    doc.add_text(DocItemLabel.TEXT, "この規程は、会社の情報資産を守るために定める。", prov=prov(1))
    doc.add_heading("第2条 定義", level=2, prov=prov(2))
    doc.add_text(DocItemLabel.TEXT, "情報資産とは、MX-17 型番の機器と、その中のデータをいう。", prov=prov(2))
    data, pv = table(
        [
            ["区分", "保管期間"],
            ["機密", "10年"],
            ["社外秘", "5年"],
            ["一般", "1年"],
            ["個人情報", "7年"],
            ["契約書", "10年"],
        ],
        2,
    )
    doc.add_table(data=data, prov=pv)
    doc.add_heading("第2章 管理", level=1, prov=prov(3))
    lst = doc.add_list_group()
    for t in ["パスワードは 12 文字以上とする。", "共有アカウントは禁止する。"]:
        doc.add_list_item(t, parent=lst, prov=prov(3))
    return doc


def headingless_doc(pages: int = 4) -> DoclingDocument:
    doc = DoclingDocument(name="議事録")
    for p in range(1, pages + 1):
        doc.add_page(page_no=p, size=Size(width=600, height=800))
        doc.add_text(DocItemLabel.TEXT, f"{p} ページ目の本文。" * 4, prov=prov(p))
    return doc


def cross_page_table_doc(cols_b: int = 3, caption_b: bool = False) -> DoclingDocument:
    """ページをまたぐ表（2 ページ目の続きにヘッダ行が無い）。"""
    doc = DoclingDocument(name="点検台帳")
    for p in (1, 2):
        doc.add_page(page_no=p, size=Size(width=600, height=800))
    doc.add_heading("点検表", level=1, prov=prov(1))
    a, pa = table([["設備ID", "判定", "注記"], ["MX-11", "監視", "N1"], ["MX-14", "再点検", "N7"]], 1)
    doc.add_table(data=a, prov=pa)
    rows_b = [["MX-17", "停止候補", "N9"], ["MX-21", "監視", "N2"]]
    b, pb = table([r[:cols_b] for r in rows_b], 2, header=False)
    tb = doc.add_table(data=b, prov=pb)
    if caption_b:
        tb.captions.append(doc.add_text(DocItemLabel.CAPTION, "表2: 別の表", prov=prov(2)).get_ref())
    doc.add_text(DocItemLabel.TEXT, "MX-17 は即時停止を推奨する。", prov=prov(2))
    return doc
