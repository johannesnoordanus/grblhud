#!/usr/bin/env python3
"""
grblhub: a command line tool to handle grbl code.
"""

import re
import threading
from time import sleep
# needs pyserial!
import serial
from grblhud import lineinput
from grblhud.grblmessages import grbl_errors
from grblhud.grblmessages import grbl_alarm
from grblhud.grblmessages import grbl_settings

# subclass of Thread
class Grblbuffer(threading.Thread):
    """
    Grblbuffer: buffering and access to serial io for grbl devices
    """
    #
    # class variables
    #

    # Regular Colors
    Black  = '\033[0;30m'    # Black
    Red    = '\033[0;31m'    # Red
    IRed   = '\033[0;91m'    # Intense red
    Green  = '\033[0;32m'    # Green
    Yellow = '\033[0;33m'    # Yellow
    IYellow= '\033[0;93m'    # Intense yellow
    Blue   = '\033[0;34m'    # Blue
    Purple = '\033[0;35m'    # Purple
    Cyan   = '\033[0;36m'    # Cyan
    White  = '\033[0;37m'    # White

    EndCol = '\033[0;0m'     # End of color setting

    # lock
    serialio_lock = threading.Lock()

    # buffer empty condition
    bec = threading.Condition()

    # device buffer size
    RX_BUFFER_SIZE = 128

    # class global thread exit signal
    GRBLHUD_EXIT = False

    # pauze status report when true
    STATUS_PAUZE = False

    def __init__(self, serial, grblinput, interactive: bool):
        threading.Thread.__init__(self)
        self.serial = serial
        self.interactive = interactive

        # init
        self.grblinput = grblinput
        self.init_buffer()
        self.WCO = {"X" : 0.0, "Y" : 0.0, "Z" : 0.0}
        self.machinestatus = { "state" : "", "X" : 0.0, "Y" : 0.0, "Z" : 0.0, "Feed" : 0, "Speed" : 0 }
        self.machinesettings = {}

        # status report
        self.status_plain = False

        # create and start query process
        self.grblstatus = threading.Thread(target=self.status, args=(.1,))
        self.grblstatus.start()

    def init_buffer(self):
        """
        init buffer
        """
        # reset device buffer count
        self.gcode_count = 0
        self.line_count = 0
        self.serial_buffer_count = []

        # initial buffer state: empty
        self.gcode_buffer = []

    def update_machinestatus(self, status):
        """
        set machinestatus info from grbl status (result of grbl '?' command)
        """
        if status != '':
            # Sample status report:
            #   <Idle|MPos:0.000,0.000,-10.000|FS:0,0>
            #   <Idle|MPos:-2.996,-2.996,0.000|Bf:15,126|FS:0,0|WCO:0.000,0.000,0.000>
            # Note that 'Real-time Status Reports' are specified here:
            # 'https://github.com/gnea/grbl/wiki/Grbl-v1.1-Interface'
            self.machinestatus = {"state" : "Error", "X" : -1.0, "Y" : -1.0, "Z" : -1.0, "Feed" : "-1", "Speed" : "-1"}

            #state = re.search("^<[a-zA-Z]+",status)
            state = re.search("<[a-zA-Z]+",status)
            if state:
                self.machinestatus["state"] = state.group(0)[1:]

            # Get WCO (Work Coordinate Offset)
            # GRBL documentation:
            #    GUI Developers: Simply track and retain the last WCO: vector and use the below equation to compute the
            #    other position vector for your position readouts. If Grbl's status reports show either WPos or MPos,
            #    just follow the equations below. It's as easy as that!
            wco = re.search("WCO:[+\-]?[0-9.,+\-]+[\|>]",status)
            if wco:
                wco_X = re.search("[+-]?[0-9.+\-]+", wco.group(0))
                if wco_X:
                    self.WCO["X"] = float(wco_X.group(0))
                wco_Y = re.search(",[+-]?[0-9.+\-]+", wco.group(0))
                if wco_Y:
                    self.WCO["Y"] = float(wco_Y.group(0)[1:])
                wco_Z = re.search(",[+-]?[0-9.+\-]+[\|>]", wco.group(0))
                if wco_Z:
                    self.WCO["Z"] = float(wco_Z.group(0)[1:-1])

            # always report WPos coordinates
            mpos = re.search("MPos:[+\-]?[0-9.,+\-]+[\|>]",status)
            if mpos:
                # * If MPos: is given, use WPos = MPos - WCO.
                X = re.search("[+-]?[0-9.+\-]+", mpos.group(0))
                if X:
                    self.machinestatus["X"] = float(X.group(0)) - self.WCO["X"]
                Y = re.search(",[+-]?[0-9.+\-]+", mpos.group(0))
                if Y:
                    self.machinestatus["Y"] = float(Y.group(0)[1:]) - self.WCO["Y"]
                Z = re.search(",[+-]?[0-9.+\-]+[\|>]", mpos.group(0))
                if Z:
                    self.machinestatus["Z"] = float(Z.group(0)[1:-1]) - self.WCO["Z"]
            else:
                wpos = re.search("WPos:[+\-]?[0-9.,+\-]+[\|>]",status)
                if wpos:
                    # always report WPos coordinates
                    # ( * If WPos: is given, use MPos = WPos + WCO.)
                    X = re.search("[+-]?[0-9.+\-]+", wpos.group(0))
                    if X:
                        # self.machinestatus["X"] = float(X.group(0)) + self.WCO["X"]
                        self.machinestatus["X"] = float(X.group(0))
                    Y = re.search(",[+-]?[0-9.+\-]+", wpos.group(0))
                    if Y:
                        # self.machinestatus["Y"] = float(Y.group(0)[1:]) + self.WCO["Y"]
                        self.machinestatus["Y"] = float(Y.group(0)[1:])
                    Z = re.search(",[+-]?[0-9.+\-]+[\|>]", wpos.group(0))
                    if Z:
                        #self.machinestatus["Z"] = float(Z.group(0)[1:-1]) + self.WCO["Z"]
                        self.machinestatus["Z"] = float(Z.group(0)[1:-1])

            fs = re.search("FS:[0-9,]+",status)
            if fs:
                F = re.search("[0-9]+", fs.group(0))
                if F:
                    self.machinestatus["Feed"] = F.group(0)
                S = re.search(",[0-9]+", fs.group(0))
                if S:
                    self.machinestatus["Speed"] = S.group(0)[1:]

    def format_machinestatus(self):
        """
        format machinestatus for printing
        """
        # machinestatus = { "state" : "", "X" : 0.0, "Y" : 0.0, "Z" : 0.0, "Feed" : 0, "Speed" : 0 }
        return (
                    f"[{self.machinestatus['state']:<4} "
                    f"XYZ:{self.machinestatus['X']:06.3f},{self.machinestatus['Y']:06.3f},{self.machinestatus['Z']:06.3f} "
                    f"FS:{self.machinestatus['Feed']},{self.machinestatus['Speed']}]"
        )

    def grbl_count_io(self):
        """
        grbl io counting
        """
        with Grblbuffer.serialio_lock:
            while not Grblbuffer.GRBLHUD_EXIT and self.serial.in_waiting:
                #read
                out_temp = self.serial.read_until().strip() # Wait for grbl response
                if out_temp.find(b"ok") < 0 and out_temp.find(b"error") < 0 :
                    if re.search("<.+", out_temp.decode('ascii')) or re.search(".+>", out_temp.decode('ascii')):
                        self.update_machinestatus(out_temp.decode('ascii'))
                        color = ''
                        # select status color
                        if "Idle" in self.machinestatus["state"]:
                            color = Grblbuffer.Green
                        elif "Hold" in self.machinestatus["state"]:
                            color = Grblbuffer.IRed
                        elif "Run" in self.machinestatus["state"]:
                            color = Grblbuffer.Red
                        elif "Alarm" in self.machinestatus["state"]:
                            color = Grblbuffer.IYellow
                        elif "Sleep" in self.machinestatus["state"]:
                            color = Grblbuffer.Blue
                        elif "Door" in self.machinestatus["state"]:
                            color = Grblbuffer.Cyan
                        elif "Check" in self.machinestatus["state"]:
                            color = ''

                        endmarker =  "> " if self.interactive else "#  "
                        endprompt =  " grbl" if self.interactive else " "

                        prompt_length = len(str(self.buffer_not_empty()) + "|" + self.format_machinestatus() + endmarker + endprompt)
                        self.grblinput.display_line(str(self.buffer_not_empty()) + "|" + color + self.format_machinestatus() +
                                                    Grblbuffer.EndCol + endprompt + color + endmarker + Grblbuffer.EndCol, prompt_length)

                        if self.status_plain:
                            # toggle it
                            self.status_plain = False
                            print(out_temp.decode('ascii'), flush=True)
                    else:
                        # Ignore all else
                        # Note that this should not happen, but sometimes, it seems, returns on direct commands are broken off
                        otds = out_temp.decode('ascii').strip()
                        if len(otds):
                            alrm = re.search("ALARM:[1-9][0-9]?",otds)
                            if alrm and int(alrm.group()[6:]) in grbl_alarm.keys():
                                otds += " (" + grbl_alarm[int(alrm.group()[6:])] + ")"
                            else:
                                # add meaning to settings
                                # $1=25
                                setting = re.search("^\$[0-9]+=[0-9]+(\.[0-9]+)?",otds)
                                if setting:
                                    setting = re.search("^\$[0-9]+",setting.group())
                                    if setting and int(setting.group()[1:]) in grbl_settings.keys():
                                        value = re.search("=[0-9]+(\.[0-9]+)?",otds)
                                        # save machine settings
                                        if value:
                                            self.machinesettings[setting.group()] = value.group()[1:]

                                        otds += " " * ((25 - len(otds)) if len(otds) < 25 else 1)  + "(" + grbl_settings[int(setting.group()[1:])] + ")"
                            print(otds)
                else:
                    # Note: ignore incomming pending ok's until counting is in balance.
                    # this is needed at startup when the device is in 'Hold' state
                    if self.serial_buffer_count:            # Delete the block character count corresponding to the last 'ok'
                        self.gcode_count += 1               # update g-code counter
                        del self.serial_buffer_count[0]     # Delete the block character count corresponding to the last 'ok'
                    otds = out_temp.decode('ascii').strip()
                    if len(otds):
                        if otds != "ok":
                            err = re.search("error:[1-9][0-9]?",otds)
                            if err and int(err.group()[6:]) in grbl_errors.keys():
                                otds += " (" + grbl_errors[int(err.group()[6:])] + ")"
                            print(otds)

    def status(self, delay):
        """
        write status request to grbl device and get response
        """
        print("Status report every", delay, "seconds (WPos coordinates)")
        while not Grblbuffer.GRBLHUD_EXIT:
            if not Grblbuffer.STATUS_PAUZE:
                with Grblbuffer.serialio_lock:
                    # write direct command '?'
                    self.serial.write("?".encode())
                # read result
                self.grbl_count_io()
            sleep(delay)
        print("Status report exit")

    def buffer_not_empty(self) -> int:
        """
       	check if gcode buffer has elements
        returns: 0 if buffer empty, buffer length if not
        """
        return len(self.gcode_buffer)

    def put(self, line, prepend=False):
        """
       	put gcode on buffer
        """
        with Grblbuffer.bec:
            if not self.buffer_not_empty():
                Grblbuffer.bec.notify()
            if prepend:
                # put line at the start of the queue (first served/prioritized)
                self.gcode_buffer = [line] + self.gcode_buffer
            else:
                # put line at the end of the queue (last served)
                self.gcode_buffer.append(line)

    def get(self):
        """
       	get gcode from buffer
        """
        # get first line put onto the queue
        line = ''
        with Grblbuffer.bec:
            Grblbuffer.bec.wait_for(self.buffer_not_empty)

            line = self.gcode_buffer[0]
            del self.gcode_buffer[0]
        return line

    # override run message
    def run(self):
        """
       	get gcode from buffer: put it in the 'device' buffer
        """
        print("Start command queue")
        while not Grblbuffer.GRBLHUD_EXIT:
            line = self.get()
            self.grbl_buffer(line)
        print("End command queue")

    def grbl_buffer(self, line):
        """
       	grbl device buffer: write gcode (block), or wait until space available
	also, handle grbl device results
        """
        # Send g-code program via a more agressive streaming protocol that forces characters into
        # Grbl's serial read buffer to ensure Grbl has immediate access to the next g-code command
        # rather than wait for the call-response serial protocol to finish. This is done by careful
        # counting of the number of characters sent by the streamer to Grbl and tracking Grbl's
        # responses, such that we never overflow Grbl's serial read buffer.

        if line != '':
            with Grblbuffer.serialio_lock:
                self.line_count += 1 # Iterate line counter
                l_block = line.strip()
                self.serial_buffer_count.append(len(l_block)+1) # Track number of characters in grbl serial read buffer

        while not Grblbuffer.GRBLHUD_EXIT and ((sum(self.serial_buffer_count) >= Grblbuffer.RX_BUFFER_SIZE-1) or self.serial.in_waiting):
            self.grbl_count_io()

        if line != '':
            with Grblbuffer.serialio_lock:
                # check for special characters not needing a nl
                l_blockn = l_block + '\n'
                self.serial.write(l_blockn.encode()) # Send g-code block to grbl


