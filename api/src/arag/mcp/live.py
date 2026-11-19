"""社内システムの「今の値」の実感（specs/033 R17・R19・R21、design §6）。

- 最新にする（R17）: 回答の出典の社内システムの記録を、同じ利用者の身元・同じツール・同じ引数で
  呼び直し、前の値との差を返す。呼び直しはメッセージの記録（システムの処理 mcp_refresh）に足す。
  回答の文は書き換えない。
- 接続の状態（R19）: 死活の確認の結果を redis に 30 秒だけ置き（runner と api が書く）、
  利用者が使えるシステムの状態を返す。
- 管理の数字（R21）: ARag 側の記録（メッセージのステップ）から、直近 1 時間の
  呼び出しの数・失敗の率・所要時間を集計する。

作った動きは出さない。返すのは本当の取得の時刻・本当の死活・本当の差だけ。
"""

import json
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from arag.db.models import McpServer, Message
from arag.mcp.client import Caller, McpError, auth_headers, call_tool, ping
from arag.mcp.registry import ServerSpec, server_spec, usable_server_ids
from arag.secrets import SecretBox

HEALTH_KEY = "arag:mcp:health:{}"
HEALTH_TTL_SEC = 30
SLOW_MS = 2000
PING_SEC = 3.0


# ── 接続の状態（R19）──


@dataclass(frozen=True)
class Health:
    ok: bool
    ms: int
    reason: str | None
    at: str

    @property
    def state(self) -> Literal["ok", "slow", "down"]:
        if not self.ok:
            return "down"
        return "slow" if self.ms > SLOW_MS else "ok"


