"""エージェント挙動設定とモデル目録（specs/005-agent R24・R28・R29）。"""

import pytest

from arag.agent.config import AgentCfg, ModelCatalog, ModelNotFound


def test_agent_cfg_defaults_and_clamp() -> None:
    d = AgentCfg()
    assert (d.max_steps, d.top_k, d.candidate_k, d.verify, d.require_citations) == (12, 6, 30, False, True)
    c = AgentCfg.clamped(
        {"max_steps": 99, "parallel_tools": 0, "top_k": 30, "candidate_k": 5, "grade_threshold": 2, "x": 1}
    )
    assert (c.max_steps, c.parallel_tools, c.top_k, c.grade_threshold) == (20, 1, 20, 1.0)
    assert c.candidate_k == 20  # top_k 以上に引き上げる
    assert AgentCfg.clamped(None) == AgentCfg()
    assert AgentCfg.clamped({"max_steps": "abc", "verify": "yes"}) == AgentCfg()


CATALOG = [
    {"id": "local", "label": "社内", "model": "openai:qwen3-8b", "base_url": "http://gpu:8090/v1"},
    {"id": "ds", "label": "DeepSeek", "model": "deepseek:deepseek-v4-pro", "tags": ["高精度"]},
    {"id": "claude", "label": "Claude", "model": "anthropic:claude-haiku-5-5"},
]


def test_catalog_availability_default_and_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    cat = ModelCatalog.from_raw(CATALOG)
    assert [(m.id, m.available) for m in cat.models] == [("local", True), ("ds", False), ("claude", True)]
    assert cat.default().id == "local"
    assert cat.resolve(None).id == "local"
    assert cat.resolve("claude").id == "claude"
    assert cat.fallback("local") is not None and cat.fallback("local").id == "claude"  # type: ignore[union-attr]
    assert cat.fallback("claude") is not None and cat.fallback("claude").id == "local"  # type: ignore[union-attr]
    with pytest.raises(ModelNotFound):
        cat.resolve("nope")
    with pytest.raises(ModelNotFound):
        cat.resolve("ds")  # 鍵が無いものは選べない


def test_empty_catalog_has_no_default() -> None:
    cat = ModelCatalog.from_raw([])
    with pytest.raises(ModelNotFound):
        cat.resolve(None)
