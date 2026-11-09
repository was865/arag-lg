"""監査ログの IP（Web の中継が伝える利用者の IP を、合言葉が合うときだけ信じる）。"""

from starlette.requests import Request

from arag.deps import client_ip


def _req(headers: dict[str, str], peer: str = "172.18.0.5") -> Request:
    return Request(
        {
            "type": "http",
            "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
            "client": (peer, 1234),
        }
    )


def test_trusts_forwarded_ip_only_with_matching_secret() -> None:
    h = {"x-arag-client-ip": "203.0.113.7", "x-arag-forward-token": "s3cret"}
    assert client_ip(_req(h), "s3cret") == "203.0.113.7"
    assert client_ip(_req(h), "other") == "172.18.0.5"
    assert client_ip(_req(h), "") == "172.18.0.5"  # 合言葉が未設定なら見出しは無視
    assert client_ip(_req({"x-arag-client-ip": "203.0.113.7"}), "s3cret") == "172.18.0.5"


def test_rejects_malformed_ip() -> None:
    h = {"x-arag-client-ip": "not-an-ip; drop", "x-arag-forward-token": "s3cret"}
    assert client_ip(_req(h), "s3cret") == "172.18.0.5"
    assert client_ip(
        _req({"x-arag-client-ip": "::ffff:10.0.0.1", "x-arag-forward-token": "s3cret"}), "s3cret"
    ) == ("::ffff:10.0.0.1")