async def put_health(redis: Redis | None, name: str, reason: str | None, ms: int) -> None:
    """死活の確認の結果を共有する（失敗しても回答は止めない）。"""
    if redis is None:
        return
    body = {
        "ok": reason is None,
        "ms": ms,
        "reason": reason,
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    try:
        await redis.set(HEALTH_KEY.format(name), json.dumps(body, ensure_ascii=False), ex=HEALTH_TTL_SEC)
    except Exception:
        return


async def get_health(redis: Redis | None, name: str) -> Health | None:
    if redis is None:
        return None
    try:
        raw = await redis.get(HEALTH_KEY.format(name))
    except Exception:
        return None
    if not raw:
        return None
    d = json.loads(raw)
    return Health(bool(d["ok"]), int(d["ms"]), d.get("reason"), str(d["at"]))


async def check_health(spec: ServerSpec, caller: Caller, identity_key: str, box: SecretBox | None) -> Health:
    ep = spec.endpoint(box)
    t0 = time.perf_counter()
    reason: str | None = None
    try:
        await ping(ep, auth_headers(ep, caller, identity_key), PING_SEC)
    except McpError as e:
        reason = f"{type(e).__name__}: {e}"
    ms = max(1, round((time.perf_counter() - t0) * 1000))
    return Health(reason is None, ms, reason, datetime.now(UTC).isoformat(timespec="seconds"))


async def usable_servers(session: AsyncSession, dept_ids: frozenset[str]) -> list[McpServer]:
    allowed = await usable_server_ids(session, dept_ids)
    rows = (
        await session.execute(select(McpServer).where(McpServer.enabled.is_(True)).order_by(McpServer.label))
    ).scalars()
    return [r for r in rows if r.id in allowed]


# ── 最新にする（R17）──


def _cell(v: Any) -> Any:
    return "" if v is None else v


def diff_records(old: dict[str, Any], new: dict[str, Any]) -> list[dict[str, Any]]:
    """前の値と新しい値の差。行は 1 列目（部品番号・発注番号など）で対応させる。

    戻り値: {key, column, before, after}（列の変化）・
    {key, column: None, change: "added"|"removed"}（行の増減）。
    """
    cols_old = [str(c) for c in old.get("columns") or []]
    cols_new = [str(c) for c in new.get("columns") or []]
    if not cols_old or not cols_new:
        return []
    by_old = {str(r[0]): r for r in old.get("rows") or [] if r}
    by_new = {str(r[0]): r for r in new.get("rows") or [] if r}
    out: list[dict[str, Any]] = []
    for key, row in by_new.items():
        before = by_old.get(key)
        if before is None:
            out.append({"key": key, "column": None, "change": "added"})
            continue
        for j, col in enumerate(cols_new):
            if col not in cols_old:
                continue
            i = cols_old.index(col)
            a = _cell(before[i] if i < len(before) else None)
            b = _cell(row[j] if j < len(row) else None)
            if a != b:
                out.append({"key": key, "column": col, "before": a, "after": b})
    for key in by_old:
        if key not in by_new:
            out.append({"key": key, "column": None, "change": "removed"})
    return out


def section_n(msg: Message, section_id: str) -> int | None:
    """出典の章（社内システムの記録）の引用番号（保存した回答の番号。画面の振り直した番号ではない）。"""
    for k, ref in (msg.citation_map or {}).items():
        if str((ref or {}).get("section_id")) == section_id and str(k).isdigit():
            return int(k)
    return None


def find_record(msg: Message, n: int) -> dict[str, Any] | None:
    """引用番号 n の社内システムの記録（回答のときの値）。"""
    ref = (msg.citation_map or {}).get(str(n))
    if not ref:
        return None
    for src in msg.sources or []:
        for sec in src.get("sections") or []:
            if str(sec.get("id")) == str(ref.get("section_id")) and isinstance(sec.get("record"), dict):
                rec: dict[str, Any] = sec["record"]
                return rec
    return None


def latest_record(msg: Message, n: int) -> dict[str, Any] | None:
    """最後に「最新にする」で取り直した記録（無ければ回答のときの記録）。"""
    for st in reversed(msg.steps or []):
        inp = st.get("input") or {}
        if inp.get("kind") == "mcp_refresh" and inp.get("n") == n and isinstance(st.get("output"), dict):
            rec = st["output"].get("record")
            if isinstance(rec, dict):
                return rec
    return find_record(msg, n)


def normalize(data: dict[str, Any] | None, base: dict[str, Any]) -> dict[str, Any] | None:
    """ツールの結果 → 出典の記録の形（agent/mcp_tools.invoke と同じ項目）。表でなければ None。"""
    if data is None or not isinstance(data.get("columns"), list):
        return None
    rows = [list(r) for r in data.get("rows") or [] if isinstance(r, list)]
    return {
        **{k: base.get(k) for k in ("system", "server", "tool", "args", "title")},
        "fetched_at": str(data.get("fetched_at") or ""),
        "basis": str(data.get("basis") or ""),
        "columns": [str(c) for c in data["columns"]],
        "rows": rows,
        "total": int(data.get("total") or len(rows)),
        "truncated": False,
        "restricted": [str(x) for x in data.get("restricted") or []],
        "note": data.get("note") if isinstance(data.get("note"), str) else None,
        **({"trace": data["trace"]} if isinstance(data.get("trace"), dict) else {}),
    }


async def refresh(
    session: AsyncSession,
    msg: Message,
    n: int,
    *,
    caller: Caller,
    dept_ids: frozenset[str],
    identity_key: str,
    box: SecretBox | None,
    timeout_sec: float,
) -> dict[str, Any]:
    """引用番号 n の記録を呼び直し、差とステップを返す。

    ステップはメッセージの記録に足す（呼び出し側が commit）。"""
    base = find_record(msg, n)
    if base is None:
        raise LookupError(f"引用 [{n}] は社内システムの記録ではありません")
    prev = latest_record(msg, n) or base
    server = str(base.get("server") or "")
    srv = await session.scalar(select(McpServer).where(McpServer.name == server))
    step_id = f"system-mcp_refresh-{n}-{uuid.uuid4().hex[:8]}"
    t0 = time.perf_counter()
    args = dict(base.get("args") or {})
    tool = str(base.get("tool") or "")
    record: dict[str, Any] | None = None
    error: str | None = None
    if srv is None or not srv.enabled:
        error = "このシステムは今は登録されていないか、使わない設定です"
    elif srv.id not in await usable_server_ids(session, dept_ids):
        error = "この利用者の部門は、このシステムの使える範囲に入っていません"
    else:
        spec = server_spec(srv)
        ep = spec.endpoint(box)
        try:
            res = await call_tool(
                ep, auth_headers(ep, caller, identity_key), tool, args, srv.timeout_sec or timeout_sec
            )
            data = res.data
            if data is not None and data.get("error"):
                error = str(data.get("message") or data.get("error"))
            else:
                record = normalize(data, base)
                if record is None:
                    error = "表の形の結果が返りませんでした"
        except McpError as e:
            error = f"{type(e).__name__}: {e}"
    ms = max(1, round((time.perf_counter() - t0) * 1000))
    changes = diff_records(prev, record) if record else []
    label = str(base.get("system") or server)
    if error:
        summary = f"「{label}」の {tool} を呼び直せなかった（{error}）"
    elif changes:
        summary = f"「{label}」の {tool} を呼び直した: {len(changes)} か所が変わった"
    else:
        summary = f"「{label}」の {tool} を呼び直した: 変わった値は無い"
    step = {
        "id": step_id,
        "name": "system",
        "label": "社内システムを最新にした",
        "status": "error" if error else "done",
        "duration_ms": ms,
        "input": {
            "kind": "mcp_refresh",
            "n": n,
            "server": server,
            "tool": tool,
            "args": args,
            "user": caller.user_id,
            "previous_fetched_at": prev.get("fetched_at"),
        },
        "output": {"record": record, "changes": changes, **({"error": error} if error else {})},
        "summary": summary,
        "node": "refresh",
    }
    msg.steps = [*(msg.steps or []), step]
    return {"n": n, "record": record, "previous": prev, "changes": changes, "error": error, "step": step}


# ── 管理の数字（R21）──


def _pct(xs: list[int], p: float) -> int | None:
    if not xs:
        return None
    s = sorted(xs)
    return s[min(len(s) - 1, max(0, round(p * (len(s) - 1))))]


async def server_stats(
    session: AsyncSession, server: str, *, hours: int = 1, recent: int = 20
) -> dict[str, Any]:
    """ARag の記録（メッセージのステップ）から、直近 hours 時間の呼び出しを集計する。"""
    since = datetime.now(UTC) - timedelta(hours=hours)
    msgs = (
        await session.execute(
            select(Message).where(Message.created_at >= since).order_by(Message.created_at.desc())
        )
    ).scalars()
    prefix = f"{server}__"
    calls: list[dict[str, Any]] = []
    fail_kinds = {"mcp_timeout", "mcp_unavailable", "mcp_denied", "mcp_too_many"}
    for m in msgs:
        failed_ids = set()
        for st in m.steps or []:
            kind = (st.get("input") or {}).get("kind")
            if kind in fail_kinds and (st.get("input") or {}).get("server") == server:
                failed_ids.add(str(st.get("id", "")).removeprefix(f"system-{kind}-"))
        for st in m.steps or []:
            name = str(st.get("name") or "")
            kind = (st.get("input") or {}).get("kind")
            if name.startswith(prefix):
                call_id = str(st.get("id") or "")
                ok = st.get("status") != "error" and call_id not in failed_ids
                calls.append(
                    {
                        "at": m.created_at.isoformat(timespec="seconds"),
                        "tool": name[len(prefix) :],
                        "ms": int(st.get("duration_ms") or 0),
                        "ok": ok,
                        "message_id": str(m.id),
                        "summary": str(st.get("summary") or "")[:200],
                    }
                )
            elif kind == "mcp_refresh" and (st.get("input") or {}).get("server") == server:
                calls.append(
                    {
                        "at": m.created_at.isoformat(timespec="seconds"),
                        "tool": str(st["input"].get("tool")),
                        "ms": int(st.get("duration_ms") or 0),
                        "ok": st.get("status") != "error",
                        "message_id": str(m.id),
                        "summary": str(st.get("summary") or "")[:200],
                        "refresh": True,
                    }
                )
    ms = [c["ms"] for c in calls if c["ms"] > 0]
    failures = sum(1 for c in calls if not c["ok"])
    return {
        "server": server,
        "hours": hours,
        "calls": len(calls),
        "failures": failures,
        "failure_rate": round(failures / len(calls), 3) if calls else 0.0,
        "p50_ms": _pct(ms, 0.5),
        "p95_ms": _pct(ms, 0.95),
        "recent": calls[:recent],
    }
