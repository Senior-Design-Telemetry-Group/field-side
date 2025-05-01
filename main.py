import matplotlib
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import tkinter as tk
from tkinter import filedialog
from tkinter import ttk 
import math
import re
import json
import serial
from threading import Thread
import time
import tkintermapview
import serial.tools.list_ports

matplotlib.use("TkAgg")

# Configurable Settings
expectedPacketDelay = 50

expectedFields = [
    "FUEL", 
    "RPM", 
    "Speed", 
    "Slope", 
    "BV", 
    "Throttle", 
    "OXY", 
    "INJ",
    "LAT",
    "LON"
]
fieldUnits = {
    "FUEL": "MPG",
    "RPM": "RPM",
    "Speed": "MPH",
    "Slope": "°",
    "Throttle": "%",
    "BV": "V"
}

port = "/dev/ttyUSB0"
baudrate = 115200
fieldLoraAddress = 100
carLoraAddress = 101

# *SF7to SF9 at 125kHz, SF7 to SF10 at 250kHz, and SF7 to SF11 at 500kHz
loraSpreadFactor = 7
# 7: 125kHz, 8: 250kHz, 9: 500kHz
loraBW = 9
# 1: 4/5, 2: 4/6, 3: 4/7, 4: 4/8
loraCodingRate = 4
loraPreamble = 12

mapRegions = {
    "Indianapolis Speedway": [(39.802591, -86.239712), (39.788232, -86.229659)],
    "Burke": [(42.119826,-79.980805), (42.118107,-79.979292)]
}
region = "Indianapolis Speedway"

# Not configurable.
timeOptionLabels = ["1s", "5s", "10s", "15s", "30s", "1m", "5m", "10m", "30m"]
timeOptionMS = [1000, 5000, 10000, 15000, 30000, 60000, 60000*5, 60000*10, 60000*30]
maxBufferLength = round(60000 * 60 / expectedPacketDelay)
displayRefreshDelay = 200

activePopup = None
mainBuffer = None
serialThread = None
logInfo = None
statContainer = None

def getPacketLimit(option):
    """Get packet # limit when given a selected timeOptionLabel
    """
    if option is None:
        return 0
    idx = timeOptionLabels.index(option)
    avg = mainBuffer.getAvg("delta")
    return round(timeOptionMS[idx] / avg)


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
        try:
            if activePopup and activePopup.winfo_exists():
                activePopup.destroy()
                activePopup = None
        except tk.TclError:
            pass
        activePopup = self
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

class GeneralSettingsPopup(tk.Tk):
    def __init__(self):
        tk.Tk.__init__(self)
        mf = tk.Frame(self)
        mf.grid(row=0,column=0)
        mf.columnconfigure(0, weight=1)
        mf.rowconfigure(0, weight=1)

        serialFrame = tk.Frame(mf)
        serialFrame["borderwidth"] = 2
        serialFrame["relief"] = "raised"
        serialFrame.grid(column=0,row=0,sticky=(tk.W,tk.E,tk.N,tk.S))
        serialFrame.rowconfigure(0, weight=1)
        serialFrame.columnconfigure(0, weight=1)

        portlist = serial.tools.list_ports.comports()
        self.portlookup = {}
        for p in portlist:
            self.portlookup[str(p)] = p.device
        tk.Label(serialFrame, text="Serial Port:", padx=10, pady=10).grid(column=0,row=0)
        self.portBox = ttk.Combobox(serialFrame, values=portlist)
        self.portBox.set(port)
        self.portBox.grid(column=1,row=0,padx=10,pady=10)

        connectButton = ttk.Button(serialFrame, text="Connect",command=self.__connect)
        connectButton.grid(column=1,row=1,sticky=(tk.W, tk.E))

        mapSettingFrame = tk.Frame(mf)
        mapSettingFrame.grid(column=0,row=1,sticky=(tk.W,tk.E,tk.N,tk.S))
        mapSettingFrame["borderwidth"] = 2
        mapSettingFrame["relief"] = "raised"

        tk.Label(mapSettingFrame, text="Map Region:", padx=10,pady=10).grid(column=0,row=0)
        self.mapRegionBox = ttk.Combobox(mapSettingFrame, values=list(mapRegions.keys()))
        self.mapRegionBox.set(region)
        self.mapRegionBox.grid(column=1,row=0)

        ttk.Button(mf, text="Save", command=self.__save).grid(column=0,row=2,sticky=(tk.W, tk.E))

    def __connect(self):
        global port
        value = self.portBox.get()
        port = self.portlookup.get(value) or value
        startSerialThread()

    def __save(self):
        global port, region
        value = self.portBox.get()
        port = self.portlookup.get(value) or value
        region = self.mapRegionBox.get()
        self.destroy()
        setRegion(region)

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
    if pkt[0:5] != "TELEM":
        return None
    matches = re.findall("([a-zA-Z]+)=(-?[0-9]+\\.?[0-9]*)[;\n]", pkt)
    values = {}
    for match in matches:
        values[match[0]] = float(match[1])
    return values

