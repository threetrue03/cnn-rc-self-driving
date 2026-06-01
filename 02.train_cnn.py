"""수집한 left/straight/right 영상으로 자율주행 CNN을 학습한다."""

from __future__ import annotations

import argparse
import json
import os
import random
from collections import Counter
from pathlib import Path

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import tensorflow as tf
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import train_test_split

from ai_common import (
    CAMERA_MIRROR_HORIZONTAL,
    CAMERA_ROTATION_DEGREES,
    CLASS_NAMES,
    IMAGE_HEIGHT,
    IMAGE_WIDTH,
)


AUTOTUNE = tf.data.AUTOTUNE


def parse_args():
    parser = argparse.ArgumentParser(description="RC카 CNN 학습")
    parser.add_argument("--dataset", default="dataset", help="dataset 폴더")
    parser.add_argument(
        "--output",
        default="trained_model",
        help="모델과 학습 결과를 저장할 폴더",
    )
    parser.add_argument("--epochs", type=int, default=40)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def find_images(dataset_directory: Path):
    image_paths = []
    labels = []

    for label_id, class_name in enumerate(CLASS_NAMES):
        class_images = sorted(
            dataset_directory.glob(f"session_*/{class_name}/*.jpg")
        )

        if not class_images:
            raise FileNotFoundError(
                f"{class_name} 이미지가 없습니다: {dataset_directory}"
            )

        image_paths.extend(str(path) for path in class_images)
        labels.extend([label_id] * len(class_images))

    return np.asarray(image_paths), np.asarray(labels, dtype=np.int32)


def split_data(paths, labels, seed):
    train_paths, temporary_paths, train_labels, temporary_labels = (
        train_test_split(
            paths,
            labels,
            test_size=0.20,
            random_state=seed,
            stratify=labels,
        )
    )

    validation_paths, test_paths, validation_labels, test_labels = (
        train_test_split(
            temporary_paths,
            temporary_labels,
            test_size=0.50,
            random_state=seed,
            stratify=temporary_labels,
        )
    )

    return (
        (train_paths, train_labels),
        (validation_paths, validation_labels),
        (test_paths, test_labels),
    )


def decode_image(path, label):
    image = tf.io.read_file(path)
    image = tf.io.decode_jpeg(image, channels=3)
    image = tf.image.resize(
        image,
        (IMAGE_HEIGHT, IMAGE_WIDTH),
        antialias=True,
    )
    image = tf.cast(image, tf.float32)
    return image, label


def make_dataset(paths, labels, batch_size, training, seed):
    dataset = tf.data.Dataset.from_tensor_slices((paths, labels))

    if training:
        dataset = dataset.shuffle(
            buffer_size=len(paths),
            seed=seed,
            reshuffle_each_iteration=True,
        )

    dataset = dataset.map(
        decode_image,
        num_parallel_calls=AUTOTUNE,
    )
    dataset = dataset.batch(batch_size)
    dataset = dataset.prefetch(AUTOTUNE)
    return dataset


