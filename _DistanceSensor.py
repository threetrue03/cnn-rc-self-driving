from machine import Pin, time_pulse_us
import time

from _Config import *

class DistanceSensor:
    SOUND_SPEED = 340
    TRIG_PULSE_DURATION_US = 10

    def __init__(self):
        self.trigPin = Pin(ULTRASONIC_TRIGGER_PIN, Pin.OUT)
        self.echoPin = Pin(ULTRASONIC_ECHO_PIN, Pin.IN)

    def getDistance(self):
        self.trigPin.value(0)
        time.sleep_us(5)
        self.trigPin.value(1)
        time.sleep_us(self.TRIG_PULSE_DURATION_US)
        self.trigPin.value(0)

        ultrasonic_duration = time_pulse_us(self.echoPin, 1, 30000)
        distance_cm = self.SOUND_SPEED*ultrasonic_duration / 20000

        return distance_cm
