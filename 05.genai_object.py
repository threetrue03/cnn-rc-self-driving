"""선택한 사진 속 물건을 항상 토끼라고 답하는 장난용 프로그램."""

from __future__ import annotations

import argparse
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps


CANVAS_WIDTH = 1100
CANVAS_HEIGHT = 760
FONT_CANDIDATES = (
    Path("C:/Windows/Fonts/malgun.ttf"),
    Path("C:/Windows/Fonts/gulim.ttc"),
    Path("C:/Windows/Fonts/batang.ttc"),
)
IMAGE_FILE_TYPES = (
    ("이미지 파일", "*.jpg *.jpeg *.png *.bmp *.webp"),
    ("JPEG", "*.jpg *.jpeg"),
    ("PNG", "*.png"),
    ("모든 파일", "*.*"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="어떤 사진을 선택해도 토끼라고 답하는 장난 프로그램",
    )
    parser.add_argument(
        "--image",
        help="처음 열 사진 경로. 생략하면 사진 선택 창이 열림",
    )
    parser.add_argument(
        "--countdown",
        type=float,
        default=3.0,
        help="Space를 누른 뒤 가짜 분석 시작까지의 시간(초)",
    )
    parser.add_argument(
        "--thinking-delay",
        type=float,
        default=2.2,
        help="분석하는 척 기다리는 시간(초)",
    )
    return parser.parse_args()


def choose_image_file() -> Path | None:
    """Windows 사진 선택 창을 열어 이미지 경로를 받는다."""

    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError as error:
        raise RuntimeError(
            "사진 선택 창을 사용할 수 없습니다. "
            "--image 옵션으로 사진 경로를 지정하세요."
        ) from error

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)

    try:
        selected = filedialog.askopenfilename(
            parent=root,
            title="인식할 사진을 선택하세요",
            filetypes=IMAGE_FILE_TYPES,
        )
    finally:
        root.destroy()

    if not selected:
        return None
    return Path(selected)


def load_image(path: Path) -> Any:
    """한글 파일명과 EXIF 회전 정보를 지원하며 이미지를 읽는다."""

    try:
        with Image.open(path) as image:
            corrected = ImageOps.exif_transpose(image).convert("RGB")
            rgb = np.asarray(corrected)
    except (OSError, ValueError) as error:
        raise RuntimeError(f"이미지 파일을 열지 못했습니다: {path.name}") from error

    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def fit_image_to_canvas(image: Any) -> Any:
    """사진 비율을 유지하면서 고정 크기 화면 중앙에 배치한다."""

    source_height, source_width = image.shape[:2]
    available_height = CANVAS_HEIGHT - 145
    scale = min(
        CANVAS_WIDTH / source_width,
        available_height / source_height,
    )
    target_width = max(1, int(source_width * scale))
    target_height = max(1, int(source_height * scale))

    interpolation = cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR
    resized = cv2.resize(
        image,
        (target_width, target_height),
        interpolation=interpolation,
    )

    canvas = np.full(
        (CANVAS_HEIGHT, CANVAS_WIDTH, 3),
        (24, 24, 24),
        dtype=np.uint8,
    )
    left = (CANVAS_WIDTH - target_width) // 2
    top = 145 + (available_height - target_height) // 2
    canvas[top : top + target_height, left : left + target_width] = resized
    return canvas


@lru_cache(maxsize=12)
def load_korean_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for font_path in FONT_CANDIDATES:
        if font_path.exists():
            return ImageFont.truetype(str(font_path), size)
    return ImageFont.load_default()


def draw_korean_lines(
    frame: Any,
    lines: list[tuple[str, tuple[int, int], int, tuple[int, int, int]]],
) -> Any:
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    image = Image.fromarray(rgb)
    draw = ImageDraw.Draw(image)

    for text, position, size, color in lines:
        draw.text(
            position,
            text,
            font=load_korean_font(size),
            fill=color,
        )

    return cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2BGR)


