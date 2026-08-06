from collections import deque
from pathlib import Path

import numpy as np
import pandas as pd


PIXEL_COLUMNS = [f"pixel_{index}" for index in range(64)]
FEATURE_COUNT = 76


def load_dataset(path: str | Path) -> pd.DataFrame:
    """Load and validate an AMG8833 presence dataset."""
    frame = pd.read_csv(path)
    required = {"student_id", "label", *PIXEL_COLUMNS}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"Dataset is missing columns: {', '.join(missing)}")

    frame = frame.dropna(subset=list(required)).copy()
    frame = frame[frame["label"].isin({"empty", "present"})]
    frame[PIXEL_COLUMNS] = frame[PIXEL_COLUMNS].apply(pd.to_numeric, errors="coerce")
    frame = frame.dropna(subset=PIXEL_COLUMNS)
    if frame.empty:
        raise ValueError("Dataset has no valid thermal readings")
    return frame


def largest_hot_region(grid: np.ndarray, threshold: float) -> int:
    """Return the largest four-connected region above a temperature threshold."""
    visited = np.zeros((8, 8), dtype=bool)
    largest = 0

    for row in range(8):
        for column in range(8):
            if visited[row, column] or grid[row, column] <= threshold:
                continue

            queue = deque([(row, column)])
            visited[row, column] = True
            size = 0
            while queue:
                current_row, current_column = queue.popleft()
                size += 1
                for row_delta, column_delta in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    next_row = current_row + row_delta
                    next_column = current_column + column_delta
                    if not (0 <= next_row < 8 and 0 <= next_column < 8):
                        continue
                    if visited[next_row, next_column]:
                        continue
                    if grid[next_row, next_column] <= threshold:
                        continue
                    visited[next_row, next_column] = True
                    queue.append((next_row, next_column))
            largest = max(largest, size)

    return largest


def spatial_features(raw_pixels: np.ndarray) -> np.ndarray:
    """Compute eight shape and location features from one 8x8 thermal frame."""
    grid = np.asarray(raw_pixels, dtype=np.float32).reshape(8, 8)
    median = float(np.median(grid))
    threshold = median + 3.0

    horizontal = np.abs(grid[:, 1:] - grid[:, :-1]).mean()
    vertical = np.abs(grid[1:, :] - grid[:-1, :]).mean()
    gradient = float((horizontal + vertical) / 2.0)

    quadrant_means = [
        grid[:4, :4].mean(),
        grid[:4, 4:].mean(),
        grid[4:, :4].mean(),
        grid[4:, 4:].mean(),
    ]
    quadrant_variance = float(np.var(quadrant_means))

    center = grid[2:6, 2:6]
    outer_mask = np.ones((8, 8), dtype=bool)
    outer_mask[2:6, 2:6] = False
    center_vs_edge = float(center.mean() - grid[outer_mask].mean())

    hot_rows, hot_columns = np.where(grid > threshold)
    hot_count = len(hot_rows)
    if hot_count:
        centroid_distance = float(
            np.hypot(hot_rows.mean() - 3.5, hot_columns.mean() - 3.5)
        )
    else:
        centroid_distance = 0.0

    return np.array(
        [
            gradient,
            largest_hot_region(grid, threshold),
            quadrant_variance,
            center_vs_edge,
            float(np.std(grid.max(axis=1))),
            float(np.std(grid.max(axis=0))),
            centroid_distance,
            hot_count / 64.0,
        ],
        dtype=np.float32,
    )


def engineer_features(frame: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Create 76 model features, binary labels, and group identifiers."""
    pixels = frame[PIXEL_COLUMNS].to_numpy(dtype=np.float32)
    medians = np.median(pixels, axis=1, keepdims=True)
    standard_deviations = np.std(pixels, axis=1, keepdims=True)
    standard_deviations = np.maximum(standard_deviations, 0.1)

    normalized_pixels = (pixels - medians) / standard_deviations
    maximum = pixels.max(axis=1, keepdims=True)
    temperature_range = maximum - pixels.min(axis=1, keepdims=True)
    count_above_three = (pixels > medians + 3.0).sum(axis=1, keepdims=True)
    count_above_five = (pixels > medians + 5.0).sum(axis=1, keepdims=True)
    spatial = np.stack([spatial_features(row) for row in pixels])

    features = np.hstack(
        [
            normalized_pixels,
            maximum,
            temperature_range,
            count_above_three,
            count_above_five,
            spatial,
        ]
    ).astype(np.float32)
    if features.shape[1] != FEATURE_COUNT:
        raise RuntimeError(f"Expected {FEATURE_COUNT} features, got {features.shape[1]}")

    labels = (frame["label"].to_numpy() == "present").astype(np.float32)
    groups = frame["student_id"].astype(str).to_numpy()
    return features, labels, groups
