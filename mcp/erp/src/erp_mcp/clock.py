"""時計: 評価の再現のため「今日」を固定できる（ERP_TODAY、既定 2026-11-18）。時:分は実際の時刻（JST）。"""

import os
from datetime import date, datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))


def today() -> date:
    raw = os.environ.get("ERP_TODAY", "2026-11-18")
    return date.fromisoformat(raw) if raw else datetime.now(JST).date()


def now() -> datetime:
    real = datetime.now(JST)
    return datetime.combine(today(), real.time().replace(microsecond=0), tzinfo=JST)
