import matplotlib
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import tkinter as tk
from tkinter import filedialog
from tkinter import ttk 
import math
import random
import re
import json

matplotlib.use("TkAgg")

# Configurable Settings
expectedPacketDelay = 200

expectedFields = ["FUEL", "RPM", "Speed", "Slope", "BV", "Throttle", "OXY", "INJ"]
fieldUnits = {
    "FUEL": "MPG",
    "RPM": "RPM",
    "Speed": "MPH",
    "Slope": "°",
    "Throttle": "%",
    "BV": "V"
}


# Not configurable.
timeOptionLabels = ["1s", "5s", "10s", "15s", "30s", "1m", "5m", "10m", "30m"]
timeOptionMS = [1000, 5000, 10000, 15000, 30000, 60000, 60000*5, 60000*10, 60000*30]
maxBufferLength = 60000 * 60 / expectedPacketDelay
displayRefreshDelay = 200

activePopup = None

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
        ttk.Combobox.__init__(self, parent, state="readonly", values=timeOptionLabels, width=5)
        self.set(current)

    def getLimit(self):
        return self.get()

class GraphSettingsPopup(tk.Tk):
    def __init__(self, graph):
        global activePopup
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

        self.time = timeCombobox = TimeFrameSelector(self, settings["limit"] or "30m")
        timeCombobox.grid(column=1,row=0)
        self.grab_set()
        if activePopup:
            activePopup.destroy()
            activePopup = None
        activePopup = self
    def __saveButton(self):
        print(self)
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

        f = Figure(layout="tight")
        subplot = f.add_subplot(111)
        self.subplot = subplot
        self.buffer = buffer
        self.fields = []
        self.limit = None
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        self.canvas = FigureCanvasTkAgg(f, self)
        self.canvas.get_tk_widget().grid(column=0,row=0,sticky=(tk.N,tk.W,tk.E,tk.S))
        
        lb = tk.Button(self, width=10, command=self.__settingsPopup, text="Settings")
        lb.grid(column=0,row=1)

        self.draw()

    def __settingsPopup(self):
        GraphSettingsPopup(self)
    
    def setFields(self, fs):
        self.fields = fs
    
    def setBufferLimit(self, limit):
        self.limit = limit
    
    def draw(self):
        self.subplot.clear()
        # self.subplot.axes.get_xaxis().set_visible(False)
        limit = getPacketLimit(self.limit)
        for _, v in enumerate(self.fields):
            values = self.buffer.get(v, limit)
            self.subplot.plot(values)
        self.subplot.axes.set_xticks([])
        self.subplot.legend(self.fields, loc="upper left")
        self.subplot.set_xlabel(f"Last {self.limit}")
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

class StatGraphContainer(tk.Frame):
    def __init__(self, parent):
        tk.Frame.__init__(self, parent)
        self["borderwidth"] = 2
        self["relief"] = "raised"
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.graphs = []
        self.graphFrame = tk.Frame(self)
        self.graphFrame.grid(column=0,row=0,sticky=(tk.N,tk.W,tk.E,tk.S))
        self.graphFrame.rowconfigure(0, weight=1)

        buttonFrame = tk.Frame(self)
        buttonFrame.grid(column=0,row=1,sticky=(tk.E))
        buttonFrame.rowconfigure(0, weight=1)
        tk.Button(buttonFrame, text="Add", command=self.addGraph).grid(column=1,row=0)
        tk.Button(buttonFrame, text="Remove", command=self.removeGraph).grid(column=0,row=0)
        self.addGraph()

    def __redoGraphs(self):
        gBackup = self.graphs
        self.graphs = []
        for i, g in enumerate(gBackup):
            settings = g.getSettings()
            g.destroy()
            graph = StatGraph(self.graphFrame, mainBuffer)
            graph.grid(column=i,row=0,sticky=(tk.N,tk.W,tk.E,tk.S))
            graph.setSettings(settings)
            self.graphFrame.columnconfigure(i, weight=1)
            self.graphs.append(graph)

    def __addGraph(self):
        idx = len(self.graphs)
        graph = StatGraph(self.graphFrame, mainBuffer)
        graph.grid(column=idx,row=0,sticky=(tk.N,tk.W,tk.E,tk.S))
        self.graphFrame.columnconfigure(idx, weight=1)
        self.graphs.append(graph)

    def addGraph(self):
        # This is so janky
        # But if we only append a new graph it will be a different size than the rest of the graphs
        # So instead remove all existing graphs, and recreate them.
        self.__redoGraphs()
        self.__addGraph()
    
    def __removeGraph(self):
        idx = len(self.graphs)
        self.graphFrame.columnconfigure(idx, weight=0)
        graph = self.graphs.pop()
        graph.destroy()

    def removeGraph(self):
        self.__removeGraph()
        self.__redoGraphs()
    
    def draw(self):
        for _, graph in enumerate(self.graphs):
            graph.draw()
    
    def getSettings(self):
        settings = []
        for _, graph in enumerate(self.graphs):
            settings.append(graph.getSettings())
        return settings
    
    def __setGraphCount(self, count):
        current = len(self.graphs)
        while current > count:
            self.__removeGraph()
            current -= 1
        while current < count:
            self.__addGraph()
            current += 1
        self.__redoGraphs()

    def setSettings(self, settings):
        graphCount = len(settings)
        self.__setGraphCount(graphCount)
        for i, set in enumerate(settings):
            self.graphs[i].setSettings(set)

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
            gs.grid(column=math.floor(i/2),row=i%2,sticky=(tk.N,tk.E,tk.W,tk.S))
            self.statViews.append(gs)
        
    def draw(self):
        for _, statView in enumerate(self.statViews):
            statView.draw()

