# TinyML pipeline

This directory contains the project-owned data interface, 76-feature thermal
pipeline, grouped evaluation, final-model training, and full-INT8 export used by
the ESP32 firmware.

The original training CSV is intentionally excluded because it contains
collection identifiers from other course participants. To reproduce training,
provide an authorized CSV with these columns:

- `student_id`: collection-group identifier used to prevent group leakage
- `label`: `empty` or `present`
- `pixel_0` through `pixel_63`: one AMG8833 thermal frame

Run from the repository root:

```text
python -m pip install -r ml/requirements.txt
python -m ml.thermal_presence.train path/to/thermal_dataset.csv --output ml/artifacts
python -m ml.thermal_presence.export path/to/thermal_dataset.csv \
  --artifacts ml/artifacts --firmware-include esp32/include
```

Training evaluates on a held-out collection group, records metrics, then trains
a fresh deployment model on all authorized samples using the exact scaler that
is exported to firmware. Export uses representative calibration frames to
produce an INT8-input/INT8-output TFLite model.
