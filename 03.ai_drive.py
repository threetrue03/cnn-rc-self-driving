"""학습한 CNN으로 카메라를 보며 RC카를 자율주행한다."""

from __future__ import annotations

import argparse
import os
import queue
import threading
import time
from pathlib import Path

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import cv2
import numpy as np
import requests
import serial
import tensorflow as tf

from ai_common import (
    CLASS_NAMES,
    STEERING_COMMANDS,
    load_model_metadata,
    rotate_camera_frame,
)


def parse_args():
    parser = argparse.ArgumentParser(description="RC카 CNN 자율주행")
    parser.add_argument(
        "--model",
        default="trained_model/model.keras",
        help="학습된 Keras 모델",
    )
    parser.add_argument(
        "--camera",
        default="http://192.168.4.1:81/stream",
        help="ESP32-CAM MJPEG 스트림 주소",
    )
    parser.add_argument("--port", default="COM6")
    parser.add_argument("--baudrate", type=int, default=9600)
    parser.add_argument(
        "--confidence",
        type=float,
        default=0.52,
        help="이 값보다 예측 확률이 낮으면 정지",
    )
    parser.add_argument(
        "--no-serial",
        action="store_true",
        help="차량 명령 없이 화면과 예측만 시험",
    )
    parser.add_argument(
        "--fullscreen",
        action="store_true",
        help="카메라 창을 전체 화면으로 표시",
    )
    parser.add_argument(
        "--debug-serial",
        action="store_true",
        help="실제로 전송하는 상태 명령을 터미널에 표시",
    )
    return parser.parse_args()


class SerialCar:
    HEARTBEAT_SECONDS = 0.25

    def __init__(self, port, baudrate, disabled=False, debug=False):
        self.disabled = disabled
        self.debug = debug
        self.serial = None
        self.last_by_group = {}
        self.last_heartbeat = 0.0
        self.current_steering_command = "|"

        if not disabled:
            self.serial = serial.Serial(
                port=port,
                baudrate=baudrate,
                timeout=0,
                write_timeout=1,
            )
            time.sleep(0.4)

        self.send("A", force=True)
        self.send("S", group="motion", force=True)
        self.send("|", group="steering", force=True)
        self.send("B", group="brake", force=True)
        self.send("O", group="signal", force=True)

    def send(self, command, group=None, force=False):
        if len(command) != 1:
            raise ValueError("차량 명령은 한 글자여야 합니다.")

        previous_command = self.last_by_group.get(group) if group else None

        if group and not force and previous_command == command:
            return

        if self.serial is not None:
            self.serial.write(command.encode("ascii"))

        if group:
            self.last_by_group[group] = command

        if self.debug and (not group or previous_command != command):
            print(f"SERIAL TX  {group or 'command':>8}: {command!r}")

    def drive(self, label):
        self.current_steering_command = STEERING_COMMANDS[label]
        self.send("b", group="brake")
        self.send(self.current_steering_command, group="steering")
        self.send("F", group="motion")

        now = time.monotonic()
        if now - self.last_heartbeat >= self.HEARTBEAT_SECONDS:
            # Pico가 통신 시간 초과로 제동/중앙 조향한 경우에도
            # 현재 브레이크, 조향, 전진 상태를 모두 정상 복구한다.
            self.send("b", group="brake", force=True)
            self.send(
                self.current_steering_command,
                group="steering",
                force=True,
            )
            self.send("F", force=True)
            self.last_heartbeat = now

    def stop(self, brake_light=True):
        self.current_steering_command = "|"
        self.send("S", group="motion", force=True)
        self.send("|", group="steering")
        self.send("B" if brake_light else "b", group="brake")

    def set_signal(self, mode):
        commands = {
            "OFF": "O",
            "LEFT": "[",
            "RIGHT": "]",
            "HAZARD": "H",
        }
        self.send(commands[mode], group="signal")

    def close(self):
        try:
            self.send("!", force=True)
        finally:
            if self.serial is not None and self.serial.is_open:
                self.serial.close()


