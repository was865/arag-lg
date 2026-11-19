"""会社の骨格（specs/034 R1〜R3・design §2）: 部品・仕入先・顧客・倉庫・社員・設備・製品の部品表。

今の harukaze（032 の seed.py の 8 部品・3 仕入先）はそのまま含め、乱数で動かさない（R1）。
新しく足すものは重ならない帯（部品 P-5000 番台〜・仕入先 S-20 番台〜）を使う。乱数は random.Random(seed) だけ。
"""

import random
from dataclasses import dataclass, field
from datetime import date

from mock_systems import seed as fixed

SIM_SEED = 20261118
START = date(2026, 4, 1)
TODAY = date(2026, 11, 18)

# 倉庫コード, 名称, 使える（在庫に数える）か, 工場
WAREHOUSES = [
    ("WH2", "第二工場 資材倉庫", True, "浜松第二工場"),
    ("WH1", "第一工場 資材倉庫", True, "浜松第一工場"),
    ("DEAD", "第二工場 呆滞品置場", False, "浜松第二工場"),
    ("SMPL", "見本・展示品", False, "浜松第二工場"),
]
USABLE = frozenset(w[0] for w in WAREHOUSES if w[2])

DEPARTMENTS = ["製造課", "保全課", "品質保証部", "購買課", "資材係", "サービス課", "営業課", "生産管理課"]


@dataclass(frozen=True)
class Part:
    part_no: str
    name: str
    name_en: str
    models: str
    category: str
    std_price: int  # 標準単価（円、今の値）
    reorder_point: int
    supplier_code: str
    status: str  # 通常 / 廃止
    uom: str = "個"  # 在庫の単位
    purchase_uom: str = "個"  # 発注の単位
    purchase_ratio: int = 1  # 発注の単位 1 つが在庫の単位でいくつか
    lot: int = 10  # 発注の最小のまとまり（発注の単位で）
    successor: str = ""
    retired_on: date | None = None
    warehouse: str = "WH2"
    fixed: bool = False  # 今の harukaze の部品（乱数で動かさない）
    old_std_price: int | None = None  # 上期の標準単価（10/1 に改めた。無ければ変えていない）

    @property
    def sellable(self) -> bool:
        return self.category in ("製品", "シール", "軸受", "羽根車")


@dataclass(frozen=True)
class Supplier:
    code: str
    name: str
    location: str
    lead_days: int
    contact: str
    overseas: bool
    delay_rate: float  # 納期に遅れる割合


@dataclass(frozen=True)
class Customer:
    code: str
    name: str
    location: str
    monthly_pumps: float  # 月あたりのポンプの需要の平均
    spare_rate: float  # 月あたりの補修部品の注文の平均


@dataclass(frozen=True)
class Employee:
    emp_no: str
    name: str
    dept: str
    title: str
    extension: str


@dataclass(frozen=True)
class Equipment:
    id: str
    name: str
    location: str
    installed: int
    spare_parts: tuple[str, ...]  # 保全で使う部品


@dataclass
class World:
    parts: dict[str, Part]
    suppliers: dict[str, Supplier]
    customers: dict[str, Customer]
    employees: list[Employee]
    equipment: list[Equipment]
    bom: dict[str, list[tuple[str, float]]]  # 製品 → [(部品, 1 台あたりの数)]
    products: list[str] = field(default_factory=list)


# ── 名前の材料 ──

_JP_FAMILY = [
    "佐藤", "鈴木", "高橋", "田中", "伊藤", "渡辺", "山本", "中村", "小林", "加藤", "吉田", "山田", "佐々木", "松本",
    "井上", "木村", "林", "斎藤", "清水", "山崎", "森", "池田", "橋本", "阿部", "石川", "山下", "中島", "石井",
    "小川", "前田", "岡田", "長谷川", "藤田", "後藤", "近藤", "村上", "遠藤", "青木", "坂本", "斉藤", "福田", "太田",
]  # fmt: skip
_JP_GIVEN = [
    "翔", "陽菜", "蓮", "結衣", "大輔", "美咲", "健太", "彩", "直樹", "里奈", "亮", "真由", "拓海", "千尋", "悠",
    "恵", "隆之", "沙織", "和也", "瞳", "誠一", "奈々", "浩二", "由紀",
]  # fmt: skip
_PLACES = ["浜松", "磐田", "掛川", "豊橋", "湖西", "袋井", "静岡", "名古屋", "岡崎", "刈谷", "沼津", "富士"]
_SUPPLIER_KINDS = ["精機", "工業", "製作所", "商事", "産業", "金属", "化成", "電機", "ゴム工業", "興産"]
_OVERSEAS = [
    ("Taichung Precision Co., Ltd.", "台湾 台中", "Lin"),
    ("Suzhou Hengda Bearing Co.", "中国 蘇州", "Wang"),
    ("Kessler Dichtungstechnik GmbH", "ドイツ シュトゥットガルト", "M. Kessler"),
    ("Pacific Pump Components Inc.", "米国 シアトル", "R. Diaz"),
    ("Penang Motor Works Sdn. Bhd.", "マレーシア ペナン", "Tan"),
]
_CUSTOMER_KINDS = ["水道サービス", "化学工業", "食品", "製紙", "ビル管理", "設備工業", "冷熱", "工機", "環境開発"]


