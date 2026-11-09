"""API キーの暗号化（specs/013-llm-keys R1・R2）。"""

from cryptography.fernet import Fernet

from arag.secrets import SecretBox


def test_roundtrip_and_ciphertext_hides_plaintext() -> None:
    box = SecretBox.from_setting(Fernet.generate_key().decode())
    assert box is not None
    enc = box.encrypt("sk-live-abcdef1234")
    assert "abcdef" not in enc
    assert box.decrypt(enc) == "sk-live-abcdef1234"


def test_rotation_decrypts_with_old_key_and_encrypts_with_new() -> None:
    old, new = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    enc_old = SecretBox.from_setting(old).encrypt("k1")  # type: ignore[union-attr]
    both = SecretBox.from_setting(f"{new}, {old}")
    assert both is not None
    assert both.decrypt(enc_old) == "k1"
    enc_new = both.encrypt("k2")
    assert SecretBox.from_setting(new).decrypt(enc_new) == "k2"  # type: ignore[union-attr]


def test_missing_or_invalid_key_disables() -> None:
    assert SecretBox.from_setting("") is None
    assert SecretBox.from_setting("not-a-fernet-key") is None


def test_decrypt_with_wrong_key_returns_none() -> None:
    a = SecretBox.from_setting(Fernet.generate_key().decode())
    b = SecretBox.from_setting(Fernet.generate_key().decode())
    assert a is not None and b is not None
    assert b.try_decrypt(a.encrypt("x")) is None


def test_hint() -> None:
    assert SecretBox.hint("sk-abcdef1234") == "1234"
    assert SecretBox.hint("ab") == "ab"
    assert SecretBox.hint("") is None
