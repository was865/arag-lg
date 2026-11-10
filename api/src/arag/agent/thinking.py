"""モデルの「考えた過程」を回答から切り分ける。

思考の出し方はサーバーによって 2 通りある。
- 本文の先頭に `<think>…</think>` を書く（vLLM で reasoning parser を指定しないときの Qwen3 など）
- 本文とは別の欄で返す（`reasoning_content` / `reasoning`。vLLM の reasoning parser・DeepSeek）
どちらも回答には含めず、「考えた過程」のステップとして見せる。
"""

OPEN = "<think>"
CLOSE = "</think>"


def split_thinking(text: str) -> tuple[str, str]:
    """（考えた過程, 回答）に分ける。思考が無ければ（"", text）。"""
    s = text.lstrip()
    if s.startswith(OPEN):
        end = s.find(CLOSE)
        if end == -1:  # 考えている途中で終わった
            return s[len(OPEN) :].strip(), ""
        return s[len(OPEN) : end].strip(), s[end + len(CLOSE) :].lstrip()
    if CLOSE in text:  # 開始タグをチャットテンプレート側が書いた
        thinking, answer = text.split(CLOSE, 1)
        return thinking.strip(), answer.lstrip()
    return "", text


def _held_back(buf: str) -> int:
    """buf の末尾が閉じタグの書きかけなら、その長さ（次の断片を待つ）。"""
    for n in range(min(len(buf), len(CLOSE) - 1), 0, -1):
        if CLOSE.startswith(buf[-n:]):
            return n
    return 0


class ThinkSplitter:
    """ストリームの断片を（思考の差分, 回答の差分, 回答を取り消すか）に分ける。

    1 回のモデル呼び出しに 1 つ使う。
    """

    def __init__(self) -> None:
        self.state = "start"  # start → think → answer
        self.buf = ""
        self.answer = ""  # これまでに回答として出した分
        self.lstrip = False  # 思考の直後の空行は回答に含めない

    def feed(self, piece: str) -> tuple[str, str, bool]:
        if not piece:
            return "", "", False
        if self.state == "start":
            self.buf += piece
            s = self.buf.lstrip()
            if s.startswith(OPEN):
                self.state, self.buf = "think", ""
                return self._think(s[len(OPEN) :])
            if OPEN.startswith(s):  # まだ判断できない
                return "", "", False
            self.state, piece, self.buf = "answer", self.buf, ""
        if self.state == "think":
            return self._think(piece)
        return self._answer(piece)

    def _think(self, piece: str) -> tuple[str, str, bool]:
        self.buf += piece
        end = self.buf.find(CLOSE)
        if end == -1:
            keep = _held_back(self.buf)
            out = self.buf[: len(self.buf) - keep]
            self.buf = self.buf[len(self.buf) - keep :]
            return out, "", False
        thought, rest = self.buf[:end], self.buf[end + len(CLOSE) :]
        self.state, self.buf, self.lstrip = "answer", "", True
        _, answer, _ = self._answer(rest)
        return thought, answer, False

    def _answer(self, piece: str) -> tuple[str, str, bool]:
        if self.lstrip:
            piece = piece.lstrip()
            if not piece:
                return "", "", False
            self.lstrip = False
        joined = self.answer + piece
        if CLOSE in joined and OPEN not in joined:
            # 開始タグ無しで閉じタグが来た → ここまでの回答は思考だった
            thought, rest = joined.split(CLOSE, 1)
            self.answer = rest.lstrip()
            return thought, self.answer, True
        self.answer = joined
        return "", piece, False