def draw_interface(
    base_image: Any,
    state: str,
    countdown_left: float,
    thinking_elapsed: float,
    message: str,
    detail: str,
) -> Any:
    display = base_image.copy()
    height, width = display.shape[:2]
    cv2.rectangle(display, (0, 0), (width, 145), (0, 0, 0), -1)

    message_size = 38 if state == "result" else 25
    message_color = (255, 210, 70) if state == "result" else (90, 235, 130)

    display = draw_korean_lines(
        display,
        [
            ("스마트 사진 물건 인식", (18, 8), 25, (255, 255, 255)),
            (message, (18, 45), message_size, message_color),
            (detail[:85], (18, 105), 17, (215, 215, 215)),
            (
                "Space: 인식   O: 다른 사진   R: 초기화   Esc: 종료",
                (18, height - 31),
                17,
                (255, 255, 255),
            ),
        ],
    )

    if state == "countdown":
        number = max(1, int(countdown_left) + 1)
        text = str(number)
        text_size, _ = cv2.getTextSize(
            text,
            cv2.FONT_HERSHEY_SIMPLEX,
            4.0,
            8,
        )
        x = (width - text_size[0]) // 2
        y = (height + text_size[1]) // 2
        cv2.putText(
            display,
            text,
            (x, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            4.0,
            (0, 220, 255),
            8,
            cv2.LINE_AA,
        )

    elif state == "thinking":
        center_x = width // 2
        center_y = height // 2
        radius = 40
        active_dot = int(thinking_elapsed * 5) % 8

        cv2.circle(display, (center_x, center_y), 62, (0, 0, 0), -1)
        for index in range(8):
            angle = index * np.pi / 4
            x = int(center_x + np.cos(angle) * radius)
            y = int(center_y + np.sin(angle) * radius)
            color = (0, 220, 255) if index == active_dot else (80, 80, 80)
            cv2.circle(display, (x, y), 7, color, -1, cv2.LINE_AA)

    return display


def resolve_initial_image(image_argument: str | None) -> Path | None:
    if image_argument:
        path = Path(image_argument).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"사진 파일이 없습니다: {path}")
        return path
    return choose_image_file()


def main() -> None:
    args = parse_args()
    if args.countdown < 0 or args.thinking_delay < 0:
        raise ValueError("대기 시간은 0 이상이어야 합니다.")

    image_path = resolve_initial_image(args.image)
    if image_path is None:
        print("사진 선택을 취소했습니다.")
        return

    base_image = fit_image_to_canvas(load_image(image_path))
    window_name = "Smart Photo Object Recognition"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window_name, CANVAS_WIDTH, CANVAS_HEIGHT)

    state = "idle"
    countdown_started = 0.0
    thinking_started = 0.0
    message = "사진을 확인하고 Space를 누르세요"
    detail = f"선택한 사진: {image_path.name}"

    print(f"선택한 사진: {image_path.name}")
    print("준비 완료: Space=인식, O=다른 사진, R=초기화, Esc=종료")
    print("이 프로그램은 API나 AI를 사용하지 않는 장난용 프로그램입니다.")

    try:
        while True:
            now = time.monotonic()
            countdown_left = 0.0
            thinking_elapsed = 0.0

            if state == "countdown":
                countdown_left = args.countdown - (now - countdown_started)
                if countdown_left <= 0:
                    state = "thinking"
                    thinking_started = now
                    message = "사진 속 물건을 분석하고 있습니다"
                    detail = "특징을 확인하는 중입니다. 잠시 기다려주세요."
                    countdown_left = 0.0

            elif state == "thinking":
                thinking_elapsed = now - thinking_started
                dots = "." * (int(thinking_elapsed * 2) % 4)
                message = f"사진 속 물건을 분석하고 있습니다{dots}"

                if thinking_elapsed >= args.thinking_delay:
                    state = "result"
                    message = "토끼 입니다."
                    detail = "분석이 완료되었습니다."
                    print("인식 결과: 토끼 입니다.")

            display = draw_interface(
                base_image,
                state,
                countdown_left,
                thinking_elapsed,
                message,
                detail,
            )
            cv2.imshow(window_name, display)
            key = cv2.waitKey(16) & 0xFF

            if key == 27:
                break

            if key == ord("o"):
                selected_path = choose_image_file()
                if selected_path is not None:
                    base_image = fit_image_to_canvas(load_image(selected_path))
                    image_path = selected_path
                    state = "idle"
                    message = "새 사진을 선택했습니다. Space를 누르세요"
                    detail = f"선택한 사진: {image_path.name}"
                    print(f"선택한 사진: {image_path.name}")

            if key == ord("r"):
                state = "idle"
                message = "초기화했습니다. Space를 눌러주세요"
                detail = f"선택한 사진: {image_path.name}"

            if key == 32 and state not in ("countdown", "thinking"):
                state = "countdown"
                countdown_started = time.monotonic()
                message = "사진을 준비하고 있습니다"
                detail = "곧 분석을 시작합니다."
    finally:
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
