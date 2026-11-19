"""出力先 Odoo（specs/034 R6・R7・design §4）: 出来事を Odoo の業務の流れとして JSON-RPC で入れる。在庫は Odoo が計算する。

- 発注 → 承認（button_confirm）→ 入荷（受け入れの伝票を確定。分けた入荷は残りの伝票＝backorder）
- 受注 → 確定（action_confirm）→ 出荷（出荷の伝票を確定。分けた出荷も backorder）
- 払出し・製造の出入り・保全の出庫・廃棄・倉庫の移動は、種類ごとの運送の種類（stock.picking.type）の伝票
- 最初の在庫と 9 月末の棚卸は在庫の調整（stock.quant の inventory_quantity）

過去の日付（R7。T2 で実測）: Odoo は確定した時刻を「今」で記録するが、確定の後に
stock.picking.date_done・stock.move.date・stock.move.line.date・purchase.order.date_approve・sale.order.date_order を
出来事の日付に書き直せる。stock.quant.in_date（在庫の入った時刻）だけは流した日のまま残る（答えの計算では使わない）。
時刻は JST 10:00（UTC 01:00）にそろえる。

技術用の利用者（erp-kobai・erp-genba・erp-viewer）と管理者のパスワードは ERP_ODOO_SECRET から作る（mcp/erp と同じ作り方）。
"""

import hashlib
import hmac
import json
import os
import sys
import time
import urllib.request
from collections import defaultdict
from datetime import date
from typing import Any

from harukaze_sim.events import (
    Event,
    Move,
    PurchaseCancelled,
    PurchaseChanged,
    PurchaseOrdered,
    SalesCancelled,
    SalesOrdered,
)
from harukaze_sim.world import WAREHOUSES, World

# 種類 → 運送の種類の sequence_code（mcp/erp/config/odoo.yaml の kinds と対）
KIND_TYPES = {"出庫": "ISS", "製造出庫": "MCON", "製造入庫": "MPRD", "保全出庫": "MNT", "廃棄": "SCR", "移動": "INT"}
TYPE_NAMES = {"ISS": "払出し", "MCON": "製造出庫", "MPRD": "製造入庫", "MNT": "保全出庫", "SCR": "廃棄"}

# 利用者 → 権限の組（Odoo の xml id）。erp-viewer は購買の権限を持たない（発注は Odoo が拒否する）
USERS = {
    "erp-kobai": ["stock.group_stock_user", "purchase.group_purchase_user", "sales_team.group_sale_salesman_all_leads"],
    "erp-genba": ["stock.group_stock_user", "purchase.group_purchase_user", "sales_team.group_sale_salesman_all_leads"],
    "erp-viewer": ["stock.group_stock_user", "sales_team.group_sale_salesman_all_leads"],
}

UOMS = {"箱（100個）": 100, "袋（50個）": 50}


def password(login: str, secret: str | None = None) -> str:
    """技術用の利用者のパスワード（mcp/erp の odoo アダプタと同じ作り方）。"""
    secret = secret if secret is not None else os.environ.get("ERP_ODOO_SECRET", "")
    if not secret:
        raise SystemExit("ERP_ODOO_SECRET を設定してください（.env）")
    return hmac.new(secret.encode(), f"odoo:{login}".encode(), hashlib.sha256).hexdigest()[:32]


def ts(day: date) -> str:
    return f"{day.isoformat()} 01:00:00"


class Rpc:
    def __init__(self, url: str, db: str) -> None:
        self.url, self.db = url.rstrip("/") + "/jsonrpc", db
        self.uid = 0
        self.pw = ""
        self.calls = 0

    def raw(self, service: str, method: str, *args: Any) -> Any:
        body = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {"service": service, "method": method, "args": list(args)},
        }
        req = urllib.request.Request(self.url, json.dumps(body).encode(), {"content-type": "application/json"})
        self.calls += 1
        with urllib.request.urlopen(req, timeout=300) as r:
            out = json.load(r)
        if "error" in out:
            raise RuntimeError(out["error"].get("data", {}).get("message") or out["error"])
        return out.get("result")

    def login(self, login: str, pw: str) -> bool:
        uid = self.raw("common", "login", self.db, login, pw)
        if uid:
            self.uid, self.pw = uid, pw
        return bool(uid)

    def x(self, model: str, method: str, *args: Any, **kw: Any) -> Any:
        kw.setdefault("context", {}).setdefault("lang", "ja_JP")
        return self.raw("object", "execute_kw", self.db, self.uid, self.pw, model, method, list(args), kw)

    def ref(self, xmlid: str) -> int:
        mod, name = xmlid.split(".")
        r = self.x("ir.model.data", "search_read", [["module", "=", mod], ["name", "=", name]], fields=["res_id"])
        return int(r[0]["res_id"])


