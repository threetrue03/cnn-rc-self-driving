"""조이스틱으로 RC카를 운전하며 CNN 학습 영상을 수집한다."""

from __future__ import annotations

import argparse
from pathlib import Path

import serial

from myjoystickcamapp import MyJoystickCamApp


DEFAULT_CAMERA_URL = "http://192.168.4.1:81/stream"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RC카 조종 및 학습 데이터 수집")
    parser.add_argument("--port", default="COM6", help="Pico 시리얼 포트")
    parser.add_argument("--baudrate", type=int, default=9600)
    parser.add_argument(
        "--camera",
        default=DEFAULT_CAMERA_URL,
        help="ESP32-CAM MJPEG 스트림 주소",
    )
    parser.add_argument(
        "--dataset",
        default="dataset",
        help="수집 데이터를 저장할 폴더",
    )
    return parser.parse_args()


class CarController:
    """GUI의 차량 상태를 Pico용 1바이트 명령으로 변환한다."""

    COMMAND_GROUPS = (
        ("brake", {True: "B", False: "b"}),
        ("motion", {"FORWARD": "F", "REVERSE": "V", "STOP": "S"}),
        ("steering", {-1: "<", 0: "|", 1: ">"}),
        (
            "turn_signal",
            {"LEFT": "[", "RIGHT": "]", "HAZARD": "H", "OFF": "O"},
        ),
    )

    def __init__(self, port: str, baudrate: int):
        self.serial = serial.Serial(
            port=port,
            baudrate=baudrate,
            timeout=0,
            write_timeout=1,
        )
        self.last_state: dict[str, object] = {}

    def send(self, command: str) -> None:
        if len(command) != 1:
            raise ValueError("명령은 반드시 1글자여야 합니다.")

        self.serial.write(command.encode("ascii"))
        print("전송:", command)

    def update(self, state: dict) -> None:
        current_state = {
            "brake": state["brake"],
            "motion": state["motion"],
            "steering": state["steering"],
            "turn_signal": state.get("turn_signal", "OFF"),
        }

        print(
            f"motion={current_state['motion']}, "
            f"steering={current_state['steering']}, "
            f"brake={current_state['brake']}, "
            f"turn_signal={current_state['turn_signal']}"
        )

        for state_name, command_map in self.COMMAND_GROUPS:
            state_value = current_state[state_name]
            if self.last_state.get(state_name) == state_value:
                continue

            self.send(command_map[state_value])
            self.last_state[state_name] = state_value

    def close(self) -> None:
        if self.serial.is_open:
            # 프로그램 종료 시 차량이 계속 움직이지 않도록 비상 정지한다.
            self.send("!")
            self.serial.close()


def main() -> None:
    args = parse_args()
    controller = CarController(args.port, args.baudrate)
    data_directory = Path(args.dataset).resolve()
    app = MyJoystickCamApp(
        cbControlState=controller.update,
        v_source=args.camera,
        data_directory=data_directory,
    )

    try:
        app.run()
    finally:
        controller.close()


if __name__ == "__main__":
    main()
