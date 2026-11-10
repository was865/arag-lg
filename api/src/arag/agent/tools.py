"""エージェントのツール（specs/005-agent R14）。中身は ops.py。"""

from typing import Any

from langchain.tools import ToolRuntime, tool

from arag.agent.calc import CalcError, evaluate
from arag.agent.context import RunContext
from arag.agent.ops import op_get_outline, op_keyword_search, op_list_documents, op_read_section, op_search

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


TOOLS = [search, keyword_search, list_documents, get_outline, read_section, calculate]

LABELS = {
    "search": ("資料を検索", "検索しています"),
    "keyword_search": ("キーワード検索", "完全一致で探しています"),
    "list_documents": ("文書の一覧", "文書を確認しています"),
    "get_outline": ("章立てを見る", "章立てを確認しています"),
    "read_section": ("章を読む", "本文を読んでいます"),
    "calculate": ("計算", "計算しています"),
}
