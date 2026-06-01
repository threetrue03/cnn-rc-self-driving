import sys
import cv2
import csv
import time

from datetime import datetime
from pathlib import Path

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QSizePolicy
)


# 카메라가 거꾸로 장착되어 있어 기본적으로 180도 회전한다.
# 정상 방향으로 다시 장착하면 0으로 변경하면 된다.



class CameraThread(QThread):
    """ESP32-CAM 영상을 읽는 스레드."""

    frameReady = pyqtSignal(QImage)
    collectionFrameReady = pyqtSignal(object)
    statusChanged = pyqtSignal(str)

    def __init__(self, v_source, parent=None):
        super().__init__(parent)

        self.v_source = v_source
        self.running = True

    def run(self):
        cap = cv2.VideoCapture(self.v_source)

        if not cap.isOpened():
            self.statusChanged.emit(
                "카메라에 연결할 수 없습니다."
            )
            return

        self.statusChanged.emit("카메라 연결 완료")

        while self.running:
            ret, frame = cap.read()

            if not ret or frame is None:
                self.statusChanged.emit(
                    "영상 프레임을 가져오지 못했습니다."
                )
                self.msleep(50)
                continue



            collection_frame = cv2.resize(
                frame,
                (160, 120)
            )

            self.collectionFrameReady.emit(
                collection_frame
            )

            frame = cv2.cvtColor(
                frame,
                cv2.COLOR_BGR2RGB
            )

            height, width, channel = frame.shape
            bytes_per_line = width * channel

            image = QImage(
                frame.data,
                width,
                height,
                bytes_per_line,
                QImage.Format_RGB888
            ).copy()

            self.frameReady.emit(image)

        cap.release()

    def stop(self):
        self.running = False
        self.wait(1000)


