"""API キーなどの秘密値の暗号化（specs/013-llm-keys R1）。

`ARAG_SECRET_KEY` に Fernet 鍵を置く。カンマ区切りで複数並べると先頭で暗号化し、
全部で復号する（鍵の入れ替え）。
"""

from cryptography.fernet import Fernet, InvalidToken, MultiFernet


class SecretBox:
    def __init__(self, keys: list[Fernet]) -> None:
        self._f = MultiFernet(keys)

    @classmethod
    def from_setting(cls, raw: str) -> "SecretBox | None":
        """空・不正な鍵なら None（登録を止める）。"""
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        if not parts:
            return None
        try:
            return cls([Fernet(p) for p in parts])
        except (ValueError, TypeError):
            return None

    def encrypt(self, plain: str) -> str:
        return self._f.encrypt(plain.encode()).decode()

    def decrypt(self, token: str) -> str:
        return self._f.decrypt(token.encode()).decode()

    def try_decrypt(self, token: str) -> str | None:
        try:
            return self.decrypt(token)
        except InvalidToken:
            return None

    @staticmethod
    def hint(plain: str) -> str | None:
        """画面に出す末尾 4 文字。"""
        return plain[-4:] if plain else None
