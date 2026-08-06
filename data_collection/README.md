# Thermal data collection

This directory preserves the reusable data-quality stage that precedes model
training. It accepts labeled 8x8 AMG8833 frames, rejects malformed sensor data,
creates a local CSV backup, retries unreliable uploads with exponential backoff,
and checks class balance before training.

The portfolio repository intentionally excludes collected CSV files. The
original class dataset contained participant identifiers, while locally
collected frames can reveal occupancy patterns and timestamps.

## CSV contract

Each row contains `timestamp`, `label`, and `p0` through `p63`. Labels are
`empty` or `present`; temperatures must be numeric values from 0 to 80 C.

Validate an authorized local collection from the repository root:

```text
python -m data_collection.validate_collection path/to/collection.csv
```

Applications can call `upload_with_retry()` around their HTTP or MQTT gateway,
so the data-quality logic remains independent of a specific course API or
deployment service.
