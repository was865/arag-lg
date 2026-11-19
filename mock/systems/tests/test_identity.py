import time

import jwt
import pytest

from mock_systems.common import ISSUER, IdentityError, issue_identity, verify_identity

from .conftest import KEY


def test_roundtrip() -> None:
    tok = issue_identity("u1", ["保全課"], audience="erp", key=KEY)
    ident = verify_identity(f"Bearer {tok}", audience="erp", key=KEY)
    assert ident.user_id == "u1"
    assert ident.depts == frozenset({"保全課"})


@pytest.mark.parametrize(
    "header",
    [
        None,
        "Basic abc",
        f"Bearer {issue_identity('u1', [], audience='cmms', key=KEY)}",  # 宛先が違う
        f"Bearer {issue_identity('u1', [], audience='erp', key='other-key-0123456789abcdef0123456')}",  # 署名が違う
        "Bearer "
        + jwt.encode({"sub": "u1", "aud": "erp", "iss": ISSUER, "exp": int(time.time()) - 5}, KEY),  # 期限切れ
    ],
)
def test_rejects(header: str | None) -> None:
    with pytest.raises(IdentityError):
        verify_identity(header, audience="erp", key=KEY)
