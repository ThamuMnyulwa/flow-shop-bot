"""One clock for the whole service, so time can be moved forward in local and staging (E8).

The offset lives in the database, so the web process and the scheduled-jobs endpoint agree on the time.
"""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import holidays
from sqlalchemy.orm import Session

from flowshop.config import get_settings

SA_TZ = ZoneInfo("Africa/Johannesburg")
OFFSET_KEY = "clock_offset_seconds"


def now(db: Session | None = None) -> datetime:
    real = datetime.now(UTC)
    if db is None or not get_settings().allow_time_travel:
        return real
    from flowshop.models import Setting

    row = db.get(Setting, OFFSET_KEY)
    return real + timedelta(seconds=int(row.value)) if row else real


def advance(db: Session, delta: timedelta) -> None:
    if not get_settings().allow_time_travel:
        raise PermissionError("Time travel is turned off in this environment")
    from flowshop.models import Setting

    row = db.get(Setting, OFFSET_KEY)
    if row is None:
        db.add(Setting(key=OFFSET_KEY, value=int(delta.total_seconds())))
    else:
        row.value = int(row.value) + int(delta.total_seconds())
    db.flush()


def reset(db: Session) -> None:
    from flowshop.models import Setting

    row = db.get(Setting, OFFSET_KEY)
    if row is not None:
        db.delete(row)
        db.flush()


def local_date(moment: datetime) -> date:
    return moment.astimezone(SA_TZ).date()


def _za_holidays(years: range) -> holidays.HolidayBase:
    return holidays.country_holidays("ZA", years=years)


def is_working_day(day: date) -> bool:
    return day.weekday() < 5 and day not in _za_holidays(range(day.year, day.year + 1))


def add_working_days(moment: datetime, days: int) -> date:
    """The dispatch-by date: `days` South African working days after `moment` (D1)."""
    day = local_date(moment)
    added = 0
    while added < days:
        day += timedelta(days=1)
        if is_working_day(day):
            added += 1
    return day


def working_days_between(start: date, end: date) -> int:
    """Working days from start (exclusive) to end (inclusive). Negative when end is before start."""
    if end < start:
        return -working_days_between(end, start)
    count, day = 0, start
    while day < end:
        day += timedelta(days=1)
        if is_working_day(day):
            count += 1
    return count
