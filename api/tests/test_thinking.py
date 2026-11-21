"""考えた過程を回答から切り分ける。"""

import pytest

from arag.agent.domain.thinking import ThinkSplitter, split_thinking
from arag.llm import _reasoning_of, chat_model

QWEN = "<think>\nMX-17 の判定を確かめる。\n</think>\n\nMX-17 は停止候補です [1]。"


def test_split_thinking() -> None:
    assert split_thinking(QWEN) == ("MX-17 の判定を確かめる。", "MX-17 は停止候補です [1]。")
    assert split_thinking("回答だけ") == ("", "回答だけ")
    # 開始タグはテンプレート側（閉じタグだけが出る）
    assert split_thinking("考え中\n</think>\n\n回答") == ("考え中", "回答")
    # 考えている途中で打ち切られた
    assert split_thinking("<think>考え中") == ("考え中", "")
    # 思考を切ったときに空のタグが出ても回答は残る
    assert split_thinking("<think>\n\n</think>\n\n回答") == ("", "回答")


def run(pieces: list[str]) -> tuple[str, str, int]:
    sp = ThinkSplitter()
    thought = answer = ""
    resets = 0
    for p in pieces:
        t, a, reset = sp.feed(p)
        if reset:
            answer, resets = "", resets + 1
        thought, answer = thought + t, answer + a
    return thought.strip(), answer, resets


@pytest.mark.parametrize("size", [1, 2, 3, 5, 7, 100])
def test_splitter_handles_tags_split_across_chunks(size: int) -> None:
    pieces = [QWEN[i : i + size] for i in range(0, len(QWEN), size)]
    assert run(pieces) == ("MX-17 の判定を確かめる。", "MX-17 は停止候補です [1]。", 0)


def test_splitter_plain_answer_and_bare_close() -> None:
    assert run(["MX-17 は", "停止候補です。"]) == ("", "MX-17 は停止候補です。", 0)
    # 開始タグが無く閉じタグが後から来たら、それまでの回答を取り消して思考に回す
    assert run(["考え", "中</th", "ink>\n\n回答"]) == ("考え中", "回答", 1)
    # 「<」で始まる回答（表や HTML）は回答のまま
    assert run(["<", "b>太字</b>"]) == ("", "<b>太字</b>", 0)


def test_reasoning_field_is_read_from_server_responses() -> None:
    assert _reasoning_of({"reasoning_content": "考え"}) == "考え"
    assert _reasoning_of({"reasoning": "考え", "content": None}) == "考え"
    assert _reasoning_of({"content": "回答"}) is None
    m = chat_model("openai:qwen3-8b", base_url="http://gpu:8090/v1")
    chunk = {"choices": [{"index": 0, "delta": {"role": "assistant", "reasoning": "考え"}}]}
    gen = m._convert_chunk_to_generation_chunk(chunk, type(None), None)  # type: ignore[attr-defined]
    assert gen.message.additional_kwargs["reasoning_content"] == "考え"
