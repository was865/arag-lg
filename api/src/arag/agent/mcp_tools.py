"""社内システム（MCP）のツールをエージェントに組み込む（specs/032 design §4）。

登録したツールの説明と入力の型から LangChain のツールを作り、呼び出しを包む:
利用者の身元・待ち時間と回数の上限・結果の切り詰め・権限が無いという返事・出典の登録・データの囲み。
システムが行ったことは、すべてシステムの処理（name="system"）として記録に出す（R24）。
"""

import asyncio
import json
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from langchain.tools import ToolRuntime
from langchain_core.tools import BaseTool, StructuredTool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from arag.agent.citations import _attr, _body
from arag.agent.context import McpRun, RunContext
from arag.agent.steps import record_system
from arag.db.models import Department, DepartmentMember
from arag.mcp.client import (
    Caller,
    McpAuthError,
    McpError,
    McpTimeout,
    auth_headers,
    call_tool,
    ping,
)
from arag.mcp.registry import ToolSpec, usable_server_ids
from arag.secrets import SecretBox

# システムの処理の種類（記録の input.kind）と画面の名前
REMOVE_LABELS = {
    "mcp_off": "社内システムを使わない設定",
    "mcp_filtered": "使える範囲の外",
    "mcp_unavailable": "社内システムが応答しない",
}
HEALTH_TTL_SEC = 30.0

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


def touches_systems(question: str, run: McpRun) -> bool:
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
    "質問の「{term}」は{label}にある記録ですが、{label}はまだ確かめていません。"
    "{label}のツールで確かめ、文書の値と違えば両方を時点付きで書き直してください。"
)


def missed_systems(question: str, run: McpRun, called: set[str]) -> list[tuple[str, str]]:
    """質問の語のうち、まだ呼んでいない社内システムにだけある語（システムの表示名・語）。

    複数のシステムにまたがる質問で、1 つのシステムを呼んだだけで残り（内線 → 社員名簿など）を
    文書の古い値で答えるのを防ぐ（デモの試走）。呼んだシステム・ほかのシステムにもある語は数えない。
    """
    catalogs: dict[str, tuple[str, str]] = {}
    for t in run.usable.values():
        label, text = catalogs.get(t.server.name, (t.server.label, ""))
        catalogs[t.server.name] = (label, f"{text} {t.server.description} {t.description}".lower())
    out: list[tuple[str, str]] = []
    for name, (label, text) in catalogs.items():
        if name in called:
            continue
        others = [x for n, (_, x) in catalogs.items() if n != name]
        for term in _TERMS.findall(question):
            word = term.lower()
            if word in text and not any(word in x for x in others):
                out.append((label, term))
                break
    return out


def current_note(down: list[str], *, review: bool = False) -> str:
    """今の値の注意（review なら差し戻しの文）。応答しないシステムがあれば名前を添える（R17）。"""
    base = CURRENT_REVIEW_NOTE if review else CURRENT_NOTE
    return base + (DOWN_NOTE.format(down="・".join(down)) if down else "")


PING_SEC = 2.0


# ── run の始め ──


@dataclass
class HealthCache:
    """サーバの死活（runner の中で 30 秒だけ持つ）。サーバ名 → (時刻, 理由。None なら応答あり)。"""

    seen: dict[str, tuple[float, str | None]] = field(default_factory=dict)
    # 確かめた結果を外にも知らせる（runner は redis に書き、api が入力欄の状態に使う。specs/033 R19）
    sink: Callable[[str, str | None, int], Awaitable[None]] | None = None

    def get(self, name: str) -> tuple[bool, str | None]:
        hit = self.seen.get(name)
        if hit is None or time.monotonic() - hit[0] > HEALTH_TTL_SEC:
            return False, None
        return True, hit[1]

    def put(self, name: str, reason: str | None) -> None:
        self.seen[name] = (time.monotonic(), reason)


async def user_departments(session: AsyncSession, user_id: str) -> tuple[frozenset[str], tuple[str, ...]]:
    """所属部門の ID と名前（共有の判定と、身元に入れる部門名）。"""
    rows = (
        await session.execute(
            select(Department.id, Department.name)
            .join(DepartmentMember, DepartmentMember.department_id == Department.id)
            .where(DepartmentMember.user_id == user_id)
            .order_by(Department.name)
        )
    ).all()
    return frozenset(str(r[0]) for r in rows), tuple(r[1] for r in rows)