class PredictionWorker(threading.Thread):
    def __init__(self, model, class_names, width, height):
        super().__init__(daemon=True)
        self.model = model
        self.class_names = class_names
        self.width = width
        self.height = height
        # 교재 예제처럼 큐에 프레임을 받고, 추론 직전에 오래된 것을 버린다.
        self.frames = queue.Queue(maxsize=10)
        self.running = True
        self.result_lock = threading.Lock()
        self.latest_result = None
        self.smoothed_probabilities = None
        self.normalization_in_model = any(
            isinstance(layer, tf.keras.layers.Rescaling)
            for layer in model.layers
        )

    def submit(self, frame):
        try:
            self.frames.put_nowait(frame.copy())
        except queue.Full:
            # 카메라 수신을 CNN 처리 속도 때문에 기다리게 하지 않는다.
            pass

    def get_result(self):
        with self.result_lock:
            return self.latest_result

    def run(self):
        while self.running:
            try:
                frame = self.frames.get(timeout=0.2)
            except queue.Empty:
                continue

            thrown_frames = 0
            while not self.frames.empty():
                try:
                    frame = self.frames.get_nowait()
                    thrown_frames += 1
                except queue.Empty:
                    break

            if thrown_frames:
                print(f"오래된 프레임 {thrown_frames}장 버림")

            resized = cv2.resize(frame, (self.width, self.height))
            rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
            batch = np.expand_dims(rgb, axis=0).astype(np.float32)

            # 교재 모델처럼 정규화 층이 없는 모델은 여기서 /255를 한다.
            # 현재 학습 모델은 Rescaling 층이 있으므로 중복 정규화하지 않는다.
            if not self.normalization_in_model:
                batch /= 255.0

            probabilities = self.model(batch, training=False).numpy()[0]

            if self.smoothed_probabilities is None:
                self.smoothed_probabilities = probabilities
            else:
                # 순간적인 한 프레임의 오판으로 핸들이 흔들리지 않게 한다.
                alpha = 0.45
                self.smoothed_probabilities = (
                    alpha * probabilities
                    + (1.0 - alpha) * self.smoothed_probabilities
                )

            label_id = int(np.argmax(self.smoothed_probabilities))
            result = {
                "label": self.class_names[label_id],
                "confidence": float(
                    self.smoothed_probabilities[label_id]
                ),
                "probabilities": self.smoothed_probabilities.copy(),
                "time": time.monotonic(),
            }

            with self.result_lock:
                self.latest_result = result

    def stop(self):
        self.running = False
        self.join(timeout=1.0)


