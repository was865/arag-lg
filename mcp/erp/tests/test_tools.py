"""ツールの層（specs/033 R3・R5・R9〜R13）を模擬のアダプタで確かめる。"""

import json
from pathlib import Path

import pytest

from erp_mcp.model import ErpUnavailable, PoQuery
from erp_mcp.ops import Breaker, Guard, TtlCache
from erp_mcp.tools import Service

from .conftest import who


async def _call(service: Service, tool: str, depts: tuple[str, ...] = ("購買課",), **kw):  # type: ignore[no-untyped-def]
    ident = who(*depts)
    produce = {
        "get_stock": lambda w: service.get_stock(w, kw["part"]),
        "find_parts": lambda w: service.find_parts(w, kw.get("term", ""), kw.get("status", "")),
        "po": lambda w: service.list_purchase_orders(w, PoQuery(**kw.get("q", {})), kw.get("overdue", False)),
        "moves": lambda w: service.list_stock_moves(w, kw["part"], None, None),
        "below": lambda w: service.list_below_reorder(w, kw.get("without_orders", False)),
    }[tool]
    args = {k: str(v) for k, v in kw.items() if k != "cursor"}
    return await service.call(ident, tool, args, produce, cursor=kw.get("cursor", ""))


async def test_stock_of_fixed_part_is_the_same_as_032(service: Service) -> None:
    out = await _call(service, "get_stock", part="P-1042")
    assert out["columns"][:7] == [
        "部品番号",
        "名称",
        "現在庫",
        "発注点",
        "発注点との比較",
        "未入荷の発注数",
        "最後の入出庫",
    ]
    assert out["rows"][0][:5] == ["P-1042", "シールキット SK-300", 15, 10, "発注点を満たしている"]
    assert out["fetched_at"].startswith("2026-11-18") and "取得" in out["basis"]
    assert out["trace"]["erp_user"] == "erp-kobai" and out["trace"]["backend"] == "mock"


async def test_below_reorder_lists_every_short_part_in_one_call(service: Service) -> None:
    """「今、発注点を下回っている部品は何件」を 1 回で答えられる（部品ごとに get_stock を呼ばせない）。"""
    out = await _call(service, "below")
    assert out["columns"][:5] == ["部品番号", "名称", "現在庫", "発注点", "不足"]
    nos = [r[0] for r in out["rows"]]
    assert out["total"] == len(nos) == 49
    assert "P-1043" in nos and "P-1042" not in nos
    assert all(r[2] < r[3] and r[4] == r[3] - r[2] for r in out["rows"])
    # 不足の大きい順（「不足の大きいものから 3 つ」をそのまま読める）
    short = [r[4] for r in out["rows"]]
    assert short == sorted(short, reverse=True)
    assert "49 件" in out["note"] and "廃止" in out["note"]


async def test_below_reorder_without_open_orders(service: Service) -> None:
    """「発注点を下回り、未入荷の発注も無い部品」をツールで絞る（デモの試走でモデルが 49 件全部をそう答えた）。"""
    every = await _call(service, "below")
    col = every["columns"].index("未入荷の発注数")
    assert all(isinstance(r[col], (int, float)) for r in every["rows"])
    want = [r[0] for r in every["rows"] if r[col] == 0]
    out = await _call(service, "below", without_orders=True)
    assert [r[0] for r in out["rows"]] == want and out["total"] == len(want) < 49
    assert f"未入荷の発注が無いものは {len(want)} 件" in every["note"]


async def test_purchase_order_by_number(service: Service) -> None:
    """発注番号で 1 件を引ける（「PO-2026-2241 は今どうなっていますか」）。"""
    out = await _call(service, "po", q={"po_no": "po-2026-2241 "})
    assert [r[0] for r in out["rows"]] == ["PO-2026-2241"]


async def test_stock_shows_purchase_unit(service: Service) -> None:
    """発注の単位（袋・箱）を在庫の単位と別に出す（「発注するときの単位は」に答えられる）。"""
    out = await _call(service, "get_stock", part="P-5052")
    row = dict(zip(out["columns"], out["rows"][0], strict=True))
    assert row["単位"] == "個" and row["発注の単位"] == "袋（50個）"
    parts = await _call(service, "find_parts", term="P-5052")
    assert dict(zip(parts["columns"], parts["rows"][0], strict=True))["発注の単位"] == "袋（50個）"


async def test_retired_part_names_successor(service: Service) -> None:
    out = await _call(service, "get_stock", part="P-4002")
    assert out["rows"][0][4] == "廃止（発注しない。後継 P-4001）"