def parseLoraPacket(pkt):
    if pkt[0:5] != "+RCV=":
        return None
    idx = pkt.find("TELEM")
    if idx == -1:
        return None
    return parsePacket(pkt[idx:])


# i = 0
# def getDummyData():
#     global i
#     i += 1
#     return {
#         "RPM": 1800 * abs(math.sin(i / 10)),
#         "Speed": 30 * abs(math.cos(i / 30)), 
#         "Slope": 10 * random.random(),
#         "BV": 11.8 + random.random() * 0.4,
#     }

# dummyFileData = None
# def preloadDummyFileData():
#     global dummyFileData
#     dummyFileData = []
#     with open("dummy.txt", "r") as fin:
#         lines = fin.readlines()
#     for l in lines:
#         dummyFileData.append(parsePacket(l))
# preloadDummyFileData()


# def getDummyFileData():
#     global i
#     data = dummyFileData[i % len(dummyFileData)]
#     i += 1
#     return data

fileTypes = [("Layout config", "*.config")]

running = True
class AsyncSerial(Thread):
    def __init__(self):
        super().__init__()
        self.lastPktTime = time.time()

    def open(self, port):
        try:
            self.s = serial.Serial(port, baudrate=baudrate, timeout=1)
            self.lastPktTime = time.time()
            return True
        except serial.serialutil.SerialException:
            return False
    
    def initLora(self):
        log("Resetting Modem")
        self.s.write("AT+RESET\r\n".encode())
        data = self.s.readline()
        log(data)
        data = self.s.readline()
        log(data)
        log("Setting RF Power")
        self.s.write("AT+CRFOP=10\r\n".encode())
        data = self.s.readline()
        log(data)
        log("Setting Address")
        self.s.write(f"AT+ADDRESS={fieldLoraAddress}\r\n".encode())
        data = self.s.readline()
        log(data)
        log("Setting Parameters")
        self.s.write(f"AT+PARAMETER={loraSpreadFactor},{loraBW},{loraCodingRate},{loraPreamble}\r\n".encode())
        data = self.s.readline()
        log(data)
    
    def run(self):
        while running:
            data = self.s.readline()
            log(data)
            try:
                pkt = parseLoraPacket(data.decode())
                if pkt:
                    delta = (time.time() - self.lastPktTime) * 1000 # second to ms
                    if delta < 3*expectedPacketDelay:
                        # filter outliers
                        pkt['delta'] = delta
                    if pkt.get("LAT"):
                        logPosition(pkt.get("LAT"), pkt.get("LON"))
                    if pkt.get("ACCZ") and pkt.get("ACCX"):
                        z = pkt.get("ACCZ")
                        x = pkt.get("ACCX")
                        pkt["Slope"] = -math.degrees(math.atan2(z, -x))
                    mainBuffer.add(pkt)
                    statContainer.draw()
            except UnicodeDecodeError as e:
                pass
            self.lastPktTime = time.time()

def log(s):
    logInfo.insert("end", f"[{time.strftime('%I:%M:%S')}]: {s}\n")
    logInfo.see("end")

def startSerialThread():
    global serialThread
    if serialThread:
        log("Serial thread already running!")
        return
    serialThread = AsyncSerial()
    log(port)
    if not serialThread.open(port):
        log("Failed to open serial port!")
        serialThread = None
        return False
    serialThread.initLora()
    serialThread.start()
    return True

def showSettingsMenu():
    settings = GeneralSettingsPopup()

mapWidget = None
mapPath = None
positionLog = []
def setRegion(region):
    selectedRegion = mapRegions[region]
    mapWidget.fit_bounding_box(selectedRegion[0], selectedRegion[1])