def parsePacket(pkt):
    if pkt[0:3] != "PKT":
        return None
    matches = re.findall("([a-zA-Z]+)=([0-9.]+)[;\n]", pkt)
    values = {}
    for match in matches:
        values[match[0]] = float(match[1])
    return values

i = 0
def getDummyData():
    global i
    i += 1
    return {
        "RPM": 1800 * abs(math.sin(i / 10)),
        "Speed": 30 * abs(math.cos(i / 30)), 
        "Slope": 10 * random.random(),
        "BV": 11.8 + random.random() * 0.4,
    }

dummyFileData = None
def preloadDummyFileData():
    global dummyFileData
    dummyFileData = []
    with open("dummy.txt", "r") as fin:
        lines = fin.readlines()
    for l in lines:
        dummyFileData.append(parsePacket(l))
preloadDummyFileData()


def getDummyFileData():
    global i
    data = dummyFileData[i % len(dummyFileData)]
    i += 1
    return data

fileTypes = [("Layout config", "*.config")]

mainBuffer = None
def main():
    def loadSettings():
        fn = filedialog.askopenfilename(filetypes=fileTypes)
        with open(fn, 'r') as file:
            content = file.read()
        j = json.loads(content)
        graphContainer.setSettings(j["graphs"])

    def saveSettings():
        fn = filedialog.asksaveasfilename(filetypes=fileTypes)
        j = {}
        j["graphs"] = graphContainer.getSettings()
        with open(fn, 'w') as file:
            file.write(json.dumps(j))
    global mainBuffer
    mainBuffer = RollingBuffer(maxBufferLength)
    root = tk.Tk()
    menubar = tk.Menu(root)
    root.config(menu=menubar)

    filemenu = tk.Menu(menubar, tearoff=False)
    filemenu.add_command(
        label="Save Config",
        command=saveSettings
    )
    filemenu.add_command(
        label="Load Config",
        command=loadSettings
    )
    filemenu.add_command(
        label="Quit",
        command=root.destroy
    )
    menubar.add_cascade(
        label="File",
        menu=filemenu,
        underline=0
    )

    root.columnconfigure(0, weight=1)
    root.rowconfigure(0,weight=1)
    mainFrame = tk.Frame(root)
    mainFrame.grid(column=0,row=0)
    mainFrame.columnconfigure(0, weight=1)
    mainFrame.rowconfigure(0,weight=1)

    graphContainer = StatGraphContainer(mainFrame)
    graphContainer.grid(column=0,row=0,sticky=(tk.N,tk.W,tk.E,tk.S))
    statContainer = StatOverviewContainer(mainFrame, mainBuffer)
    statContainer.grid(column=0,row=1,sticky=(tk.N,tk.W,tk.E,tk.S))

    def tick():
        mainBuffer.add(getDummyFileData())
        statContainer.draw()
        root.after(expectedPacketDelay, tick)

    def graphDrawTick():
        graphContainer.draw()
        root.after(displayRefreshDelay, graphDrawTick)

    root.after(expectedPacketDelay, tick)
    root.after(displayRefreshDelay, graphDrawTick)
    root.mainloop()


if __name__ == "__main__":
    main()