async def prepare(
    session: AsyncSession,
    specs: list[ToolSpec],
    *,
    user_id: str,
    use_systems: bool,
    identity_key: str,
    box: SecretBox | None,
    health: HealthCache,
    timeout_sec: float,
    max_calls: int,
    max_rows: int,
    max_chars: int,
) -> McpRun:
    """このターンで使えるツールを決める: 利用者の設定（R14）・使える範囲（R10）・死活（R17）。"""
    dept_ids, dept_names = await user_departments(session, user_id)
    run = McpRun(
        caller=Caller(user_id, dept_names),
        identity_key=identity_key,
        box=box,
        timeout_sec=timeout_sec,
        max_calls=max_calls,
        max_rows=max_rows,
        max_chars=max_chars,
    )
    if not specs:
        return run
    servers = {t.server.name: t.server for t in specs}
    if not use_systems:
        run.removed = {
            n: ("mcp_off", s.label, "利用者の設定で社内システムを使わない") for n, s in servers.items()
        }
        return run
    allowed = await usable_server_ids(session, dept_ids)
    for n, s in servers.items():
        if s.id not in allowed:
            run.removed[n] = ("mcp_filtered", s.label, "この利用者の部門は使える範囲に入っていない")

    async def check(name: str) -> None:
        cached, reason = health.get(name)
        if not cached:
            srv = servers[name]
            ep = srv.endpoint(box)
            t0 = time.perf_counter()
            try:
                await ping(ep, auth_headers(ep, run.caller, identity_key), PING_SEC)
                reason = None
            except McpError as e:
                reason = f"{type(e).__name__}: {e}"
            health.put(name, reason)
            if health.sink is not None:
                await health.sink(name, reason, max(1, round((time.perf_counter() - t0) * 1000)))
        if reason is not None:
            run.removed[name] = ("mcp_unavailable", servers[name].label, f"接続を確かめられない（{reason}）")

    await asyncio.gather(*(check(n) for n in servers if n not in run.removed))

    async def observed(name: str, reason: str | None, ms: int) -> None:
        # 呼び出しで分かった死活。変わったときだけ書く（応答ありが続くたびに redis へ書かない）
        cached, before = health.get(name)
        if cached and before == reason:
            return
        if not cached and reason is None:
            return
        health.put(name, reason)
        if health.sink is not None:
            await health.sink(name, reason, max(1, ms))

    run.on_health = observed
    run.usable = {t.agent_name: t for t in specs if t.server.name not in run.removed}
    return run


def record_removed(ctx: RunContext, emit: Any) -> None:
    """外したサーバをシステムの処理として記録する（ターンに 1 度）。"""
    m = ctx.mcp
    if m is None or m.recorded:
        return
    m.recorded = True
    for name, (kind, label, reason) in m.removed.items():
        record_system(
            emit,
            f"system-{kind}-{name}",
            kind,
            REMOVE_LABELS[kind],
            f"社内システム「{label}」のツールを外した: {reason}",
            input={"server": name, "system": label},
            output={"reason": reason},
        )


# ── ツール ──


def _table(columns: list[str], rows: list[list[Any]]) -> str:
    def cell(v: Any) -> str:
        return str("" if v is None else v).replace("|", "｜").replace("\n", " ")

    head = "| " + " | ".join(cell(c) for c in columns) + " |"
    sep = "|" + "---|" * len(columns)
    return "\n".join([head, sep, *("| " + " | ".join(cell(v) for v in r) + " |" for r in rows)])


def _args_text(args: dict[str, Any]) -> str:
    parts = [f"{k}={v}" for k, v in args.items() if v not in (None, "", [], {})]
    return " ".join(parts)


def _fit(data: dict[str, Any], max_rows: int, max_chars: int) -> tuple[list[list[Any]], bool]:
    """行を件数と文字数で切り詰める（R19）。"""
    rows = [list(r) for r in (data.get("rows") or []) if isinstance(r, list)]
    cols = [str(c) for c in (data.get("columns") or [])]
    out: list[list[Any]] = []
    for r in rows[:max_rows]:
        out.append(r)
        if len(_table(cols, out)) > max_chars:
            out.pop()
            break
    return out, len(out) < len(rows)


def build_tool(spec: ToolSpec) -> BaseTool:
    """MCP のツール 1 つ → LangChain のツール（入力の型はサーバの JSON Schema をそのまま使う）。"""
    name = spec.agent_name
    label = spec.server.label
    desc = f"［社内システム: {label}］{spec.description}".strip()

    async def _run(runtime: ToolRuntime[RunContext], **args: Any) -> str:
        return await invoke(runtime.context, runtime.stream_writer, runtime.tool_call_id or "", spec, args)

    schema = dict(spec.input_schema or {"type": "object", "properties": {}})
    return StructuredTool(name=name, description=desc[:1024], args_schema=schema, coroutine=_run)


