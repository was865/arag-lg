"""ツールの結果の構造（specs/037 R5〜R7）。

モデルに渡す文（text）と、確認・記録が読む構造を分ける。確認はモデルに見せる文の言い回しを読まない。
構造は `ToolMessage.artifact` に dict で載せる（checkpoint に保存できる形）。
"""

from dataclasses import asdict, dataclass, field, replace
from typing import Any, Literal

Fallback = Literal["codes", "semantic"]


@dataclass(frozen=True)
class ToolOutput:
    text: str
    # 添えた資料（<資料 n=…>）の数
    materials: int = 0
    # 0 件か、関連度の低い資料だけ（最初の検索の空振りの判断。specs/026 T17）
    weak: bool = False
    # 章立ての中略・文書の打ち切りがある（省略の読み残しの確認。specs/031 R5）
    omitted: bool = False
    # keyword_search が広げた先（型番だけ・意味検索）
    fallback: Fallback | None = None
    # table_query: (表の行数, 当てはまった行数)
    rows: tuple[int, int] | None = field(default=None)

    def artifact(self) -> dict[str, Any]:
        out = asdict(self)
        del out["text"]
        out["rows"] = list(self.rows) if self.rows is not None else None
        return out

    @classmethod
    def from_artifact(cls, text: str, artifact: Any) -> "ToolOutput":
        """ToolMessage の文と artifact から作る。構造が無い（037 より前の記録・社内システム）ときは文だけ。"""
        if not isinstance(artifact, dict):
            return cls(text)
        rows = artifact.get("rows")
        fb = artifact.get("fallback")
        return cls(
            text,
            materials=int(artifact.get("materials") or 0),
            weak=bool(artifact.get("weak")),
            omitted=bool(artifact.get("omitted")),
            fallback=fb if fb in ("codes", "semantic") else None,
            rows=(int(rows[0]), int(rows[1])) if isinstance(rows, list | tuple) and len(rows) == 2 else None,
        )

    def prefixed(self, note: str) -> "ToolOutput":
        """文の前に注意を足す（構造はそのまま）。"""
        return replace(self, text=f"{note}\n\n{self.text}")
