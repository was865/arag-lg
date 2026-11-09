"""入庫ワーカー（`python -m arag.ingest.worker`。specs/003-ingestion/design.md §3.0）。

- 並列数 ARAG_INGEST_CONCURRENCY でジョブを実行し、15 秒ごとにハートビート。
- LISTEN ingest_jobs で即時に起き、無通知でも 5 秒ごとに確認する。
- 停止したワーカーのジョブを再投入し（R27）、1 時間ごとに GC（R35）。
"""

import asyncio
import contextlib
import os
import signal
import socket
import uuid
from datetime import UTC, datetime, timedelta

import psycopg
import structlog
from qdrant_client import AsyncQdrantClient
from redis.asyncio import Redis

from arag.db.engine import make_engine, make_sessionmaker
from arag.inference import build_embedder, build_figure_describer, describe_inference
from arag.ingest import queue
from arag.ingest.chunking import load_tokenizer
from arag.ingest.contextualize import Contextualizer, HeadingContextualizer, LlmContextualizer
from arag.ingest.events import RedisPublisher
from arag.ingest.figures import FigureDescriber
from arag.ingest.gc import run_gc
from arag.ingest.index import QdrantIndex
from arag.ingest.parser import DoclingServeParser
from arag.ingest.pipeline import IngestDeps, run_ingest
from arag.ingest.sparse import SparseEncoder
from arag.llm import chat_model
from arag.logging import configure_logging, get_logger
from arag.settings import Settings
from arag.storage import LocalStorage

log = get_logger("arag.ingest.worker")

POLL_SEC = 5.0
GC_EVERY = timedelta(hours=1)
STALE_CHECK_EVERY = timedelta(seconds=30)


class Worker:
    def __init__(
        self, deps: IngestDeps, *, database_url: str, concurrency: int, retention: timedelta
    ) -> None:
        self.deps = deps
        self.database_url = database_url
        self.concurrency = max(1, concurrency)
        self.retention = retention
        self.worker_id = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"
        self.wake = asyncio.Event()
        self.running: set[asyncio.Task[None]] = set()

    async def _listen(self, stop: asyncio.Event) -> None:
        """NOTIFY を受けたら起こす。切れても 5 秒ポーリングで動き続ける。"""
        while not stop.is_set():
            try:
                conn = await psycopg.AsyncConnection.connect(self.database_url, autocommit=True)
                async with conn:
                    await conn.execute(f"LISTEN {queue.NOTIFY_CHANNEL}")
                    while not stop.is_set():
                        async for _ in conn.notifies(timeout=POLL_SEC, stop_after=1):
                            self.wake.set()
            except Exception as e:
                log.warning("listen_failed", error=f"{type(e).__name__}: {e}")
                await asyncio.sleep(POLL_SEC)

    async def _run_job(self, job_id: uuid.UUID) -> None:
        with structlog.contextvars.bound_contextvars(job_id=str(job_id)):

            async def beat() -> None:
                while True:
                    await asyncio.sleep(queue.HEARTBEAT_EVERY.total_seconds())
                    async with self.deps.sessionmaker() as s:
                        await queue.heartbeat(s, job_id, self.worker_id)

            hb = asyncio.create_task(beat())
            try:
                status = await run_ingest(job_id, self.deps)
                log.info("job_finished", status=status)
            except Exception:
                log.exception("job_crashed")
            finally:
                hb.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await hb
                self.wake.set()

    async def tick(self) -> int:
        """空きスロット分だけジョブを取って起動する。起動数を返す。"""
        started = 0
        while len(self.running) < self.concurrency:
            async with self.deps.sessionmaker() as s:
                job_id = await queue.claim(s, self.worker_id)
            if job_id is None:
                break
            task = asyncio.create_task(self._run_job(job_id))
            self.running.add(task)
            task.add_done_callback(self.running.discard)
            started += 1
        return started

    async def run(self, stop: asyncio.Event) -> None:
        log.info("worker_started", worker_id=self.worker_id, concurrency=self.concurrency)
        listener = asyncio.create_task(self._listen(stop))
        last_stale = last_gc = datetime.min.replace(tzinfo=UTC)
        try:
            while not stop.is_set():
                now = datetime.now(UTC)
                if now - last_stale >= STALE_CHECK_EVERY:
                    async with self.deps.sessionmaker() as s:
                        if requeued := await queue.requeue_stale(s):
                            log.info("requeued_stale", jobs=[str(j) for j in requeued])
                    last_stale = now
                if now - last_gc >= GC_EVERY:
                    try:
                        async with self.deps.sessionmaker() as s:
                            await run_gc(
                                s, self.deps.storage, self.deps.index, now=now, retention=self.retention
                            )
                    except Exception:
                        log.exception("gc_failed")
                    last_gc = now
                await self.tick()
                self.wake.clear()
                with contextlib.suppress(TimeoutError):
                    async with asyncio.timeout(POLL_SEC):
                        await self.wake.wait()
        finally:
            listener.cancel()
            # 実行中のジョブは途中で止めず、終わるまで待つ（graceful shutdown）
            if self.running:
                log.info("waiting_running_jobs", count=len(self.running))
                await asyncio.gather(*self.running, return_exceptions=True)