class CarControlWindow(QMainWindow):
    """
    방향키로 전진, 후진, 조향을 제어하고
    스페이스 바로 브레이크를 제어한다.
    """

    def __init__(
        self,
        cbControlState=None,
        v_source=0,
        data_directory=None
    ):
        super().__init__()

        self.cbControlState = cbControlState

        # =====================================
        # 차량 제어 상태
        # =====================================

        # 전진/후진 방향키 상태
        self.forwardPressed = False
        self.reversePressed = False

        # 브레이크 상태
        self.brakePressed = False

        # 핸들 상태
        self.steerLeftPressed = False
        self.steerRightPressed = False

        # 방향지시등 상태: OFF / LEFT / RIGHT / HAZARD
        self.turnSignal = "OFF"

        # =====================================
        # 학습 데이터 수집 상태
        # =====================================

        if data_directory is None:
            data_directory = (
                Path(__file__).resolve().parent
                / "dataset"
            )

        self.dataDirectory = Path(
            data_directory
        )

        self.isCollecting = False
        self.collectionSessionDirectory = None
        self.collectionCsvFile = None
        self.collectionCsvWriter = None

        self.collectionCounts = {
            "left": 0,
            "straight": 0,
            "right": 0,
            "total": 0
        }

        # 초당 최대 10장 저장
        self.collectionIntervalSeconds = 0.1
        self.lastCollectionTime = 0.0

        # 조향 변경 직후 카메라 지연으로 라벨이 어긋나는 것을 방지
        self.steeringSettleSeconds = 0.2
        self.collectionSteering = 0
        self.lastSteeringChangeTime = time.monotonic()

        # =====================================
        # 창 설정
        # =====================================

        self.setWindowTitle(
            "RC Car Driving Controller"
        )

        self.setMinimumSize(
            680,
            650
        )

        self.setFocusPolicy(
            Qt.StrongFocus
        )

        # =====================================
        # 영상 영역
        # =====================================

        self.videoLabel = QLabel(
            "카메라 연결 중..."
        )

        self.videoLabel.setMinimumSize(
            640,
            480
        )

        self.videoLabel.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Expanding
        )

        self.videoLabel.setAlignment(
            Qt.AlignCenter
        )

        self.videoLabel.setStyleSheet(
            """
            QLabel {
                background-color: black;
                color: white;
                font-size: 18px;
            }
            """
        )

        # =====================================
        # 상태 표시 영역
        # =====================================

        self.motionLabel = QLabel()
        self.steeringLabel = QLabel()
        self.brakeLabel = QLabel()
        self.turnSignalLabel = QLabel()

        statusLayout = QHBoxLayout()
        statusLayout.addWidget(self.motionLabel)
        statusLayout.addWidget(self.steeringLabel)
        statusLayout.addWidget(self.brakeLabel)
        statusLayout.addWidget(self.turnSignalLabel)

        self.messageLabel = QLabel(
            "방향키로 주행하고 Space 바로 브레이크를 제어하세요."
        )

        self.messageLabel.setAlignment(
            Qt.AlignCenter
        )

        self.messageLabel.setStyleSheet(
            """
            QLabel {
                font-size: 14px;
                padding: 8px;
            }
            """
        )

        self.helpLabel = QLabel(
            "전진: ↑    "
            "후진: ↓    "
            "핸들: ← / →    "
            "브레이크: Space\n"
            "방향지시등: Q(좌) / E(우) / H(비상등) / 0(끄기)    "
            "데이터 수집: F5(시작/종료)"
        )

        self.helpLabel.setAlignment(
            Qt.AlignCenter
        )

        self.collectionLabel = QLabel()
        self.collectionLabel.setAlignment(
            Qt.AlignCenter
        )
        self.updateCollectionStatus()

        # =====================================
        # 전체 배치
        # =====================================

        centralWidget = QWidget()
        mainLayout = QVBoxLayout(centralWidget)

        mainLayout.addWidget(
            self.videoLabel,
            alignment=Qt.AlignCenter
        )

        mainLayout.addLayout(
            statusLayout
        )

        mainLayout.addWidget(
            self.collectionLabel
        )

        mainLayout.addWidget(
            self.messageLabel
        )

        mainLayout.addWidget(
            self.helpLabel
        )

        self.setCentralWidget(
            centralWidget
        )

        # =====================================
        # 카메라 스레드
        # =====================================

        self.cameraThread = CameraThread(
            v_source=v_source,
            parent=self
        )

        self.cameraThread.frameReady.connect(
            self.updateFrame
        )

        self.cameraThread.collectionFrameReady.connect(
            self.collectFrame
        )

        self.cameraThread.statusChanged.connect(
            self.messageLabel.setText
        )

        self.cameraThread.start()

        self.updateStatus()
        self.sendControlState()

    def getSteering(self):
        """
        왼쪽: -1
        중앙:  0
        오른쪽: 1
        """

        if (
            self.steerLeftPressed
            and not self.steerRightPressed
        ):
            return -1

        if (
            self.steerRightPressed
            and not self.steerLeftPressed
        ):
            return 1

        return 0

    def getMotion(self):
        """
        전진: FORWARD
        후진: REVERSE
        정지: STOP
        """

        if (
            self.forwardPressed
            and not self.reversePressed
        ):
            return "FORWARD"

        if (
            self.reversePressed
            and not self.forwardPressed
        ):
            return "REVERSE"

        return "STOP"

    def sendControlState(self):
        """현재 차량 상태 전체를 콜백으로 전달한다."""

        steering = self.getSteering()

        if steering != self.collectionSteering:
            self.collectionSteering = steering
            self.lastSteeringChangeTime = time.monotonic()

        self.updateStatus()

        if self.cbControlState:
            self.cbControlState(
                {
                    "motion": self.getMotion(),
                    "steering": steering,
                    "brake": self.brakePressed,
                    "turn_signal": self.turnSignal
                }
            )

    def updateStatus(self):
        """현재 기어, 핸들, 페달 상태를 화면에 표시한다."""

        steering = self.getSteering()

        if steering < 0:
            steering_text = "LEFT"

        elif steering > 0:
            steering_text = "RIGHT"

        else:
            steering_text = "CENTER"

        self.motionLabel.setText(
            f"주행: {self.getMotion()}"
        )

        self.steeringLabel.setText(
            f"핸들: {steering_text}"
        )

        self.brakeLabel.setText(
            "브레이크: "
            + (
                "ON"
                if self.brakePressed
                else "OFF"
            )
        )

        self.turnSignalLabel.setText(
            f"방향지시등: {self.turnSignal}"
        )

    def updateCollectionStatus(self):
        if self.isCollecting:
            status_text = (
                "데이터 수집: ON  |  "
                f"LEFT {self.collectionCounts['left']}  "
                f"STRAIGHT {self.collectionCounts['straight']}  "
                f"RIGHT {self.collectionCounts['right']}  "
                f"TOTAL {self.collectionCounts['total']}"
            )

            color = "#b00020"

        else:
            status_text = "데이터 수집: OFF  |  F5를 눌러 시작"
            color = "#555555"

        self.collectionLabel.setText(
            status_text
        )

        self.collectionLabel.setStyleSheet(
            f"""
            QLabel {{
                color: {color};
                font-size: 14px;
                font-weight: bold;
                padding: 5px;
            }}
            """
        )

    def startDataCollection(self):
        if self.isCollecting:
            return

        session_name = datetime.now().strftime(
            "session_%Y%m%d_%H%M%S_%f"
        )[:-3]

        self.collectionSessionDirectory = (
            self.dataDirectory
            / session_name
        )

        for label in (
            "left",
            "straight",
            "right"
        ):
            (
                self.collectionSessionDirectory
                / label
            ).mkdir(
                parents=True,
                exist_ok=False
            )

        csv_path = (
            self.collectionSessionDirectory
            / "labels.csv"
        )

        self.collectionCsvFile = csv_path.open(
            "w",
            newline="",
            encoding="utf-8-sig"
        )

        self.collectionCsvWriter = csv.DictWriter(
            self.collectionCsvFile,
            fieldnames=(
                "timestamp",
                "image",
                "label",
                "steering",
                "motion",
                "brake",
                "turn_signal"
            )
        )

        self.collectionCsvWriter.writeheader()
        self.collectionCsvFile.flush()

        self.collectionCounts = {
            "left": 0,
            "straight": 0,
            "right": 0,
            "total": 0
        }

        self.lastCollectionTime = 0.0
        self.lastSteeringChangeTime = time.monotonic()
        self.isCollecting = True

        self.updateCollectionStatus()

        self.messageLabel.setText(
            "데이터 수집을 시작했습니다. "
            "위쪽 방향키로 전진할 때만 저장됩니다."
        )

        print(
            "데이터 수집 시작:",
            self.collectionSessionDirectory
        )

    def stopDataCollection(self):
        if not self.isCollecting:
            return

        self.isCollecting = False

        if self.collectionCsvFile:
            self.collectionCsvFile.flush()
            self.collectionCsvFile.close()

        self.collectionCsvFile = None
        self.collectionCsvWriter = None

        self.updateCollectionStatus()

        self.messageLabel.setText(
            "데이터 수집을 종료했습니다. "
            f"총 {self.collectionCounts['total']}장을 저장했습니다."
        )

        print(
            "데이터 수집 종료:",
            self.collectionSessionDirectory,
            self.collectionCounts
        )

    def toggleDataCollection(self):
        if self.isCollecting:
            self.stopDataCollection()

        else:
            try:
                self.startDataCollection()

            except OSError as error:
                self.messageLabel.setText(
                    f"데이터 폴더를 만들 수 없습니다: {error}"
                )

    def collectFrame(self, frame):
        if not self.isCollecting:
            return

        # 위쪽 방향키로 전진 중인 영상만 학습 데이터로 저장
        if (
            self.getMotion() != "FORWARD"
            or self.brakePressed
        ):
            return

        current_time = time.monotonic()

        if (
            current_time
            - self.lastSteeringChangeTime
        ) < self.steeringSettleSeconds:
            return

        if (
            current_time
            - self.lastCollectionTime
        ) < self.collectionIntervalSeconds:
            return

        steering = self.getSteering()

        if steering < 0:
            label = "left"

        elif steering > 0:
            label = "right"

        else:
            label = "straight"

        timestamp = datetime.now()
        frame_number = self.collectionCounts["total"] + 1

        filename = (
            f"frame_{frame_number:06d}_"
            f"{timestamp.strftime('%H%M%S_%f')[:-3]}.jpg"
        )

        image_path = (
            self.collectionSessionDirectory
            / label
            / filename
        )

        success, encoded_image = cv2.imencode(
            ".jpg",
            frame,
            (
                cv2.IMWRITE_JPEG_QUALITY,
                90
            )
        )

        if not success:
            self.messageLabel.setText(
                "이미지를 JPEG로 변환하지 못했습니다."
            )
            return

        try:
            image_path.write_bytes(
                encoded_image.tobytes()
            )

        except OSError as error:
            self.messageLabel.setText(
                f"이미지를 저장할 수 없습니다: {error}"
            )
            self.stopDataCollection()
            return

        relative_path = image_path.relative_to(
            self.collectionSessionDirectory
        ).as_posix()

        self.collectionCsvWriter.writerow(
            {
                "timestamp": timestamp.isoformat(
                    timespec="milliseconds"
                ),
                "image": relative_path,
                "label": label,
                "steering": steering,
                "motion": self.getMotion(),
                "brake": int(
                    self.brakePressed
                ),
                "turn_signal": self.turnSignal
            }
        )

        self.collectionCsvFile.flush()

        self.collectionCounts[label] += 1
        self.collectionCounts["total"] += 1
        self.lastCollectionTime = current_time

        self.updateCollectionStatus()

    def keyPressEvent(self, event):
        """키를 누르는 순간 차량 상태를 변경한다."""

        if event.isAutoRepeat():
            return

        key = event.key()
        state_changed = False

        if key == Qt.Key_F5:
            self.toggleDataCollection()
            return

        # -------------------------------------
        # 전진 / 후진
        # -------------------------------------

        if key == Qt.Key_Up:
            self.forwardPressed = True
            state_changed = True

        elif key == Qt.Key_Down:
            self.reversePressed = True
            state_changed = True

        # -------------------------------------
        # 브레이크
        # -------------------------------------

        elif key == Qt.Key_Space:
            self.brakePressed = True
            state_changed = True

        # -------------------------------------
        # 핸들
        # -------------------------------------

        elif key == Qt.Key_Left:
            self.steerLeftPressed = True
            state_changed = True

        elif key == Qt.Key_Right:
            self.steerRightPressed = True
            state_changed = True

        # -------------------------------------
        # 방향지시등
        # 같은 키를 다시 누르면 해당 지시등을 끈다.
        # -------------------------------------

        elif key == Qt.Key_Q:
            self.turnSignal = (
                "OFF"
                if self.turnSignal == "LEFT"
                else "LEFT"
            )
            state_changed = True

        elif key == Qt.Key_E:
            self.turnSignal = (
                "OFF"
                if self.turnSignal == "RIGHT"
                else "RIGHT"
            )
            state_changed = True

        elif key == Qt.Key_H:
            self.turnSignal = (
                "OFF"
                if self.turnSignal == "HAZARD"
                else "HAZARD"
            )
            state_changed = True

        elif key == Qt.Key_0:
            self.turnSignal = "OFF"
            state_changed = True

        if state_changed:
            self.sendControlState()

    def keyReleaseEvent(self, event):
        """키를 놓는 순간 해당 조작을 해제한다."""

        if event.isAutoRepeat():
            return

        key = event.key()
        state_changed = False

        if key == Qt.Key_Up:
            self.forwardPressed = False
            state_changed = True

        elif key == Qt.Key_Down:
            self.reversePressed = False
            state_changed = True

        elif key == Qt.Key_Space:
            self.brakePressed = False
            state_changed = True

        elif key == Qt.Key_Left:
            self.steerLeftPressed = False
            state_changed = True

        elif key == Qt.Key_Right:
            self.steerRightPressed = False
            state_changed = True

        if state_changed:
            self.sendControlState()

    def focusOutEvent(self, event):
        """
        다른 창으로 포커스가 이동하면 안전을 위해
        주행과 핸들 입력을 모두 해제한다.
        """

        self.forwardPressed = False
        self.reversePressed = False
        self.steerLeftPressed = False
        self.steerRightPressed = False

        self.sendControlState()

        super().focusOutEvent(event)

    def updateFrame(self, image):
        pixmap = QPixmap.fromImage(image)

        # 원본 카메라 영상보다 크게 확대하지 않는다.
        # 화면 영역보다 원본이 클 때만 비율을 유지하며 축소한다.
        if (
            pixmap.width() > self.videoLabel.width()
            or pixmap.height() > self.videoLabel.height()
        ):
            pixmap = pixmap.scaled(
                self.videoLabel.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )

        self.videoLabel.setPixmap(
            pixmap
        )

    def closeEvent(self, event):
        """창을 닫으면 자동차를 정지시키고 카메라를 종료한다."""

        self.stopDataCollection()

        self.forwardPressed = False
        self.reversePressed = False
        self.brakePressed = True
        self.steerLeftPressed = False
        self.steerRightPressed = False
        self.turnSignal = "OFF"

        self.sendControlState()

        self.cameraThread.stop()

        event.accept()


class MyJoystickCamApp:
    """
    기존 호출 형식을 유지하기 위한 실행 클래스.

    이름은 기존과 같지만 더 이상 조이스틱을 사용하지 않는다.
    """

    def __init__(
        self,
        cbControlState=None,
        v_source=0,
        data_directory=None
    ):
        self.app = QApplication.instance()

        if self.app is None:
            self.app = QApplication(
                sys.argv
            )

        self.window = CarControlWindow(
            cbControlState=cbControlState,
            v_source=v_source,
            data_directory=data_directory
        )

    def run(self):
        self.window.showMaximized()
        self.window.setFocus()

        return self.app.exec_()
