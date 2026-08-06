import argparse
import json
import random
from pathlib import Path

import numpy as np
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import StandardScaler
import tensorflow as tf
from tensorflow import keras

from .features import engineer_features, load_dataset


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    tf.random.set_seed(seed)


def build_model(input_count: int) -> keras.Model:
    regularizer = keras.regularizers.l2(0.005)
    model = keras.Sequential(
        [
            keras.layers.Input(shape=(input_count,)),
            keras.layers.Dense(32, activation="relu", kernel_regularizer=regularizer),
            keras.layers.Dense(16, activation="relu", kernel_regularizer=regularizer),
            keras.layers.Dense(1, activation="sigmoid"),
        ]
    )
    model.compile(optimizer="adam", loss="binary_crossentropy", metrics=["accuracy"])
    return model


def callbacks() -> list[keras.callbacks.Callback]:
    return [
        keras.callbacks.EarlyStopping(
            monitor="val_accuracy", patience=20, restore_best_weights=True
        ),
        keras.callbacks.ReduceLROnPlateau(
            monitor="val_loss", factor=0.5, patience=10, min_lr=1e-6
        ),
    ]


def train_pipeline(
    dataset_path: str | Path,
    output_directory: str | Path,
    seed: int = 1314,
) -> dict:
    set_seed(seed)
    frame = load_dataset(dataset_path)
    features, labels, groups = engineer_features(frame)

    unique_groups = np.unique(groups)
    split_count = min(5, len(unique_groups))
    if split_count < 2:
        raise ValueError("At least two independent collection groups are required")

    splits = list(GroupKFold(n_splits=split_count).split(features, labels, groups))
    train_indices, validation_indices = splits[-1]
    evaluation_scaler = StandardScaler()
    train_features = evaluation_scaler.fit_transform(features[train_indices])
    validation_features = evaluation_scaler.transform(features[validation_indices])

    evaluation_model = build_model(features.shape[1])
    history = evaluation_model.fit(
        train_features,
        labels[train_indices],
        validation_data=(validation_features, labels[validation_indices]),
        epochs=200,
        batch_size=32,
        callbacks=callbacks(),
        verbose=2,
    )
    probabilities = evaluation_model.predict(validation_features, verbose=0).reshape(-1)
    predictions = (probabilities >= 0.5).astype(np.float32)
    accuracy = float(accuracy_score(labels[validation_indices], predictions))
    report = classification_report(
        labels[validation_indices],
        predictions,
        target_names=["empty", "present"],
        output_dict=True,
        zero_division=0,
    )

    best_epoch = int(np.argmax(history.history["val_accuracy"]) + 1)
    deployment_scaler = StandardScaler()
    all_scaled = deployment_scaler.fit_transform(features)
    deployment_model = build_model(features.shape[1])
    deployment_model.fit(
        all_scaled,
        labels,
        epochs=best_epoch,
        batch_size=32,
        verbose=2,
    )

    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)
    deployment_model.save(output / "model.keras")
    np.savez(output / "scaler.npz", mean=deployment_scaler.mean_, scale=deployment_scaler.scale_)

    metrics = {
        "held_out_accuracy": accuracy,
        "best_epoch": best_epoch,
        "training_samples": int(len(train_indices)),
        "held_out_samples": int(len(validation_indices)),
        "collection_groups": int(len(unique_groups)),
        "classification_report": report,
        "seed": seed,
    }
    (output / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the thermal presence model")
    parser.add_argument("dataset", help="CSV containing pixel_0 through pixel_63")
    parser.add_argument("--output", default="artifacts")
    parser.add_argument("--seed", type=int, default=1314)
    arguments = parser.parse_args()
    metrics = train_pipeline(arguments.dataset, arguments.output, arguments.seed)
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
