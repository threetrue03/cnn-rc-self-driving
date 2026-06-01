from _ServoMotor import ServoMotor
from _Config import *
from machine import Pin

class Drive:
    def __init__(self):
        self.forward_pin = Pin(DRIVE_FORWARD_PIN, Pin.OUT)
        self.backward_pin = Pin(DRIVE_BACKWARD_PIN, Pin.OUT)

        self.steering_pin = ServoMotor(STEERING_SERVO_PIN)

    def forward(self):
        self.forward_pin.value(1)
        self.backward_pin.value(0)

    def backward(self):
        self.forward_pin.value(0)
        self.backward_pin.value(1)

    def stop(self):
        self.forward_pin.value(0)
        self.backward_pin.value(0)

    def right(self):
        self.steering_pin.setAngle(155)

    def left(self):
        self.steering_pin.setAngle(25)

    def mid(self):
        self.steering_pin.setAngle(90)
