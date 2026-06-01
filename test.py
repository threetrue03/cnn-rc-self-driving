import sys
import cv2

from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QLabel,
    QVBoxLayout
)
from PyQt5.QtCore import (
    Qt,
    QPointF,
    QRectF,
    QLineF,
    QTimer
)
from PyQt5.QtGui import (
    QPainter,
    QImage,
    QPixmap
)


class Joystick(QWidget):
    def __init__(self, parent=None, cbJoyPos=None):
        super().__init__(parent)

        self.setMinimumSize(200, 200)

        # 조이스틱 손잡이의 현재 위치
        self.movingOffset = self._center()

        # 조이스틱 손잡이를 잡고 있는지
        self.grabCenter = False

        # 중심에서 움직일 수 있는 최대 거리
        self.__maxDistance = 50

        # 좌표를 전달할 콜백 함수
        self.cbJoyPos = cbJoyPos

        # 50ms마다 현재 조이스틱 좌표 전달
        self.timer = QTimer(self)
        self.timer.setInterval(50)
        self.timer.timeout.connect(self.timeout)
        self.timer.start()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        center = self._center()

        # 조이스틱 이동 가능 범위
        bounds = QRectF(
            -self.__maxDistance,
            -self.__maxDistance,
            self.__maxDistance * 2,
            self.__maxDistance * 2
        ).translated(center)

        # 조이스틱 바깥쪽 원
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(bounds)

        # 조이스틱 검은색 손잡이
        painter.setBrush(Qt.black)
        painter.drawEllipse(self._centerEllipse())

    def _center(self):
        """현재 위젯의 중심 좌표를 반환한다."""

        return QPointF(
            self.width() / 2,
            self.height() / 2
        )

    def _centerEllipse(self):
        """검은색 조이스틱 손잡이의 영역을 반환한다."""

        if self.grabCenter:
            joypos = self.movingOffset
        else:
            joypos = self._center()

        return QRectF(
            -20,
            -20,
            40,
            40
        ).translated(joypos)

    def mousePressEvent(self, event):
        """마우스 버튼을 눌렀을 때 실행된다."""

        if event.button() != Qt.LeftButton:
            return

        # 검은색 손잡이를 클릭했는지 확인
        if self._centerEllipse().contains(event.pos()):
            self.grabCenter = True

            self.movingOffset = self._boundJoystick(
                event.pos()
            )

            self.update()

    def mouseMoveEvent(self, event):
        """마우스를 누른 상태로 움직일 때 실행된다."""

        if not self.grabCenter:
            return

        if not event.buttons() & Qt.LeftButton:
            return

        self.movingOffset = self._boundJoystick(
            event.pos()
        )

        self.update()

        if self.cbJoyPos:
            self.cbJoyPos(
                self.getPosition()
            )

    def mouseReleaseEvent(self, event):
        """마우스 버튼을 놓았을 때 실행된다."""

        if event.button() != Qt.LeftButton:
            return

        self.grabCenter = False
        self.movingOffset = self._center()

        self.update()

        if self.cbJoyPos:
            self.cbJoyPos(
                (0.0, 0.0)
            )

    def _boundJoystick(self, point):
        """조이스틱이 최대 범위 밖으로 나가지 않도록 제한한다."""

        limitLine = QLineF(
            self._center(),
            QPointF(point)
        )

        if limitLine.length() > self.__maxDistance:
            limitLine.setLength(
                self.__maxDistance
            )

        return limitLine.p2()

    def getPosition(self):
        """조이스틱 위치를 -1.0~1.0 범위로 반환한다."""

        if not self.grabCenter:
            return 0.0, 0.0

        center = self._center()

        dx = self.movingOffset.x() - center.x()
        dy = self.movingOffset.y() - center.y()

        posX = dx / self.__maxDistance

        # 화면 좌표는 아래쪽이 +이므로
        # 일반적인 좌표계에 맞게 Y축 부호를 반대로 바꾼다.
        posY = -dy / self.__maxDistance

        posX = max(
            -1.0,
            min(posX, 1.0)
        )

        posY = max(
            -1.0,
            min(posY, 1.0)
        )

        return posX, posY

    def timeout(self):
        """50ms마다 현재 조이스틱 좌표를 전달한다."""

        if self.cbJoyPos:
            self.cbJoyPos(
                self.getPosition()
            )


