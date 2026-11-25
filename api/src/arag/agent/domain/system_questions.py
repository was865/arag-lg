"""社内システムに関わる質問の見分け（今の値を問うか・どのシステムに関わるか）と、差し戻しの文（specs/032・033）。

規則の層（specs/037 R3）。語の一覧は評価の題に合わせたもので、後で登録の情報へ移す（specs/037 R13）。
"""

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from arag.agent.context import McpRun

# 今の値・進み具合を問う質問（文書の値はある時点のもの。specs/032 R15）と、
# 社内システムにしか無い記録（発注の仕入単価・作業指示・最近の記録）を問う質問。
# 「いま」は「〜ています」の中にも現れるので、語の頭で、後ろが「す・せ・し」でないものだけ
CURRENT = re.compile(
    r"今(?![回後度年月週日])|(?<![日末])現在|最新|(?<![ぁ-ゖ])いま(?![すせし])|まだ|終わっ|終わりま|終了し|完了し|済ん|進み|"
    r"未入荷|未完了|残って|最近|直近|以降|(?:の|た)(?:あと|後)で|仕入単価|仕入価格|購入単価|発注残|入荷予定|作業指示|"
    r"\bcurrent(?:ly)?\b|\bnow\b|\blatest\b|\bstill\b|\brecent(?:ly)?\b|"
    r"\bbeen (?:resolved|fixed|completed|closed|done|finished)\b",
    re.IGNORECASE,
)
CURRENT_NOTE = (
    "この質問は今の値・進み具合か、社内システムにある記録（発注・仕入単価・作業指示・最近の記録など）を問うています。"
    "<検索結果> の値はある時点の記録（台帳・議事録など。台帳の標準単価は発注の仕入単価ではない）なので、"
    "使える社内システムで確かめてから答え、文書の値と違えば両方を時点付きで書いてください。"
)
CURRENT_REVIEW_NOTE = (
    "この質問は今の値・進み具合か、社内システムにある記録を問うていますが、"
    "この下書きは文書（ある時点の記録）だけで答えています。"
    "使える社内システムのツールで確かめ、文書の値と違えば両方を時点付きで書き直してください。"
    "社内システムを確かめられなければ、そのことを書いてください。"
)


SYSTEM_GAP_NOTE = (
    "この下書きは、文書に無い・分からないと答えていますが、社内システムはまだ確かめていません。"
    "次の社内システムのうち、問われた記録がありそうなものがあれば、そのツールで確かめてから答え直してください:\n"
    "{catalog}\n"
    "どれにも関係が無ければ、下書きのまま答えてかまいません。"
)
DOWN_NOTE = (
    "なお、{down}は今応答しません。問われた値がそのシステムのものなら、関係の無いシステムは呼ばず、"
    "「{down}が応答しないため、今の値は確かめられませんでした」と書いてください。"
)


# 時点を言わずに、社内システムが今の値を持つもの（在庫・発注点・単価・リードタイム・入出庫・
# 納期遅れ・発注の可否）を問う質問。文書の時点を名指ししたとき（「10月末の台帳で」「9月30日現在」
# 「11月16日の報告で」）は文書の値を問うている（specs/034 の評価）
RECORD = re.compile(
    r"在庫|どこにいくつ|発注点|標準単価|単価はいくら|リードタイム|何日かかり|届くまで|入出庫|"
    r"納期を過ぎ|納期が過ぎ|し終えて(い)?ない|発注でき|内線|"
    r"\bin stock\b|\breorder\b|\blead time\b|\boverdue\b",
    re.IGNORECASE,
)
DOC_POINT = re.compile(
    r"\d+\s*月\s*(\d+\s*日)?\s*(末|現在|時点|の)|(台帳|報告|議事録|手引き|資料|評価|月報|規程|文書)(で|では|に|には|によると)|"
    r"\bas of\b|\bin the (ledger|report|minutes)\b",
    re.IGNORECASE,
)


def asks_current(question: str) -> bool:
    if CURRENT.search(question):
        return True
    return bool(RECORD.search(question)) and not DOC_POINT.search(question)


