import random
import math

i = 0
count = 1000
delay = 50

timePerIter = delay / 1000

def pack(data):
    s = f"TELEM{i}"
    for k in data:
        d = data[k]
        s += f";{k}={d:.2f}"
    s+="\n"
    return s

def iterToTime(i):
    return (i * delay) / 1000

def sine(t, A, f):
    return 0.5 * A + (0.5 * A * math.sin(f * 2 * math.pi * t))

def cosine(t, A, f):
    return 0.5 * A + (0.5 * A * math.cos(f * 2 * math.pi * t))

def tri(t, A, f):
    period = 1 / f
    p = (t / period) % 1
    if p < 0.5:
        return p * 2 * A
    return (1 - p) * 2 * A

def getDummyData():
    global i
    i += 1
    t = iterToTime(i)
    return {
        "RPM": sine(t, 1800, 2),
        "Throttle": cosine(t, 100, 1),
        "Speed": sine(t, 30, 1),
        "BV": 11.8 + tri(t, 0.4, 0.25),
    }

with open("dummy.txt", "w") as f:
    for x in range(0,count):
        f.write(pack(getDummyData()))