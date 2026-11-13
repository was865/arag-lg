"""イベントの中継に使う Redis クライアントの読み取りタイムアウト。"""

from arag.agent.stream import READ_BLOCK_MS, redis_client


def test_socket_timeout_outlasts_blocking_read() -> None:
    # redis-py 8 の既定（5 秒）のままだと、モデルが 5 秒以上黙ると XREAD の待ちで切れて SSE が落ちる
    r = redis_client("redis://localhost:6379/0")
    kw = r.connection_pool.connection_kwargs
    assert kw["socket_timeout"] > READ_BLOCK_MS / 1000
    assert kw["decode_responses"] is True


def test_stream_closes_after_followups_when_they_are_pending() -> None:
    """候補を後から送る完了では閉じず、followups で閉じる（specs/028 T24）。"""
    from arag.agent.events import closes_stream

    assert closes_stream("run.completed", {"followups_pending": False})
    assert not closes_stream("run.completed", {"followups_pending": True})
    assert closes_stream("followups", {})
    assert closes_stream("run.failed", {}) and closes_stream("run.cancelled", {})
    assert not closes_stream("step", {})
