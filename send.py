import serial
import time

s = serial.Serial("COM8")

with open("dummy.txt", "r") as f:
    for line in f.readlines():
        s.write(line)
        print(line)
        time.sleep(0.2)

s.close()