from _Config import *
from machine import ADC

class Battery:
    def __init__(self):
        self.batterySensor = ADC(BATTERY_VOLTAGE_PIN)

        self.batteryVoltage = 0.0
        self.batteryPercent = 0.0

    def getBattery(self):
        batteryValue = self.batterySensor.read_u16()

        adcVoltage = batteryValue / 65535 * 3.3

        batteryVoltage = adcVoltage * 3.077

        batteryPercent = (
            (batteryVoltage - 6.4)
            / (8.4 - 6.4)
            * 100
        )

        batteryPercent = max(
            0,
            min(100, batteryPercent)
        )

        self.batteryVoltage = batteryVoltage
        self.batteryPercent = batteryPercent

        return (self.batteryVoltage, self.batteryPercent)
