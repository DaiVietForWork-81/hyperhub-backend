from __future__ import annotations

import re

MULTIPLIERS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def parse_time(time_str: str) -> int | None:
    """Chuyển chuỗi như '30s', '1m', '1h', '2d' sang số giây."""
    if not time_str:
        return None

    match = re.match(r"^(\d+)([smhd])$", time_str.strip().lower())
    if not match:
        return None

    amount = int(match.group(1))
    unit = match.group(2)
    return amount * MULTIPLIERS[unit]