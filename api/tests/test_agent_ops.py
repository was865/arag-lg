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


# ── 章立て（specs/031 R1〜R3） ──


def _secs(n: int, toc_at: int | None = None) -> list[object]:
    from types import SimpleNamespace

    return [
        SimpleNamespace(
            id=f"id-{i}",
            level=1,
            heading_path="目 次" if i == toc_at else f"節{i}",
            page_start=i,
            token_len=10,
        )
        for i in range(1, n + 1)
    ]


def test_short_outline_lists_every_section_with_numbers() -> None:
    from arag.agent.ops import OUTLINE_OMITTED, format_outline

    out = format_outline("a.pdf", _secs(3))
    assert "（3 節）" in out and "- 1. 節1（p.1、10 トークン、ID: id-1）" in out and "- 3. 節3" in out
    assert OUTLINE_OMITTED not in out and "目次の節" not in out


def test_long_outline_shows_head_and_tail_and_how_to_read_the_middle() -> None:
    from arag.agent.ops import OUTLINE_HEAD, OUTLINE_OMITTED, OUTLINE_TAIL, format_outline

    out = format_outline("a.pdf", _secs(643))
    # 「最後の章」が見えるように末尾も出す
    assert f"- {OUTLINE_HEAD}. 節{OUTLINE_HEAD}（" in out and "- 643. 節643（" in out
    assert f"- {643 - OUTLINE_TAIL + 1}. " in out and f"- {643 - OUTLINE_TAIL}. " not in out
    assert f"- {OUTLINE_HEAD + 1}. " not in out
    assert f"{OUTLINE_OMITTED}第 {OUTLINE_HEAD + 1}〜{643 - OUTLINE_TAIL} 節は未表示" in out
    assert f"start={OUTLINE_HEAD + 1}" in out


def test_outline_start_pages_through_the_middle() -> None:
    from arag.agent.ops import OUTLINE_MAX, OUTLINE_OMITTED, format_outline

    out = format_outline("a.pdf", _secs(643), start=121)
    assert "- 121. 節121（" in out and "- 120. " not in out
    assert f"- {120 + OUTLINE_MAX}. " in out and f"- {121 + OUTLINE_MAX}. " not in out
    assert f"{OUTLINE_OMITTED}第 {121 + OUTLINE_MAX}〜643 節は未表示" in out
    # 末尾まで届けば省略の印は出さない
    assert OUTLINE_OMITTED not in format_outline("a.pdf", _secs(643), start=600)


def test_outline_points_to_the_table_of_contents_section() -> None:
    from arag.agent.ops import format_outline

    out = format_outline("a.pdf", _secs(5, toc_at=2))
    assert "目次の節「目 次」（p.2、ID: id-2）" in out and "read_section" in out
    # 最初の検索で目次の節を読むときは、この案内から ID を取る（specs/031 R11）
    from types import SimpleNamespace

    from arag.agent.ops import TOC_SECTION_ID

    sid = "49bc9475-3832-4e76-8400-a2792a4a25ff"
    toc = [SimpleNamespace(id=sid, level=1, heading_path="Contents", page_start=None, token_len=3)]
    m = TOC_SECTION_ID.search(format_outline("a.pdf", toc))
    assert m is not None and m.group(1) == sid


def test_filename_with_spaces_and_fullwidth_brackets_is_found_in_the_question() -> None:
    from arag.agent.ops import filename_in_question

    name = "Architect-Professional-学習ハンドブック（iPad 版）.pdf"
    assert filename_in_question(name, f"{name}\nこの資料の最後の章の内容を教えて")
    # 全角・半角、空白の有無、大文字小文字の違いは無視する
    assert filename_in_question(name, "architect-professional-学習ハンドブック(iPad版).PDF の目次")
    # 拡張子なしでも、十分長い名前なら
    assert filename_in_question(name, "Architect-Professional-学習ハンドブック（iPad 版）の最後の章")
    # 短い名前は拡張子なしでは照合しない（本文の語と偶然に一致する）
    assert not filename_in_question("a.md", "a の内容")
    assert filename_in_question("a.md", "a.md を要約して")
    assert not filename_in_question(name, "学習ハンドブックの最後の章")
