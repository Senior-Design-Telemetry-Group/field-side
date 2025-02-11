import matplotlib
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import tkinter as tk
from tkinter import ttk 
import math
import random

matplotlib.use("TkAgg")

# Configurable Settings
expectedPacketDelay = 100

expectedFields = ["FUEL", "RPM", "Speed", "Slope", "BV", "Throttle", "OXY", "INJ"]
fieldUnits = {
    "FUEL": "MPG",
    "RPM": "RPM",
    "Speed": "MPH",
    "Slope": "°",
    "Throttle": "%",
}

# Not configurable.
timeOptionLabels = ["1s", "5s", "10s", "15s", "30s", "1m", "5m", "10m", "30m"]
timeOptionMS = [1000, 5000, 10000, 15000, 30000, 60000, 60000*5, 60000*10, 60000*30]


def getPacketLimit(option):
    """Get packet # limit when given a selected timeOptionLabel
    """
    if option is None:
        return 0
    idx = timeOptionLabels.index(option)
    return round(timeOptionMS[idx] / expectedPacketDelay)


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

class FieldSelectionFrame(tk.Frame):
    def __init__(self, parent, selected=[]):
        tk.Frame.__init__(self, parent)
        tk.Label(self, text="Fields").grid(column=0,row=0)
        self["borderwidth"] = 2
        self["relief"] = "sunken"
        self["pady"] = 5
        self["padx"] = 5
        self.cbs = []

        for i, field in enumerate(expectedFields):
            cb = ttk.Checkbutton(self, text=field)
            cb.grid(column=0,row=i+1,sticky=(tk.W))
            cb.state(['!selected', '!alternate'])
            if field in selected:
                cb.state(['selected'])
            self.cbs.append(cb)
    
    def getSelected(self):
        selected = []
        for i, cb in enumerate(self.cbs):
            if "selected" in cb.state():
                selected.append(cb['text'])
        return selected

class TimeFrameSelector(ttk.Combobox):
    def __init__(self, parent, current):
        ttk.Combobox.__init__(self, parent, state="readonly", values=timeOptionLabels)
        self.set(current)

    def getLimit(self):
        return self.get()

class GraphSettingsPopup(tk.Tk):
    def __init__(self, graph):
        tk.Tk.__init__(self)
        self.exitValue = None
        mf = tk.Frame(self)
        mf.grid()
        self.graph = graph
        settings = graph.getSettings()
        fs = self.fs = FieldSelectionFrame(mf, settings["fields"])
        fs.grid(column=0,row=0)

        tk.Button(self, text="Save", command=self.__saveButton).grid(column=0,row=1)
        tk.Button(self, text="Cancel", command=self.__quitButton).grid(column=1,row=1)

        self.time = timeCombobox = TimeFrameSelector(self, settings["limit"])
        timeCombobox.grid(column=1,row=0)
        self.grab_set()
    def __saveButton(self):
        settings = {
            "fields": self.fs.getSelected(),
            "limit": self.time.getLimit()
        }
        self.graph.setSettings(settings)
        self.exitValue = "Save"
        self.destroy()
    def __quitButton(self):
        self.destroy()


class StatGraph(tk.Frame):
    def __init__(self, parent, buffer):
        tk.Frame.__init__(self, parent)
        self["borderwidth"] = 2
        self["relief"] = "raised"
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

        lb = tk.Button(self, width=10, command=self.__settingsPopup, text="Settings")
        lb.grid(column=0,row=2)

        self.draw()

    def __settingsPopup(self):
        GraphSettingsPopup(self)
    
    def setFields(self, fs):
        self.fields = fs
    
    def setBufferLimit(self, limit):
        self.limit = limit
    
    def draw(self):
        self.subplot.clear()
        self.subplot.axes.get_xaxis().set_visible(False)
        limit = getPacketLimit(self.limit)
        for _, v in enumerate(self.fields):
            values = self.buffer.get(v, limit)
            self.subplot.plot(values)
        self.subplot.legend(self.fields, loc="upper left")
        self.canvas.draw()

    def getSettings(self):
        return {
            "fields": self.fields,
            "limit": self.limit
        }

    def setSettings(self, settings):
        if settings:
            self.setFields(settings["fields"])
            self.setBufferLimit(settings["limit"])


class StatOverview(tk.Frame):
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
        fstr = '{:9.2f}'
        self.valueVar.set('{:9.2f}{:s}'.format(self.buffer.getLast(self.key) or 0, fieldUnits.get(self.key) or ""))
        self.minVar.set(fstr.format(self.buffer.getMin(self.key) or 0))
        self.avgVar.set('({:9.2f})'.format(self.buffer.getAvg(self.key) or 0))
        self.maxVar.set(fstr.format(self.buffer.getMax(self.key) or 0))


class StatOverviewContainer(tk.Frame):
    def __init__(self, parent, buffer):
        tk.Frame.__init__(self, parent)
        self.statViews = []
        self.rowconfigure(0,weight=1)
        for i, field in enumerate(expectedFields):
            gs = StatOverview(self, buffer, field)
            gs.grid(column=i,row=0,sticky=(tk.N,tk.E,tk.W,tk.S))
            self.statViews.append(gs)
        
    def draw(self):
        for _, statView in enumerate(self.statViews):
            statView.draw()

root = tk.Tk()

buffer = RollingBuffer(getPacketLimit("30m"))
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

gg = StatGraph(graphFrame, buffer)
gg.grid(column=0,row=0)
gg.setFields(["Speed"])
gg.setBufferLimit("1s")
gg2 = StatGraph(graphFrame, buffer)
gg2.grid(column=1,row=0)
gg2.setFields(["Speed"])
gg2.setBufferLimit("5s")

so = StatOverviewContainer(root, buffer)
so.grid(column=0,row=1)

i = 0

def test():
    global i
    buffer.add({"RPM": 1800 * abs(math.sin(i / 10)), "Speed": 30 * abs(math.cos(i / 30)), "Slope": 10 * random.random()})
    i+= 1
    gg.draw()
    gg2.draw()
    so.draw()
    root.after(expectedPacketDelay, test)

# popup = GenericGraphSettingsPopup({})
# popup.show()

root.after(expectedPacketDelay, test)
root.mainloop() 