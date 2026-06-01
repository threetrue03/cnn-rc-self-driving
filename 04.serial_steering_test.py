"""카메라와 CNN을 제외하고 PC-Pico 조향 명령만 검사한다."""

from __future__ import annotations

import argparse
import time

import serial


def parse_args():
    parser = argparse.ArgumentParser(description="RC카 시리얼 조향 검사")
    parser.add_argument("--port", default="COM6")
    parser.add_argument("--baudrate", type=int, default=9600)
    return parser.parse_args()


def send(connection, command):
    connection.write(command.encode("ascii"))
    connection.flush()
    print(f"전송: {command!r}")


def repeat_command(connection, command, seconds=1.5):
    end_time = time.monotonic() + seconds
    while time.monotonic() < end_time:
        send(connection, command)
        time.sleep(0.2)


def main():
    args = parse_args()
    connection = serial.Serial(
        port=args.port,
        baudrate=args.baudrate,
        timeout=0,
        write_timeout=1,
    )
    time.sleep(0.4)

    try:
        # 모터는 정지한 상태로 서보 조향만 시험한다.
        send(connection, "M")
        send(connection, "S")
        send(connection, "b")

        input("Enter를 누르면 핸들을 왼쪽으로 돌립니다.")
        repeat_command(connection, "<")

        input("Enter를 누르면 핸들을 중앙으로 돌립니다.")
        repeat_command(connection, "|")

        input("Enter를 누르면 핸들을 오른쪽으로 돌립니다.")
        repeat_command(connection, ">")

        input("Enter를 누르면 중앙으로 복귀하고 종료합니다.")
        repeat_command(connection, "|", seconds=0.6)

    finally:
        send(connection, "S")
        send(connection, "|")
        connection.close()


if __name__ == "__main__":
    main()
