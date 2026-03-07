"""Read delivery orders from a CSV file."""

import csv
from pathlib import Path

from models.order import Order


def read_orders(csv_path: str | Path) -> list[Order]:
    """
    Read delivery orders from a CSV file.

    Expected columns: id, city, address, house, time_start, time_end.
    Empty time_start/time_end are allowed (no time window).

    Returns:
        List of Order objects.
    """
    path = Path(csv_path)
    orders: list[Order] = []

    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            order = Order(
                id=int(row["id"]),
                city=row["city"].strip(),
                address=row["address"].strip(),
                house=row["house"].strip(),
                time_start=(row.get("time_start") or "").strip() or None,
                time_end=(row.get("time_end") or "").strip() or None,
            )
            orders.append(order)

    return orders