def build_deps(settings: Settings) -> IngestDeps:
    embedder = build_embedder(settings)
    if embedder is None:
        raise SystemExit("ARAG_EMBED_URL（または ARAG_TEI_EMBED_URL）が未設定です（埋め込みが必要です）")
    engine = make_engine(settings.database_url)
    sessionmaker = make_sessionmaker(engine)
    contextualizer: Contextualizer = HeadingContextualizer()
    if settings.context_model:
        contextualizer = LlmContextualizer(
            chat_model(
                settings.context_model,
                base_url=settings.context_base_url,
                kwargs=settings.context_model_kwargs,
            ),
            model_name=settings.context_model,
            concurrency=settings.context_concurrency,
            max_document_tokens=settings.context_max_document_tokens,
        )
    describer: FigureDescriber | None = build_figure_describer(settings)
    tokenizer = load_tokenizer(settings.embed_tokenizer, settings.chunk_max_tokens)
    return IngestDeps(
        sessionmaker=sessionmaker,
        storage=LocalStorage(settings.storage_dir),
        tokenizer=tokenizer,
        embedder=embedder,
        index=QdrantIndex(AsyncQdrantClient(url=settings.qdrant_url), settings.qdrant_collection),
        docling=DoclingServeParser(
            settings.docling_url,
            page_window=settings.docling_page_window,
            ocr_lang=[x.strip() for x in settings.docling_ocr_lang.split(",") if x.strip()],
            timeout_sec=settings.docling_timeout_sec,
            http_timeout_sec=settings.http_timeout_sec,
        )
        if settings.docling_url
        else None,
        contextualizer=contextualizer,
        describer=describer,
        sparse_factory=lambda: SparseEncoder(
            settings.sudachi_mode, avgdl=settings.bm25_avgdl, en_stem=settings.sparse_en_stem
        ),
        publisher=RedisPublisher(Redis.from_url(settings.redis_url, decode_responses=True)),
        section_max_tokens=settings.section_max_tokens,
        section_level=settings.section_level,
        max_retries=settings.ingest_max_retries,
    )


async def main() -> None:
    settings = Settings()
    configure_logging(settings.log_level)
    log.info("inference_config", **describe_inference(settings))  # 各役割が自前か API か（鍵は出さない）
    worker = Worker(
        build_deps(settings),
        database_url=settings.database_url,
        concurrency=settings.ingest_concurrency,
        retention=timedelta(days=settings.trash_retention_days),
    )
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    await worker.run(stop)


if __name__ == "__main__":
    asyncio.run(main())
