"""社内システム（MCP）のツールをエージェントに組み込む（specs/032 design §4）。

登録したツールの説明と入力の型から LangChain のツールを作り、呼び出しを包む:
利用者の身元・待ち時間と回数の上限・結果の切り詰め・権限が無いという返事・出典の登録・データの囲み。
システムが行ったことは、すべてシステムの処理（name="system"）として記録に出す（R24）。
"""

import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from langchain.tools import ToolRuntime
from langchain_core.tools import BaseTool, StructuredTool
from sqlalchemy.ext.asyncio import AsyncSession

from arag.agent.context import McpRun, RunContext
from arag.agent.domain.citations import _attr, _body
from arag.agent.steps import record_system
from arag.mcp.client import (
    Caller,
    McpAuthError,
    McpError,
    McpTimeout,
    auth_headers,
    call_tool,
    ping,
)
from arag.mcp.registry import ToolSpec, usable_server_ids, user_departments
from arag.secrets import SecretBox

# システムの処理の種類（記録の input.kind）と画面の名前
REMOVE_LABELS = {
    "mcp_off": "社内システムを使わない設定",
    "mcp_filtered": "使える範囲の外",
    "mcp_unavailable": "社内システムが応答しない",
}
HEALTH_TTL_SEC = 30.0

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
    # 何をどう呼んだか（画面の「詳細」で技術者が確かめる。specs/036 R1・R2）
    meta = ctx.table_outputs[call_id] = {"server": server, "tool": spec.name, "args": args}
    try:
        res = await call_tool(ep, auth_headers(ep, m.caller, m.identity_key), spec.name, args, limit)
    except McpError as e:
        meta["rtt_ms"] = round((time.perf_counter() - t0) * 1000)
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
    meta["rtt_ms"] = round((time.perf_counter() - t0) * 1000)
    data = res.data
    if data is not None and isinstance(data.get("trace"), dict):
        meta["trace"] = data["trace"]
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
    meta.update(
        {
            "system": label,
            "columns": cols,
            "rows": rows[:20],
            "total": total,
            "fetched_at": fetched,
            "basis": basis,
            "n": n,
            **({"trace": trace} if trace else {}),
        }
    )
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
