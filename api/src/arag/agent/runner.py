"""run の実行（specs/005-agent R2・R12・R20〜R25、design §1）。

`runs` 表をキューにして取り出し、create_agent を流し、イベントを Redis Stream に書き、
終了時に messages / citations を 1 トランザクションで保存する。
"""

import asyncio
import contextlib
import inspect
import os
import socket
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from redis.asyncio import Redis
from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from arag.agent.citations import CitationRegistry, Cited, FinalCitations, cited_numbers, finalize_citations
from arag.agent.config import AgentCfg
from arag.agent.context import RunContext, SearchFn
from arag.agent.graph import build_agent
from arag.agent.query_image import with_image_description
from arag.agent.service import RUNS_CHANNEL, delete_messages_from
from arag.agent.steps import Step, StepClock
from arag.agent.stream import EventSink, is_cancelled, redis_client
from arag.audit import AuditEvent, write_audit
from arag.auth.principal import Principal
from arag.db.models import Citation, Message, Run, Thread
from arag.logging import get_logger
from arag.storage import Storage

log = get_logger("arag.agent.runner")

NO_ANSWER_TEXT = {
    "no_sources": "社内の資料から、この質問に答えられる情報は見つかりませんでした。"
    "言い方を変えるか、検索範囲（知識ベース）を広げてもう一度お試しください。",
    "step_budget_exhausted": "調べる回数の上限に達したため、回答をまとめられませんでした。"
    "質問を絞るか、エージェント設定の「最大ステップ数」を増やしてください。",
    "tool_failed": "検索の実行に失敗したため回答できませんでした。しばらくしてからもう一度お試しください。",
    "generation_failed": "回答の生成に失敗しました。しばらくしてからもう一度お試しください。",
}


RUNNER_LOST = "回答の生成が中断されました。もう一度お試しください。"


class ImageReader(Protocol):
    async def read(self, image: bytes, question: str) -> str: ...


@dataclass
class ResolvedModels:
    id: str
    model: BaseChatModel
    utility: BaseChatModel | None = None
    fallback: BaseChatModel | None = None


@dataclass
class RunnerDeps:
    sessionmaker: async_sessionmaker[AsyncSession]
    redis: Redis
    checkpointer: Any
    search: SearchFn
    # 同期・非同期どちらでもよい（本番は実行ごとに DB の目録を読む）
    resolve_models: Callable[[str | None], ResolvedModels | Awaitable[ResolvedModels]]
    events_ttl_sec: int = 3600
    cancel_poll_sec: float = 0.5
    agent_cache: dict[str, Any] = field(default_factory=dict)
    # 質問に添えた画像（specs/017）。画像の保存先と、画像を文章にする読み手（未設定なら読めない扱い）
    storage: Storage | None = None
    image_reader: ImageReader | None = None

    def agent_for(self, m: ResolvedModels) -> Any:
        if m.id not in self.agent_cache:
            self.agent_cache[m.id] = build_agent(
                m.model, utility=m.utility, fallback=m.fallback, checkpointer=self.checkpointer
            )
        return self.agent_cache[m.id]


class _Turn:
    """ストリームから組み立てる 1 ターン分の表示用の状態。"""

    def __init__(self) -> None:
        self.answer = ""
        self.steps: dict[str, dict[str, Any]] = {}
        self.tokens_in = 0
        self.tokens_out = 0
        self.t0 = time.monotonic()

    @property
    def duration_ms(self) -> int:
        return round((time.monotonic() - self.t0) * 1000)


def _uuids(v: list[str] | None) -> list[uuid.UUID] | None:
    return None if v is None else [uuid.UUID(x) for x in v]


def _sources_event(reg: CitationRegistry) -> dict[str, Any]:
    """生成中の出典（登録した全資料・登録順の番号）。確定時は _final_sources で置き換える。"""
    cmap, sources = reg.sources()
    return {"citation_map": {str(k): v for k, v in cmap.items()}, "sources": sources}


def _final_sources(fin: FinalCitations) -> dict[str, Any]:
    return {"citation_map": {str(k): v for k, v in fin.cmap.items()}, "sources": fin.sources}


