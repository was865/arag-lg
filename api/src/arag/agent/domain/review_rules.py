"""最終回答の下書きの確認（差し戻し）の規則（specs/026 ④・031・032・037 R8〜R10）。

規則の層: LangChain のメッセージではなく、このターンを写した値（Draft）を受け取る。
規則は RULES に並べた順に確かめ、最初に当てはまった 1 つで差し戻す。種類を足すときは RULES に 1 行足す。
理由の裏付け（reason）は補助モデルを呼ぶので、並びの外（middleware.reason_review）で確かめる。
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Collection
from dataclasses import dataclass, field
from functools import cached_property
from typing import TYPE_CHECKING

from arag.agent.domain.numbers import NumberCheck, check_numbers
from arag.agent.domain.system_questions import (
    SYSTEM_GAP_NOTE,
    asks_current,
    current_note,
    missed_systems,
    system_missed_note,
    touches_systems,
)
from arag.agent.domain.tool_output import ToolOutput

if TYPE_CHECKING:
    from arag.agent.context import McpRun, Primer
    from arag.agent.domain.citations import CitationRegistry

# 差し戻しの依頼に添える（書き直しで出典番号が落ちて引用が付かなくなるのを防ぐ）。
# 「[n]」と書くと小さいモデルがそのまま写すので、実際の数字の例で示す
KEEP_CITATIONS = "書き直すときも、根拠にした資料の出典番号（[3] など、実際の番号）を残してください。"
# 下書きが「資料に無い」「確認が必要」などと調べ残しを認めているか（日本語・英語）
GAP = re.compile(
    r"記載(されていない|されていません|がない|がありません|はありません)|見つかりません|見つからな|見当たりません|見当たらな|不明|"
    r"確認(することは|することが|が|は)?でき(ません|ない|なかった)|"
    r"分かりません|わかりません|確認(する|が)必要|情報(が)?不足|計算(することは|は)?でき(ません|ない)|"
    r"特定(することは|することが|は)?でき(ません|ない)|答え(することは|することが|ることは|ることが)?でき(ません|ない)|"
    r"not (mentioned|found|available|specified)|no information|could not find|unknown",
    re.IGNORECASE,
)
GAP_NOTE = (
    "この下書きには、資料で確かめられていない点があります。回答する前に、まだ調べていない資料"
    "（台帳・一覧・記録・議事録・規程など、その点が書かれていそうな種類）を、"
    "その点に絞った語で search してください。"
    "数の計算が要るなら、値をそろえてから calculate で計算してください。"
    "調べても見つからない点だけを、見つからないと書いてください。"
    # 理由・因果を尋ねる質問で、別の資料の事実をつないで理由を作らない（specs/031 R9。KG-2 の廃止の理由）
    "調べても書かれていなければ、下書きの「書かれていない」はそのまま残してください。"
    "別々の資料の事実をつないで、資料に書かれていない理由・因果を作らないでください"
    "（関連しそうな事実を添えるときは、推測だと明記する）。" + KEEP_CITATIONS
)
# 省略されたツールの結果（章立ての中略・read_document の打ち切り）を読まずに「分からない」と答えた下書き
OMITTED_GAP = re.compile(GAP.pattern + r"|表示されていません|省略されて", re.IGNORECASE)
OMITTED_NOTE = (
    "この下書きは答えを「分からない」としていますが、このターンのツールの結果の一部が省略されたままです"
    "（章立ての「中略」や、read_document の「長いため先頭の〜節まで」）。"
    "省略された部分を読んでから答えてください: 章立ては get_outline に start（中略の最初の番号）を渡す、"
    "文書の中の目次の節や該当の章は read_section で読む。"
    "「最後の章」「付録」のように場所で尋ねられたら、末尾の節を確かめる。" + KEEP_CITATIONS
)
# モデル自身の検索がこの回数を超えていれば、調べ尽くしたとみなす（システムの最初の検索は数えない）
GAP_REVIEW_MAX_OWN_SEARCHES = 1
SEARCH_TOOLS = {"search", "keyword_search"}
TABLE_NOTE = (
    "この質問は、表の行を条件で選ぶ・数える・集計する必要があります。目で比べたり暗算したりすると誤ります。"
    "回答する前に table_query を使ってください（source に表のある資料の出典番号、where に行の条件、"
    "必要なら compute に行ごとの計算式）。その結果どおりに答えてください。" + KEEP_CITATIONS
)
NUMBER_NOTE = (
    "この下書きの数字 {numbers} は、資料にも計算結果にも見当たりません。"
    "資料の値はそのまま書き写してください。計算した値なら calculate か table_query で計算し直してください。"
    "資料に無い数字は書かないでください。" + KEEP_CITATIONS
)
STRUCTURE_NOTE = (
    "この下書きの章の見出し（{titles}）は、資料に見当たりません。章の構成は、get_outline か、文書の中の"
    "目次の節を read_section で読んで確かめ、資料に書かれたとおりの見出しだけを書いてください。"
    + KEEP_CITATIONS
)
# 資料の中の表の行（Markdown）
_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$\n\s*\|[\s:\-|]+\|\s*$", re.MULTILINE)
# 件数（「14 件」「50件」）と、同じ文の出典の印
_COUNT = re.compile(r"\d[\d,]*\s*件")
_SENTENCE = re.compile(r"[^。\n]+")
_MARK_N = re.compile(r"\[(\d+)\]")
# 回答に書いた「第N章: 見出し」（区切りの後に見出しが続くもの。「第1章と第2章」は見出しではない）
_CHAPTER = re.compile(r"第\s*(\d+)\s*章\s*\**\s*(?:[>＞:：\-—・|]\s*|\s+)\**\s*([^\n\[［（(]+)")


@dataclass(frozen=True, slots=True)
class Review:
    """下書きを差し戻す理由。kind は記録と画面で種類を見分けるのに使う。"""

    kind: str
    trigger: str
    note: str
    label: str


@dataclass(frozen=True)
class ToolResult:
    """このターンのツールの結果 1 件。"""

    name: str
    text: str
    ok: bool = True
    out: ToolOutput = field(default_factory=lambda: ToolOutput(""))
    # 社内システム（MCP）のツールか
    mcp: bool = False


@dataclass
class Draft:
    """確認に渡す、このターンの写し（middleware がメッセージと実行文脈から作る）。"""

    answer: str
    # 利用者の質問（画像の説明を足す前。無ければこのターンの最初の発言）
    question: str
    results: list[ToolResult]
    registry: CitationRegistry
    primer: Primer | None = None
    primer_searches: int = 0
    mcp: McpRun | None = None
    # このターンに呼んだ社内システムのツール（要約で結果が消えても数える）
    mcp_called: set[str] = field(default_factory=set)
    # 数字を照合するか（雑談・一般知識で補ってよい設定では照合しない）
    check_numbers: bool = False
    # 数字の照合で資料と並べて見る文（質問・今日の日付）
    number_sources: list[str] = field(default_factory=list)

    @cached_property
    def materials(self) -> list[str]:
        """このターンにモデルへ渡した資料（ツールの結果と最初の検索結果）。"""
        out = [r.text for r in self.results if r.ok]
        if self.primer and self.primer.text:
            out.append(self.primer.text)
        return out

    @property
    def own_searches(self) -> int:
        return sum(1 for r in self.results if r.name in SEARCH_TOOLS)

    @property
    def searches(self) -> int:
        """このターンの検索の回数（システムが最初に行った分を含む）。"""
        return self.own_searches + self.primer_searches

    @property
    def weak(self) -> bool:
        """最初の検索が 0 件・関連度の低い資料だけ（資料に無い質問らしい）。"""
        return self.primer is not None and self.primer.weak

    @property
    def omitted(self) -> bool:
        """ツールの結果か最初の検索の結果に、省略した部分があるか。"""
        if self.primer is not None and self.primer.omitted:
            return True
        return any(r.out.omitted for r in self.results)

    @cached_property
    def current(self) -> bool:
        """今の値・社内システムにある記録を問う質問か。"""
        return self.mcp is not None and asks_current(self.question)

    @cached_property
    def checked(self) -> bool:
        """社内システムを（失敗せずに）確かめたか。"""
        return any(r.mcp and r.ok for r in self.results)

    @cached_property
    def numbers(self) -> NumberCheck:
        return check_numbers(self.answer, [*self.materials, *self.number_sources])


def counts_from_documents(registry: CitationRegistry, answer: str) -> bool:
    """件数を書いた文に文書の出典が付いているか（文書の表の行を目で数えた件数。3100 の試走）。"""
    for sentence in _SENTENCE.findall(answer):
        if not _COUNT.search(sentence):
            continue
        for n in _MARK_N.findall(sentence):
            cited = registry.get(int(n))
            if cited is not None and cited.kind != "system":
                return True
    return False


def _flat(s: str) -> str:
    return re.sub(r"[\s*|_`]+", "", unicodedata.normalize("NFKC", s)).lower()


def ungrounded_chapters(answer: str, materials: list[str]) -> list[str]:
    """回答の「第N章: 見出し」のうち、見出しが資料に無いもの（specs/031 T17）。"""
    pool = _flat("\n".join(materials))
    out: list[str] = []
    for m in _CHAPTER.finditer(answer):
        title = m.group(2).strip().strip("*").strip()
        key = _flat(title)[:10]
        if len(key) >= 3 and key not in pool:
            out.append(f"第{m.group(1)}章 {title}")
    return out


# ── 規則（当てはまれば (きっかけ, 依頼の文)） ──

Found = tuple[str, str] | None


def _omitted(d: Draft) -> Found:
    # 章立ての中略・読み切れなかった文書を読まずに「分からない」と答えない（specs/031 R5）
    if (m := OMITTED_GAP.search(d.answer)) and d.omitted:
        return m.group(0), OMITTED_NOTE
    return None


def _current(d: Draft) -> Found:
    # 今の値を問われたのに、ある時点の文書だけで答えた（specs/032 R15）
    if d.current and d.mcp is not None and d.mcp.usable and not d.checked:
        return "今の値を社内システムで確かめていない", current_note(d.mcp.down, review=True)
    return None


def _system_missed(d: Draft) -> Found:
    # 複数のシステムにまたがる質問で、呼んでいないシステムにしか無い記録（内線など）を文書の値で答えた
    if not (d.checked and d.mcp is not None and d.mcp.usable):
        return None
    if missed := missed_systems(d.question, d.mcp, d.mcp_called):
        why = "・".join(f"{label}の {tool}（{term}）" for label, tool, term in missed) + "を確かめていない"
        return why, system_missed_note(missed)
    return None


def _system_gap(d: Draft) -> Found:
    # 文書に無いと答えた（最初の検索が弱くても）: 社内システムに記録があるかもしれない（specs/032 R15）
    if d.mcp is None or not d.mcp.usable or d.checked:
        return None
    if (m := GAP.search(d.answer)) and touches_systems(d.question, d.mcp):
        return m.group(0), SYSTEM_GAP_NOTE.format(catalog=d.mcp.catalog)
    return None


def _gap(d: Draft) -> Found:
    # 複数の資料を照合する質問で、小さいモデルは 1 回の検索だけで「資料に無い」と答えがち
    if d.weak or not d.searches or d.own_searches > GAP_REVIEW_MAX_OWN_SEARCHES:
        return None
    if m := GAP.search(d.answer):
        return m.group(0), GAP_NOTE
    return None


def _table(d: Draft) -> Found:
    # 表の行を目で比べると誤る（在庫 4・発注点 4 を「下回る」と答えるなど）
    if d.primer is None or not d.primer.table:
        return None
    # 今の値を社内システムで確かめた回答では、文書の表は時点の比較に添えるだけなので計算させない。
    # ただし文書の表から件数を数えて書いたら数え直させる（検索で拾った行だけを数えて少なく答える）
    if d.current and d.checked and not counts_from_documents(d.registry, d.answer):
        return None
    if any(r.name == "table_query" for r in d.results):
        return None
    if any(_TABLE_ROW.search(t) for t in d.materials):
        return "表の集計を計算していない", TABLE_NOTE
    return None


def _structure(d: Draft) -> Found:
    # 資料に無い章の見出しを作った（目次を見ずに、検索で拾った見出しから章立てを組み立てた。T17）
    if made := ungrounded_chapters(d.answer, d.materials):
        shown = "・".join(made[:5])
        return f"資料に無い章の見出し {shown}", STRUCTURE_NOTE.format(titles=shown)
    return None


def _numbers(d: Draft) -> Found:
    if d.check_numbers and (missing := d.numbers.missing):
        shown = "・".join(missing[:8])
        return f"資料に無い数字 {shown}", NUMBER_NOTE.format(numbers=shown)
    return None


@dataclass(frozen=True)
class ReviewRule:
    kind: str
    label: str
    check: Callable[[Draft], Found]


RULES: tuple[ReviewRule, ...] = (
    ReviewRule("omitted", "省略の読み残し", _omitted),
    ReviewRule("current", "今の値の確認", _current),
    ReviewRule("system_missed", "残りのシステムの確認", _system_missed),
    ReviewRule("system_gap", "社内システムの確認", _system_gap),
    ReviewRule("gap", "調べ残しの見直し", _gap),
    ReviewRule("table", "表の集計の確認", _table),
    ReviewRule("structure", "章の見出しの確認", _structure),
    ReviewRule("numbers", "数字の確認", _numbers),
)
REASON = "reason"
REASON_LABEL = "理由の裏付けの確認"
# 記録・画面に出す確認の表示名（種類 → 名前）
REVIEW_LABELS: dict[str, str] = {r.kind: r.label for r in RULES} | {REASON: REASON_LABEL}


def pick(draft: Draft, done: Collection[str] = ()) -> Review | None:
    """当てはまる最初の規則で差し戻す。done はこのターンで済んだ種類（種類ごとに 1 度まで）。"""
    for rule in RULES:
        if rule.kind in done:
            continue
        if (found := rule.check(draft)) is not None:
            return Review(rule.kind, found[0], found[1], rule.label)
    return None