def receivePosition(position):
    """조이스틱으로부터 좌표를 전달받는다."""

    posX, posY = position

    print(
        f"x={posX:.3f}, y={posY:.3f}",
        end=" → "
    )

    if posX > 0.6:
        print("right")

    elif posX < -0.6:
        print("left")

    elif posY > 0.7:
        print("forward")

    elif posY < -0.7:
        print("backward")

    else:
        print("stop")


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle(
            "RC Car Controller"
        )

        # =====================================
        # 영상 표시 영역
        # =====================================

        self.videoLabel = QLabel(
            "카메라 연결 중..."
        )

        self.videoLabel.setFixedSize(
            640,
            480
        )

        self.videoLabel.setAlignment(
            Qt.AlignCenter
        )

        self.videoLabel.setStyleSheet(
            """
            QLabel {
                background-color: black;
                color: white;
            }
            """
        )

        # =====================================
        # 조이스틱
        # =====================================

        self.joystick = Joystick(
            parent=self,
            cbJoyPos=receivePosition
        )

        self.joystick.setFixedSize(
            200,
            200
        )

        # =====================================
        # 영상과 조이스틱을 세로로 배치
        # =====================================

        layout = QVBoxLayout()

        layout.addWidget(
            self.videoLabel,
            alignment=Qt.AlignCenter
        )

        layout.addWidget(
            self.joystick,
            alignment=Qt.AlignCenter
        )

        self.setLayout(layout)

        # =====================================
        # ESP32-CAM 영상 스트림 연결
        # =====================================

        self.v_source = (
            "http://192.168.4.1:81/stream"
        )

        self.capture = cv2.VideoCapture(
            self.v_source
        )

        if not self.capture.isOpened():
            self.videoLabel.setText(
                "카메라에 연결할 수 없습니다.\n"
                "Wi-Fi 연결과 영상 주소를 확인하세요."
            )

        # =====================================
        # 영상 갱신용 타이머
        # =====================================

        self.videoTimer = QTimer(self)

        # 30ms마다 영상 한 프레임 읽기
        self.videoTimer.setInterval(30)

        self.videoTimer.timeout.connect(
            self.updateFrame
        )

        self.videoTimer.start()

    def updateFrame(self):
        """카메라 영상 한 프레임을 읽어 QLabel에 표시한다."""

        ret, frame = self.capture.read()

        if not ret or frame is None:
            self.videoLabel.setText(
                "카메라 영상을 가져오지 못했습니다."
            )
            return

        # OpenCV는 BGR 순서,
        # PyQt의 QImage는 RGB 순서를 사용한다.
        frame = cv2.cvtColor(
            frame,
            cv2.COLOR_BGR2RGB
        )

        height, width, channel = frame.shape

        bytesPerLine = (
            width * channel
        )

        image = QImage(
            frame.data,
            width,
            height,
            bytesPerLine,
            QImage.Format_RGB888
        ).copy()

        pixmap = QPixmap.fromImage(
            image
        )

        # 영상 비율을 유지하면서 QLabel 크기에 맞춘다.
        pixmap = pixmap.scaled(
            self.videoLabel.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )

        self.videoLabel.setPixmap(
            pixmap
        )

    def closeEvent(self, event):
        """창을 닫을 때 카메라와 타이머를 정리한다."""

        self.videoTimer.stop()
        self.joystick.timer.stop()

        if self.capture.isOpened():
            self.capture.release()

        event.accept()


if __name__ == "__main__":
    app = QApplication(
        sys.argv
    )

    window = MainWindow()
    window.show()

    sys.exit(
        app.exec_()
    )