def build_model():
    augmentation = tf.keras.Sequential(
        [
            tf.keras.layers.RandomBrightness(
                factor=0.08,
                value_range=(0.0, 1.0),
            ),
            tf.keras.layers.RandomContrast(factor=0.08),
        ],
        name="brightness_augmentation",
    )

    inputs = tf.keras.Input(
        shape=(IMAGE_HEIGHT, IMAGE_WIDTH, 3),
        name="camera_rgb",
    )
    x = tf.keras.layers.Rescaling(1.0 / 255.0)(inputs)
    x = augmentation(x)
    # 화면 위쪽보다 차량 가까이에 있는 아래쪽 차선이 더 중요하다.
    x = tf.keras.layers.Cropping2D(
        cropping=((30, 0), (0, 0))
    )(x)

    # Donkey Car CNN 계열 구조. 초기 합성곱의 연속 Dropout 대신
    # BatchNormalization을 사용해 작은 데이터에서도 특징을 유지한다.
    x = tf.keras.layers.Conv2D(
        24, (5, 5), strides=(2, 2), padding="same", use_bias=False
    )(x)
    x = tf.keras.layers.BatchNormalization()(x)
    x = tf.keras.layers.Activation("relu")(x)
    x = tf.keras.layers.Conv2D(
        32, (5, 5), strides=(2, 2), padding="same", use_bias=False
    )(x)
    x = tf.keras.layers.BatchNormalization()(x)
    x = tf.keras.layers.Activation("relu")(x)
    x = tf.keras.layers.Conv2D(
        64, (5, 5), strides=(2, 2), padding="same", use_bias=False
    )(x)
    x = tf.keras.layers.BatchNormalization()(x)
    x = tf.keras.layers.Activation("relu")(x)
    x = tf.keras.layers.Conv2D(
        64, (3, 3), strides=(2, 2), padding="same", use_bias=False
    )(x)
    x = tf.keras.layers.BatchNormalization()(x)
    x = tf.keras.layers.Activation("relu")(x)
    x = tf.keras.layers.Flatten()(x)
    x = tf.keras.layers.Dense(100, activation="relu")(x)
    x = tf.keras.layers.Dropout(0.20)(x)
    x = tf.keras.layers.Dense(50, activation="relu")(x)
    x = tf.keras.layers.Dropout(0.15)(x)
    outputs = tf.keras.layers.Dense(
        len(CLASS_NAMES),
        activation="softmax",
        name="steering",
    )(x)

    model = tf.keras.Model(inputs, outputs, name="rc_car_donkey_cnn")
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=0.0003),
        loss="sparse_categorical_crossentropy",
        metrics=["accuracy"],
    )
    return model


def calculate_class_weights(train_labels):
    counts = Counter(int(label) for label in train_labels)
    total = len(train_labels)
    class_count = len(CLASS_NAMES)
    weights = {}
    for label_id in range(class_count):
        inverse_frequency = total / (class_count * counts[label_id])
        # 우회전 표본이 너무 적어 완전 균형 가중치(약 4.9)를 주면
        # 모델이 한 클래스로 붕괴할 수 있으므로 상한을 둔다.
        weights[label_id] = min(inverse_frequency, 3.0)
    return weights


def save_history_plot(history, output_directory):
    figure, axes = plt.subplots(1, 2, figsize=(11, 4))

    axes[0].plot(history.history["loss"], label="train")
    axes[0].plot(history.history["val_loss"], label="validation")
    axes[0].set_title("Loss")
    axes[0].set_xlabel("Epoch")
    axes[0].legend()

    axes[1].plot(history.history["accuracy"], label="train")
    axes[1].plot(history.history["val_accuracy"], label="validation")
    axes[1].set_title("Accuracy")
    axes[1].set_xlabel("Epoch")
    axes[1].legend()

    figure.tight_layout()
    figure.savefig(output_directory / "training_history.png", dpi=150)
    plt.close(figure)


def save_confusion_matrix(matrix, output_directory):
    figure, axis = plt.subplots(figsize=(6, 5))
    image = axis.imshow(matrix, cmap="Blues")
    axis.set_xticks(range(len(CLASS_NAMES)), CLASS_NAMES)
    axis.set_yticks(range(len(CLASS_NAMES)), CLASS_NAMES)
    axis.set_xlabel("Predicted")
    axis.set_ylabel("Actual")
    axis.set_title("Confusion matrix")

    for row in range(matrix.shape[0]):
        for column in range(matrix.shape[1]):
            axis.text(
                column,
                row,
                str(matrix[row, column]),
                ha="center",
                va="center",
            )

    figure.colorbar(image, ax=axis)
    figure.tight_layout()
    figure.savefig(output_directory / "confusion_matrix.png", dpi=150)
    plt.close(figure)


def counts_by_name(labels):
    counts = Counter(int(label) for label in labels)
    return {
        class_name: counts[index]
        for index, class_name in enumerate(CLASS_NAMES)
    }


