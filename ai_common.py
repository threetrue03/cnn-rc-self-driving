"""CNN 학습과 자율주행에서 함께 사용하는 설정과 영상 처리 함수."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import cv2


CLASS_NAMES = ("left", "straight", "right")
STEERING_COMMANDS = {
    "left": "<",
    "straight": "|",
    "right": ">",
}

IMAGE_WIDTH = 160
IMAGE_HEIGHT = 120

# 수집 프로그램(myjoystickcamapp.py)과 반드시 같은 값이어야 한다.
CAMERA_ROTATION_DEGREES = 180
CAMERA_MIRROR_HORIZONTAL = True


def rotate_camera_frame(
    frame,
    rotation_degrees: int = CAMERA_ROTATION_DEGREES,
    mirror_horizontal: bool = CAMERA_MIRROR_HORIZONTAL,
):
    """수집 때와 같은 방향으로 카메라 프레임을 보정한다."""

    if rotation_degrees == 90:
        frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
    elif rotation_degrees == 180:
        frame = cv2.rotate(frame, cv2.ROTATE_180)
    elif rotation_degrees == 270:
        frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
    elif rotation_degrees != 0:
        raise ValueError("rotation_degrees는 0, 90, 180, 270만 가능합니다.")

    if mirror_horizontal:
        frame = cv2.flip(frame, 1)

    return frame


def load_model_metadata(path: str | Path) -> dict[str, Any]:
    path = Path(path)

    if not path.exists():
        return {
            "class_names": list(CLASS_NAMES),
            "image_width": IMAGE_WIDTH,
            "image_height": IMAGE_HEIGHT,
            "camera_rotation_degrees": CAMERA_ROTATION_DEGREES,
            "camera_mirror_horizontal": CAMERA_MIRROR_HORIZONTAL,
        }

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)
