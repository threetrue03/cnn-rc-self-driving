from _Drive import Drive
from machine import UART, Pin
from _Battery import Battery
from _DistanceSensor import DistanceSensor
from _Oled import Oled
from _VehicleLights import VehicleLights
from _Config import *

import time


# ==================================================
# 하드웨어 초기화
# ==================================================

uart1 = UART(
    BLUETOOTH_UART_ID,
    BLUETOOTH_BAUDRATE,
    bits=8,
    parity=None,
    stop=1,
    tx=Pin(BLUETOOTH_TX_PIN),
    rx=Pin(BLUETOOTH_RX_PIN)
)

battery = Battery()
distance_sensor = DistanceSensor()
drive = Drive()
vehicle_lights = VehicleLights()

Oled.begin()


# 처음 실행될 때 차량 정지
drive.stop()
drive.mid()


vehicle_state = {
    "motion": "STOP",
    "steering": 0,
    "brake": False,
    "turn_signal": "OFF"
}

# "A" 명령으로 자율주행을 시작한 뒤 PC 통신이 끊기면 비상 정지한다.
AUTONOMOUS_TIMEOUT_MS = 1000
autonomous_watchdog = False
last_control_time = time.ticks_ms()


# ==================================================
# 차량 상태 적용
# ==================================================

def apply_drive_state():
    # 브레이크 또는 정지 상태에서는 구동 모터 정지
    if (
        vehicle_state["brake"]
        or vehicle_state["motion"] == "STOP"
    ):
        drive.stop()

    elif vehicle_state["motion"] == "FORWARD":
        drive.forward()

    elif vehicle_state["motion"] == "REVERSE":
        drive.backward()

    else:
        drive.stop()


def apply_steering_state():
    if vehicle_state["steering"] < 0:
        drive.left()

    elif vehicle_state["steering"] > 0:
        drive.right()

    else:
        drive.mid()


# ==================================================
# 독립 상태 명령 처리
# ==================================================

def execute_command(command):
    """
    노트북에서 받은 한 글자 상태 명령을 처리한다.
    조향은 구동 상태와 관계없이 즉시 적용된다.
    """

    global autonomous_watchdog
    global last_control_time

    last_control_time = time.ticks_ms()

    if command == "A":
        autonomous_watchdog = True

    elif command == "M":
        autonomous_watchdog = False

    elif command == "F":
        vehicle_state["motion"] = "FORWARD"
        apply_drive_state()

    elif command == "V":
        vehicle_state["motion"] = "REVERSE"
        apply_drive_state()

    elif command == "S":
        vehicle_state["motion"] = "STOP"
        apply_drive_state()

    elif command == "<":
        vehicle_state["steering"] = -1
        apply_steering_state()

    elif command == "|":
        vehicle_state["steering"] = 0
        apply_steering_state()

    elif command == ">":
        vehicle_state["steering"] = 1
        apply_steering_state()

    elif command == "B":
        vehicle_state["brake"] = True
        vehicle_lights.setBrake(True)
        apply_drive_state()

    elif command == "b":
        vehicle_state["brake"] = False
        vehicle_lights.setBrake(False)
        apply_drive_state()

    elif command == "[":
        vehicle_state["turn_signal"] = "LEFT"
        vehicle_lights.setTurnSignal("LEFT")

    elif command == "]":
        vehicle_state["turn_signal"] = "RIGHT"
        vehicle_lights.setTurnSignal("RIGHT")

    elif command == "H":
        vehicle_state["turn_signal"] = "HAZARD"
        vehicle_lights.setTurnSignal("HAZARD")

    elif command == "O":
        vehicle_state["turn_signal"] = "OFF"
        vehicle_lights.setTurnSignal("OFF")

    elif command == "!":
        autonomous_watchdog = False
        vehicle_state["motion"] = "STOP"
        vehicle_state["steering"] = 0
        vehicle_state["brake"] = True
        vehicle_state["turn_signal"] = "OFF"

        apply_steering_state()
        apply_drive_state()
        vehicle_lights.setBrake(True)
        vehicle_lights.setTurnSignal("OFF")

    else:
        return

    #print("명령 수신:", command)


# ==================================================
# 배터리와 거리 센서 출력
# ==================================================

def update_display():
    bat_vol, bat_perc = battery.getBattery()
    distance_cm = distance_sensor.getDistance()

    Oled.print(
        f"{bat_vol:.3f}V ({bat_perc:.2f} %)"
    )

    Oled.print(
        f"{distance_cm} cm",
        pos=(0, 20),
        clear=False
    )


# 5Hz = 200ms마다 센서 갱신
last_display_time = time.ticks_ms()
DISPLAY_INTERVAL_MS = 200


# ==================================================
# 메인 반복
# ==================================================

while True:
    # ----------------------------------------------
    # Bluetooth UART 명령 수신
    # ----------------------------------------------

    if uart1.any() > 0:
        received_data = uart1.read()

        if received_data:
            # 받은 모든 바이트를 순서대로 처리
            for byte_value in received_data:
                command = chr(byte_value)
                execute_command(command)

    # ----------------------------------------------
    # 배터리 및 거리 센서 갱신
    # ----------------------------------------------

    current_time = time.ticks_ms()

    # 자율주행 중 프로그램/카메라가 멈추면 1초 안에 정지한다.
    if (
        autonomous_watchdog
        and time.ticks_diff(
            current_time,
            last_control_time
        ) >= AUTONOMOUS_TIMEOUT_MS
        and (
            vehicle_state["motion"] != "STOP"
            or not vehicle_state["brake"]
        )
    ):
        vehicle_state["motion"] = "STOP"
        vehicle_state["steering"] = 0
        vehicle_state["brake"] = True

        apply_steering_state()
        apply_drive_state()
        vehicle_lights.setBrake(True)

        print("자율주행 통신 시간 초과: 비상 정지")

    # 방향지시등 점멸 갱신
    vehicle_lights.update(current_time)

    if time.ticks_diff(
        current_time,
        last_display_time
    ) >= DISPLAY_INTERVAL_MS:

        update_display()
        last_display_time = current_time

    # CPU를 계속 100% 점유하지 않도록 짧게 대기
    time.sleep_ms(1)
