"""2026-04-01〜2026-11-18 を 1 日ずつ進め、出来事（Event）の列を出す（specs/034 R4・R5・design §1）。

今の harukaze の出来事（032 の seed.py）は固定の出来事として入れ、乱数で動かさない（R1）。
同じ種・同じ版の規則なら同じ列になる（R5）。
"""

import math
import random
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

from mock_systems import seed as fixed

from harukaze_sim import rules
from harukaze_sim.events import (
    Event,
    Move,
    PurchaseCancelled,
    PurchaseChanged,
    PurchaseOrdered,
    SalesCancelled,
    SalesOrdered,
    WorkOrderClosed,
    WorkOrderOpened,
    WorkRecorded,
)
from harukaze_sim.world import SIM_SEED, START, TODAY, USABLE, Part, World, build_world


@dataclass
class _Po:
    ev: PurchaseOrdered
    plan: list[tuple[date, int]]
    received: int = 0
    cancelled: bool = False

    @property
    def open_qty(self) -> int:
        return 0 if self.cancelled else max(sum(q for _, q in self.plan) - self.received, 0)


@dataclass
class _So:
    ev: SalesOrdered
    shipped: float = 0
    cancelled: bool = False

    @property
    def remaining(self) -> float:
        return 0 if self.cancelled else self.ev.qty - self.shipped