def main():
    args = parse_args()
    random.seed(args.seed)
    np.random.seed(args.seed)
    tf.keras.utils.set_random_seed(args.seed)

    dataset_directory = Path(args.dataset).resolve()
    output_directory = Path(args.output).resolve()
    output_directory.mkdir(parents=True, exist_ok=True)

    paths, labels = find_images(dataset_directory)
    train, validation, test = split_data(paths, labels, args.seed)
    train_paths, train_labels = train
    validation_paths, validation_labels = validation
    test_paths, test_labels = test

    print("전체 데이터:", counts_by_name(labels))
    print("학습 데이터:", counts_by_name(train_labels))
    print("검증 데이터:", counts_by_name(validation_labels))
    print("시험 데이터:", counts_by_name(test_labels))

    train_dataset = make_dataset(
        train_paths,
        train_labels,
        args.batch_size,
        training=True,
        seed=args.seed,
    )
    validation_dataset = make_dataset(
        validation_paths,
        validation_labels,
        args.batch_size,
        training=False,
        seed=args.seed,
    )
    test_dataset = make_dataset(
        test_paths,
        test_labels,
        args.batch_size,
        training=False,
        seed=args.seed,
    )

    model = build_model()
    model.summary()

    best_model_path = output_directory / "best_model.keras"
    callbacks = [
        tf.keras.callbacks.ModelCheckpoint(
            best_model_path,
            monitor="val_loss",
            save_best_only=True,
            verbose=1,
        ),
        tf.keras.callbacks.EarlyStopping(
            monitor="val_loss",
            patience=7,
            restore_best_weights=True,
            verbose=1,
        ),
        tf.keras.callbacks.ReduceLROnPlateau(
            monitor="val_loss",
            factor=0.5,
            patience=3,
            min_lr=0.00001,
            verbose=1,
        ),
        tf.keras.callbacks.CSVLogger(
            output_directory / "training_history.csv"
        ),
    ]

    class_weights = calculate_class_weights(train_labels)
    print("클래스 가중치:", class_weights)

    history = model.fit(
        train_dataset,
        validation_data=validation_dataset,
        epochs=args.epochs,
        class_weight=class_weights,
        callbacks=callbacks,
        verbose=2,
    )

    # EarlyStopping이 복구한 최적 가중치를 최종 파일에도 저장한다.
    model.save(output_directory / "model.keras")
    save_history_plot(history, output_directory)

    test_loss, test_accuracy = model.evaluate(
        test_dataset,
        verbose=1,
    )
    probabilities = model.predict(test_dataset, verbose=1)
    predictions = np.argmax(probabilities, axis=1)

    matrix = confusion_matrix(
        test_labels,
        predictions,
        labels=range(len(CLASS_NAMES)),
    )
    np.savetxt(
        output_directory / "confusion_matrix.csv",
        matrix,
        delimiter=",",
        fmt="%d",
    )
    save_confusion_matrix(matrix, output_directory)

    report = classification_report(
        test_labels,
        predictions,
        labels=range(len(CLASS_NAMES)),
        target_names=CLASS_NAMES,
        output_dict=True,
        zero_division=0,
    )

    metrics = {
        "test_loss": float(test_loss),
        "test_accuracy": float(test_accuracy),
        "classification_report": report,
        "confusion_matrix": matrix.tolist(),
    }
    with (output_directory / "test_metrics.json").open(
        "w", encoding="utf-8"
    ) as file:
        json.dump(metrics, file, ensure_ascii=False, indent=2)

    metadata = {
        "class_names": list(CLASS_NAMES),
        "image_width": IMAGE_WIDTH,
        "image_height": IMAGE_HEIGHT,
        "camera_rotation_degrees": CAMERA_ROTATION_DEGREES,
        "camera_mirror_horizontal": CAMERA_MIRROR_HORIZONTAL,
        "dataset_directory": str(dataset_directory),
        "dataset_counts": counts_by_name(labels),
        "split_counts": {
            "train": counts_by_name(train_labels),
            "validation": counts_by_name(validation_labels),
            "test": counts_by_name(test_labels),
        },
        "class_weights": {
            CLASS_NAMES[index]: float(weight)
            for index, weight in class_weights.items()
        },
        "test_accuracy": float(test_accuracy),
    }
    with (output_directory / "model_metadata.json").open(
        "w", encoding="utf-8"
    ) as file:
        json.dump(metadata, file, ensure_ascii=False, indent=2)

    print()
    print("학습 완료")
    print("모델:", output_directory / "model.keras")
    print(f"시험 정확도: {test_accuracy:.4f}")


if __name__ == "__main__":
    main()
