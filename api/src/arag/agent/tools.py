"""エージェントのツール（specs/005-agent R14）。中身は ops.py。"""

from typing import Any

from langchain.tools import ToolRuntime, tool

from arag.agent.calc import CalcError, evaluate
from arag.agent.context import RunContext
from arag.agent.ops import (
    op_get_outline,
    op_keyword_search,
    op_list_documents,
    op_read_section,
    op_search,
    op_table_query,
)

Runtime = ToolRuntime[RunContext]


def _emit(runtime: Runtime) -> Any:
    return runtime.stream_writer


@tool
async def search(query: str, runtime: Runtime, document_ids: list[str] | None = None) -> str:
    """社内文書を意味と語の両方で検索し、関連する箇所を出典番号 [n] 付きで返す。

    Args:
        query: 単独で意味が通る検索文（日本語でも英語でもよい）
        document_ids: 特定の文書に絞るときの文書 ID か出典番号（例 ["3"]）
    """
    return await op_search(
        runtime.context, _emit(runtime), runtime.tool_call_id or "", query, document_ids=document_ids
    )


@tool
async def keyword_search(terms: list[str], runtime: Runtime, document_ids: list[str] | None = None) -> str:
    """型番・条項番号・製品名など、すべての語をそのまま含む箇所を探す（完全一致）。

    内容（「異常時の対応」「保存期間」など）は search で調べる。terms に説明的な語句を入れると一致しにくい。

    Args:
        terms: 資料にそのまま出る語だけ（例 ["MX-17"]、["第12条"]、["MX-17", "N9"]）
        document_ids: 特定の文書に絞るときの文書 ID か出典番号
    """
    return await op_keyword_search(
        runtime.context, _emit(runtime), runtime.tool_call_id or "", terms, document_ids=document_ids
    )


@tool
async def list_documents(runtime: Runtime, query: str | None = None) -> str:
    """検索範囲の文書の一覧（名前・ID・ページ数・登録日）。どんな文書があるか分からないときに使う。

    Args:
        query: 文書名の一部で絞り込む（省略可）
    """
    return await op_list_documents(runtime.context, query)


@tool
async def get_outline(document: str, runtime: Runtime) -> str:
    """文書の章立て（見出しの階層・ページ・セクション ID）を返す。

    Args:
        document: 文書 ID か出典番号（例 "3"）
    """
    return await op_get_outline(runtime.context, document)


@tool
async def read_section(section: str, runtime: Runtime) -> str:
    """章（セクション）の本文を読む。検索で見つけた箇所の前後や、章全体を確かめるときに使う。

    Args:
        section: セクション ID（get_outline の結果）か出典番号（その箇所を含む章を読む）
    """
    return await op_read_section(runtime.context, section)


@tool
async def table_query(
    source: str, runtime: Runtime, where: str = "", compute: str = "", table: int = 1
) -> str:
    """資料の表から、条件に合う行を選び、行数と合計を正確に求める。表の行を選ぶ・数える・合計するときは、
    目で比べたり暗算したりせず、必ずこれを使う。

    Args:
        source: 表のある資料の出典番号（例 "1"）かセクション ID
        where: 行の条件。列名と比較で書く（例 "在庫 < 発注点"、"単価 >= 10000 and \"HP-300\" in 適用機種"）。
            省略すると全行
        compute: 行ごとに計算する式（例 "(発注点 - 在庫) * 単価"）。結果と合計・平均が返る。
            集計関数 max(列)・min(列)・sum(式)・avg(式)・count() も使え、該当行全体の値が返る
            （max / min はその値の行も）。省略可
        table: 資料に表が複数あるときの番号（1 から）
    """
    return await op_table_query(runtime.context, source, where, compute, table, emit=_emit(runtime))


@tool
async def calculate(expression: str) -> str:
    """数の計算をする。資料の値の合計・差・平均・割合などは、暗算せずに必ずこれで計算してから答える。

    Args:
        expression: 計算式。数・+ - * / ( ) と sum・avg・min・max・round・abs が使える
            （例 "30 + 25 + 80"、"(1200 - 950) / 950 * 100"、"round(avg(3, 4, 8), 1)"）
    """
    try:
        return f"{expression} = {evaluate(expression)}"
    except CalcError as e:
        return f"計算できませんでした: {e}"


TOOLS = [search, keyword_search, list_documents, get_outline, read_section, table_query, calculate]

LABELS = {
    "search": ("検索", "検索中"),
    "keyword_search": ("キーワード検索", "キーワードで検索中"),
    "list_documents": ("文書一覧", "文書一覧を取得中"),
    "get_outline": ("目次を取得", "目次を取得中"),
    "read_section": ("セクションを読む", "本文を読み込み中"),
    "table_query": ("表の集計", "表を集計中"),
    "calculate": ("計算", "計算中"),
}
