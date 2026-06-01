from PyQt5.QtWidgets import *
from myjoystickex import MyJoystickEx

class MyJoystickApp:
	def __init__(self, cbJoyPos=None):
		self.app = QApplication([])
		self.mw = QMainWindow()
		self.mw.setWindowTitle('RC Car Joystick')
		self.mw.setGeometry(100, 100, 600, 400)

		cw = QWidget()
		cw.setStyleSheet("background-color:yellow;")
		self.mw.setCentralWidget(cw)

		ml = QGridLayout()
		cw.setLayout(ml)

		self.video=QLabel('Video here~')
		self.video.setStyleSheet("background-color:white;")
		ml.addWidget(self.video,0,0)

		self.joystick=MyJoystickEx(cbJoyPos=cbJoyPos)
		ml.addWidget(self.joystick,1,0)

		self.app.aboutToQuit.connect(self.app.deleteLater)

		self.mw.show()

	def run(self):
		self.app.exec_()

if __name__=='__main__':

	def cbJoyPos(joystickPosition) :
		print(joystickPosition)

	myJoystickApp = MyJoystickApp(cbJoyPos=cbJoyPos)
	myJoystickApp.run()
