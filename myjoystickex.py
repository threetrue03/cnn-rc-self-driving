from PyQt5.QtCore import *
from myjoystick import MyJoystick

class MyJoystickEx(MyJoystick):
	def __init__(self, parent=None, cbJoyPos=None):
		super(MyJoystickEx, self).__init__(parent,cbJoyPos)
		self.setFocusPolicy(Qt.StrongFocus)
		self.keyPressed=False
		self.posX, self.posY=0,0

	def keyPressEvent(self,event):
		self.keyPressed=True
		posX,posY=0,0
		if event.key() == Qt.Key_Right:
			posX,posY=1,0
		elif event.key() == Qt.Key_Left:
			posX,posY=-1,0
		elif event.key() == Qt.Key_Up:
			posX,posY=0,1
		elif event.key() == Qt.Key_Down:
			posX,posY=0,-1

		self.posX,self.posY=posX,posY

		return super().keyPressEvent(event)

	def keyReleaseEvent(self,event):
		self.keyPressed=False
		return super().keyReleaseEvent(event)

	def timeout(self):
		sender=self.sender()
		if id(sender)==id(self.timer):
			if self.cbJoyPos:
				if self.keyPressed:
					self.cbJoyPos((self.posX,self.posY))
				else:
					self.cbJoyPos(self._joystickPosition())
