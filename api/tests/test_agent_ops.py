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