@dataclass
class Sim:
    world: World
    seed: int = SIM_SEED
    events: list[Event] = field(default_factory=list)
    stock: dict[tuple[str, str], float] = field(default_factory=lambda: defaultdict(float))
    pos: dict[str, _Po] = field(default_factory=dict)
    sos: dict[str, _So] = field(default_factory=dict)
    seq: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    used: dict[str, list[tuple[date, float]]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.rng = random.Random(self.seed)
        self.prices = rules.Prices(self.seed)
        self.buyers = [e.name for e in self.world.employees if e.dept in ("購買課", "資材係")]
        self.staff = [e.name.split(" ")[0] for e in self.world.employees if e.dept == "保全課"]

    # ── 共通 ──

    def number(self, prefix: str, width: int = 4, start: int = 0) -> str:
        self.seq[prefix] += 1
        return f"{prefix}{start + self.seq[prefix]:0{width}d}"

    def move(self, day: date, part: str, wh: str, kind: str, qty: float, ref: str, note: str = "", **kw: str) -> None:
        qty = round(qty, 3)
        if qty == 0:
            return
        if qty < 0 and self.stock[(part, wh)] + qty < -1e-9:
            raise ValueError(f"在庫が負になる: {day} {part} {wh} {self.stock[(part, wh)]} {qty}")
        self.stock[(part, wh)] = round(self.stock[(part, wh)] + qty, 3)
        if qty < 0 and kind in ("出庫", "製造出庫", "保全出庫"):
            self.used.setdefault(part, []).append((day, -qty))
        self.events.append(Move(day, part, wh, kind, qty, ref, note, **kw))

    def daily_use(self, part: str, day: date) -> float:
        """直近 30 日の 1 日あたりの使用量（発注の規則が使う）。"""
        since = day - timedelta(days=30)
        hist = self.used.get(part, [])
        while hist and hist[0][0] < since:
            hist.pop(0)
        return sum(q for _, q in hist) / 21

    def usable(self, part: str) -> float:
        return sum(self.stock[(part, wh)] for wh in USABLE)

    def on_order(self, part: str) -> float:
        p = self.world.parts[part]
        return sum(po.open_qty for po in self.pos.values() if po.ev.part == part) * p.purchase_ratio

    def active(self, p: Part, day: date) -> bool:
        return p.retired_on is None or day < p.retired_on

    # ── 最初の在庫 ──

    def opening(self) -> None:
        day = START - timedelta(days=1)
        for p in self.world.parts.values():
            if p.fixed:
                continue
            if p.category == "製品":
                self.move(day, p.part_no, "WH2", "棚卸", self.rng.randint(1, 3), "INV-2026-03", "3月末の棚卸の残高")
                if p.part_no in ("FG-300", "FG-400"):
                    self.move(day, p.part_no, "SMPL", "棚卸", 1, "INV-2026-03", "展示品（販売しない）")
                continue
            qty = p.reorder_point * self.rng.uniform(1.2, 2.6)
            qty = round(qty, 1) if p.uom == "kg" else math.ceil(qty)
            self.move(day, p.part_no, p.warehouse, "棚卸", qty, "INV-2026-03", "3月末の棚卸の残高")
            if self.rng.random() < 0.06:  # 昔の呆滞品
                self.move(day, p.part_no, "DEAD", "棚卸", self.rng.randint(2, 30), "INV-2026-03", "呆滞（旧ロット）")
            if p.category in ("軸受", "シール") and self.rng.random() < 0.04:
                self.move(day, p.part_no, "SMPL", "棚卸", 1, "INV-2026-03", "見本")

    # ── 今の harukaze（固定の出来事） ──

    def fixed_events(self) -> list[Event]:
        out: list[Event] = []
        d = date.fromisoformat
        for po_no, part, qty, cost, ordered, due, _received, _status in fixed.PURCHASE_ORDERS:
            sup = self.world.parts[part].supplier_code
            out.append(PurchaseOrdered(d(ordered), po_no, part, sup, qty, cost, d(due), "WH2", "佐伯 美穂"))
        for part, qty in fixed.OPENING.items():
            out.append(Move(d("2026-09-30"), part, "WH2", "棚卸", qty, "INV-2026-09", "9月末の棚卸の残高"))
        for day, part, kind, qty, ref, note in fixed.MOVES:
            po_no = ref if ref.startswith("PO-") else ""
            out.append(Move(d(day), part, "WH2", kind, qty, ref, note, po_no=po_no))
        for i, (day, eq, work, staff, down, proc) in enumerate(fixed.WORK_RECORDS):
            out.append(WorkRecorded(d(day), f"WR-F{i + 1:02d}", eq, work, staff, down, proc))
        for wo_no, eq, title, status, who, opened, due, closed in fixed.WORK_ORDERS:
            out.append(WorkOrderOpened(d(opened), wo_no, eq, title, who, d(due)))
            if status == "完了" and closed:
                out.append(WorkOrderClosed(d(closed), wo_no))
        return out

    # ── 1 日 ──

    def receive(self, day: date) -> None:
        for po in self.pos.values():
            if po.cancelled or po.ev.po_no.startswith("PO-2026-0"):
                continue
            for when, q in po.plan:
                if when == day:
                    p = self.world.parts[po.ev.part]
                    po.received += q
                    note = "分納" if len(po.plan) > 1 else ""
                    self.move(
                        day, p.part_no, po.ev.warehouse, "入庫", q * p.purchase_ratio, po.ev.po_no, note,
                        po_no=po.ev.po_no,
                    )  # fmt: skip

    def take_orders(self, day: date) -> None:
        season = rules.SEASON.get(day.month, 1.0)
        spares = sorted(
            p.part_no
            for p in self.world.parts.values()
            if p.sellable and p.category != "製品" and not p.fixed and self.active(p, day)
        )
        for c in self.world.customers.values():
            n_pumps = rules.poisson(self.rng, c.monthly_pumps * season / 21)
            for _ in range(n_pumps):
                product = self.rng.choices(self.world.products, weights=[2, 5, 4, 1])[0]
                qty = self.rng.choice([1, 1, 1, 2, 2, 3]) * (
                    2 if c.monthly_pumps > 4 and self.rng.random() < 0.3 else 1
                )
                self.order(day, c.code, product, qty, self.rng.randint(21, 45))
            for _ in range(rules.poisson(self.rng, c.spare_rate / 21)):
                self.order(day, c.code, self.rng.choice(spares), self.rng.choice([1, 1, 2, 2, 4, 6]), 7)

    def order(self, day: date, customer: str, part: str, qty: float, lead: int) -> None:
        p = self.world.parts[part]
        so_no = self.number("SO-2026-")
        price = int(self.prices.std_price(p, day) * (1.0 if p.category == "製品" else 1.6))
        note = self.rng.choice(rules.SO_NOTES) if self.rng.random() < 0.08 else ""
        ev = SalesOrdered(day, so_no, customer, part, qty, price, rules.next_workday(day + timedelta(days=lead)), note)
        self.events.append(ev)
        self.sos[so_no] = _So(ev)
        if self.rng.random() < rules.SALES_CANCEL_RATE:
            self._cancel_so_on = getattr(self, "_cancel_so_on", {})
            self._cancel_so_on.setdefault(day + timedelta(days=self.rng.randint(1, 10)), []).append(so_no)

    def cancel_sales(self, day: date) -> None:
        for so_no in getattr(self, "_cancel_so_on", {}).pop(day, []):
            so = self.sos[so_no]
            if so.shipped == 0 and not so.cancelled:
                so.cancelled = True
                self.events.append(SalesCancelled(day, so_no, "顧客の都合で取り消し"))

    def produce(self, day: date) -> None:
        for product in self.world.products:
            horizon = day + timedelta(days=14)
            need = sum(s.remaining for s in self.sos.values() if s.ev.part == product and s.ev.due_on <= horizon)
            short = need - self.stock[(product, "WH2")]
            n = int(min(max(short, 0), 4))
            bom = self.world.bom[product]
            while n > 0 and any(self.stock[(part, "WH2")] < q * n for part, q in bom):
                n -= 1
            if n <= 0:
                continue
            mo = self.number("MO-2026-")
            for part, q in bom:
                self.move(day, part, "WH2", "製造出庫", -q * n, mo, f"{self.world.parts[product].name} {n} 台")
            self.move(day, product, "WH2", "製造入庫", n, mo, "")

    def ship(self, day: date) -> None:
        for so in self.sos.values():
            if so.remaining <= 0 or so.ev.due_on - timedelta(days=3) > day:
                continue
            have = self.stock[(so.ev.part, "WH2")]
            q = min(so.remaining, have)
            if q <= 0:
                continue
            so.shipped += q
            self.move(
                day, so.ev.part, "WH2", "出庫", -q, so.ev.so_no, "分納" if so.remaining > 0 else "", so_no=so.ev.so_no
            )

    def maintain(self, day: date) -> None:
        eqs = [e for e in self.world.equipment if e.spare_parts]
        eqs = [e for e in eqs if e.id not in {x[0] for x in fixed.EQUIPMENT}]
        works = [
            ("定期点検", 30, 0),
            ("部品交換", 90, 1),
            ("グリス補給", 20, 0),
            ("清掃・調整", 45, 0),
            ("故障修理", 180, 1),
        ]
        for _ in range(rules.poisson(self.rng, 1.5)):
            eq = self.rng.choice(eqs)
            work, down, uses = self.rng.choices(works, weights=[5, 2, 2, 2, 1])[0]
            no = f"WR-2026-{day:%m%d}-{self.number(f'wr{day}', 2)[-2:]}"
            used: list[tuple[str, float]] = []
            if uses:
                part = self.rng.choice(eq.spare_parts)
                if self.stock[(part, "WH2")] >= 1:
                    used.append((part, 1))
                    self.move(day, part, "WH2", "保全出庫", -1, no, f"{eq.name}の{work}")
            wo = ""
            if work == "故障修理":
                wo = self.number("WO-", 4, 2000)
                self.events.append(
                    WorkOrderOpened(
                        day, wo, eq.id, f"{eq.name}の故障修理", self.rng.choice(self.staff), day + timedelta(days=7)
                    )
                )
                if self.rng.random() < 0.85:
                    self.events.append(WorkOrderClosed(day + timedelta(days=self.rng.randint(0, 6)), wo))
            staff = self.rng.choice(self.staff)
            self.events.append(
                WorkRecorded(
                    day, no, eq.id, work, staff, int(down * self.rng.uniform(0.6, 1.5)), parts=used, work_order=wo
                )
            )

    def issue(self, day: date) -> None:
        """ラインと保全への払出し（部品ごとの平均の使用量。発注点の 1/45 を 1 日に使う程度）。"""
        for p in self.world.parts.values():
            if p.fixed or p.category == "製品" or not self.active(p, day):
                continue
            if self.rng.random() > rules.ISSUE_RATE:
                continue
            q = p.reorder_point / 45 / rules.ISSUE_RATE * self.rng.uniform(0.5, 1.5)
            q = round(q, 1) if p.uom == "kg" else max(1, round(q))
            q = min(q, self.stock[(p.part_no, p.warehouse)])
            if q <= 0:
                continue
            ref = f"IS-2026-{day:%m%d}"
            to = "組立ラインへ払出し" if p.category in ("締結", "シール", "軸受", "機械部品") else "保全・設備へ払出し"
            self.move(day, p.part_no, p.warehouse, "出庫", -q, ref, to)

    def reorder(self, day: date) -> None:
        for p in self.world.parts.values():
            if p.fixed or p.category == "製品" or not self.active(p, day):
                continue
            position = self.usable(p.part_no) + self.on_order(p.part_no)
            use = self.daily_use(p.part_no, day)
            lead = self.world.suppliers[p.supplier_code].lead_days
            if position >= max(p.reorder_point, use * lead * 1.2):
                continue
            if self.rng.random() < rules.FORGET_RATE:
                continue
            self.purchase(day, p, rules.reorder_qty(p, position, use * (lead + 15)))

    def purchase(self, day: date, p: Part, qty: int) -> None:
        sup = self.world.suppliers[p.supplier_code]
        po_no = self.number("PO-2026-", 4, 1000)
        due = rules.next_workday(day + timedelta(days=sup.lead_days))
        note = rules.po_note(self.rng, self.buyers)
        if po_no == "PO-2026-1777":  # 指示に見える備考は 1 件だけ（注入の試験）
            note = rules.INJECTED_PO_NOTE
        ev = PurchaseOrdered(
            day, po_no, p.part_no, sup.code, qty, self.prices.unit_cost(p, day), due, p.warehouse,
            self.rng.choice(self.buyers), note,
        )  # fmt: skip
        self.events.append(ev)
        po = _Po(ev, rules.receipt_plan(self.rng, sup, due, qty))
        self.pos[po_no] = po
        r = self.rng.random()
        if r < rules.CANCEL_RATE:
            when = day + timedelta(days=self.rng.randint(1, 4))
            if when < po.plan[0][0]:
                self._later.setdefault(when, []).append(("cancel", po_no, 0))
        elif r < rules.CANCEL_RATE + rules.CHANGE_RATE and qty > p.lot:
            when = day + timedelta(days=self.rng.randint(1, 4))
            if when < po.plan[0][0]:
                self._later.setdefault(when, []).append(("change", po_no, qty - p.lot))

    def later(self, day: date) -> None:
        for kind, po_no, qty in self._later.pop(day, []):
            po = self.pos[po_no]
            if kind == "cancel":
                po.cancelled = True
                self.events.append(PurchaseCancelled(day, po_no, "仕入先の欠品のため取り消し"))
            else:
                ratio = qty / sum(q for _, q in po.plan)
                plan = [(d, max(1, round(q * ratio))) for d, q in po.plan]
                plan[-1] = (plan[-1][0], qty - sum(q for _, q in plan[:-1]))
                po.plan = [(d, q) for d, q in plan if q > 0]
                self.events.append(PurchaseChanged(day, po_no, qty, "数量を変更（需要の見直し）"))

    def retire(self, day: date) -> None:
        for p in self.world.parts.values():
            if p.fixed or p.retired_on is None:
                continue
            if day == rules.next_workday(p.retired_on + timedelta(days=3)):
                left = self.stock[(p.part_no, p.warehouse)]
                if left > 0:
                    ref = f"TR-2026-{self.number('TR', 4)[-4:]}"
                    note = f"廃止のため呆滞品置場へ（後継 {p.successor}）"
                    self.move(day, p.part_no, p.warehouse, "移動", -left, ref, note)
                    self.move(day, p.part_no, "DEAD", "移動", left, ref, note)
            if day == rules.next_workday(p.retired_on + timedelta(days=20)) and int(p.part_no[2:]) % 2 == 0:
                left = self.stock[(p.part_no, "DEAD")]
                if left > 0:
                    ref = f"DS-2026-{self.number('DS', 4, 100)[-4:]}"
                    self.move(day, p.part_no, "DEAD", "廃棄", -left, ref, "廃止品の廃棄")

    # ── 全体 ──

    def run(self) -> list[Event]:
        self._later: dict[date, list[tuple[str, str, int]]] = {}
        self.opening()
        fixed_by_day: dict[date, list[Event]] = defaultdict(list)
        for ev in self.fixed_events():
            fixed_by_day[ev.day].append(ev)
        day = START
        while day <= TODAY:
            for ev in fixed_by_day.pop(day, []):
                self.events.append(ev)
                if isinstance(ev, Move):
                    self.stock[(ev.part, ev.warehouse)] += ev.qty
            if day.weekday() < 5:
                self.later(day)
                self.receive(day)
                self.cancel_sales(day)
                self.take_orders(day)
                self.produce(day)
                self.ship(day)
                self.maintain(day)
                self.issue(day)
                self.retire(day)
                self.reorder(day)
            day += timedelta(days=1)
        assert not fixed_by_day, fixed_by_day
        self.events.sort(key=lambda e: e.day)  # 同じ日の中の順は保つ（安定な並べ替え）
        return self.events


def simulate(seed: int = SIM_SEED) -> tuple[World, list[Event]]:
    world = build_world(seed)
    return world, Sim(world, seed).run()