def _person(rng: random.Random) -> str:
    return f"{rng.choice(_JP_FAMILY)} {rng.choice(_JP_GIVEN)}"


def _suppliers(rng: random.Random) -> dict[str, Supplier]:
    out: dict[str, Supplier] = {}
    for code, name, loc, lead, contact in fixed.SUPPLIERS:
        overseas = not loc.endswith(("県浜松市", "県豊橋市"))
        out[code] = Supplier(code, name, loc, lead, contact, overseas, 0.25 if overseas else 0.08)
    used: set[str] = set()
    for i in range(27):
        code = f"S-{20 + i}"
        if i < len(_OVERSEAS):
            name, loc, contact = _OVERSEAS[i]
            out[code] = Supplier(code, name, loc, rng.choice([28, 35, 42]), contact, True, rng.uniform(0.15, 0.3))
            continue
        while True:
            place = rng.choice(_PLACES)
            name = f"{rng.choice(['株式会社', '有限会社', ''])}{place}{rng.choice(_SUPPLIER_KINDS)}"
            name = name if name.startswith(("株式会社", "有限会社")) else name + "株式会社"
            if name not in used:
                used.add(name)
                break
        pref = "愛知県" if place in ("豊橋", "名古屋", "岡崎", "刈谷") else "静岡県"
        out[code] = Supplier(
            code, name, f"{pref}{place}市", rng.choice([5, 7, 10, 14, 21]), rng.choice(_JP_FAMILY), False,
            rng.uniform(0.04, 0.14),
        )  # fmt: skip
    return out


def _customers(rng: random.Random) -> dict[str, Customer]:
    out: dict[str, Customer] = {}
    used: set[str] = set()
    for i in range(40):
        while True:
            name = f"{rng.choice(_PLACES)}{rng.choice(_CUSTOMER_KINDS)}株式会社"
            if name not in used:
                used.add(name)
                break
        big = i < 6  # 大口の顧客
        out[f"C-{i + 1:03d}"] = Customer(
            f"C-{i + 1:03d}",
            name,
            rng.choice(_PLACES),
            rng.uniform(2, 5) if big else rng.uniform(0.2, 1.0),
            rng.uniform(1.5, 3) if big else rng.uniform(0.2, 1.2),
        )
    return out


def _fixed_parts() -> dict[str, Part]:
    out: dict[str, Part] = {}
    for no, name, models, price, rop, sup, status in fixed.PARTS:
        category = {"P-1": "シール", "P-2": "軸受", "P-3": "羽根車", "P-4": "グリス"}[no[:3]]
        en = {
            "P-1042": "Seal kit SK-300",
            "P-1043": "Mechanical seal MS-30",
            "P-2010": "Ball bearing 6308ZZ",
            "P-2011": "Ball bearing 6309ZZ",
            "P-3100": "Impeller IM-300",
            "P-3120": "Impeller IM-320",
            "P-4001": "Grease KG-5 (400 g)",
            "P-4002": "Grease KG-2 (400 g)",
        }[no]
        out[no] = Part(
            no, name, en, models, category, price, rop, sup, status,
            successor="P-4001" if no == "P-4002" else "",
            retired_on=date(2026, 10, 31) if no == "P-4002" else None,
            lot=1 if category == "羽根車" else 4,
            fixed=True,
        )  # fmt: skip
    return out


class _Numbers:
    def __init__(self) -> None:
        self.n = 5000

    def next(self) -> str:
        self.n += 1
        return f"P-{self.n}"


