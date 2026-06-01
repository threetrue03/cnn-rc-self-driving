"""MicroPython PWM을 이용한 SG90 서보모터 제어."""

from machine import PWM, Pin


class ServoMotor:
    MIN_DUTY = 1600
    MAX_DUTY = 7900
    DUTY_PER_DEGREE = (MAX_DUTY - MIN_DUTY) / 180

    def __init__(self, pwm_pin):
        self.pwm = PWM(Pin(pwm_pin))
        self.pwm.freq(50)

    def setDutyCycle(self, position):
        self.pwm.duty_u16(int(position))

    def setAngle(self, angle):
        angle = int(angle)
        if not 0 <= angle <= 180:
            raise ValueError("angle must be between 0 and 180")

        position = self.MIN_DUTY + self.DUTY_PER_DEGREE * angle
        self.setDutyCycle(position)
