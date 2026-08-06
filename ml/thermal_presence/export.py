import argparse
from pathlib import Path

import numpy as np
import tensorflow as tf

from .features import engineer_features, load_dataset


def convert_to_int8(model: tf.keras.Model, calibration_features: np.ndarray) -> bytes:
    def representative_dataset():
        for sample in calibration_features[:500]:
            yield [sample.reshape(1, -1).astype(np.float32)]

    converter = tf.lite.TFLiteConverter.from_keras_model(model)
    converter.optimizations = [tf.lite.Optimize.DEFAULT]
    converter.representative_dataset = representative_dataset
    converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
    converter.inference_input_type = tf.int8
    converter.inference_output_type = tf.int8
    return converter.convert()


def format_array(values: np.ndarray, values_per_line: int = 8) -> str:
    formatted = [f"{float(value):.6f}f" for value in values]
    return "\n".join(
        "    " + ", ".join(formatted[index : index + values_per_line]) + ","
        for index in range(0, len(formatted), values_per_line)
    )


def write_model_header(model_bytes: bytes, destination: Path) -> None:
    values = [f"0x{value:02x}" for value in model_bytes]
    rows = [
        "    " + ", ".join(values[index : index + 12]) + ","
        for index in range(0, len(values), 12)
    ]
    destination.write_text(
        "\n".join(
            [
                "#ifndef MODEL_DATA_H",
                "#define MODEL_DATA_H",
                "#include <cstdint>",
                "",
                "alignas(16) const unsigned char model_tflite[] = {",
                *rows,
                "};",
                f"const unsigned int model_tflite_len = {len(model_bytes)};",
                "",
                "#endif",
                "",
            ]
        ),
        encoding="utf-8",
    )


def write_scaler_header(mean: np.ndarray, scale: np.ndarray, destination: Path) -> None:
    destination.write_text(
        "\n".join(
            [
                "#ifndef MODEL_PARAMS_H",
                "#define MODEL_PARAMS_H",
                "",
                f"const int N_FEATURES = {len(mean)};",
                f"const float SCALER_MEAN[{len(mean)}] = {{",
                format_array(mean),
                "};",
                f"const float SCALER_SCALE[{len(scale)}] = {{",
                format_array(scale),
                "};",
                "",
                "#endif",
                "",
            ]
        ),
        encoding="utf-8",
    )


def export_pipeline(dataset_path: str | Path, artifacts: str | Path, firmware_include: str | Path) -> None:
    artifact_directory = Path(artifacts)
    scaler = np.load(artifact_directory / "scaler.npz")
    frame = load_dataset(dataset_path)
    features, _, _ = engineer_features(frame)
    scaled = (features - scaler["mean"]) / scaler["scale"]

    model = tf.keras.models.load_model(artifact_directory / "model.keras")
    model_bytes = convert_to_int8(model, scaled)
    (artifact_directory / "model.tflite").write_bytes(model_bytes)

    include_directory = Path(firmware_include)
    include_directory.mkdir(parents=True, exist_ok=True)
    write_model_header(model_bytes, include_directory / "model_data.h")
    write_scaler_header(scaler["mean"], scaler["scale"], include_directory / "model_params.h")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export the model for ESP32 inference")
    parser.add_argument("dataset")
    parser.add_argument("--artifacts", default="artifacts")
    parser.add_argument("--firmware-include", default="../esp32/include")
    arguments = parser.parse_args()
    export_pipeline(arguments.dataset, arguments.artifacts, arguments.firmware_include)


if __name__ == "__main__":
    main()