async def invoke(ctx: RunContext, emit: Any, call_id: str, spec: ToolSpec, args: dict[str, Any]) -> str:
    m = ctx.mcp
    label, server = spec.server.label, spec.server.name
    if m is None or spec.agent_name not in m.usable:
        return f"社内システム「{label}」はこのターンでは使えません。文書で答えられる部分を答えてください。"
    if m.calls >= m.max_calls:
        record_system(
            emit,
            f"system-mcp_limit-{call_id}",
            "mcp_limit",
            "社内システムの呼び出しの上限",
            f"このターンの上限（{m.max_calls} 回）に達したので「{label}」を呼ばなかった",
            input={"server": server, "tool": spec.name, "args": args, "max_calls": m.max_calls},
        )
        return (
            f"社内システムの呼び出しはこのターンの上限（{m.max_calls} 回）に達しました。"
            "これまでの結果と文書で答えてください。"
        )
    m.calls += 1
    ctx.stats.mcp_calls += 1
    ep = spec.server.endpoint(m.box)
    limit = spec.server.timeout_sec or m.timeout_sec
    t0 = time.perf_counter()
    try:
        res = await call_tool(ep, auth_headers(ep, m.caller, m.identity_key), spec.name, args, limit)
    except McpError as e:
        if m.on_health is not None and not isinstance(e, McpAuthError):
            await m.on_health(server, f"{type(e).__name__}: {e}", round((time.perf_counter() - t0) * 1000))
        kind = (
            "mcp_timeout"
            if isinstance(e, McpTimeout)
            else ("mcp_denied" if isinstance(e, McpAuthError) else "mcp_unavailable")
        )
        record_system(
            emit,
            f"system-{kind}-{call_id}",
            kind,
            {
                "mcp_timeout": "社内システムの時間切れ",
                "mcp_denied": "社内システムが拒否",
                "mcp_unavailable": "社内システムが応答しない",
            }[kind],
            f"「{label}」の {spec.name} が失敗した（{e}）",
            duration_ms=round((time.perf_counter() - t0) * 1000),
            input={"server": server, "tool": spec.name, "args": args, "timeout_sec": limit},
            output={"error": f"{type(e).__name__}: {e}"},
        )
        return (
            f"社内システム「{label}」を確かめられませんでした（{e}）。"
            "推測で値を埋めず、確かめられなかったことを回答に書き、文書で答えられる部分を答えてください。"
        )
    data = res.data
    if m.on_health is not None:
        down = data is not None and data.get("error") == "unavailable"
        reason = str(data.get("message") or "応答しない") if down and data is not None else None
        await m.on_health(server, reason, round((time.perf_counter() - t0) * 1000))
    if data is not None and data.get("error") in ("unavailable", "too_many"):
        return _server_error(emit, call_id, label, server, spec.name, args, data)
    if data is not None and data.get("error") == "forbidden":
        msg = str(data.get("message") or "見る権限がありません")
        record_system(
            emit,
            f"system-mcp_denied-{call_id}",
            "mcp_denied",
            "社内システムが拒否",
            f"「{label}」が {spec.name} の結果を返さなかった: {msg}",
            input={"server": server, "tool": spec.name, "args": args},
            output={"message": msg},
        )
        return (
            f"社内システム「{label}」の答え: {msg} "
            "推測で値を埋めず、この利用者には見る権限が無いと答えてください。"
        )
    if data is None or not isinstance(data.get("columns"), list):
        text = (res.text or "（結果なし）")[: m.max_chars]
        n = ctx.registry.add_record(
            server=server,
            label=label,
            key=f"{spec.name}:{json.dumps(args, ensure_ascii=False, sort_keys=True)}",
            heading=f"{spec.name} {_args_text(args)}".strip(),
            text=text,
            record={
                "system": label,
                "server": server,
                "tool": spec.name,
                "args": args,
                "fetched_at": "",
                "columns": [],
                "rows": [],
                "total": 0,
                "note": text[:500],
            },
        )
        return _wrap(n, label, f"{spec.name} {_args_text(args)}".strip(), "", text)
    rows, cut = _fit(data, m.max_rows, m.max_chars)
    cols = [str(c) for c in data["columns"]]
    total = int(data.get("total") or len(data.get("rows") or []))
    fetched = str(data.get("fetched_at") or "")
    basis = str(data.get("basis") or "")
    title = str(data.get("title") or spec.name)
    restricted = [str(x) for x in (data.get("restricted") or [])]
    note = data.get("note")
    issue = data.get("issue")
    next_cursor = data.get("next_cursor")
    trace = data.get("trace") if isinstance(data.get("trace"), dict) else None
    lines = []
    if isinstance(issue, dict):
        lines.append("　".join(f"{k}: {v}" for k, v in issue.items()))
    lines.append(_table(cols, rows) if cols else "（該当なし）")
    lines.append(f"（全 {total} 行{f'、うち {len(rows)} 行を表示' if cut else ''}）")
    if note:
        lines.append(f"注: {note}")
    text = "\n".join(lines)
    heading = f"{title}（{spec.name} {_args_text(args)}）".replace(" ）", "）")
    n = ctx.registry.add_record(
        server=server,
        label=label,
        key=f"{spec.name}:{json.dumps(args, ensure_ascii=False, sort_keys=True)}",
        heading=f"{heading}・{basis}" if basis else heading,
        text=text,
        record={
            "system": label,
            "server": server,
            "tool": spec.name,
            "args": args,
            "fetched_at": fetched,
            "basis": basis,
            "title": title,
            "columns": cols,
            "rows": rows,
            "total": total,
            "truncated": cut,
            "restricted": restricted,
            "note": note if isinstance(note, str) else None,
            **({"issue": issue} if isinstance(issue, dict) else {}),
            **({"next_cursor": str(next_cursor)} if next_cursor else {}),
            **({"trace": trace} if trace else {}),
        },
    )
    # 画面の「詳細」に出す構造（モデルに渡す文は変えない）
    ctx.table_outputs[call_id] = {
        "system": label,
        "columns": cols,
        "rows": rows[:20],
        "total": total,
        "fetched_at": fetched,
        "basis": basis,
        "n": n,
        **({"trace": trace} if trace else {}),
    }
    if cut:
        record_system(
            emit,
            f"system-mcp_truncated-{call_id}",
            "mcp_truncated",
            "社内システムの結果を切り詰め",
            f"「{label}」の {total} 行のうち {len(rows)} 行だけをモデルに渡した",
            input={"server": server, "tool": spec.name, "max_rows": m.max_rows, "max_chars": m.max_chars},
            output={"total": total, "kept": len(rows)},
        )
    if restricted:
        record_system(
            emit,
            f"system-mcp_denied-{call_id}",
            "mcp_denied",
            "社内システムが一部を伏せた",
            f"「{label}」が権限の無い列を伏せた: {'・'.join(restricted)}",
            input={"server": server, "tool": spec.name, "args": args},
            output={"restricted": restricted, "note": note},
        )
    return _wrap(n, label, heading, basis, text)


