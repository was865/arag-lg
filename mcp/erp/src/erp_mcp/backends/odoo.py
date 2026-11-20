"""Odoo のアダプタ（specs/033 R4〜R7・R9〜R10・R12・R15、design §2）。JSON-RPC（/jsonrpc の execute_kw）で読む。

- 条件（domain）は型の付いた引数からコードが組み立てる。利用者の語は ilike の値としてだけ使う（R4）。
- 結果はページ（page_size 行）ごとに上限まですべて取る。上限を超えたら TooMany（R5）。
- 部門ごとの技術用の利用者（users.yaml の login）で入る。読めない記録は Odoo が AccessError を返す → ErpForbidden（R9・R10）。
- 接続は httpx.AsyncClient を 1 つ持ち回す（keep-alive。R15）。
- 項目の対応は config/odoo.yaml（R7）。日時は Odoo の UTC を JST の日付に直す。
"""

import hashlib
import hmac
import os
import re
import time
from datetime import date, datetime, timedelta
from typing import Any

import httpx

from erp_mcp import querylog
from erp_mcp.clock import today
from erp_mcp.model import (
    ErpError,
    ErpForbidden,
    ErpUnavailable,
    ErpUser,
    Fetch,
    Health,
    LastMoves,
    MoveRec,
    Part,
    PoLine,
    PoQuery,
    SoLine,
    SoQuery,
    StockLine,
    Supplier,
    TooMany,
)

JST = timedelta(hours=9)


def password(login: str, secret: str) -> str:
    """技術用の利用者のパスワード（sim の Odoo の出力先と同じ作り方）。"""
    return hmac.new(secret.encode(), f"odoo:{login}".encode(), hashlib.sha256).hexdigest()[:32]


def _jst_day(s: str | bool | None) -> date | None:
    if not s or not isinstance(s, str):
        return None
    dt = datetime.fromisoformat(s.replace(" ", "T"))
    return (dt + JST).date() if len(s) > 10 else dt.date()


def _utc(d: date, end: bool = False) -> str:
    """JST の日付の始まり（end なら終わり）を Odoo の UTC の文字列にする。"""
    start = datetime.combine(d, datetime.min.time()) - JST
    if end:
        start += timedelta(days=1, seconds=-1)
    return start.strftime("%Y-%m-%d %H:%M:%S")


def _text(html: str | bool | None) -> str:
    if not html or not isinstance(html, str):
        return ""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


def _m2o(v: Any) -> tuple[int, str] | None:
    return (int(v[0]), str(v[1])) if isinstance(v, list) and v else None