def convertNmeaToDecimal(nmea_value):
    sign = -1 if nmea_value < 0 else 1
    abs_value = abs(nmea_value)

    degrees = int(abs_value // 100)
    minutes = abs_value - (degrees * 100)
    decimal = degrees + (minutes / 60)

    return sign * decimal

def logPosition(lat, lon):
    global mapPath
    lat = convertNmeaToDecimal(lat)
    lon = -convertNmeaToDecimal(lon)
    positionLog.append((lat,lon))
    if len(positionLog) > 3:
        mapPath = mapWidget.set_path(positionLog)
        mapWidget.update()
        mapWidget.update_idletasks()
        positionLog.pop(0)

def main():
    def loadSettings(fn):
        global port, region
        with open(fn, 'r') as file:
            content = file.read()
        j = json.loads(content)
        port = j["port"]
        region = j["region"]
        graphContainer.setSettings(j["graphs"])
        setRegion(region)
    def loadSettingsPopup():
        fn = filedialog.askopenfilename(filetypes=fileTypes)
        if fn is None:
            return
        loadSettings(fn)

    def saveSettings():
        fn = filedialog.asksaveasfilename(filetypes=fileTypes)
        if fn is None:
            return
        j = {}
        j["port"] = port
        j["graphs"] = graphContainer.getSettings()
        j["region"] = region
        with open(fn, 'w') as file:
            file.write(json.dumps(j))
    global mainBuffer, serialThread, logInfo, statContainer, mapWidget, mapPath, root, mainFrame
    mainBuffer = RollingBuffer(maxBufferLength)
    # Initialize time buffer with expected time, to reduce the effect of outliers
    for i in range(0, 100):
        mainBuffer.add({"delta": expectedPacketDelay})
    root = tk.Tk()
    menubar = tk.Menu(root)
    root.config(menu=menubar)

    filemenu = tk.Menu(menubar, tearoff=False)
    filemenu.add_command(
        label="Edit Settings",
        command=showSettingsMenu
    )
    filemenu.add_command(
        label="Save Config",
        command=saveSettings
    )
    filemenu.add_command(
        label="Load Config",
        command=loadSettingsPopup
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
    mainFrame.grid(column=0,row=0,sticky=(tk.N,tk.W,tk.E,tk.S))
    mainFrame.columnconfigure(0, weight=1)
    # mainFrame.columnconfigure(1, weight=1)
    mainFrame.rowconfigure(0,weight=1)

    graphContainer = StatGraphContainer(mainFrame)
    graphContainer.grid(column=0,row=0,sticky=(tk.N,tk.W,tk.E,tk.S))
    graphContainer.columnconfigure(0, weight=1)
    graphContainer.rowconfigure(0,weight=1)

    bottomContainer = tk.Frame(mainFrame)
    bottomContainer.grid(column=0,row=1,sticky=(tk.N,tk.W,tk.E,tk.S))
    bottomContainer.columnconfigure(0, weight=1)
    bottomContainer.rowconfigure(0,weight=1)

    statColumn = tk.Frame(bottomContainer)
    statColumn.grid(column=0,row=0,sticky=(tk.N,tk.W,tk.E,tk.S))
    statColumn.columnconfigure(0, weight=1)
    statColumn.rowconfigure(0,weight=1)
    statContainer = StatOverviewContainer(statColumn, mainBuffer)
    statContainer.grid(column=1,row=0,sticky=(tk.N,tk.W,tk.E,tk.S))

    logInfo = tk.Text(statColumn,height=8)
    logInfo.grid(column=0,row=0,sticky=(tk.N,tk.W,tk.E,tk.S))

    mapWidget = tkintermapview.TkinterMapView(mainFrame, width=500)
    mapWidget.grid(column=1,row=0,sticky=(tk.N,tk.W,tk.E,tk.S),rowspan=2)
    mapWidget.set_position(39.789184736877345, -86.23609137045648)

    # def tick():
    #     mainBuffer.add(getDummyFileData())
    #     statContainer.draw()
    #     root.after(expectedPacketDelay, tick)

    def graphDrawTick():
        graphContainer.draw()
        root.after(displayRefreshDelay, graphDrawTick)

    startSerialThread()
    # root.after(expectedPacketDelay, tick)
    root.after(displayRefreshDelay, graphDrawTick)
    root.mainloop()
    global running
    running = False
    serialThread.join()


if __name__ == "__main__":
    main()