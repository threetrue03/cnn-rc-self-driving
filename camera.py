import cv2
import numpy as np
import time

cap = cv2.VideoCapture("http://192.168.4.1:81/stream")

t_now = time.time()
t_prev = time.time()
cnt_frame = 0

if not cap.isOpened():
    print("비디오 열기 오류")

while True:
    ret, frame = cap.read()
    if not ret:
        print("frame 읽기 오류")
        break
    frame = np.flip(frame, axis=0)
    frame2 = cv2.resize(frame, (640, 480))
    cv2.imshow("frame", frame2)

    key = cv2.waitKey(1)
    if key == 27:
        break

    cnt_frame += 1
    t_now = time.time()
    if t_now - t_prev >= 1.0:
        t_prev = t_now
        print("frame count : %f" %cnt_frame)
        cnt_frame = 0

cap.release()
cv2.destroyAllWindows()
