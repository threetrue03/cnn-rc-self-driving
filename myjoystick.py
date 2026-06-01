from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
import math

class MyJoystick(QWidget):
	def __init__(self, parent=None, cbJoyPos=None):
		super(MyJoystick, self).__init__(parent)
		self.setMinimumSize(200, 200)
		self.movingOffset = QPointF(0, 0) # 조이스틱 위치
		self.grabCenter = False # 조이스틱을 잡았느냐?
		self.__maxDistance = 50 # 조이스틱 범위
		self.cbJoyPos = cbJoyPos # 사용자 정의 콜백 함수

		self.timer=QTimer(self)
		self.timer.setInterval(50)
		self.timer.timeout.connect(self.timeout)
		self.timer.start()

	def paintEvent(self, event):
		painter = QPainter(self)
		bounds = QRectF(
			-self.__maxDistance,
			-self.__maxDistance,
			self.__maxDistance * 2,
			self.__maxDistance * 2
		).translated(self._center())
		painter.drawEllipse(bounds)
		painter.setBrush(Qt.black)
		painter.drawEllipse(self._centerEllipse())

	def _center(self):
		return QPointF(self.width()/2, self.height()/2)

	def _centerEllipse(self):
		joypos = self._center()
		if self.grabCenter:
			joypos = self.movingOffset
		return QRectF(-20, -20, 40, 40).translated(joypos)

	def mousePressEvent(self, event):
		self.grabCenter = self._centerEllipse().contains(event.pos())
		self.movingOffset = self._boundJoystick(event.pos())
		self.update()
		return super().mousePressEvent(event)

	def mouseMoveEvent(self, event):
		if self.grabCenter:
			self.movingOffset = self._boundJoystick(event.pos())
			self.update()
			if self.cbJoyPos:
				self.cbJoyPos(self._joystickPosition())

	def _boundJoystick(self, point):
		limitLine = QLineF(self._center(), point)
		if (limitLine.length() > self.__maxDistance):
			limitLine.setLength(self.__maxDistance)
		return limitLine.p2()

	def mouseReleaseEvent(self, event):
		self.grabCenter = False
		self.movingOffset = QPointF(0, 0)
		self.update()
		if self.cbJoyPos:
			self.cbJoyPos(self._joystickPosition())

	def timeout(self):
		sender=self.sender()
		if id(sender)==id(self.timer):
			if self.cbJoyPos:
				self.cbJoyPos(self._joystickPosition())

	def _joystickPosition(self):
		if not self.grabCenter:
			return (0, 0)
		normVector = QLineF(self._center(), self.movingOffset)
		currentDistance = normVector.length()
		angle = normVector.angle()

		distance = min(currentDistance / self.__maxDistance, 1.0)

		posX = math.cos(angle*math.pi/180)*distance
		posY = math.sin(angle*math.pi/180)*distance

		return (posX, posY)
