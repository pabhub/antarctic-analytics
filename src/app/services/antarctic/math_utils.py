from __future__ import annotations

import calendar
from datetime import datetime
from math import atan2, ceil, cos, radians, sin
from statistics import fmean

from app.models import TimeAggregation


def avg(values: list[float | None]) -> float | None:
    real = [v for v in values if v is not None]
    return round(fmean(real), 3) if real else None


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, ceil(p * len(ordered)) - 1))
    return round(ordered[index], 3)


def avg_angle_deg(values: list[float | None]) -> float | None:
    angles = [v for v in values if v is not None]
    if not angles:
        return None
    x = sum(cos(radians(a)) for a in angles)
    y = sum(sin(radians(a)) for a in angles)
    if x == 0 and y == 0:
        return None
    angle = atan2(y, x)
    return round((angle * 180.0 / 3.141592653589793) % 360, 3)


def dominant_angle_deg(values: list[float | None]) -> float | None:
    angles = [v for v in values if v is not None]
    if not angles:
        return None
    bins = [0] * 16
    for value in angles:
        normalized = value % 360.0
        index = int(((normalized + 11.25) % 360) // 22.5)
        bins[index] += 1
    max_count = max(bins)
    if max_count <= 0:
        return None
    dominant_index = bins.index(max_count)
    return round((dominant_index * 22.5) % 360.0, 3)


def wind_toward_direction_deg(direction_from_deg: float | None) -> float | None:
    if direction_from_deg is None:
        return None
    return round((direction_from_deg + 180.0) % 360.0, 3)


def point_hours(aggregation: TimeAggregation) -> float:
    if aggregation == TimeAggregation.NONE:
        return 10.0 / 60.0
    if aggregation == TimeAggregation.HOURLY:
        return 1.0
    if aggregation == TimeAggregation.DAILY:
        return 24.0
    return 30.0 * 24.0


def add_one_calendar_month(value: datetime) -> datetime:
    if value.month == 12:
        year = value.year + 1
        month = 1
    else:
        year = value.year
        month = value.month + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def expected_points(start_local: datetime, end_local: datetime, aggregation: TimeAggregation) -> int:
    if end_local <= start_local:
        return 0
    total_seconds = (end_local - start_local).total_seconds()
    if aggregation == TimeAggregation.NONE:
        return max(1, int(total_seconds // 600))
    if aggregation == TimeAggregation.HOURLY:
        return max(1, int(total_seconds // 3600))
    if aggregation == TimeAggregation.DAILY:
        return max(1, int(total_seconds // 86400))
    count = 0
    cursor = start_local
    while cursor < end_local:
        cursor = add_one_calendar_month(cursor)
        count += 1
        if count > 240:
            break
    return max(1, count)
