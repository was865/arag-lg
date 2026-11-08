"""OpenAPI 文書の書き出し（specs/001-p0-skeleton R9）。"""

from pathlib import Path

from arag.openapi_export import export_openapi, render_openapi


def test_render_is_deterministic() -> None:
    assert render_openapi() == render_openapi()


def test_contains_health_endpoints() -> None:
    text = render_openapi()
    assert '"/healthz"' in text
    assert '"/readyz"' in text


def test_export_writes_file(tmp_path: Path) -> None:
    out = tmp_path / "openapi.json"
    export_openapi(out)
    assert out.read_text(encoding="utf-8") == render_openapi()


def test_committed_document_is_up_to_date() -> None:
    committed = Path(__file__).resolve().parents[1] / "openapi.json"
    assert committed.read_text(encoding="utf-8") == render_openapi(), (
        "api/openapi.json が古い。`make gen` で再生成すること"
    )