async def _repair_dangling_tool_calls(agent: Any, config: dict[str, Any]) -> None:
    """取消・異常終了で応答の無いツール呼び出しが残っていたら閉じる（次のモデル呼び出しが失敗するため）。"""
    state = await agent.aget_state(config)
    msgs = state.values.get("messages", []) if state.values else []
    answered = {m.tool_call_id for m in msgs if isinstance(m, ToolMessage)}
    fix = [
        ToolMessage(content="（取り消されました）", tool_call_id=tc["id"], name=tc["name"], status="error")
        for m in msgs
        if isinstance(m, AIMessage)
        for tc in m.tool_calls
        if tc["id"] not in answered
    ]
    if fix:
        await agent.aupdate_state(config, {"messages": fix}, as_node="tools")


def _classify(answer: str, ctx: RunContext) -> str | None:
    if answer.strip():
        # 調べたのに資料が 1 件も無く、引用も無い回答は「資料なし」として数える（知識ギャップの分析用）
        if ctx.stats.tool_calls and not cited_numbers(answer):
            if len(ctx.registry) == 0:
                return "no_sources"
            # 資料はあったが引用の無い回答（多くは「見つからなかった」）。引用必須のときだけ数える
            if ctx.cfg.require_citations:
                return "no_relevant_sources"
        return None
    if ctx.stats.tool_errors and len(ctx.registry) == 0:
        return "tool_failed"
    if len(ctx.registry) == 0:
        return "no_sources"
    return "step_budget_exhausted"


async def execute_run(deps: RunnerDeps, run_id: uuid.UUID) -> str:
    """claim 済み（running）の run を最後まで実行し、終了状態を返す。"""
    async with deps.sessionmaker() as s:
        run = await s.get(Run, run_id)
        assert run is not None
        req = dict(run.request)
        thread_id, message_id, model_id = run.thread_id, run.message_id, run.model_id
    sink = EventSink(deps.redis, str(run_id), ttl_sec=deps.events_ttl_sec)
    pr = req["principal"]
    principal = Principal(user_id=pr["user_id"], role=pr.get("role", "member"), email=pr.get("email"))
    cfg = AgentCfg.clamped(req.get("agent_cfg"))
    turn = _Turn()
    ctx = RunContext(
        principal=principal,
        sessionmaker=deps.sessionmaker,
        search=deps.search,
        question=req["query"],
        kb_ids=_uuids(req.get("kb_ids")),
        document_ids=_uuids(req.get("document_ids")),
        include_archived=bool(req.get("include_archived")),
        cfg=cfg,
    )
    checkpoint_id: str | None = None
    status, code, err = "completed", None, ""
    try:
        got = deps.resolve_models(model_id)
        models = await got if inspect.isawaitable(got) else got
    except Exception as e:
        models, status, code, err = None, "failed", "model_unavailable", str(e)
    await sink.emit(
        {
            "type": "run.started",
            "run_id": str(run_id),
            "thread_id": str(thread_id),
            "message_id": str(message_id),
            "model_id": models.id if models else (model_id or ""),
        }
    )
    if models is not None:
        # 書き換え（CRAG）は utility が無ければ会話モデルで行う
        ctx.utility_model = models.utility or models.model
        agent = deps.agent_for(models)
        base = {"configurable": {"thread_id": str(thread_id)}}
        if req.get("branch"):
            if req.get("branch_checkpoint_id"):
                base["configurable"]["checkpoint_id"] = req["branch_checkpoint_id"]
            else:  # 先頭のターンからやり直すときは状態を空にする
                await deps.checkpointer.adelete_thread(str(thread_id))
        try:
            await _repair_dangling_tool_calls(agent, base)
            before = await agent.aget_state(base)
            checkpoint_id = (before.config or {}).get("configurable", {}).get("checkpoint_id")
            config = {
                **base,
                "max_concurrency": cfg.parallel_tools,
                "recursion_limit": cfg.max_steps * 3 + 10,
            }
            query = req["query"]
            if isinstance(req.get("image"), dict):
                description = await _read_image(deps, sink, turn, req)
                query = with_image_description(query, description)
                # 検索語の書き換えでも画像の内容を踏まえる（R5）
                ctx.question = query
            await _stream(agent, config, ctx, sink, turn, query)
            final = await agent.aget_state({"configurable": {"thread_id": str(thread_id)}})
            msgs = final.values.get("messages", [])
            last = msgs[-1] if msgs else None
            if isinstance(last, AIMessage) and not last.tool_calls:
                turn.answer = last.text
        except asyncio.CancelledError:
            status = "cancelled"
        except Exception as e:
            log.exception("run_failed", run_id=str(run_id))
            status, code, err = "failed", "generation_failed", f"{type(e).__name__}: {e}"[:500]

    # 引用を確定する（回答に出た順に振り直し、引用した箇所だけを出典にする）
    fin = finalize_citations(turn.answer, ctx.registry)
    answer = fin.answer
    reason: str | None = None
    if status == "completed":
        reason = _classify(answer, ctx)
        if not answer.strip() and reason:
            answer = NO_ANSWER_TEXT[reason]
    elif status == "failed":
        reason = "generation_failed"
        answer = answer or NO_ANSWER_TEXT["generation_failed"]
    src = _final_sources(fin)
    await asyncio.shield(
        _persist(
            deps,
            run_id,
            thread_id,
            message_id,
            req,
            models.id if models else model_id,
            status,
            code,
            err,
            answer,
            reason,
            turn,
            src,
            fin.items,
            ctx,
            checkpoint_id,
        )
    )
    if status == "completed":
        await sink.emit(
            {
                "type": "run.completed",
                "message_id": str(message_id),
                "answer": answer,
                "tokens_in": turn.tokens_in,
                "tokens_out": turn.tokens_out,
                "duration_ms": turn.duration_ms,
                "no_answer_reason": reason,
                **src,
            }
        )
    elif status == "cancelled":
        await sink.emit({"type": "run.cancelled", "message_id": str(message_id)})
    else:
        await sink.emit({"type": "run.failed", "code": code or "generation_failed", "message": answer})
    return status