def _generated_parts(rng: random.Random, suppliers: dict[str, Supplier]) -> dict[str, Part]:
    out: dict[str, Part] = {}
    num = _Numbers()
    domestic = [s.code for s in suppliers.values() if not s.overseas and not s.code.startswith("S-0")]
    domestic += ["S-02"]
    overseas = [s.code for s in suppliers.values() if s.overseas and s.code != "S-07"]

    def add(name: str, en: str, models: str, category: str, price: int, rop: int, sup: str, **kw: object) -> str:
        no = num.next()
        out[no] = Part(no, name, en, models, category, price, rop, sup, "通常", **kw)  # type: ignore[arg-type]
        return no

    # 軸受: 型番 × 仕様（似た名前。6308ZZ ／ 6308ZZ-C3 ／ 6308-2RS）
    for size in ["6204", "6205", "6206", "6208", "6210", "6305", "6306", "6307", "6308", "6309", "6310", "6312"]:
        base = 900 + int(size[1:]) * 90
        for spec, mult in [("ZZ", 1.0), ("ZZ-C3", 1.12), ("-2RS", 1.08), ("ZZ（NTN 指定）", 1.25)]:
            if size in ("6308", "6309") and spec == "ZZ":
                continue  # 今の P-2010・P-2011
            if rng.random() < 0.25 and size not in ("6308", "6309"):
                continue
            sup = rng.choice(["S-02", *rng.sample(domestic, 2), rng.choice(overseas)])
            add(
                f"軸受 {size}{spec}", f"Ball bearing {size}{spec.replace('（NTN 指定）', ' (NTN)')}",
                rng.choice(["HP-300", "HP-320", "HP-400", "HP-250", "共通"]), "軸受",
                int(base * mult), rng.choice([6, 8, 10, 12, 20]), sup, lot=rng.choice([10, 20]),
            )  # fmt: skip
    # シール・ガスケット・O リング
    for i, (nm, en) in enumerate(
        [("メカニカルシール MS-%d", "Mechanical seal MS-%d"), ("シールキット SK-%d", "Seal kit SK-%d")]
    ):
        for model in [250, 320, 400, 450]:
            for var in ["", "（耐熱）"]:
                if var and rng.random() < 0.5:
                    continue
                add(
                    (nm % (model // 10 if i == 0 else model)) + var, en % (model // 10 if i == 0 else model),
                    f"HP-{model}", "シール", rng.randint(14000, 32000), rng.choice([2, 4, 6]),
                    rng.choice(["S-07", "S-22", *rng.sample(domestic, 1)]), lot=rng.choice([2, 4, 5]),
                )  # fmt: skip
    for d in range(20, 160, 8):
        add(
            f"Oリング P{d}（NBR）", f"O-ring P{d} NBR", "共通", "シール", 60 + d, 40, rng.choice(domestic),
            uom="個", purchase_uom="袋（50個）", purchase_ratio=50, lot=2,
        )  # fmt: skip
    for model in [250, 300, 320, 400]:
        for kind in ["ケーシング用", "フランジ用"]:
            add(
                f"ガスケット {kind} G-{model}", f"Gasket {kind} G-{model}", f"HP-{model}", "シール",
                rng.randint(380, 1600), 20, rng.choice(domestic), lot=20,
            )  # fmt: skip
    # 羽根車・ケーシング・シャフト
    for model in [250, 400, 450]:
        for var in ["", "（SCS13）"]:
            add(
                f"羽根車 IM-{model}{var}", f"Impeller IM-{model}", f"HP-{model}", "羽根車",
                rng.randint(42000, 88000), 1 if var else 2, rng.choice(["S-11", *rng.sample(domestic, 1)]), lot=2,
            )  # fmt: skip
    for model in [250, 300, 320, 400]:
        add(
            f"ケーシング CS-{model}", f"Casing CS-{model}", f"HP-{model}", "鋳物", rng.randint(38000, 72000), 2,
            "S-11", lot=4,
        )  # fmt: skip
        add(
            f"主軸 SH-{model}", f"Shaft SH-{model}", f"HP-{model}", "機械部品", rng.randint(9000, 18000), 4,
            rng.choice(domestic), lot=5,
        )  # fmt: skip
    # モーター
    for kw in ["1.5kW", "2.2kW", "3.7kW", "5.5kW", "7.5kW"]:
        add(
            f"モーター 4P {kw}", f"Motor 4P {kw}", "共通", "電装", rng.randint(38000, 120000), 2,
            rng.choice(["S-24", *rng.sample(domestic, 1)]), lot=2,
        )  # fmt: skip
    # ボルト・ナット（箱で買う）
    for size in ["M6", "M8", "M10", "M12", "M16"]:
        for length in [20, 25, 30, 40, 50, 60]:
            if rng.random() < 0.3:
                continue
            for mat in ["SUS304", "SCM435"]:
                if rng.random() < 0.35:
                    continue
                add(
                    f"六角ボルト {size}×{length} {mat}", f"Hex bolt {size}x{length} {mat}", "共通", "締結",
                    rng.randint(18, 120), 300, rng.choice(domestic),
                    purchase_uom="箱（100個）", purchase_ratio=100, lot=2,
                )  # fmt: skip
        add(
            f"六角ナット {size} SUS304", f"Hex nut {size} SUS304", "共通", "締結", rng.randint(8, 40), 400,
            rng.choice(domestic), purchase_uom="箱（100個）", purchase_ratio=100, lot=2,
        )  # fmt: skip
    # グリス・油（kg と缶）
    for nm, en in [
        ("グリス KG-5", "Grease KG-5"),
        ("グリス EP-2", "Grease EP-2"),
        ("グリス HT-3（耐熱）", "Grease HT-3"),
    ]:
        add(
            f"{nm}（16kg 缶）", f"{en} (16 kg pail)", "共通", "グリス", rng.randint(18000, 30000), 2, "S-02",
            uom="缶", purchase_uom="缶", lot=1,
        )  # fmt: skip
        add(
            f"{nm}（量り売り）", f"{en} (bulk)", "共通", "グリス", rng.randint(1100, 1900), 10, "S-02",
            uom="kg", purchase_uom="kg", lot=10,
        )  # fmt: skip
    # 電装・配管・計器・消耗品で数を足す（300〜500 に届くまで）
    misc = [
        ("圧力計 PG-%d", "Pressure gauge PG-%d", "計器", 4800, 9600),
        ("電磁開閉器 MC-%d", "Magnetic contactor MC-%d", "電装", 6200, 18000),
        ("フレキシブル継手 FJ-%d", "Flexible coupling FJ-%d", "配管", 3800, 12000),
        ("ボールバルブ BV-%d", "Ball valve BV-%d", "配管", 2600, 9800),
        ("フィルタエレメント FE-%d", "Filter element FE-%d", "消耗品", 1200, 4800),
        ("Vベルト B-%d", "V-belt B-%d", "消耗品", 900, 2600),
        ("近接センサ PX-%d", "Proximity sensor PX-%d", "電装", 5200, 14800),
        ("温度センサ TS-%d", "Temperature sensor TS-%d", "計器", 6800, 19800),
    ]
    k = 0
    while len(out) + 8 < 420:
        nm, en, cat, lo, hi = misc[k % len(misc)]
        n = 10 + (k // len(misc)) * 5
        add(nm % n, en % n, "共通", cat, rng.randint(lo, hi), rng.choice([2, 4, 6, 10]), rng.choice(domestic), lot=4)
        k += 1
    # 製品（受注して出荷する）
    for model, price in [(250, 420000), (300, 560000), (320, 640000), (400, 880000)]:
        no = f"FG-{model}"
        out[no] = Part(
            no, f"冷却水ポンプ HP-{model}", f"Cooling water pump HP-{model}", f"HP-{model}", "製品", price, 0, "",
            "通常", uom="台", purchase_uom="台", lot=1,
        )  # fmt: skip
    return out


def _retire(rng: random.Random, parts: dict[str, Part]) -> None:
    """10 部品に廃止の日と後継を持たせる（KG-2 → KG-5 と同じ形）。"""
    cands = [p for p in parts.values() if not p.fixed and p.category in ("軸受", "シール", "電装", "計器")]
    for p in rng.sample(cands, 10):
        succ = next(
            (q for q in parts.values() if q.category == p.category and q.part_no > p.part_no and not q.fixed), None
        )
        if succ is None:
            continue
        day = date(2026, rng.choice([6, 7, 8, 9, 10]), rng.randint(1, 28))
        parts[p.part_no] = Part(**{**p.__dict__, "successor": succ.part_no, "retired_on": day})


def _revise_std_prices(rng: random.Random, parts: dict[str, Part]) -> None:
    """標準単価は年に 1 度だけ改める（10/1、下期）。今の値が新しい値、上期の値を old_std_price に残す。"""
    for no, p in list(parts.items()):
        if p.fixed or p.category == "製品" or rng.random() < 0.4:
            continue
        old = p.std_price
        new = int(round(old * rng.uniform(1.0, 1.08), -1 if old < 1000 else -2)) or old
        if new != old:
            parts[no] = Part(**{**p.__dict__, "std_price": new, "old_std_price": old})


def _employees(rng: random.Random) -> list[Employee]:
    out = [Employee(e[0], e[1], e[2], e[3], e[4]) for e in fixed.EMPLOYEES]
    used = {e.name for e in out}
    n = 1300
    while len(out) < 60:
        name = _person(rng)
        if name in used:
            continue
        used.add(name)
        dept = rng.choice(DEPARTMENTS)
        out.append(Employee(f"E-{n}", name, dept, "", f"2{rng.randint(300, 699)}"))
        n += 7
    return out


def _equipment(rng: random.Random, parts: dict[str, Part]) -> list[Equipment]:
    spares = [p.part_no for p in parts.values() if p.category in ("消耗品", "軸受", "電装") and not p.fixed]
    out = [
        Equipment(e[0], e[1], e[2], e[3], ("P-4001", "P-2010") if e[0] == "PM-04" else ())  # 今の 4 設備
        for e in fixed.EQUIPMENT
    ]
    names = [
        ("CP", "冷却水ポンプ（HP-320）", "第二工場 機械室"),
        ("AL", "組立ライン", "第二工場 1階"),
        ("TS", "性能試験台", "第二工場 試験室"),
        ("CM", "コンプレッサ", "第二工場 機械室"),
        ("CN", "天井クレーン", "第二工場 1階"),
        ("MC", "マシニングセンタ", "第一工場 加工棟"),
        ("WD", "溶接ロボット", "第一工場 加工棟"),
        ("PT", "塗装ブース", "第一工場 塗装棟"),
    ]
    for i in range(20):
        code, name, loc = names[i % len(names)]
        n = i // len(names) + 2
        out.append(
            Equipment(f"{code}-{n:02d}", f"{name}{n}号", loc, rng.randint(2012, 2025), tuple(rng.sample(spares, 3)))
        )
    return out


def _bom(rng: random.Random, parts: dict[str, Part]) -> dict[str, list[tuple[str, float]]]:
    def pick(category: str, model: int) -> str:
        c = [
            p.part_no
            for p in parts.values()
            if p.category == category and not p.fixed and str(model) in p.models and p.retired_on is None
        ]
        if not c:
            c = [p.part_no for p in parts.values() if p.category == category and not p.fixed and p.retired_on is None]
        return sorted(c)[0]

    bolts = sorted(p.part_no for p in parts.values() if p.category == "締結" and "ボルト" in p.name)
    out: dict[str, list[tuple[str, float]]] = {}
    for model in (250, 300, 320, 400):
        bearing = sorted(
            p.part_no for p in parts.values() if p.category == "軸受" and not p.fixed and p.retired_on is None
        )[model % 7]
        motor = sorted(p.part_no for p in parts.values() if p.category == "電装" and "モーター" in p.name)[
            (model // 100) % 5
        ]
        grease = next(p.part_no for p in parts.values() if p.name == "グリス KG-5（量り売り）")
        out[f"FG-{model}"] = [
            (pick("鋳物", model), 1),
            (pick("機械部品", model), 1),
            (pick("羽根車", model), 1),
            (bearing, 2),
            (pick("シール", model), 1),
            (motor, 1),
            (bolts[model % len(bolts)], 8),
            (grease, 0.2),
        ]
    return out


def build_world(seed: int = SIM_SEED) -> World:
    rng = random.Random(seed)
    suppliers = _suppliers(rng)
    parts = {**_fixed_parts(), **_generated_parts(rng, suppliers)}
    _retire(rng, parts)
    _revise_std_prices(rng, parts)
    world = World(
        parts=parts,
        suppliers=suppliers,
        customers=_customers(rng),
        employees=_employees(rng),
        equipment=_equipment(rng, parts),
        bom={},
    )
    world.bom = _bom(rng, parts)
    world.products = sorted(world.bom)
    return world