class Loader:
    def __init__(self, rpc: Rpc, world: World) -> None:
        self.r, self.w = rpc, world
        self.product: dict[str, int] = {}
        self.partner: dict[str, int] = {}
        self.wh: dict[str, dict[str, int]] = {}
        self.types: dict[tuple[str, str], int] = {}
        self.po: dict[str, int] = {}
        self.po_part: dict[str, str] = {}
        self.po_cost: dict[str, int] = {}
        self.so: dict[str, int] = {}
        self.loc_production = 0
        self.loc_scrap = 0
        self.loc_customer = 0
        self.loc_inventory = 0

    # ── 準備 ──

    def setup(self) -> None:
        r = self.r
        self._fields()
        uom_unit = r.ref("uom.product_uom_unit")
        cat_unit = r.x("uom.uom", "read", [uom_unit], ["category_id"])[0]["category_id"][0]
        self.uom = {"個": uom_unit, "kg": r.ref("uom.product_uom_kgm")}
        self.uom_ratio: dict[int, float] = {}
        for name, ratio in UOMS.items():
            self.uom[name] = self._get_or_create(
                "uom.uom", [["name", "=", name]],
                {"name": name, "category_id": cat_unit, "uom_type": "bigger", "factor_inv": ratio, "rounding": 1},
            )  # fmt: skip
            self.uom_ratio[self.uom[name]] = ratio
        for name in ("缶", "台"):
            self.uom[name] = self._get_or_create(
                "uom.uom", [["name", "=", name]],
                {"name": name, "category_id": cat_unit, "uom_type": "bigger", "factor_inv": 1, "rounding": 1},
            )  # fmt: skip
        self.loc_production = int(r.x("stock.location", "search", [["usage", "=", "production"]], limit=1)[0])
        self.loc_scrap = int(
            r.x("stock.location", "search", [["usage", "=", "inventory"], ["scrap_location", "=", True]], limit=1)[0]
        )
        self.loc_inventory = int(
            r.x("stock.location", "search", [["usage", "=", "inventory"], ["scrap_location", "=", False]], limit=1)[0]
        )
        self.loc_customer = r.ref("stock.stock_location_customers")
        self._warehouses()
        self._users()

    def _fields(self) -> None:
        r = self.r
        for model, name, label, ttype in [
            ("product.template", "x_name_en", "英名", "char"),
            ("product.template", "x_models", "適用機種", "char"),
            ("product.template", "x_successor", "後継の部品", "char"),
            ("product.template", "x_retired_on", "廃止の日", "date"),
            ("res.partner", "x_contact", "先方の担当者", "char"),
        ]:
            mid = r.x("ir.model", "search", [["model", "=", model]])[0]
            if not r.x("ir.model.fields", "search", [["model", "=", model], ["name", "=", name]]):
                r.x("ir.model.fields", "create", {
                    "model_id": mid, "name": name, "field_description": label, "ttype": ttype, "state": "manual",
                })  # fmt: skip

    def _get_or_create(self, model: str, domain: list[Any], vals: dict[str, Any]) -> int:
        found = self.r.x(model, "search", domain, limit=1)
        return int(found[0]) if found else int(self.r.x(model, "create", vals))

    def _warehouses(self) -> None:
        r = self.r
        default = r.x("stock.warehouse", "search", [], limit=1)[0]
        for code, name, _usable, _plant in WAREHOUSES:
            ids = r.x("stock.warehouse", "search", [["code", "=", code]])
            if ids:
                wid = ids[0]
            elif code == "WH2":
                wid = default
                r.x("stock.warehouse", "write", [wid], {"code": code, "name": name})
            else:
                wid = r.x("stock.warehouse", "create", {"code": code, "name": name})
            w = r.x("stock.warehouse", "read", [wid], ["lot_stock_id", "in_type_id", "out_type_id", "int_type_id"])[0]
            self.wh[code] = {
                "id": wid, "stock": w["lot_stock_id"][0], "IN": w["in_type_id"][0], "OUT": w["out_type_id"][0],
                "INT": w["int_type_id"][0],
            }  # fmt: skip
            for seq, label in TYPE_NAMES.items():
                code_kind = "incoming" if seq == "MPRD" else "outgoing"
                src = self.loc_production if seq == "MPRD" else w["lot_stock_id"][0]
                dst = {
                    "MPRD": w["lot_stock_id"][0], "SCR": self.loc_scrap,
                }.get(seq, self.loc_production)  # fmt: skip
                self.types[(code, seq)] = self._get_or_create(
                    "stock.picking.type",
                    [["warehouse_id", "=", wid], ["sequence_code", "=", seq]],
                    {"name": label, "code": code_kind, "sequence_code": seq, "warehouse_id": wid,
                     "default_location_src_id": src, "default_location_dest_id": dst},
                )  # fmt: skip
            self.types[(code, "INT")] = w["int_type_id"][0]

    def _users(self) -> None:
        r = self.r
        for login, groups in USERS.items():
            gids = [r.ref(g) for g in groups] + [r.ref("base.group_user")]
            vals = {"name": login, "login": login, "password": password(login), "groups_id": [(6, 0, gids)]}
            ids = r.x("res.users", "search", [["login", "=", login]])
            if ids:
                r.x("res.users", "write", ids, vals)
            else:
                r.x("res.users", "create", vals)

    # ── 骨格 ──

    def masters(self) -> None:
        r = self.r
        cats: dict[str, int] = {}
        for p in self.w.parts.values():
            if p.category not in cats:
                cats[p.category] = self._get_or_create(
                    "product.category", [["name", "=", p.category]], {"name": p.category}
                )
        for s in self.w.suppliers.values():
            self.partner[s.code] = self._get_or_create(
                "res.partner", [["ref", "=", s.code]],
                {"name": s.name, "ref": s.code, "city": s.location, "x_contact": s.contact, "is_company": True,
                 "supplier_rank": 1},
            )  # fmt: skip
        for c in self.w.customers.values():
            self.partner[c.code] = self._get_or_create(
                "res.partner", [["ref", "=", c.code]],
                {"name": c.name, "ref": c.code, "city": c.location, "is_company": True, "customer_rank": 1},
            )  # fmt: skip
        existing = {
            x["default_code"]: x["id"]
            for x in r.x("product.product", "search_read", [["default_code", "!=", False]], fields=["default_code"])
        }
        for p in self.w.parts.values():
            if p.part_no in existing:
                self.product[p.part_no] = existing[p.part_no]
                continue
            vals: dict[str, Any] = {
                "name": p.name, "default_code": p.part_no, "type": "consu", "is_storable": True,
                "uom_id": self.uom[p.uom], "uom_po_id": self.uom[p.purchase_uom], "standard_price": p.std_price,
                "list_price": p.std_price, "categ_id": cats[p.category], "x_name_en": p.name_en,
                "x_models": p.models, "x_successor": p.successor or False,
                "x_retired_on": p.retired_on.isoformat() if p.retired_on else False,
                "purchase_ok": p.category != "製品", "sale_ok": p.sellable,
            }  # fmt: skip
            if p.supplier_code:
                sup = self.w.suppliers[p.supplier_code]
                vals["seller_ids"] = [(0, 0, {"partner_id": self.partner[sup.code], "delay": sup.lead_days,
                                               "price": p.std_price * p.purchase_ratio})]  # fmt: skip
            pid = int(r.x("product.product", "create", vals))
            self.product[p.part_no] = pid
            r.x("product.product", "write", [pid], {"name": p.name_en}, context={"lang": "en_US"})
            if p.reorder_point and p.category != "製品":
                wh = self.wh[p.warehouse]
                r.x("stock.warehouse.orderpoint", "create", {
                    "product_id": pid, "warehouse_id": wh["id"], "location_id": wh["stock"], "trigger": "manual",
                    "product_min_qty": p.reorder_point, "product_max_qty": p.reorder_point * 2,
                })  # fmt: skip

    # ── 出来事 ──

    def inventory(self, day: date, moves: list[Move]) -> None:
        r = self.r
        qids = []
        for m in moves:
            qid = r.x(
                "stock.quant", "create",
                {"product_id": self.product[m.part], "location_id": self.wh[m.warehouse]["stock"],
                 "inventory_quantity": m.qty},
                context={"inventory_mode": True},
            )  # fmt: skip
            qids.append(qid)
        last = r.x("stock.move.line", "search", [], order="id desc", limit=1)
        r.x("stock.quant", "action_apply_inventory", qids, context={"inventory_name": moves[0].ref})
        mls = r.x("stock.move.line", "search", [["id", ">", last[0] if last else 0], ["is_inventory", "=", True]])
        mvs = r.x("stock.move", "search", [["move_line_ids", "in", mls]])
        r.x("stock.move.line", "write", mls, {"date": ts(day)})
        r.x("stock.move", "write", mvs, {"date": ts(day)})

    def purchase(self, ev: PurchaseOrdered) -> None:
        p = self.w.parts[ev.part]
        vals = {
            "name": ev.po_no, "partner_id": self.partner[ev.supplier], "date_order": ts(ev.day),
            "picking_type_id": self.wh[ev.warehouse]["IN"], "notes": ev.note or False,
            "order_line": [(0, 0, {
                "product_id": self.product[ev.part], "product_qty": ev.qty, "product_uom": self.uom[p.purchase_uom],
                "price_unit": ev.unit_cost, "date_planned": ts(ev.due_on), "name": p.name,
            })],
        }  # fmt: skip
        oid = int(self.r.x("purchase.order", "create", vals))
        self.r.x("purchase.order", "button_confirm", [oid])
        self.r.x("purchase.order", "write", [oid], {"date_approve": ts(ev.day), "date_order": ts(ev.day)})
        self.po[ev.po_no] = oid
        self.po_part[ev.po_no] = ev.part
        self.po_cost[ev.po_no] = ev.unit_cost

    def purchase_changed(self, ev: PurchaseChanged) -> None:
        """発注の数を変える。Odoo 18 は入荷の前に数を減らすと「仕入先への返品」の伝票を作るので、
        それを取り消し、残りの入荷の伝票の数を新しい数に合わせる（模擬器の出来事は「数を変えた」だけ）。"""
        r = self.r
        oid = self.po[ev.po_no]
        lines = r.x("purchase.order.line", "search", [["order_id", "=", oid]])
        # 数を変えると Odoo は仕入先の価格表から単価を引き直すので、発注のときの単価を書き戻す
        r.x("purchase.order.line", "write", lines, {"product_qty": ev.qty, "price_unit": self.po_cost[ev.po_no]})
        rets = r.x(
            "stock.picking", "search",
            [["purchase_id", "=", oid], ["picking_type_code", "=", "outgoing"], ["state", "not in", ["done", "cancel"]]],
        )  # fmt: skip
        if rets:
            r.x("stock.picking", "action_cancel", rets)
        ratio = self.w.parts[self.po_part[ev.po_no]].purchase_ratio
        moves = r.x(
            "stock.move", "search_read",
            [["purchase_line_id", "in", lines], ["picking_code", "=", "incoming"], ["state", "!=", "cancel"]],
            fields=["id", "state", "product_uom", "quantity", "product_uom_qty"],
        )  # fmt: skip
        done = sum(m["quantity"] * self.uom_ratio.get(m["product_uom"][0], 1) for m in moves if m["state"] == "done")
        left = ev.qty * ratio - done
        for m in moves:
            if m["state"] != "done":
                r.x(
                    "stock.move",
                    "write",
                    [m["id"]],
                    {"product_uom_qty": left / self.uom_ratio.get(m["product_uom"][0], 1)},
                )
                left = 0

    def purchase_cancelled(self, ev: PurchaseCancelled) -> None:
        self.r.x("purchase.order", "button_cancel", [self.po[ev.po_no]])

    def sale(self, ev: SalesOrdered) -> None:
        vals = {
            "name": ev.so_no, "partner_id": self.partner[ev.customer], "date_order": ts(ev.day),
            "commitment_date": ts(ev.due_on), "note": ev.note or False,
            "warehouse_id": self.wh["WH2"]["id"],
            "order_line": [(0, 0, {"product_id": self.product[ev.part], "product_uom_qty": ev.qty,
                                   "price_unit": ev.unit_price})],
        }  # fmt: skip
        oid = int(self.r.x("sale.order", "create", vals))
        self.r.x("sale.order", "action_confirm", [oid])
        self.r.x("sale.order", "write", [oid], {"date_order": ts(ev.day)})
        self.so[ev.so_no] = oid

    def sale_cancelled(self, ev: SalesCancelled) -> None:
        self.r.x("sale.order", "action_cancel", [self.so[ev.so_no]], context={"disable_cancel_warning": True})

    def _open_picking(self, field: str, order_id: int) -> int:
        code = "incoming" if field == "purchase_id" else "outgoing"
        ids = self.r.x(
            "stock.picking", "search",
            [[field, "=", order_id], ["picking_type_code", "=", code], ["state", "not in", ["done", "cancel"]]],
            order="id",
        )  # fmt: skip
        if not ids:
            raise RuntimeError(f"{field}={order_id} に残りの伝票がありません")
        return int(ids[0])

    def validate(self, pick: int, qty_by_product: dict[int, float], day: date, ref: str = "") -> None:
        """伝票を数量（在庫の単位）で済みにする。移動の単位が箱・袋なら換算する（Odoo 18 の入荷は在庫の単位）。"""
        r = self.r
        moves = r.x(
            "stock.move", "search_read", [["picking_id", "=", pick]], fields=["id", "product_id", "product_uom"]
        )
        for mv in moves:
            q = qty_by_product.get(mv["product_id"][0], 0.0) / self.uom_ratio.get(mv["product_uom"][0], 1)
            r.x("stock.move", "write", [mv["id"]], {"quantity": q, "picked": True})
        res = r.x("stock.picking", "button_validate", [pick], context={"skip_sms": True})
        if isinstance(res, dict) and res.get("res_model") == "stock.backorder.confirmation":
            ctx = res.get("context", {})
            wiz = r.x("stock.backorder.confirmation", "create", {"pick_ids": [(6, 0, [pick])]}, context=ctx)
            r.x("stock.backorder.confirmation", "process", [wiz], context=ctx)
        vals: dict[str, Any] = {"date_done": ts(day)}
        if ref:
            vals["origin"] = ref
        r.x("stock.picking", "write", [pick], vals)
        done = r.x("stock.move", "search", [["picking_id", "=", pick], ["state", "=", "done"]])
        r.x("stock.move", "write", done, {"date": ts(day)})
        mls = r.x("stock.move.line", "search", [["picking_id", "=", pick]])
        r.x("stock.move.line", "write", mls, {"date": ts(day)})

    def receive(self, m: Move) -> None:
        pick = self._open_picking("purchase_id", self.po[m.po_no])
        self.validate(pick, {self.product[m.part]: m.qty}, m.day)

    def ship(self, m: Move) -> None:
        pick = self._open_picking("sale_id", self.so[m.so_no])
        self.validate(pick, {self.product[m.part]: -m.qty}, m.day)

    def internal(self, day: date, kind: str, wh: str, ref: str, note: str, moves: list[Move]) -> None:
        """払出し・製造・保全・廃棄（1 つの伝票に部品をまとめる）。"""
        seq = KIND_TYPES[kind]
        tid = self.types[(wh, seq)]
        stock = self.wh[wh]["stock"]
        src, dst = (
            (self.loc_production, stock)
            if seq == "MPRD"
            else (stock, self.loc_scrap if seq == "SCR" else self.loc_production)
        )
        lines = []
        qty: dict[int, float] = defaultdict(float)
        for m in moves:
            pid = self.product[m.part]
            qty[pid] += abs(m.qty)
        for pid, q in qty.items():
            lines.append((0, 0, {"product_id": pid, "product_uom_qty": q, "name": ref, "location_id": src,
                                 "location_dest_id": dst}))  # fmt: skip
        pick = int(self.r.x("stock.picking", "create", {
            "picking_type_id": tid, "location_id": src, "location_dest_id": dst, "origin": ref,
            "note": note or False, "move_ids": lines, "scheduled_date": ts(day),
        }))  # fmt: skip
        self.r.x("stock.picking", "action_confirm", [pick])
        self.validate(pick, dict(qty), day, ref)

    def transfer(self, day: date, ref: str, note: str, out: Move, into: Move) -> None:
        src, dst = self.wh[out.warehouse]["stock"], self.wh[into.warehouse]["stock"]
        pid = self.product[out.part]
        pick = int(self.r.x("stock.picking", "create", {
            "picking_type_id": self.types[(out.warehouse, "INT")], "location_id": src, "location_dest_id": dst,
            "origin": ref, "note": note or False, "scheduled_date": ts(day),
            "move_ids": [(0, 0, {"product_id": pid, "product_uom_qty": into.qty, "name": ref, "location_id": src,
                                 "location_dest_id": dst})],
        }))  # fmt: skip
        self.r.x("stock.picking", "action_confirm", [pick])
        self.validate(pick, {pid: into.qty}, day, ref)

    def events(self, events: list[Event], *, progress: bool = True) -> None:
        by_day: dict[date, list[Event]] = defaultdict(list)
        for ev in events:
            by_day[ev.day].append(ev)
        t0 = time.time()
        for i, day in enumerate(sorted(by_day)):
            evs = by_day[day]
            inv = [e for e in evs if isinstance(e, Move) and e.kind == "棚卸"]
            if inv:
                self.inventory(day, inv)
            groups: dict[tuple[str, str, str], list[Move]] = defaultdict(list)
            for ev in evs:
                if isinstance(ev, PurchaseOrdered):
                    self.purchase(ev)
                elif isinstance(ev, PurchaseChanged):
                    self.purchase_changed(ev)
                elif isinstance(ev, PurchaseCancelled):
                    self.purchase_cancelled(ev)
                elif isinstance(ev, SalesOrdered):
                    self.sale(ev)
                elif isinstance(ev, SalesCancelled):
                    self.sale_cancelled(ev)
                elif isinstance(ev, Move) and ev.kind != "棚卸":
                    if ev.po_no and ev.kind == "入庫":
                        self.receive(ev)
                    elif ev.so_no and ev.kind == "出庫":
                        self.ship(ev)
                    else:
                        groups[(ev.kind, ev.warehouse if ev.kind != "移動" else "", ev.ref)].append(ev)
            for (kind, wh, ref), ms in groups.items():
                if kind == "移動":
                    out = next(m for m in ms if m.qty < 0)
                    into = next(m for m in ms if m.qty > 0)
                    self.transfer(day, ref, out.note, out, into)
                else:
                    self.internal(day, kind, wh, ref, ms[0].note, ms)
            if progress and i % 10 == 0:
                print(
                    f"{day} 済み（呼び出し {self.r.calls} 回・{time.time() - t0:.0f} 秒）", file=sys.stderr, flush=True
                )


def load(world: World, events: list[Event], *, url: str, db: str) -> int:
    rpc = Rpc(url, db)
    admin = password("admin")
    if not rpc.login("admin", admin):
        if not rpc.login("admin", "admin"):
            raise SystemExit("Odoo の管理者で入れません")
        rpc.x("res.users", "write", [rpc.uid], {"password": admin})
        rpc.login("admin", admin)
    if rpc.x("purchase.order", "search_count", []):
        raise SystemExit("Odoo にすでに発注があります。make erp-init で作り直してから流してください")
    loader = Loader(rpc, world)
    loader.setup()
    loader.masters()
    print(f"骨格を入れました（呼び出し {rpc.calls} 回）", file=sys.stderr)
    loader.events(events)
    print(f"入れ終えました（呼び出し {rpc.calls} 回）", file=sys.stderr)
    return 0