async def _read_image(deps: RunnerDeps, sink: EventSink, turn: _Turn, req: dict[str, Any]) -> str | None:
    """添付画像を文章にする（R4）。失敗しても回答は止めず None を返す（R5）。"""
    img = req["image"]
    step = Step(id=f"img-{img['id']}", name="read_image", label="画像を読み取る", status="running")
    events: list[dict[str, Any]] = []
    clock = StepClock(events.append, step)

    async def flush() -> None:
        # 進行表示に出しつつ、保存するステップにも残す
        for ev in events:
            turn.steps[ev["step"]["id"]] = ev["step"]
            await sink.emit(ev)
        events.clear()

    await flush()  # 「読み取り中」を先に出す
    description: str | None = None
    try:
        if deps.image_reader is None or deps.storage is None:
            raise RuntimeError("画像の読み取りが設定されていません")
        data = await deps.storage.read(img["key"])
        description = (await deps.image_reader.read(data, req["query"])).strip() or None
        if description is None:
            raise RuntimeError("画像から何も読み取れませんでした")
        clock.done("読み取りました", {"description": description})
        img["description"] = description
    except Exception as e:
        log.warning("read_image_failed", error=f"{type(e).__name__}: {e}")
        clock.done("画像を読み取れませんでした", {"error": str(e)[:200]}, error=True)
    await flush()
    return description


async def _stream(
    agent: Any, config: dict[str, Any], ctx: RunContext, sink: EventSink, turn: _Turn, query: str
) -> None:
    async for mode, chunk in agent.astream(
        {"messages": [HumanMessage(query)]}, config, context=ctx, stream_mode=["messages", "custom"]
    ):
        if mode == "custom":
            if chunk.get("type") == "step":
                step = chunk["step"]
                turn.steps[step["id"]] = step
                await sink.emit(chunk)
                # ツールが終わるたびに出典を送る（右パネルを先に用意できる）
                if step["status"] == "done" and step.get("parent_id") is None and len(ctx.registry):
                    await sink.emit({"type": "sources", **_sources_event(ctx.registry)})
            continue
        msg, meta = chunk
        if meta.get("langgraph_node") != "model" or not isinstance(msg, AIMessageChunk):
            continue
        if msg.usage_metadata:
            turn.tokens_in += msg.usage_metadata.get("input_tokens", 0)
            turn.tokens_out += msg.usage_metadata.get("output_tokens", 0)
        piece = msg.text
        if piece:
            turn.answer += piece
            await sink.emit({"type": "answer.delta", "text": piece})
        if msg.tool_call_chunks and turn.answer:
            # ツール呼び出しの前置き文は回答ではない
            turn.answer = ""
            await sink.emit({"type": "answer.reset"})


