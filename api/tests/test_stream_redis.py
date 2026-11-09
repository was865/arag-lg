"""イベントの中継に使う Redis クライアントの読み取りタイムアウト。"""

from arag.agent.stream import READ_BLOCK_MS, redis_client


def test_socket_timeout_outlasts_blocking_read() -> None:
    # redis-py 8 の既定（5 秒）のままだと、モデルが 5 秒以上黙ると XREAD の待ちで切れて SSE が落ちる
    r = redis_client("redis://localhost:6379/0")
    kw = r.connection_pool.connection_kwargs
    assert kw["socket_timeout"] > READ_BLOCK_MS / 1000
    assert kw["decode_responses"] is True
