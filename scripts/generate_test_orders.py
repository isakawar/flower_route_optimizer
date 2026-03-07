#!/usr/bin/env python3
"""Generate realistic test delivery orders around Kyiv for the route optimizer."""

import argparse
import csv
import random
import sys
from pathlib import Path

OUTPUT_PATH = Path(__file__).resolve().parent.parent / "data" / "test_orders.csv"

# ---------------------------------------------------------------------------
# Street pool — grouped by geographic zone
# ---------------------------------------------------------------------------

STREETS: dict[str, list[str]] = {
    # Historic centre / Pechersk / Shevchenkivskyi
    "center": [
        "Khreshchatyk",
        "Volodymyrska",
        "Lesi Ukrainky Boulevard",
        "Instytutska",
        "Bankova",
        "Prorizna",
        "Bohdana Khmelnytskoho",
        "Tarasa Shevchenka Boulevard",
        "Pushkinska",
        "Velyka Vasylkivska",
        "Antonovycha",
        "Zhylianska",
        "Baseina",
        "Panasa Myrnoho",
        "Mechnikova",
        "Sichnevoho Povstannia",
    ],

    # Left bank — Dniprovskyi / Darnytskyi / Desnianski districts
    "left_bank": [
        "Mykhaila Braichevskogo",
        "Revutskoho",
        "Raiduzhna",
        "Miloslavska",
        "Serhiia Danченка",
        "Akademika Zabolotnoho",
        "Baltiiska",
        "Urlivska",
        "Trostianetska",
        "Knyshova",
        "Petra Hryhorenka Avenue",
        "Brovarskyi Avenue",
        "Leninahirska",
        "Chernihivska",
        "Voskresenka",
    ],

    # Right bank — Obolon / Podil / Syrets / Sviatoshyn
    "right_bank": [
        "Obolonska",
        "Obolon Avenue",
        "Heroiv Dnipra",
        "Marshala Tymoshenka",
        "Minska",
        "Pivnichna",
        "Bratyslavska",
        "Pryorianka",
        "Syretska",
        "Shcherbakivska",
        "Saksahanskoho",
        "Petropavlivska",
        "Kontraktova Square",
        "Sahaidachnoho",
        "Illinska",
        "Yaroslavska",
    ],

    # Outskirts / satellite towns
    "outskirts": [
        ("Brovary", "Kyivska"),
        ("Brovary", "Nezalezhnosti"),
        ("Brovary", "Heroiv Ukrainy"),
        ("Brovary", "Bohdana Khmelnytskoho"),
        ("Vyshneve", "Bilotserkivska"),
        ("Vyshneve", "Nezalezhnosti"),
        ("Vyshneve", "Kyivska"),
        ("Irpin", "Universytetska"),
        ("Irpin", "Soborna"),
        ("Irpin", "Yavorova"),
        ("Irpin", "Shevchenkа"),
        ("Bucha", "Vokzalna"),
        ("Bucha", "Yablunska"),
    ],
}

# Probability weights for each zone (must sum to 1.0)
ZONE_WEIGHTS = {
    "center":    0.35,
    "right_bank": 0.25,
    "left_bank":  0.25,
    "outskirts":  0.15,
}

# ---------------------------------------------------------------------------
# Time window presets — (start, end)
# ---------------------------------------------------------------------------

TIME_WINDOWS = [
    ("09:00", "10:00"),
    ("10:00", "11:00"),
    ("10:00", "12:00"),
    ("11:00", "13:00"),
    ("12:00", "14:00"),
    ("13:00", "15:00"),
    ("14:00", "16:00"),
    ("15:00", "17:00"),
    ("16:00", "18:00"),
]

# 30 % of orders get a time window
TIME_WINDOW_PROBABILITY = 0.30


def pick_address() -> tuple[str, str, str]:
    """Return (city, street, house) for a random Kyiv-area address."""
    zones = list(ZONE_WEIGHTS.keys())
    weights = [ZONE_WEIGHTS[z] for z in zones]
    zone = random.choices(zones, weights=weights, k=1)[0]

    streets = STREETS[zone]
    choice = random.choice(streets)

    if zone == "outskirts":
        city, street = choice          # tuple ("Brovary", "Kyivska")
    else:
        city = "Kyiv"
        street = choice

    house = str(random.randint(1, 200))
    # Occasionally append a letter suffix (apartment block variant)
    if random.random() < 0.15:
        house += random.choice(["а", "б", "в", "г"])

    return city, street, house


def pick_time_window() -> tuple[str, str] | tuple[None, None]:
    """Return a (time_start, time_end) pair or (None, None) for no window."""
    if random.random() < TIME_WINDOW_PROBABILITY:
        return random.choice(TIME_WINDOWS)
    return None, None


def generate_orders(n: int, seed: int | None) -> list[dict]:
    if seed is not None:
        random.seed(seed)

    orders = []
    for order_id in range(1, n + 1):
        city, street, house = pick_address()
        time_start, time_end = pick_time_window()
        orders.append({
            "id": order_id,
            "city": city,
            "address": street,
            "house": house,
            "time_start": time_start or "",
            "time_end": time_end or "",
        })
    return orders


def write_csv(orders: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["id", "city", "address", "house", "time_start", "time_end"]
        )
        writer.writeheader()
        writer.writerows(orders)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="generate_test_orders.py",
        description="Generate a synthetic CSV of Kyiv delivery orders.",
    )
    parser.add_argument(
        "--orders",
        type=int,
        default=10,
        metavar="N",
        help="Number of orders to generate (default: 10)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        metavar="N",
        help="Random seed for reproducible output",
    )
    parser.add_argument(
        "--output",
        default=str(OUTPUT_PATH),
        metavar="PATH",
        help=f"Output CSV path (default: {OUTPUT_PATH})",
    )
    parsed = parser.parse_args()

    if parsed.orders < 1:
        print("Error: --orders must be >= 1")
        sys.exit(1)

    orders = generate_orders(parsed.orders, parsed.seed)
    out_path = Path(parsed.output)
    write_csv(orders, out_path)

    windowed = sum(1 for o in orders if o["time_start"])
    zones_used: dict[str, int] = {}
    for o in orders:
        city = o["city"]
        zone = city if city != "Kyiv" else "Kyiv"
        zones_used[zone] = zones_used.get(zone, 0) + 1

    print(f"Generated {len(orders)} orders → {out_path}")
    print(f"  With time window: {windowed}  ({windowed * 100 // len(orders)}%)")
    print(f"  Flexible:         {len(orders) - windowed}")
    print("  Cities:")
    for city, count in sorted(zones_used.items(), key=lambda x: -x[1]):
        print(f"    {city}: {count}")
    print()
    print("Run the optimizer:")
    print(
        f'  python scripts/run_optimizer.py {out_path} "Kyiv, Nahorna 18"'
        f" --start-time 10:00"
    )


if __name__ == "__main__":
    main()