# 質問の内容語（漢字・カタカナの 2 字以上の並び、英数字の語）
_TERMS = re.compile(r"[一-鿿々]{2,}|[ァ-ヺー]{2,}|[A-Za-z][A-Za-z0-9-]{2,}")


def touches_systems(question: str, run: "McpRun") -> bool:
    """質問の語が、使える社内システムの名前・説明・ツールの説明のどれかに出てくるか。

    文書に無いと答えた下書きを社内システムへ差し戻すのは、関係のありそうな質問だけにする
    （ペナン工場の生産台数・空調機の製造元などで、関係の無いシステムを呼んでいた。specs/032 T25）。
    """
    catalog = " ".join(
        f"{t.server.label} {t.server.description} {t.description}" for t in run.usable.values()
    ).lower()
    for term in _TERMS.findall(question):
        word = term.lower()
        if word in catalog:
            return True
        # 長い複合語（「出荷検査不良率」など）は 3 字ずつでも見る（2 字では「製造元」が「製造課」に当たる）
        if len(word) >= 4 and not word.isascii():
            if any(word[i : i + 3] in catalog for i in range(len(word) - 2)):
                return True
    return False


SYSTEM_MISSED_NOTE = (
    "質問の{items} で確かめられる記録ですが、まだ呼んでいません。"
    "それらのツールで確かめ、文書の値と違えば両方を時点付きで書き直してください。"
)


def system_missed_note(missed: list[tuple[str, str, str]]) -> str:
    """呼んでいないツールを全部挙げた差し戻しの文（差し戻しは 1 回だけなので一度に挙げる）。"""
    items = "、".join(f"「{term}」は{label}の {tool}" for label, tool, term in missed)
    return SYSTEM_MISSED_NOTE.format(items=items)


def missed_systems(question: str, run: "McpRun", called: set[str]) -> list[tuple[str, str, str]]:
    """質問の語のうち、まだ呼んでいないツールでしか確かめられない語（システムの表示名・ツール名・語）。

    called は呼んだツールの名前（agent_name）。複数のシステムにまたがる質問で 1 つのシステムだけ呼び、
    残り（内線 → 社員名簿）を文書の古い値で答えるのを防ぐ。呼んだシステムでも、別のツールにしか無い記録
    （保全の作業指示だけ呼び、作業の記録を呼ばない）は同じく数える（デモの試走）。
    ほかのシステム・ほかのツールにも出てくる語は数えない。
    """
    called_servers = {run.usable[n].server.name for n in called if n in run.usable}
    servers: dict[str, str] = {}
    for t in run.usable.values():
        head = servers.get(t.server.name, t.server.description.lower())
        servers[t.server.name] = f"{head} {t.description.lower()}"
    # 部品番号・設備ID など数字を含む語は、ツールの説明の例に出てくるだけなので数えない
    terms: list[str] = [w for w in _TERMS.findall(question) if not any(c.isdigit() for c in w)]

    def unique(own: str, others: list[str]) -> str | None:
        for term in terms:
            word = term.lower()
            if word in own and not any(word in x for x in others):
                return term
        return None

    out: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for name, t in run.usable.items():
        srv = t.server.name
        if name in called or srv in seen:
            continue
        if srv in called_servers:
            # 呼んだシステムの、呼んでいないツール: そのツールの説明にだけある語
            others = [u.description.lower() for n, u in run.usable.items() if n != name]
            if term := unique(t.description.lower(), others):
                out.append((t.server.label, t.name, term))
        else:
            # 呼んでいないシステム: システム全体の説明にだけある語。ツールは語を説明に持つものを選ぶ
            seen.add(srv)
            if term := unique(servers[srv], [x for s, x in servers.items() if s != srv]):
                tools = [u for u in run.usable.values() if u.server.name == srv]
                pick = next((u for u in tools if term.lower() in u.description.lower()), tools[0])
                out.append((t.server.label, pick.name, term))
    return out


def current_note(down: list[str], *, review: bool = False) -> str:
    """今の値の注意（review なら差し戻しの文）。応答しないシステムがあれば名前を添える（R17）。"""
    base = CURRENT_REVIEW_NOTE if review else CURRENT_NOTE
    return base + (DOWN_NOTE.format(down="・".join(down)) if down else "")