async def test_unusable_warehouses_are_not_counted(service: Service) -> None:
    import sqlite3

    from .conftest import WORLD

    con = sqlite3.connect(WORLD)
    part = con.execute(
        "SELECT part_no FROM stock_moves WHERE warehouse = 'DEAD' GROUP BY part_no HAVING SUM(qty) > 0 LIMIT 1"
    ).fetchone()[0]
    usable = con.execute(
        "SELECT COALESCE(SUM(qty), 0) FROM stock_moves WHERE part_no = ? AND warehouse IN ('WH2', 'WH1')", (part,)
    ).fetchone()[0]
    out = await _call(service, "get_stock", part=part)
    row = next(r for r in out["rows"] if r[0] == part)
    assert row[2] == pytest.approx(usable)
    assert "DEAD" in row[8] and "数えない" in row[8]


async def test_too_many_parts_is_said_not_cut(service: Service) -> None:
    out = await _call(service, "get_stock", part="軸受")
    assert out["error"] == "too_many" and out["total"] > 30 and "絞" in out["hint"]


async def test_cost_is_hidden_for_genba_and_shown_for_kobai(service: Service) -> None:
    a = await _call(service, "po", q={"part": "MS-30"})
    assert "仕入単価（円）" in a["columns"] and "restricted" not in a
    b = await _call(service, "po", depts=("製造課",), q={"part": "MS-30"})
    assert "仕入単価（円）" not in b["columns"] and b["restricted"] == ["仕入単価（円）"]
    assert "購買課" in b["note"]


async def test_viewer_cannot_read_purchases(service: Service) -> None:
    out = await _call(service, "po", depts=("総務課",), q={})
    assert out["error"] == "forbidden" and out["trace"]["erp_user"] == "erp-viewer"


async def test_overdue_includes_fixed_late_po(service: Service) -> None:
    out = await _call(service, "po", q={"status": "未完了"}, overdue=True)
    nos = [r[0] for r in out["rows"]]
    assert "PO-2026-0436" in nos and "PO-2026-0433" not in nos
    row = next(r for r in out["rows"] if r[0] == "PO-2026-0436")
    assert "納期を過ぎて" in row[out["columns"].index("状態")]


async def test_pages_with_next_cursor(service: Service) -> None:
    first = await _call(service, "po", q={"status": "入荷済み"})
    assert first["total"] > 50 and len(first["rows"]) == 50 and first["next_cursor"] == "50"
    second = await _call(service, "po", q={"status": "入荷済み"}, cursor="50")
    assert second["rows"][0] != first["rows"][0] and second["trace"]["cached"] is True
    assert second["fetched_at"] == first["fetched_at"]  # 使い回しは元の取得の時点を書く（R13）


async def test_injection_in_term_is_only_a_value(service: Service) -> None:
    out = await _call(service, "find_parts", term="' OR 1=1 --")
    assert out["rows"] == [] and "当たる部品はありません" in out["note"]


async def test_audit_line_per_call(service: Service, tmp_path: Path) -> None:
    await _call(service, "get_stock", part="P-2011")
    await _call(service, "po", depts=("総務課",), q={})
    lines = [json.loads(x) for x in (tmp_path / "audit.jsonl").read_text().splitlines()]
    assert [x["result"] for x in lines] == ["ok", "forbidden"]
    assert {"trace", "user", "depts", "erp_user", "tool", "args", "rows", "ms", "kid"} <= set(lines[0])


async def test_breaker_opens_after_three_failures() -> None:
    t = [0.0]
    g = Guard(timeout_s=1, breaker=Breaker(threshold=3, cool_s=30, clock=lambda: t[0]))
    calls = 0

    async def down() -> None:
        nonlocal calls
        calls += 1
        raise ErpUnavailable("down")

    for _ in range(3):
        with pytest.raises(ErpUnavailable):
            await g.run(down)
    with pytest.raises(ErpUnavailable, match="止めています"):
        await g.run(down)
    assert calls == 3
    t[0] = 31
    with pytest.raises(ErpUnavailable, match="down"):
        await g.run(down)  # 半開き: 1 回だけ通す
    assert calls == 4 and g.breaker.state == "open"


async def test_timeout_is_unavailable() -> None:
    import asyncio

    g = Guard(timeout_s=0.05)

    async def slow() -> None:
        await asyncio.sleep(1)

    with pytest.raises(ErpUnavailable, match="秒以内"):
        await g.run(slow)


def test_cache_expires() -> None:
    t = [0.0]
    c = TtlCache(10, clock=lambda: t[0])
    c.put("k", 1)
    assert c.get("k") == 1
    t[0] = 11
    assert c.get("k") is None
