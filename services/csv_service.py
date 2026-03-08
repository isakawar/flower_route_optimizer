"""Read delivery orders from a CSV file."""

import csv
from pathlib import Path

from models.order import Order


def read_orders(csv_path: str | Path) -> list[Order]:
    """
    Read delivery orders from a CSV file.

    Expected columns: id, city, address, house,
                      delivery_window_start, delivery_window_end.
    Legacy columns time_start / time_end are accepted for backward compatibility.
    Window columns may be empty (no time constraint for that stop).

    Returns:
        List of Order objects.
    """
    path = Path(csv_path)
    orders: list[Order] = []

    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader, start=1):
            # id column is optional — auto-generate if absent
            order_id = int(row["id"]) if "id" in row and row["id"].strip() else idx

            # Prefer new names; fall back to legacy names
            tw_start = (
                row.get("delivery_window_start")
                or row.get("time_start")
                or ""
            ).strip() or None
            tw_end = (
                row.get("delivery_window_end")
                or row.get("time_end")
                or ""
            ).strip() or None

            order = Order(
                id=order_id,
                city=row["city"].strip(),
                address=row["address"].strip(),
                house=row["house"].strip(),
                time_start=tw_start,
                time_end=tw_end,
            )
            orders.append(order)

    return orders