async def _persist(
    deps: RunnerDeps,
    run_id: uuid.UUID,
    thread_id: uuid.UUID,
    message_id: uuid.UUID,
    req: dict[str, Any],
    model_id: str | None,
    status: str,
    code: str | None,
    err: str,
    answer: str,
    reason: str | None,
    turn: _Turn,
    src: dict[str, Any],
    cited: dict[int, Cited],
    ctx: RunContext,
    checkpoint_id: str | None,
) -> None:
    now = datetime.now(UTC)
    steps = list(turn.steps.values())
    async with deps.sessionmaker() as s, s.begin():
        await delete_messages_from(s, thread_id, int(req["ordinal"]))
        s.add(
            Message(
                id=message_id,
                thread_id=thread_id,
                ordinal=int(req["ordinal"]),
                query=req["query"],
                answer_text=answer,
                status=status,
                model_id=model_id,
                tokens_in=turn.tokens_in,
                tokens_out=turn.tokens_out,
                duration_ms=turn.duration_ms,
                steps=steps,
                sources=src["sources"],
                citation_map=src["citation_map"],
                no_answer_reason=reason,
                request={k: v for k, v in req.items() if k != "principal"},
                checkpoint_id=checkpoint_id,
                run_id=run_id,
            )
        )
        await s.flush()
        for n, c in cited.items():
            s.add(
                Citation(
                    message_id=message_id,
                    ordinal=n,
                    document_id=c.document_id,
                    chunk_id=c.item_id if c.block_type != "section" else None,
                    section_id=c.section_id,
                    document_title=c.document_name,
                    heading_path=c.heading_path,
                    snippet=c.text[:500],
                    block_type=c.block_type,
                    page=c.page,
                    score=c.score,
                )
            )
        await s.execute(update(Thread).where(Thread.id == thread_id).values(updated_at=now))
        await s.execute(
            update(Run)
            .where(Run.id == run_id)
            .values(status=status, finished_at=now, error_code=code, error=err or None)
        )
        await write_audit(
            s,
            AuditEvent(
                action="chat.run",
                resource_type="thread",
                resource_id=str(thread_id),
                result="ok" if status == "completed" else "error",
                detail={
                    "run_id": str(run_id),
                    "status": status,
                    "query_chars": len(req["query"]),
                    "tokens_in": turn.tokens_in,
                    "tokens_out": turn.tokens_out,
                    "tool_calls": ctx.stats.tool_calls,
                    "no_answer_reason": reason,
                },
            ),
            principal=ctx.principal,
        )


# --- キュー ---


async def claim(session: AsyncSession, worker_id: str) -> uuid.UUID | None:
    row = await session.execute(
        text(
            """
            UPDATE app.runs SET status = 'running', locked_by = :w, heartbeat_at = now(), started_at = now()
            WHERE id = (
                SELECT id FROM app.runs WHERE status = 'queued' ORDER BY created_at
                FOR UPDATE SKIP LOCKED LIMIT 1
            )
            RETURNING id
            """
        ),
        {"w": worker_id},
    )
    rid = row.scalar_one_or_none()
    await session.commit()
    return rid


async def reap_stale(deps: RunnerDeps, stale: timedelta) -> int:
    """心拍の途絶えた run を failed にし、待っている利用者に知らせる（R2）。"""
    async with deps.sessionmaker() as s, s.begin():
        rows = (
            (
                await s.execute(
                    update(Run)
                    .where(Run.status == "running", Run.heartbeat_at < datetime.now(UTC) - stale)
                    .values(status="failed", error_code="runner_lost", finished_at=datetime.now(UTC))
                    .returning(Run.id)
                )
            )
            .scalars()
            .all()
        )
    for rid in rows:
        sink = EventSink(deps.redis, str(rid), ttl_sec=deps.events_ttl_sec)
        await sink.emit(
            {
                "type": "run.failed",
                "code": "runner_lost",
                "message": "回答の生成が中断されました。もう一度お試しください。",
            }
        )
    return len(rows)


