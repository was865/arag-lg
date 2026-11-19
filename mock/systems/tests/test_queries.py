"""問い合わせと権限（R2・R4・R16）。"""

from mock_systems import queries as q

from .conftest import who


def _col(res, name):  # type: ignore[no-untyped-def]
    i = res["columns"].index(name)
    return [r[i] for r in res["rows"]]


def test_stock_now_differs_from_ledger(con) -> None:  # type: ignore[no-untyped-def]
    res = q.get_stock(con("erp"), who("製造課"), "SK-300")
    assert _col(res, "現在庫") == [15]
    assert _col(res, "発注点との比較") == ["発注点を満たしている"]
    assert "取得" in res["basis"]
    res = q.get_stock(con("erp"), who(), "6309ZZ")
    assert _col(res, "現在庫") == [7]
    assert _col(res, "未入荷の発注数") == [6]
    assert _col(res, "発注点との比較") == ["発注点を下回っている"]


def test_obsolete_part(con) -> None:  # type: ignore[no-untyped-def]
    res = q.get_stock(con("erp"), who(), "KG-2")
    assert _col(res, "現在庫") == [0]
    assert _col(res, "発注点との比較") == ["廃止（発注しない）"]


def test_unit_cost_only_for_purchasing(con) -> None:  # type: ignore[no-untyped-def]
    res = q.list_purchase_orders(con("erp"), who("製造課"), part="6309ZZ")
    assert "仕入単価（円）" not in res["columns"]
    assert res["restricted"] == ["仕入単価（円）"]
    assert "3850" not in str(res)
    res = q.list_purchase_orders(con("erp"), who("購買課"), part="6309ZZ")
    assert _col(res, "仕入単価（円）") == [3850]
    assert "restricted" not in res


def test_overdue_and_open_orders(con) -> None:  # type: ignore[no-untyped-def]
    res = q.list_purchase_orders(con("erp"), who(), status="未入荷")
    assert _col(res, "発注番号") == ["PO-2026-0433", "PO-2026-0436"]
    assert _col(res, "状態") == ["発注済み", "発注済み（納期を過ぎて未入荷）"]


def test_work_orders_forbidden_outside_maintenance(con) -> None:  # type: ignore[no-untyped-def]
    res = q.list_work_orders(con("cmms"), who("購買課"))
    assert res["error"] == "forbidden"
    res = q.list_work_orders(con("cmms"), who("保全課"), status="未完了")
    assert _col(res, "作業指示番号") == ["WO-1107", "WO-1109"]


def test_work_records_with_procedure(con) -> None:  # type: ignore[no-untyped-def]
    res = q.list_work_records(con("cmms"), who(), equipment="AL-01", since="2026-10-01", until="2026-10-31")
    assert _col(res, "使った手順書") == ["HP-300分解手順書 第3版"]


def test_people_never_show_private_phone(con) -> None:  # type: ignore[no-untyped-def]
    res = q.find_people(con("directory"), who("保全課"), "保全課")
    assert "090-" not in str(res)
    assert "高梨 誠" in _col(res, "氏名")
    assert _col(q.find_people(con("directory"), who(), "高梨誠"), "内線") == ["2417"]
    assert _col(q.find_people(con("directory"), who(), "保全課長"), "氏名") == ["高梨 誠"]


def test_issues(con) -> None:  # type: ignore[no-untyped-def]
    res = q.search_issues(con("tickets"), who(), "品質会議", status="未完了")
    assert _col(res, "課題番号") == ["Q-003"]
    # 空白で区切った語は、すべてを含む課題（「PM-04 異音」で「PM-04 の異音」が当たる）
    assert _col(q.search_issues(con("tickets"), who(), "PM-04 異音"), "課題番号") == ["Q-004"]
    # 一覧に最新の経過（最後のコメント）を添える
    assert "0.4%" in _col(res, "最新の経過")[0]
    res = q.get_issue(con("tickets"), who(), "q-002")
    assert res["issue"]["状態"] == "完了"
    assert len(res["rows"]) == 2
