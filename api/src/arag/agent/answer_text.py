"""回答本文の後始末（引用の正規化のあと）。

小さいモデルは、箇条書きのあとに同じことを言い直す締めの段落を付けがち。
末尾の行が前のどれか 1 行とほぼ同じなら落とす。
誤って消さないよう、見るのは末尾だけ・表とコードがある回答は触らない。
"""

import re
import unicodedata

_CITE = re.compile(r"\[\d+\]")
_LIST = re.compile(r"^\s*(?:[-*•・]|\d+[.)．])\s*")
_LABEL = re.compile(r"^\*\*[^*]{1,30}\*\*\s*[:：]?")
_DROP = re.compile(r"[\s*_`#>。、，,.：:；;！!？?「」『』（）()\[\]【】・\-—]+")

MIN_CHARS = 15  # これより短い締め（「以上です。」など）は比べない
CONTAINED = 0.7  # 末尾の行の 2 文字組のうち、前の行にも出る割合


def _key(line: str) -> str:
    s = unicodedata.normalize("NFKC", line)
    s = _LIST.sub("", s)
    s = _LABEL.sub("", s)
    s = _CITE.sub("", s)
    return _DROP.sub("", s).casefold()


def _grams(s: str) -> set[str]:
    return {s[i : i + 2] for i in range(len(s) - 1)}


def _repeats(tail: str, earlier: list[str]) -> bool:
    t = _key(tail)
    if len(t) < MIN_CHARS:
        return False
    tg = _grams(t)
    for e in earlier:
        eg = _grams(_key(e))
        if eg and len(tg & eg) / len(tg) >= CONTAINED:
            return True
    return False


def drop_repeated_tail(text: str) -> str:
    """末尾の行が前の行の言い直しなら落とす（最大 2 行）。"""
    if "```" in text or re.search(r"^\s*\|", text, re.M):
        return text
    lines = text.rstrip().split("\n")
    for _ in range(2):
        body = [i for i, ln in enumerate(lines) if ln.strip()]
        if len(body) < 3:
            break
        last = body[-1]
        if not _repeats(lines[last], [lines[i] for i in body[:-1]]):
            break
        lines = lines[:last]
        while lines and not lines[-1].strip():
            lines.pop()
    out = "\n".join(lines)
    return out if out != text.rstrip() else text
