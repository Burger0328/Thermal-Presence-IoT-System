"""Print a privacy-safe summary of a local thermal collection."""

from __future__ import annotations

import argparse

from data_collection.core import CollectionStats, load_frames


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", help="CSV containing timestamp, label, and p0-p63")
    args = parser.parse_args()
    stats = CollectionStats.from_frames(load_frames(args.csv))
    print(f"Frames: {stats.total}")
    print(f"Empty: {stats.empty}")
    print(f"Present: {stats.present}")
    print(f"Balanced: {'yes' if stats.is_balanced() else 'no'}")
    print(f"Label warnings: {stats.warnings}")


if __name__ == "__main__":
    main()
