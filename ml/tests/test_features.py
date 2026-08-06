import numpy as np
import pandas as pd
import pytest

from ml.thermal_presence.features import (
    FEATURE_COUNT,
    PIXEL_COLUMNS,
    engineer_features,
    largest_hot_region,
    spatial_features,
)


EMPTY = np.full(64, 23.0, dtype=np.float32)
PRESENT = EMPTY.copy().reshape(8, 8)
PRESENT[2:6, 2:6] = 29.0
PRESENT = PRESENT.reshape(-1)


def frame(rows):
    result = pd.DataFrame([pixels for pixels, _, _ in rows], columns=PIXEL_COLUMNS)
    result["label"] = [label for _, label, _ in rows]
    result["student_id"] = [group for _, _, group in rows]
    return result


def test_feature_contract_and_labels():
    features, labels, groups = engineer_features(
        frame([(EMPTY, "empty", "a"), (PRESENT, "present", "b")])
    )
    assert features.shape == (2, FEATURE_COUNT)
    assert labels.tolist() == [0.0, 1.0]
    assert groups.tolist() == ["a", "b"]
    assert np.isfinite(features).all()


def test_normalized_pixels_are_ambient_invariant():
    features, _, _ = engineer_features(
        frame([(PRESENT, "present", "a"), (PRESENT + 5.0, "present", "b")])
    )
    np.testing.assert_allclose(features[0, :64], features[1, :64], atol=1e-5)


def test_connected_region_uses_four_way_adjacency():
    grid = np.zeros((8, 8), dtype=np.float32)
    grid[0, 0] = grid[0, 1] = grid[1, 1] = 10.0
    grid[7, 7] = 10.0
    assert largest_hot_region(grid, 5.0) == 3


def test_presence_frame_has_expected_spatial_signal():
    empty_features = spatial_features(EMPTY)
    present_features = spatial_features(PRESENT)
    assert present_features[0] > empty_features[0]
    assert present_features[1] == 16
    assert present_features[3] > 0
    assert present_features[7] == pytest.approx(16 / 64)


def test_uniform_frame_is_stable():
    features, _, _ = engineer_features(frame([(EMPTY, "empty", "a")]))
    assert np.isfinite(features).all()
    np.testing.assert_allclose(features[0, :64], 0.0)
