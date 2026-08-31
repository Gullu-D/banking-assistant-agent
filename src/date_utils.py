"""
Deterministic date-range resolution.

Converts a `date_range` keyword (e.g. "last_month") into a concrete
(start_date, end_date) pair, always computed relative to the CURRENT date at
runtime. Nothing here is hard-coded to any specific month/year — "last
month" always means the calendar month immediately before whatever "today"
is when the code runs.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from dateutil.relativedelta import relativedelta


def _month_bounds(any_day_in_month: date) -> tuple[date, date]:
    start = any_day_in_month.replace(day=1)
    end = (start + relativedelta(months=1)) - timedelta(days=1)
    return start, end


def resolve_date_range(
    keyword: str,
    today: Optional[date] = None,
    custom_start: Optional[date] = None,
    custom_end: Optional[date] = None,
) -> tuple[Optional[date], Optional[date], str]:
    """Resolve a date-range keyword to (start_date, end_date, human_label).

    start_date/end_date are inclusive. Returns (None, None, "All time") for
    "all_time" (no date filtering applied).
    """
    today = today or date.today()

    if keyword == "today":
        return today, today, today.strftime("%B %d, %Y")

    if keyword == "yesterday":
        y = today - timedelta(days=1)
        return y, y, y.strftime("%B %d, %Y")

    if keyword == "this_week":
        start = today - timedelta(days=today.weekday())  # Monday
        end = today
        return start, end, f"{start.strftime('%B %d, %Y')} – {end.strftime('%B %d, %Y')}"

    if keyword == "last_week":
        this_week_start = today - timedelta(days=today.weekday())
        start = this_week_start - timedelta(days=7)
        end = this_week_start - timedelta(days=1)
        return start, end, f"{start.strftime('%B %d, %Y')} – {end.strftime('%B %d, %Y')}"

    if keyword == "this_month":
        start, end = _month_bounds(today)
        end = min(end, today)
        return start, end, today.strftime("%B %Y")

    if keyword == "last_month":
        last_month_any_day = today.replace(day=1) - timedelta(days=1)
        start, end = _month_bounds(last_month_any_day)
        return start, end, start.strftime("%B %Y")

    if keyword == "last_30_days":
        start = today - timedelta(days=29)
        end = today
        return start, end, f"Last 30 Days ({start.strftime('%b %d')} – {end.strftime('%b %d, %Y')})"

    if keyword == "this_year":
        start = today.replace(month=1, day=1)
        end = today
        return start, end, str(today.year)

    if keyword == "custom" and custom_start and custom_end:
        return custom_start, custom_end, f"{custom_start.strftime('%B %d, %Y')} – {custom_end.strftime('%B %d, %Y')}"

    # all_time / unrecognized -> no filtering
    return None, None, "All Time"
