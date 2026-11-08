"""check_licenses の判定（R18）。"""

import json
from pathlib import Path

import pytest

from check_licenses import Dep, check, is_denied, main, parse_pnpm


@pytest.mark.parametrize(
    "license_text",
    [
        "AGPL-3.0-only",
        "GNU Affero General Public License v3",
        "GPL-3.0-or-later",
        "GNU General Public License v2 (GPLv2)",
        "SSPL-1.0",
        "BUSL-1.1",
        "Elastic-2.0",
        "LGPL-3.0-only",  # 許可リスト外の LGPL
    ],
)
def test_denied(license_text: str) -> None:
    assert is_denied(Dep("x", "1", license_text))


@pytest.mark.parametrize(
    "license_text",
    ["MIT", "Apache-2.0", "BSD-3-Clause", "ISC", "MPL-2.0", "Mozilla Public License 2.0 (MPL 2.0)",
     "CC-BY-4.0", "PSF-2.0", "MIT OR Apache-2.0", "The Unlicense (Unlicense)"],
)
def test_allowed(license_text: str) -> None:
    assert not is_denied(Dep("x", "1", license_text))


def test_allowlisted_lgpl_passes() -> None:
    assert not is_denied(Dep("psycopg", "3.3.8", "LGPL-3.0-only"))
    assert not is_denied(Dep("psycopg-binary", "3.3.8", "LGPL-3.0-only"))


def test_unknown_is_reported_but_self_is_ignored() -> None:
    denied, unknown = check([Dep("arag", "0.1.0", "UNKNOWN"), Dep("foo", "1", "UNKNOWN")])
    assert denied == []
    assert [d.name for d in unknown] == ["foo"]


def test_parse_pnpm() -> None:
    deps = parse_pnpm({"MIT": [{"name": "next", "versions": ["16.4.5"]}]})
    assert deps == [Dep("next", "16.4.5", "MIT")]


def test_main_exit_codes(tmp_path: Path) -> None:
    ok = tmp_path / "ok.json"
    ok.write_text(json.dumps([{"Name": "fastapi", "Version": "1", "License": "MIT"}]))
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"AGPL-3.0": [{"name": "evil", "versions": ["1"]}]}))
    assert main(["--pip", str(ok)]) == 0
    assert main(["--pip", str(ok), "--pnpm", str(bad)]) == 1