def draw_overlay(
    frame,
    result,
    armed,
    confidence_limit,
    class_names,
    signal,
):
    display = frame.copy()
    panel_height = 155
    cv2.rectangle(
        display,
        (0, 0),
        (display.shape[1], panel_height),
        (0, 0, 0),
        -1,
    )

    if armed:
        state_text = "AUTO: DRIVING"
        state_color = (0, 220, 0)
    else:
        state_text = "AUTO: PAUSED"
        state_color = (0, 180, 255)

    cv2.putText(
        display,
        state_text,
        (20, 35),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.85,
        state_color,
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        display,
        f"Signal: {signal}",
        (280, 35),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )

    if result is not None:
        label = result["label"].upper()
        confidence = result["confidence"]
        safe = confidence >= confidence_limit
        color = (0, 220, 0) if safe else (0, 0, 255)
        cv2.putText(
            display,
            f"Prediction: {label}  {confidence:.1%}",
            (20, 70),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            color,
            2,
            cv2.LINE_AA,
        )

        for index, class_name in enumerate(class_names):
            value = float(result["probabilities"][index])
            y = 98 + index * 18
            cv2.putText(
                display,
                f"{class_name:8s} {value:.2f}",
                (20, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.48,
                (230, 230, 230),
                1,
                cv2.LINE_AA,
            )
            cv2.rectangle(
                display,
                (155, y - 10),
                (155 + int(value * 180), y),
                (180, 220, 255),
                -1,
            )

    help_text = (
        "A: start   SPACE: brake/pause   "
        "Q/E/H/0: signal   ESC: exit"
    )
    cv2.putText(
        display,
        help_text,
        (20, display.shape[0] - 20),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.58,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )
    return display


def iter_mjpeg_frames(response):
    """requests 스트림에서 JPEG 한 장씩 복원한다."""

    buffer = bytearray()
    jpeg_start = b"\xff\xd8"
    jpeg_end = b"\xff\xd9"

    for chunk in response.iter_content(chunk_size=4096):
        if not chunk:
            continue

        buffer.extend(chunk)

        while True:
            start = buffer.find(jpeg_start)
            if start < 0:
                if len(buffer) > 2_000_000:
                    del buffer[:-2]
                break

            end = buffer.find(jpeg_end, start + 2)
            if end < 0:
                if start > 0:
                    del buffer[:start]
                break

            jpeg = bytes(buffer[start : end + 2])
            del buffer[: end + 2]

            frame = cv2.imdecode(
                np.frombuffer(jpeg, dtype=np.uint8),
                cv2.IMREAD_COLOR,
            )

            if frame is not None:
                yield frame


def main():
    args = parse_args()
    model_path = Path(args.model).resolve()
    metadata_path = model_path.parent / "model_metadata.json"

    if not model_path.exists():
        raise FileNotFoundError(
            f"모델이 없습니다. 먼저 02.train_cnn.py를 실행하세요: {model_path}"
        )

    metadata = load_model_metadata(metadata_path)
    class_names = tuple(metadata.get("class_names", CLASS_NAMES))

    if set(class_names) != set(CLASS_NAMES):
        raise ValueError(
            f"모델 분류 이름이 맞지 않습니다: {class_names}"
        )

    width = int(metadata.get("image_width", 160))
    height = int(metadata.get("image_height", 120))
    rotation = int(metadata.get("camera_rotation_degrees", 180))
    mirror = bool(metadata.get("camera_mirror_horizontal", True))

    print("모델을 불러오는 중입니다...")
    model = tf.keras.models.load_model(model_path)

    if int(model.output_shape[-1]) != len(class_names):
        raise ValueError(
            "모델 출력 개수와 조향 클래스 개수가 다릅니다. "
            f"model={model.output_shape[-1]}, classes={len(class_names)}"
        )

    worker = PredictionWorker(
        model,
        class_names,
        width,
        height,
    )
    worker.start()

    car = SerialCar(
        args.port,
        args.baudrate,
        disabled=args.no_serial,
        debug=args.debug_serial,
    )
    stream = None

    window_name = "RC Car CNN Autonomous Driving"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window_name, 1280, 720)
    if args.fullscreen:
        cv2.setWindowProperty(
            window_name,
            cv2.WND_PROP_FULLSCREEN,
            cv2.WINDOW_FULLSCREEN,
        )

    armed = False
    signal = "OFF"

    print("준비 완료: A를 누르면 출발, Space는 정지, ESC는 종료")

    try:
        # 교재 예제와 같은 requests 기반 MJPEG 수신 방식.
        stream = requests.get(
            args.camera,
            stream=True,
            timeout=(3.0, 5.0),
        )
        stream.raise_for_status()

        for raw_frame in iter_mjpeg_frames(stream):
            frame = rotate_camera_frame(raw_frame, rotation, mirror)
            worker.submit(frame)
            result = worker.get_result()

            result_is_fresh = (
                result is not None
                and time.monotonic() - result["time"] < 0.7
            )
            result_is_confident = (
                result_is_fresh
                and result["confidence"] >= args.confidence
            )

            if armed and result_is_confident:
                car.drive(result["label"])
            elif armed:
                # 판단이 애매하거나 추론이 멈추면 전진하지 않는다.
                car.stop(brake_light=True)

            display = draw_overlay(
                frame,
                result,
                armed,
                args.confidence,
                class_names,
                signal,
            )
            cv2.imshow(window_name, display)
            key = cv2.waitKey(1) & 0xFF

            if key == ord("a"):
                armed = True
            elif key == 32:
                armed = False
                car.stop(brake_light=True)
            elif key == ord("q"):
                signal = "OFF" if signal == "LEFT" else "LEFT"
                car.set_signal(signal)
            elif key == ord("e"):
                signal = "OFF" if signal == "RIGHT" else "RIGHT"
                car.set_signal(signal)
            elif key == ord("h"):
                signal = "OFF" if signal == "HAZARD" else "HAZARD"
                car.set_signal(signal)
            elif key == ord("0"):
                signal = "OFF"
                car.set_signal(signal)
            elif key == 27:
                break
        else:
            raise RuntimeError("카메라 스트림이 종료되었습니다.")
    except requests.RequestException as error:
        raise RuntimeError(
            f"카메라 스트림 연결 오류: {args.camera}"
        ) from error
    finally:
        car.close()
        worker.stop()
        if stream is not None:
            stream.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
