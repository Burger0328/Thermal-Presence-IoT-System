"""Core utilities for collecting labeled AMG8833 frames."""

from __future__ import annotations

import csv
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence


PIXEL_COUNT = 64
LABELS = {"empty", "present"}
CSV_FIELDS = ["timestamp", "label", *[f"p{i}" for i in range(PIXEL_COUNT)]]


def validate_frame(pixels: Sequence[float], label: str) -> list[str]:
    """Validate one labeled 8x8 frame and return non-fatal warnings."""
    if label not in LABELS:
        raise ValueError("label must be 'empty' or 'present'")
    if not isinstance(pixels, (list, tuple)) or len(pixels) != PIXEL_COUNT:
        raise ValueError("pixels must contain exactly 64 values")
    try:
        values = [float(value) for value in pixels]
    except (TypeError, ValueError) as exc:
        raise ValueError("all pixels must be numeric") from exc
    if any(value < 0.0 or value > 80.0 for value in values):
        raise ValueError("pixel temperatures must be between 0 and 80 C")
    if max(values) == min(values):
        raise ValueError("all pixels are identical; check the sensor")

    warnings: list[str] = []
    if label == "present" and max(values) < 26.0:
        warnings.append("present frame has a maximum temperature below 26 C")
    return warnings


def append_frame(path: str | Path, pixels: Sequence[float], label: str) -> None:
    """Validate and append a frame to a portable local CSV backup."""
    validate_frame(pixels, label)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    is_new = not destination.exists() or destination.stat().st_size == 0
    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "label": label,
        **{f"p{i}": float(value) for i, value in enumerate(pixels)},
    }
    with destination.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        if is_new:
            writer.writeheader()
        writer.writerow(row)


def load_frames(path: str | Path) -> list[dict[str, object]]:
    """Load and validate frames from the collection CSV contract."""
    frames: list[dict[str, object]] = []
    with Path(path).open(newline="", encoding="utf-8") as handle:
        for row_number, row in enumerate(csv.DictReader(handle), start=2):
            try:
                pixels = [float(row[f"p{i}"]) for i in range(PIXEL_COUNT)]
                label = row["label"]
                warnings = validate_frame(pixels, label)
            except (KeyError, ValueError) as exc:
                raise ValueError(f"invalid frame on CSV row {row_number}: {exc}") from exc
            frames.append({"timestamp": row.get("timestamp", ""), "label": label,
                           "pixels": pixels, "warnings": warnings})
    return frames


@dataclass(frozen=True)
class CollectionStats:
    total: int
    empty: int
    present: int
    warnings: int

    @classmethod
    def from_frames(cls, frames: Iterable[Mapping[str, object]]) -> "CollectionStats":
        materialized = list(frames)
        counts = Counter(str(frame["label"]) for frame in materialized)
        warning_count = sum(len(frame.get("warnings", [])) for frame in materialized)
        return cls(len(materialized), counts["empty"], counts["present"], warning_count)

    def is_balanced(self) -> bool:
        return self.total > 0 and self.empty == self.present


def upload_with_retry(
    send: Callable[[], object],
    *,
    attempts: int = 4,
    initial_delay: float = 0.5,
    sleep: Callable[[float], None] = time.sleep,
) -> object:
    """Run an upload with bounded exponential backoff.

    ``send`` should return on success and raise on a network or server failure.
    The final exception is preserved so callers can report its useful context.
    """
    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    for attempt in range(attempts):
        try:
            return send()
        except Exception:
            if attempt == attempts - 1:
                raise
            sleep(initial_delay * (2**attempt))
    raise RuntimeError("unreachable")
