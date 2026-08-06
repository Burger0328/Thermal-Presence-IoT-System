import re
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "ml" / "artifacts"
INCLUDE = ROOT / "esp32" / "include"


def test_scaler_matches_firmware_contract():
    scaler = np.load(ARTIFACTS / "scaler.npz")
    assert scaler["mean"].shape == (76,)
    assert scaler["scale"].shape == (76,)
    assert np.all(scaler["scale"] > 0)

    header = (INCLUDE / "model_params.h").read_text(encoding="utf-8")
    assert "const int N_FEATURES = 76;" in header
    assert len(re.findall(r"-?\d+\.\d+f", header)) == 152


def test_model_header_matches_tflite_bytes():
    model = (ARTIFACTS / "model.tflite").read_bytes()
    header = (INCLUDE / "model_data.h").read_text(encoding="utf-8")
    declared = int(re.search(r"model_tflite_len = (\d+);", header).group(1))
    byte_count = len(re.findall(r"0x[0-9a-fA-F]{2}", header))
    assert 0 < len(model) < 50_000
    assert declared == byte_count == len(model)


def test_tflite_model_is_fully_int8():
    import tensorflow as tf

    interpreter = tf.lite.Interpreter(model_path=str(ARTIFACTS / "model.tflite"))
    interpreter.allocate_tensors()
    input_details = interpreter.get_input_details()[0]
    output_details = interpreter.get_output_details()[0]
    assert input_details["shape"][-1] == 76
    assert input_details["dtype"] == np.int8
    assert output_details["dtype"] == np.int8
