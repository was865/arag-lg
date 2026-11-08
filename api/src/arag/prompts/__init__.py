"""プロンプト（日本語）。本文は同じディレクトリの .md に置く。"""

from functools import cache
from importlib.resources import files


@cache
def load_prompt(name: str) -> str:
    return files(__package__).joinpath(f"{name}.md").read_text(encoding="utf-8").strip()