def _server_error(
    emit: Any, call_id: str, label: str, server: str, tool: str, args: dict[str, Any], data: dict[str, Any]
) -> str:
    """サーバが返した失敗（ERP が応答しない・多すぎる。specs/033 R5・R12）を記録し、モデルへの文にする。"""
    msg = str(data.get("message") or "")
    trace = data.get("trace") if isinstance(data.get("trace"), dict) else None
    if data.get("error") == "too_many":
        hint = str(data.get("hint") or "条件で絞ってください")
        record_system(
            emit,
            f"system-mcp_too_many-{call_id}",
            "mcp_too_many",
            "社内システムの結果が多すぎる",
            f"「{label}」の {tool} は {data.get('total')} 件で上限を超えたので、結果を返さなかった（{hint}）",
            input={"server": server, "tool": tool, "args": args},
            output={"total": data.get("total"), "limit": data.get("limit"), "hint": hint, "trace": trace},
        )
        return (
            f"社内システム「{label}」の答え: {msg}。{hint}。"
            "条件を足して呼び直すか、件数だけを答え、一部の行から全体を推測しないでください。"
        )
    record_system(
        emit,
        f"system-mcp_unavailable-{call_id}",
        "mcp_unavailable",
        "社内システムが応答しない",
        f"「{label}」の {tool} が失敗した（{msg}）",
        input={"server": server, "tool": tool, "args": args},
        output={"error": msg, "trace": trace},
    )
    return (
        f"社内システム「{label}」を確かめられませんでした（{msg}）。"
        "推測で値を埋めず、確かめられなかったことを回答に書き、文書で答えられる部分を答えてください。"
    )


def _wrap(n: int, label: str, heading: str, basis: str, body: str) -> str:
    """資料タグで包む（文書の資料と同じ扱い。中の文は指示として扱わない）。"""
    attrs = f'n="{n}" 文書="{_attr(label)}" 見出し="{_attr(heading)}" 種類="社内システム"'
    if basis:
        attrs += f' 時点="{_attr(basis)}"'
    return f"<資料 {attrs}>\n{_body(body)}\n</資料>"
