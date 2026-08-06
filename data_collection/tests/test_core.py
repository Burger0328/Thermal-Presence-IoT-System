from pathlib import Path

import pytest

from data_collection.core import (
    CollectionStats,
    append_frame,
    load_frames,
    upload_with_retry,
    validate_frame,
)


def frame(base: float = 22.0) -> list[float]:
    return [base + (index % 8) * 0.2 for index in range(64)]


def test_validation_rejects_bad_shape_range_and_constant_frame():
    with pytest.raises(ValueError, match="64"):
        validate_frame([22.0], "empty")
    with pytest.raises(ValueError, match="between"):
        validate_frame(frame()[:-1] + [81.0], "empty")
    with pytest.raises(ValueError, match="identical"):
        validate_frame([22.0] * 64, "empty")


def test_present_warning_is_nonfatal():
    assert validate_frame(frame(22.0), "present")


def test_csv_round_trip_and_balance(tmp_path: Path):
    destination = tmp_path / "frames.csv"
    append_frame(destination, frame(22.0), "empty")
    append_frame(destination, frame(27.0), "present")
    frames = load_frames(destination)
    stats = CollectionStats.from_frames(frames)
    assert stats.total == 2
    assert stats.empty == stats.present == 1
    assert stats.is_balanced()


def test_retry_uses_exponential_delays():
    calls = 0
    delays: list[float] = []

    def send():
        nonlocal calls
        calls += 1
        if calls < 3:
            raise ConnectionError("temporary")
        return "uploaded"

    assert upload_with_retry(send, sleep=delays.append) == "uploaded"
    assert calls == 3
    assert delays == [0.5, 1.0]


def test_retry_preserves_final_error():
    with pytest.raises(ConnectionError, match="offline"):
        upload_with_retry(lambda: (_ for _ in ()).throw(ConnectionError("offline")),
                          attempts=2, sleep=lambda _: None)
