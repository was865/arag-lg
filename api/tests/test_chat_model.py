"""文脈付与のモデル生成（自前の OpenAI 互換サーバ・追加引数）。"""

from arag.llm import chat_model
from arag.settings import Settings


def test_local_openai_compatible_model() -> None:
    s = Settings(
        context_model="openai:qwen3-8b",
        context_base_url="http://gpu:8090/v1",
        context_model_kwargs={
            "temperature": 0,
            "extra_body": {"chat_template_kwargs": {"enable_thinking": False}},
        },
    )
    m = chat_model(s.context_model, base_url=s.context_base_url, kwargs=s.context_model_kwargs)
    assert m.openai_api_base == "http://gpu:8090/v1"  # type: ignore[attr-defined]
    assert m.model_name == "qwen3-8b"  # type: ignore[attr-defined]
    assert m.extra_body == {"chat_template_kwargs": {"enable_thinking": False}}  # type: ignore[attr-defined]
    assert m.temperature == 0  # type: ignore[attr-defined]


def test_settings_parse_kwargs_from_env(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("ARAG_CONTEXT_MODEL_KWARGS", '{"temperature": 0.1}')
    monkeypatch.setenv("ARAG_CONTEXT_MAX_DOCUMENT_TOKENS", "6000")
    s = Settings(_env_file=None)  # type: ignore[call-arg]  # 手元の .env と混ざらないように
    assert s.context_model_kwargs == {"temperature": 0.1} and s.context_max_document_tokens == 6000
