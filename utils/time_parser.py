"""Parse time strings to seconds since midnight."""

import re

SECONDS_PER_DAY = 24 * 60 * 60
# Pattern: HH:MM or H:MM
TIME_PATTERN = re.compile(r"^(\d{1,2}):(\d{2})$")


def seconds_to_time(seconds: int) -> str:
    """Format seconds since midnight to HH:MM."""
    h = (seconds // 3600) % 24
    m = (seconds % 3600) // 60
    return f"{h:02d}:{m:02d}"


def parse_time_to_seconds(time_str: str | None) -> int | None:
    """
    Parse "HH:MM" or "H:MM" to seconds since midnight.

    Args:
        time_str: Time string like "10:00", "9:30". None returns None.

    Returns:
        Seconds since midnight (0-86399), or None if invalid/None.
    """
    if not time_str or not time_str.strip():
        return None
    match = TIME_PATTERN.match(time_str.strip())
    if not match:
        return None
    h, m = int(match.group(1)), int(match.group(2))
    if h < 0 or h > 23 or m < 0 or m > 59:
        return None
    return h * 3600 + m * 60