class Runner:
    def __init__(
        self,
        deps: RunnerDeps,
        *,
        database_url: str,
        concurrency: int = 8,
        heartbeat_sec: float = 10.0,
        stale_sec: float = 60.0,
    ) -> None:
        self.deps = deps
        self.database_url = database_url
        self.concurrency = concurrency
        self.heartbeat = heartbeat_sec
        self.stale = timedelta(seconds=stale_sec)
        self.worker_id = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"
        self.running: dict[uuid.UUID, asyncio.Task[str]] = {}
        self._wake = asyncio.Event()

    async def _run_one(self, run_id: uuid.UUID) -> str:
        task = asyncio.current_task()
        assert task is not None
        inner = asyncio.create_task(execute_run(self.deps, run_id))

        async def watch() -> None:
            last_beat = time.monotonic()
            while not inner.done():
                await asyncio.sleep(self.deps.cancel_poll_sec)
                if await is_cancelled(self.deps.redis, str(run_id)):
                    inner.cancel()
                    return
                if time.monotonic() - last_beat >= self.heartbeat:
                    last_beat = time.monotonic()
                    async with self.deps.sessionmaker() as s, s.begin():
                        await s.execute(
                            update(Run).where(Run.id == run_id).values(heartbeat_at=datetime.now(UTC))
                        )

        watcher = asyncio.create_task(watch())
        try:
            # execute_run は取消を自分で受け止めて保存まで行う。停止時も実行中の run は最後まで保存させる
            return await asyncio.shield(inner)
        finally:
            watcher.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await watcher

    def _forget(self, rid: uuid.UUID) -> Callable[[asyncio.Task[str]], None]:
        def cb(_t: asyncio.Task[str]) -> None:
            self.running.pop(rid, None)

        return cb

    async def tick(self) -> int:
        started = 0
        while len(self.running) < self.concurrency:
            async with self.deps.sessionmaker() as s:
                rid = await claim(s, self.worker_id)
            if rid is None:
                break
            t = asyncio.create_task(self._run_one(rid))
            self.running[rid] = t
            t.add_done_callback(self._forget(rid))
            started += 1
        return started

    async def _listen(self, stop: asyncio.Event) -> None:
        import psycopg

        url = self.database_url.replace("postgresql+psycopg://", "postgresql://", 1)
        while not stop.is_set():
            try:
                async with await psycopg.AsyncConnection.connect(url, autocommit=True) as conn:
                    await conn.execute(f"LISTEN {RUNS_CHANNEL}")
                    async for _n in conn.notifies():
                        self._wake.set()
                        if stop.is_set():
                            return
            except Exception as e:
                log.warning("listen_failed", error=str(e)[:200])
                await asyncio.sleep(2)

    async def run(self, stop: asyncio.Event) -> None:
        listener = asyncio.create_task(self._listen(stop))
        last_reap = 0.0
        try:
            while not stop.is_set():
                if time.monotonic() - last_reap > self.heartbeat:
                    last_reap = time.monotonic()
                    await reap_stale(self.deps, self.stale)
                await self.tick()
                self._wake.clear()
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self._wake.wait(), timeout=1.0)
        finally:
            listener.cancel()
            if self.running:
                log.info("waiting_running_runs", count=len(self.running))
                await asyncio.gather(*self.running.values(), return_exceptions=True)


async def main() -> None:
    import signal

    from qdrant_client import AsyncQdrantClient

    from arag.agent.catalog import load_catalog
    from arag.agent.checkpoint import open_checkpointer
    from arag.db.engine import make_engine, make_sessionmaker
    from arag.inference import build_query_image_reader
    from arag.logging import configure_logging
    from arag.search.service import build_search_deps, search
    from arag.settings import Settings
    from arag.storage import LocalStorage

    settings = Settings()
    configure_logging(settings.log_level)
    engine = make_engine(settings.database_url)
    sm = make_sessionmaker(engine)
    redis = redis_client(settings.redis_url)
    qdrant = AsyncQdrantClient(url=settings.qdrant_url)
    sdeps = build_search_deps(settings, qdrant)

    async def search_fn(s: AsyncSession, p: Principal, r: Any) -> Any:
        return await search(s, sdeps, p, r)

    async def resolve(model_id: str | None) -> ResolvedModels:
        # 画面での目録・鍵の変更を次の実行から効かせる（specs/013-llm-keys R5）
        async with sm() as s:
            catalog = await load_catalog(s, settings)
        spec = catalog.resolve(model_id)
        util = catalog.resolve(settings.utility_model).build() if settings.utility_model else None
        fb = catalog.fallback(spec.id)
        return ResolvedModels(
            id=spec.id, model=spec.build(), utility=util, fallback=fb.build() if fb else None
        )

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    async with open_checkpointer(settings.database_url) as saver:
        deps = RunnerDeps(
            sessionmaker=sm,
            redis=redis,
            checkpointer=saver,
            search=search_fn,
            resolve_models=resolve,
            events_ttl_sec=settings.run_events_ttl_sec,
            storage=LocalStorage(settings.storage_dir),
            image_reader=build_query_image_reader(settings),
        )
        runner = Runner(
            deps,
            database_url=settings.database_url,
            concurrency=settings.run_concurrency,
            heartbeat_sec=settings.run_heartbeat_sec,
            stale_sec=settings.run_stale_sec,
        )
        log.info("runner_started", worker=runner.worker_id)
        await runner.run(stop)
    await redis.aclose()
    await qdrant.close()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
