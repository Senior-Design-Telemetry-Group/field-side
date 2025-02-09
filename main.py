import matplotlib
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import tkinter as tk
import random
import math

matplotlib.use("TkAgg")

class RollingBuffer():
    def __init__(self, size):
        self.buffer = []
        self.size = size
        self.max = {}
        self.min = {}
        self.average = {}
        self.seenKeys = {}

    def reset(self):
        self.buffer = []
        self.max = {}
        self.min = {}
        self.average = {}
        self.seenKeys = {}

    def _checkTrim(self):
        if len(self.buffer) > self.size:
            self.buffer.pop(0)
    
    def _updateStats(self):
        for key in self.seenKeys:
            buff = [i for i in self.get(key) if i is not None]
            self.max[key] = max(buff)
            self.min[key] = min(buff)
            s = sum(buff)
            self.average[key] = s / len(buff)
        # self.max = max(self.buffer)
        # self.min = min(self.buffer)
        # s = sum(self.buffer)
        # self.average = s / len(self.buffer)

    def add(self, values):
        self.buffer.append(values)
        for key in values:
            self.seenKeys[key] = True
        self._checkTrim()
        self._updateStats()
    
    def get(self, key, count=0):
        count = count or 0
        return [d.get(key) for d in self.buffer[-count:]]
    
    def getLast(self, key):
        return next((dop for dop in reversed(self.get(key)) if dop is not None), None)
    
    def getMin(self, key):
        return self.min.get(key)
    
    def getAvg(self, key):
        return self.average.get(key)
    
    def getMax(self, key):
        return self.max.get(key)


class GenericGraph(tk.Frame):
    def __init__(self, parent, buffer):
        tk.Frame.__init__(self, parent)
        label = tk.Label(self, text="Graph Page!")
        label.grid(column=0,row=0)

        f = Figure(figsize=(5,5), dpi=100)
        subplot = f.add_subplot(111)
        self.subplot = subplot
        self.buffer = buffer
        self.fields = []
        self.limit = None

        self.canvas = FigureCanvasTkAgg(f, self)
        self.canvas.get_tk_widget().grid(column=0,row=1,sticky=(tk.N,tk.W,tk.E,tk.S))
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)

        self.draw()
    
    def setFields(self, fs):
        self.fields = fs
    
    def setBufferLimit(self, limit):
        self.limit = limit
    
    def draw(self):
        self.subplot.clear()
        self.subplot.axes.get_xaxis().set_visible(False)
        for _, v in enumerate(self.fields):
            values = self.buffer.get(v, self.limit)
            self.subplot.plot(values)
        self.subplot.legend(self.fields, loc="upper left")
        self.canvas.draw()


class GenericStats(tk.Frame):
    def __init__(self, parent, buffer, key):
        tk.Frame.__init__(self, parent)
        self["borderwidth"] = 2
        self["relief"] = "sunken"
        self["pady"] = 5
        self["padx"] = 5

        self.buffer = buffer
        self.key = key

        label = tk.Label(self, text=key)
        label.grid(column=0,row=0,columnspan=3)

        self.valueVar = tk.StringVar()
        valueLabel = tk.Label(self, textvariable=self.valueVar)
        valueLabel.grid(column=0,row=1,columnspan=3)
        valueLabel.config(font=("Courier", 15))


        self.minVar = tk.StringVar()
        minLabel = tk.Label(self, textvariable=self.minVar)
        minLabel.grid(column=0,row=2)
        tk.Label(self, text="MIN").grid(column=0,row=3)

        self.avgVar = tk.StringVar()
        avgLabel = tk.Label(self, textvariable=self.avgVar)
        avgLabel.grid(column=1,row=2)
        tk.Label(self, text="AVG").grid(column=1,row=3)

        self.maxVar = tk.StringVar()
        maxLabel = tk.Label(self, textvariable=self.maxVar)
        maxLabel.grid(column=2,row=2)
        tk.Label(self, text="MAX").grid(column=2,row=3)
    
    def draw(self):
        fstr = '{:10.2f}'
        self.valueVar.set(fstr.format(self.buffer.getLast(self.key) or 0))
        self.minVar.set(fstr.format(self.buffer.getMin(self.key) or 0))
        self.avgVar.set('({:10.2f})'.format(self.buffer.getAvg(self.key) or 0))
        self.maxVar.set(fstr.format(self.buffer.getMax(self.key) or 0))
        

root = tk.Tk()

buffer = RollingBuffer(128)
for i in range(0, 100):
    buffer.add({"RPM":i, "Speed": 100-i})

buffer.add({})
root.columnconfigure(0, weight=1)
root.rowconfigure(0,weight=1)

graphFrame = tk.Frame(root)
graphFrame.grid(column=0,row=0)
graphFrame.columnconfigure(0, weight=1)
graphFrame.columnconfigure(1, weight=1)
graphFrame.rowconfigure(0,weight=1)

gg = GenericGraph(graphFrame, buffer)
gg.grid(column=0,row=0)
gg.setFields(["RPM", "Speed"])
gg.setBufferLimit(5)
gg2 = GenericGraph(graphFrame, buffer)
gg2.grid(column=1,row=0)
gg2.setFields(["Speed"])

gs = GenericStats(root, buffer, "Speed")
gs.grid(column=0,row=1)
gs2 = GenericStats(root, buffer, "RPM")
gs2.grid(column=1,row=1)

def test():
    buffer.add({"RPM": random.randint(0,1600), "Speed": random.randrange(0,30)})
    gg.draw()
    gg2.draw()
    gs.draw()
    gs2.draw()
    root.after(200, test)

root.after(200, test)
root.mainloop()