class OdooBackend:
    name = "odoo"

    def __init__(
        self, url: str, db: str, secret: str, cfg: dict[str, Any], *, client: httpx.AsyncClient | None = None
    ) -> None:
        self.url, self.db, self.secret, self.cfg = url.rstrip("/") + "/jsonrpc", db, secret, cfg
        self.page = int(cfg.get("page_size", 200))
        self.usable = frozenset(cfg.get("usable_warehouses") or [])
        self.kinds: dict[str, str] = cfg.get("kinds") or {}
        self.uom_names: dict[str, str] = cfg.get("uom_names") or {}
        self.http = client or httpx.AsyncClient(timeout=30, limits=httpx.Limits(max_keepalive_connections=8))
        self.uids: dict[str, int] = {}
        self._wh: dict[int, str] | None = None
        self._loc_wh: dict[int, str] | None = None
        self._types: dict[int, str] | None = None

    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> "OdooBackend":
        secret = os.environ.get("ERP_ODOO_SECRET", "")
        if not secret:
            raise SystemExit("ERP_ODOO_SECRET を設定してください")
        return cls(cfg["url"], cfg["db"], secret, cfg)

    # ── JSON-RPC ──

    async def _rpc(self, service: str, method: str, *args: Any) -> Any:
        body = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {"service": service, "method": method, "args": list(args)},
        }
        try:
            r = await self.http.post(self.url, json=body)
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise ErpUnavailable(f"Odoo に接続できません（{type(e).__name__}）") from e
        out = r.json()
        if "error" in out:
            data = out["error"].get("data") or {}
            name, msg = str(data.get("name") or ""), str(data.get("message") or out["error"].get("message"))
            if "AccessError" in name or "AccessDenied" in name:
                raise ErpForbidden(f"Odoo の権限で読めません: {msg.splitlines()[0][:200]}")
            raise ErpError(f"Odoo のエラー: {msg.splitlines()[0][:200]}")
        return out.get("result")

    async def _uid(self, who: ErpUser) -> int:
        if who.login not in self.uids:
            uid = await self._rpc("common", "login", self.db, who.login, password(who.login, self.secret))
            if not uid:
                raise ErpForbidden(f"Odoo に利用者 {who.login} で入れません")
            self.uids[who.login] = int(uid)
        return self.uids[who.login]

    async def _x(self, who: ErpUser, model: str, method: str, *args: Any, **kw: Any) -> Any:
        uid = await self._uid(who)
        kw.setdefault("context", {"lang": "ja_JP", "tz": "Asia/Tokyo"})
        pw = password(who.login, self.secret)
        t0 = time.perf_counter()
        out = await self._rpc("object", "execute_kw", self.db, uid, pw, model, method, list(args), kw)
        # 問い合わせを記録する（specs/036 R3・R4）。pw・context は入れない。認証（login）は _x を通らない
        shown = [repr(a) for a in args] + [f"{k}={v!r}" for k, v in kw.items() if k != "context"]
        rows = len(out) if isinstance(out, list) else (out if isinstance(out, int) else None)
        querylog.add("odoo", f"{model}.{method}({', '.join(shown)})", querylog.since(t0), rows)
        return out

    async def _all(
        self,
        who: ErpUser,
        model: str,
        domain: list[Any],
        fields: list[str] | tuple[str, ...],
        cap: int,
        hint: str,
        order: str = "id",
    ) -> tuple[list[dict[str, Any]], int]:
        """上限までページごとにすべて取る（R5）。戻り値は（記録, 呼び出しの数）。"""
        total = int(await self._x(who, model, "search_count", domain))
        if total > cap:
            raise TooMany(total, cap, hint)
        out: list[dict[str, Any]] = []
        calls = 1
        while len(out) < total:
            batch = await self._x(
                who, model, "search_read", domain, fields=list(fields), offset=len(out), limit=self.page, order=order
            )
            calls += 1
            if not batch:
                break
            out += batch
        return out, calls

    # ── 対応表（倉庫・場所・運送の種類）──

    async def _maps(self, who: ErpUser) -> None:
        if self._wh is not None:
            return
        whs = await self._x(who, "stock.warehouse", "search_read", [], fields=["code"])
        self._wh = {int(w["id"]): str(w["code"]) for w in whs}
        locs = await self._x(
            who, "stock.location", "search_read", [["usage", "=", "internal"]], fields=["warehouse_id"]
        )
        self._loc_wh = {int(x["id"]): self._wh.get(int(x["warehouse_id"][0]), "") for x in locs if x["warehouse_id"]}
        types = await self._x(who, "stock.picking.type", "search_read", [], fields=["sequence_code"])
        self._types = {int(t["id"]): str(t["sequence_code"]) for t in types}

    async def _products(self, who: ErpUser, part_nos: list[str]) -> dict[int, str]:
        rows = await self._x(
            who, "product.product", "search_read", [["default_code", "in", part_nos]], fields=["default_code"]
        )
        return {int(r["id"]): str(r["default_code"]) for r in rows}

    def _uom(self, v: Any) -> str:
        m = _m2o(v)
        return self.uom_names.get(m[1], m[1]) if m else ""

    # ── 端口 ──

    async def find_parts(self, who: ErpUser, term: str, status: str, cap: int) -> Fetch[Part]:
        domain: list[Any] = [["default_code", "!=", False]]
        if term.strip():
            t = term.strip()
            domain += ["|", "|", "|", ["default_code", "ilike", t], ["name", "ilike", t], ["x_name_en", "ilike", t],
                       ["x_models", "ilike", t]]  # fmt: skip
        d = today().isoformat()
        if status == "廃止":
            domain += [["x_retired_on", "<=", d]]
        elif status == "通常":
            domain += ["|", ["x_retired_on", "=", False], ["x_retired_on", ">", d]]
        fields = ["default_code", "name", "x_name_en", "x_models", "categ_id", "uom_id", "uom_po_id", "x_successor",
                  "x_retired_on", "seller_ids"]  # fmt: skip
        if "std_price" not in who.hide:
            fields.append("standard_price")
        rows, calls = await self._all(
            who, "product.product", domain, fields, cap, "部品番号・名称の一部・状態で絞ってください", "default_code"
        )
        ids = [int(r["id"]) for r in rows]
        sellers: dict[int, tuple[str, str]] = {}
        rops: dict[int, float] = {}
        if ids:
            infos = await self._x(
                who, "product.supplierinfo", "search_read", [["product_tmpl_id.product_variant_ids", "in", ids]],
                fields=["product_tmpl_id", "partner_id", "sequence"], order="sequence, id",
            )  # fmt: skip
            pids = sorted({int(i["partner_id"][0]) for i in infos})
            refs = {
                int(p["id"]): (str(p["ref"] or ""), str(p["name"]))
                for p in await self._x(who, "res.partner", "read", pids, fields=["ref", "name"])
            }
            tmpl_seller: dict[int, tuple[str, str]] = {}
            for i in infos:
                tmpl_seller.setdefault(int(i["product_tmpl_id"][0]), refs[int(i["partner_id"][0])])
            tmpls = await self._x(who, "product.product", "read", ids, fields=["product_tmpl_id"])
            for t in tmpls:
                if int(t["product_tmpl_id"][0]) in tmpl_seller:
                    sellers[int(t["id"])] = tmpl_seller[int(t["product_tmpl_id"][0])]
            for op in await self._x(
                who, "stock.warehouse.orderpoint", "search_read", [["product_id", "in", ids]],
                fields=["product_id", "product_min_qty"],
            ):  # fmt: skip
                rops[int(op["product_id"][0])] = rops.get(int(op["product_id"][0]), 0) + float(op["product_min_qty"])
            calls += 4
        out = []
        for r in rows:
            retired = r.get("x_retired_on")
            code, sname = sellers.get(int(r["id"]), ("", ""))
            out.append(
                Part(
                    str(r["default_code"]),
                    str(r["name"]),
                    str(r.get("x_name_en") or ""),
                    str(r.get("x_models") or ""),
                    (_m2o(r["categ_id"]) or (0, ""))[1].split(" / ")[-1],
                    None if "std_price" in who.hide else float(r.get("standard_price") or 0),
                    rops.get(int(r["id"]), 0.0),
                    code,
                    sname,
                    "廃止" if retired and str(retired) <= today().isoformat() else "通常",
                    str(r.get("x_successor") or ""),
                    self._uom(r["uom_id"]),
                    self._uom(r["uom_po_id"]),
                )
            )
        return Fetch(out, calls)

    async def stock(self, who: ErpUser, part_nos: list[str]) -> Fetch[StockLine]:
        if not part_nos:
            return Fetch([])
        await self._maps(who)
        assert self._wh is not None
        prods = await self._products(who, part_nos)
        qs = await self._x(
            who, "stock.quant", "search_read",
            [["product_id", "in", list(prods)], ["location_id.usage", "=", "internal"]],
            fields=["product_id", "quantity", "warehouse_id"],
        )  # fmt: skip
        acc: dict[tuple[str, str], float] = {}
        for q in qs:
            wh = self._wh.get(int(q["warehouse_id"][0]), "") if q["warehouse_id"] else ""
            key = (prods[int(q["product_id"][0])], wh)
            acc[key] = acc.get(key, 0.0) + float(q["quantity"])
        return Fetch([StockLine(p, w, round(v, 3)) for (p, w), v in acc.items() if abs(v) > 1e-9], 2)

    async def on_order(self, who: ErpUser, part_nos: list[str]) -> Fetch[PoLine]:
        """入荷の予定（購買の権限が無くても在庫の権限で読める stock.move）。数は在庫の単位。"""
        if not part_nos:
            return Fetch([])
        prods = await self._products(who, part_nos)
        mvs = await self._x(
            who, "stock.move", "search_read",
            [["product_id", "in", list(prods)], ["picking_code", "=", "incoming"], ["location_id.usage", "=", "supplier"],
             ["state", "not in", ["done", "cancel"]]],
            fields=["product_id", "product_qty", "origin", "date"],
        )  # fmt: skip
        out = []
        for m in mvs:
            d = _jst_day(m["date"]) or today()
            out.append(
                PoLine(
                    str(m["origin"] or ""),
                    prods[int(m["product_id"][0])],
                    "",
                    "",
                    "",
                    float(m["product_qty"]),
                    "",
                    0.0,
                    None,
                    d,
                    d,
                    None,
                    "発注済み",
                )
            )
        return Fetch(out, 2)

    def _move_rows(self, ml: dict[str, Any], code: str, name: str, picks: dict[int, dict[str, Any]]) -> list[MoveRec]:
        assert self._loc_wh is not None and self._types is not None
        src, dst = _m2o(ml["location_id"]), _m2o(ml["location_dest_id"])
        src_wh = self._loc_wh.get(src[0], "") if src else ""
        dst_wh = self._loc_wh.get(dst[0], "") if dst else ""
        pick = _m2o(ml["picking_id"])
        p = picks.get(pick[0], {}) if pick else {}
        ref = str(p.get("origin") or ml.get("reference") or "")
        note = _text(p.get("note"))
        qty = float(ml["quantity"])
        if ml.get("is_inventory"):
            kind = "棚卸"
            # Odoo は棚卸の参照に調整した人を足す（「INV-2026-09 (Administrator)」）。参照の番号だけを返す
            ref = re.sub(r"\s*\([^()]*\)$", "", ref)
        else:
            t = _m2o(ml["picking_type_id"])
            kind = self.kinds.get(self._types.get(t[0], ""), "移動") if t else "移動"
        d = _jst_day(ml["date"]) or today()
        if src_wh and dst_wh:  # 倉庫の移動は 2 行（出と入り）
            return [
                MoveRec(d, code, name, "移動", -qty, ref, note, src_wh),
                MoveRec(d, code, name, "移動", qty, ref, note, dst_wh),
            ]
        if dst_wh:
            return [MoveRec(d, code, name, kind, qty, ref, note, dst_wh)]
        return [MoveRec(d, code, name, kind, -qty, ref, note, src_wh)]

    async def _picks(self, who: ErpUser, mls: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
        ids = sorted({int(m["picking_id"][0]) for m in mls if m.get("picking_id")})
        if not ids:
            return {}
        rows = await self._x(who, "stock.picking", "read", ids, fields=["origin", "note"])
        return {int(r["id"]): r for r in rows}

    _ML_FIELDS = ("date", "product_id", "quantity", "picking_type_id", "location_id", "location_dest_id", "is_inventory",
                  "reference", "picking_id")  # fmt: skip

    async def last_moves(self, who: ErpUser, part_nos: list[str]) -> LastMoves:
        await self._maps(who)
        prods = await self._products(who, part_nos)
        names = await self._names(who, list(prods))
        out: dict[str, MoveRec] = {}
        calls = 1
        for pid, code in prods.items():
            mls = await self._x(
                who, "stock.move.line", "search_read", [["product_id", "=", pid], ["state", "=", "done"]],
                fields=self._ML_FIELDS, order="date desc, id desc", limit=1,
            )  # fmt: skip
            calls += 1
            if mls:
                rows = self._move_rows(mls[0], code, names.get(pid, ""), await self._picks(who, mls))
                out[code] = rows[-1]
        return LastMoves(out, calls)

    async def _names(self, who: ErpUser, ids: list[int]) -> dict[int, str]:
        if not ids:
            return {}
        return {
            int(r["id"]): str(r["name"]) for r in await self._x(who, "product.product", "read", ids, fields=["name"])
        }

    async def moves(
        self, who: ErpUser, part_nos: list[str], since: date | None, until: date | None, cap: int
    ) -> Fetch[MoveRec]:
        if not part_nos:
            return Fetch([])
        await self._maps(who)
        prods = await self._products(who, part_nos)
        domain: list[Any] = [["product_id", "in", list(prods)], ["state", "=", "done"]]
        if since:
            domain.append(["date", ">=", _utc(since)])
        if until:
            domain.append(["date", "<=", _utc(until, end=True)])
        mls, calls = await self._all(
            who, "stock.move.line", domain, self._ML_FIELDS, cap, "期間（since・until）を短くしてください", "date, id"
        )
        names = await self._names(who, list(prods))
        picks = await self._picks(who, mls)
        out = []
        for ml in mls:
            pid = int(ml["product_id"][0])
            out += self._move_rows(ml, prods[pid], names.get(pid, ""), picks)
        out.sort(key=lambda m: (m.date, m.part_no))
        return Fetch(out, calls + 3)

    async def purchase_lines(self, who: ErpUser, q: PoQuery, part_nos: list[str] | None, cap: int) -> Fetch[PoLine]:
        domain: list[Any] = [["order_id.state", "in", ["purchase", "done", "cancel"]]]
        if part_nos is not None:
            domain.append(["product_id.default_code", "in", part_nos])
        if q.po_no.strip():
            domain.append(["order_id.name", "=", q.po_no.strip().upper()])
        if q.supplier.strip():
            s = q.supplier.strip()
            domain += ["|", ["order_id.partner_id.ref", "=", s], ["order_id.partner_id.name", "ilike", s]]
        if q.since:
            domain.append(["order_id.date_order", ">=", _utc(q.since)])
        if q.until:
            domain.append(["order_id.date_order", "<=", _utc(q.until, end=True)])
        if q.status == "取消":
            domain.append(["order_id.state", "=", "cancel"])
        elif q.status:
            domain.append(["order_id.state", "!=", "cancel"])
        fields = ["order_id", "product_id", "partner_id", "product_qty", "product_uom", "qty_received", "date_planned",
                  "state", "name"]  # fmt: skip
        if "unit_cost" not in who.hide:
            fields.append("price_unit")
        lines, calls = await self._all(
            who, "purchase.order.line", domain, fields, cap, "部品・仕入先・状態・期間で絞ってください", "id"
        )
        if not lines:
            return Fetch([], calls)
        oids = sorted({int(x["order_id"][0]) for x in lines})
        orders = {
            int(o["id"]): o
            for o in await self._x(who, "purchase.order", "read", oids, fields=["date_order", "notes", "partner_id"])
        }
        pids = sorted({int(o["partner_id"][0]) for o in orders.values()})
        partners = {int(p["id"]): p for p in await self._x(who, "res.partner", "read", pids, fields=["ref", "name"])}
        prod_ids = sorted({int(x["product_id"][0]) for x in lines})
        codes = {
            int(p["id"]): p
            for p in await self._x(who, "product.product", "read", prod_ids, fields=["default_code", "name"])
        }
        done = await self._x(
            who, "stock.move", "search_read",
            [["purchase_line_id", "in", [int(x["id"]) for x in lines]], ["state", "=", "done"]],
            fields=["purchase_line_id", "date"],
        )  # fmt: skip
        last: dict[int, date] = {}
        for m in done:
            d = _jst_day(m["date"])
            k = int(m["purchase_line_id"][0])
            if d and (k not in last or d > last[k]):
                last[k] = d
        calls += 4
        out = []
        for x in lines:
            o = orders[int(x["order_id"][0])]
            partner = partners[int(o["partner_id"][0])]
            qty, got = float(x["product_qty"]), float(x["qty_received"])
            if x["state"] == "cancel":
                status = "取消"
            elif got >= qty - 1e-9:
                status = "入荷済み"
            elif got > 0:
                status = "一部入荷"
            else:
                status = "発注済み"
            if q.status == "未完了" and status not in ("発注済み", "一部入荷"):
                continue
            if q.status in ("発注済み", "一部入荷", "入荷済み") and status != q.status:
                continue
            prod = codes[int(x["product_id"][0])]
            out.append(
                PoLine(
                    str(x["order_id"][1]),
                    str(prod["default_code"]),
                    str(prod["name"]),
                    str(partner["ref"] or ""),
                    str(partner["name"]),
                    qty,
                    self._uom(x["product_uom"]),
                    got,
                    None if "unit_cost" in who.hide else float(x.get("price_unit") or 0),
                    _jst_day(o["date_order"]) or today(),
                    _jst_day(x["date_planned"]) or today(),
                    last.get(int(x["id"])) if status == "入荷済み" else None,
                    status,
                    _text(o.get("notes")),
                )
            )
        out.sort(key=lambda p: (p.ordered_on, p.po_no))
        return Fetch(out, calls)

    async def sales_lines(self, who: ErpUser, q: SoQuery, part_nos: list[str] | None, cap: int) -> Fetch[SoLine]:
        domain: list[Any] = [["order_id.state", "in", ["sale", "done", "cancel"]]]
        if part_nos is not None:
            domain.append(["product_id.default_code", "in", part_nos])
        if q.customer.strip():
            c = q.customer.strip()
            domain += ["|", ["order_id.partner_id.ref", "=", c], ["order_id.partner_id.name", "ilike", c]]
        if q.since:
            domain.append(["order_id.date_order", ">=", _utc(q.since)])
        if q.until:
            domain.append(["order_id.date_order", "<=", _utc(q.until, end=True)])
        fields = ["order_id", "product_id", "product_uom_qty", "qty_delivered", "state", "order_partner_id"]
        lines, calls = await self._all(
            who, "sale.order.line", domain, fields, cap, "顧客・部品・状態・期間で絞ってください", "id"
        )
        if not lines:
            return Fetch([], calls)
        oids = sorted({int(x["order_id"][0]) for x in lines})
        orders = {
            int(o["id"]): o
            for o in await self._x(
                who, "sale.order", "read", oids, fields=["name", "date_order", "commitment_date", "state"]
            )
        }
        prod_ids = sorted({int(x["product_id"][0]) for x in lines})
        codes = {
            int(p["id"]): p
            for p in await self._x(who, "product.product", "read", prod_ids, fields=["default_code", "name"])
        }
        out = []
        for x in lines:
            o = orders[int(x["order_id"][0])]
            qty, got = float(x["product_uom_qty"]), float(x["qty_delivered"])
            if o["state"] == "cancel":
                status = "取消"
            elif got >= qty - 1e-9:
                status = "出荷済み"
            elif got > 0:
                status = "一部出荷"
            else:
                status = "受注済み"
            if q.status == "未完了" and status not in ("受注済み", "一部出荷"):
                continue
            if q.status and q.status != "未完了" and status != q.status:
                continue
            prod = codes[int(x["product_id"][0])]
            out.append(
                SoLine(
                    str(o["name"]),
                    str(x["order_partner_id"][1]),
                    str(prod["default_code"]),
                    str(prod["name"]),
                    qty,
                    got,
                    _jst_day(o["date_order"]) or today(),
                    _jst_day(o["commitment_date"]) or today(),
                    status,
                )
            )
        out.sort(key=lambda s: (s.ordered_on, s.so_no))
        return Fetch(out, calls + 2)

    async def suppliers(self, who: ErpUser, term: str) -> Fetch[Supplier]:
        domain: list[Any] = [["supplier_rank", ">", 0]]
        if term.strip():
            t = term.strip()
            domain += ["|", "|", ["ref", "ilike", t], ["name", "ilike", t], ["city", "ilike", t]]
        rows = await self._x(
            who, "res.partner", "search_read", domain, fields=["ref", "name", "city", "x_contact"], order="ref"
        )
        ids = [int(r["id"]) for r in rows]
        lead: dict[int, int] = {}
        if ids:
            for i in await self._x(
                who, "product.supplierinfo", "search_read", [["partner_id", "in", ids]], fields=["partner_id", "delay"]
            ):
                k = int(i["partner_id"][0])
                lead[k] = max(lead.get(k, 0), int(i["delay"]))
        return Fetch(
            [
                Supplier(
                    str(r["ref"] or ""),
                    str(r["name"]),
                    str(r["city"] or ""),
                    lead.get(int(r["id"])),
                    str(r.get("x_contact") or ""),
                )
                for r in rows
            ],
            2,
        )

    async def health(self) -> Health:
        t = time.perf_counter()
        v = await self._rpc("common", "version")
        n = await self._x(ErpUser("erp-viewer"), "product.product", "search_count", [])
        return Health(True, f"Odoo {v.get('server_version', '?')}", int((time.perf_counter() - t) * 1000), f"{n} 部品")

    async def aclose(self) -> None:
        await self.http.aclose()
