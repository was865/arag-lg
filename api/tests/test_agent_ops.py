"""ツール処理の純粋な部分（specs/005-agent R17）。"""

from arag.agent.ops import rewrite_message

from .agent_fakes import fake_hit


def test_rewrite_message_asks_for_japanese_for_foreign_questions() -> None:
    hits = [fake_hit("本文")]
    en = rewrite_message("What is the approval threshold?", "approval threshold", hits)
    assert "日本語に訳した" in en and "規程.pdf" in en
    ja = rewrite_message("承認の上限は？", "承認 上限", hits)
    assert "日本語に訳した" not in ja
    assert "（なし）" in rewrite_message("承認の上限は？", "承認", [])


def test_diversify_caps_hits_per_document() -> None:
    import uuid

    from arag.agent.ops import diversify

    a, b = uuid.uuid4(), uuid.uuid4()
    hits = [fake_hit(f"a{i}", 0.9 - i * 0.01).model_copy(update={"document_id": a}) for i in range(5)]
    hits += [fake_hit(f"b{i}", 0.5 - i * 0.01).model_copy(update={"document_id": b}) for i in range(2)]
    out = diversify(hits, k=4, per_document=2)
    # 1 文書に偏らず、別の文書の上位も入る（並びはスコア順のまま）
    assert [h.text for h in out] == ["a0", "a1", "b0", "b1"]
    # 他に文書が無ければ上限を超えて埋める
    assert [h.text for h in diversify(hits[:5], k=4, per_document=2)] == ["a0", "a1", "a2", "a3"]
    assert [h.text for h in diversify(hits, k=3, per_document=0)] == ["a0", "a1", "a2"]
