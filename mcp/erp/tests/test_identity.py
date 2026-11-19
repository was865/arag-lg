"""身元の JWT（specs/033 R8）: 宛先・期限・鍵の版。"""

import pytest

from erp_mcp.config import user_map
from erp_mcp.identity import IdentityError, issue, verify

from .conftest import KEY

OLD = "old-key-0123456789abcdef0123456789xx"


def test_kid_selects_key_and_rotation_accepts_both() -> None:
    keys = {"k2": KEY, "k1": OLD}
    assert (
        verify(f"Bearer {issue('u', ['保全課'], audience='erp', key=KEY, kid='k2')}", audience="erp", keys=keys).kid
        == "k2"
    )
    assert verify(f"Bearer {issue('u', [], audience='erp', key=OLD, kid='k1')}", audience="erp", keys=keys).kid == "k1"


def test_unknown_kid_wrong_aud_and_missing_are_rejected() -> None:
    keys = {"k1": KEY}
    with pytest.raises(IdentityError, match="知らない鍵"):
        verify(f"Bearer {issue('u', [], audience='erp', key=KEY, kid='k9')}", audience="erp", keys=keys)
    with pytest.raises(IdentityError):
        verify(f"Bearer {issue('u', [], audience='cmms', key=KEY)}", audience="erp", keys=keys)
    with pytest.raises(IdentityError):
        verify(None, audience="erp", keys=keys)
    with pytest.raises(IdentityError):
        verify(f"Bearer {issue('u', [], audience='erp', key=KEY, ttl_s=-5)}", audience="erp", keys=keys)


def test_token_without_kid_uses_default_key() -> None:
    import jwt

    tok = jwt.encode({"sub": "u", "aud": "erp", "iss": "arag", "exp": 9999999999}, KEY, algorithm="HS256")
    assert verify(f"Bearer {tok}", audience="erp", keys={"k1": KEY}).user_id == "u"


def test_departments_pick_erp_user() -> None:
    m = user_map()
    assert m.pick(frozenset({"購買課"})).login == "erp-kobai"
    g = m.pick(frozenset({"保全課"}))
    assert g.login == "erp-genba" and "unit_cost" in g.hide
    assert m.pick(frozenset()).login == "erp-viewer"
    assert m.pick(frozenset({"総務課"})).login == "erp-viewer"
