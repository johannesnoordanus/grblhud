#!/usr/bin/env python3
"""
grblhub: a command line based tool to handle grbl code.
"""
import os
import re
import atexit
import argparse
import threading
import readline
from time import sleep
# needs pyserial!
import serial
from inputimeout import inputimeout, TimeoutOccurred
import lineinput

# G-code error definition
#  ID :	Error Code Description
gc_errors = {
    1 : "G-code words consist of a letter and a value. Letter was not found.",
    2 : "Numeric value format is not valid or missing an expected value.",
    3 : "Grbl '$' system command was not recognized or supported.",
    4 : "Negative value received for an expected positive value.",
    5 : "Homing cycle is not enabled via settings.",
    6 : "Minimum step pulse time must be greater than 3usec",
    7 : "EEPROM read failed. Reset and restored to default values.",
    8 : "Grbl '$' command cannot be used unless Grbl is IDLE. Ensures smooth operation during a job.",
    9 : "G-code locked out during alarm or jog state",
    10 : "Soft limits cannot be enabled without homing also enabled.",
    11 : "Max characters per line exceeded. Line was not processed and executed.",
    12 : "(Compile Option) Grbl '$' setting value exceeds the maximum step rate supported.",
    13 : "Safety door detected as opened and door state initiated.",
    14 : "(Grbl-Mega Only) Build info or startup line exceeded EEPROM line length limit.",
    15 : "Jog target exceeds machine travel. Command ignored.",
    16 : "Jog command with no '=' or contains prohibited g-code.",
    17 : "Laser mode requires PWM output.",
    20 : "Unsupported or invalid g-code command found in block.",
    21 : "More than one g-code command from same modal group found in block.",
    22 : "Feed rate has not yet been set or is undefined.",
    23 : "G-code command in block requires an integer value.",
    24 : "Two G-code commands that both require the use of the XYZ axis words were detected in the block.",
    25 : "A G-code word was repeated in the block.",
    26 : "A G-code command implicitly or explicitly requires XYZ axis words in the block, but none were detected.",
    27 : "N line number value is not within the valid range of 1 - 9,999,999.",
    28 : "A G-code command was sent, but is missing some required P or L value words in the line.",
    29 : "Grbl supports six work coordinate systems G54-G59. G59.1, G59.2, and G59.3 are not supported.",
    30 : "The G53 G-code command requires either a G0 seek or G1 feed motion mode to be active. A different motion was active.",
    31 : "There are unused axis words in the block and G80 motion mode cancel is active.",
    32 : "A G2 or G3 arc was commanded but there are no XYZ axis words in the selected plane to trace the arc.",
    33 : "The motion command has an invalid target. G2, G3, and G38.2 generates this error, if the arc is impossible to generate or if the probe target is the current position.",
    34 : "A G2 or G3 arc, traced with the radius definition, had a mathematical error when computing the arc geometry. Try either breaking up the arc into semi-circles or quadrants, or redefine them with the arc offset definition.",
    35 : "A G2 or G3 arc, traced with the offset definition, is missing the IJK offset word in the selected plane to trace the arc.",
    36 : "There are unused, leftover G-code words that aren't used by any command in the block.",
    37 : "The G43.1 dynamic tool length offset command cannot apply an offset to an axis other than its configured axis. The Grbl default axis is the Z-axis.",
    38 : "Tool number greater than max supported value." }

# G-code ALARM definition
# ID:	Alarm Code Description
gc_alarm = {
    1 : "Hard limit triggered. Machine position is likely lost due to sudden and immediate halt. Re-homing is highly recommended.",
    2 : "G-code motion target exceeds machine travel. Machine position safely retained. Alarm may be unlocked.",
    3 : "Reset while in motion. Grbl cannot guarantee position. Lost steps are likely. Re-homing is highly recommended.",
    4 : "Probe fail. The probe is not in the expected initial state before starting probe cycle, where G38.2 and G38.3 is not triggered and G38.4 and G38.5 is triggered.",
    5 : "Probe fail. Probe did not contact the workpiece within the programmed travel for G38.2 and G38.4.",
    6 : "Homing fail. Reset during active homing cycle.",
    7 : "Homing fail. Safety door was opened during active homing cycle.",
    8 : "Homing fail. Cycle failed to clear limit switch when pulling off. Try increasing pull-off setting or check wiring.",
    9 : "Homing fail. Could not find limit switch within search distance. Defined as 1.5 * max_travel on search and 5 * pulloff on locate phases.",
    10 : "Homing fail. On dual axis machines, could not find the second limit switch for self-squaring." }

# G-code settings
# $x:	Setting Description, Units
gc_settings = {
    0 :	"Step pulse time, microseconds",
    1 : "Step idle delay, milliseconds",
    2 : "Step pulse invert, mask",
    3 : "Step direction invert, mask",
    4 : "Invert step enable pin, boolean",
    5 : "Invert limit pins, boolean",
    6 : "Invert probe pin, boolean",
    10 : "Status report options, mask",
    11 : "Junction deviation, millimeters",
    12 : "Arc tolerance, millimeters",
    13 : "Report in inches, boolean",
    20 : "Soft limits enable, boolean",
    21 : "Hard limits enable, boolean",
    22 : "Homing cycle enable, boolean",
    23 : "Homing direction invert, mask",
    24 : "Homing locate feed rate, mm/min",
    25 : "Homing search seek rate, mm/min",
    26 : "Homing switch debounce delay, milliseconds",
    27 : "Homing switch pull-off distance, millimeters",
    30 : "Maximum spindle speed, RPM",
    31 : "Minimum spindle speed, RPM",
    32 : "Laser-mode enable, boolean",
    100 : "X-axis steps per millimeter",
    101 : "Y-axis steps per millimeter",
    102 : "Z-axis steps per millimeter",
    110 : "X-axis maximum rate, mm/min",
    111 : "Y-axis maximum rate, mm/min",
    112 : "Z-axis maximum rate, mm/min",
    120 : "X-axis acceleration, mm/sec^2",
    121 : "Y-axis acceleration, mm/sec^2",
    122 : "Z-axis acceleration, mm/sec^2",
    130 : "X-axis maximum travel, millimeters",
    131 : "Y-axis maximum travel, millimeters",
    132 : "Z-axis maximum travel, millimeters" }

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

    def __init__(self, serial, grblinput, status_out = None):
        threading.Thread.__init__(self)
        self.serial = serial
        self.status_out = status_out

        # init
        self.grblinput = grblinput
        self.init_buffer()
        self.machinestatus = { "state" : "", "X" : 0.0, "Y" : 0.0, "Z" : 0.0, "Feed" : 0, "Speed" : 0 }

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
            # Note that this format should be part of the grbl specification.)
            self.machinestatus = {"state" : "Error", "X" : -1.0, "Y" : -1.0, "Z" : -1.0, "Feed" : "-1", "Speed" : "-1" }

            #state = re.search("^<[a-zA-Z]+",status)
            state = re.search("<[a-zA-Z]+",status)
            if state:
                self.machinestatus["state"] = state.group(0)[1:]

            mpos = re.search("MPos:[+\-]?[0-9.,+\-]+\|",status)
            if mpos:
                X = re.search("[+-]?[0-9.+\-]+", mpos.group(0))
                if X:
                    self.machinestatus["X"] = float(X.group(0))
                Y = re.search(",[+-]?[0-9.+\-]+", mpos.group(0))
                if Y:
                    self.machinestatus["Y"] = float(Y.group(0)[1:])
                Z = re.search(",[+-]?[0-9.+\-]+\|", mpos.group(0))
                if Z:
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

                        prompt_length = len(str(self.buffer_not_empty()) + "|" + self.format_machinestatus() + " grbl> ")
                        self.grblinput.display_line(str(self.buffer_not_empty()) + "|" + color + self.format_machinestatus() +
                                                    Grblbuffer.EndCol + " grbl" + color + "> " + Grblbuffer.EndCol, prompt_length)
                        if self.status_out:
                            print("\r" + lineinput.Input.ERASE_TO_EOL + out_temp.decode('ascii').strip(), file=self.status_out, end = '')
                    else:
                        # Ignore all else
                        # Note that this should not happen, but sometimes, it seems, returns on direct commands are broken off
                        otds = out_temp.decode('ascii').strip()
                        if len(otds):
                            alrm = re.search("ALARM:[1-9][0-9]?",otds)
                            if alrm and int(alrm.group()[6:]) in gc_alarm.keys():
                                otds += " (" + gc_alarm[int(alrm.group()[6:])] + ")"
                            print(otds)
                else :
                    # Note: ignore incomming pending ok's until counting is in balance.
                    # this is needed at startup when the device is in 'Hold' state
                    if self.serial_buffer_count:            # Delete the block character count corresponding to the last 'ok'
                        self.gcode_count += 1               # update g-code counter
                        del self.serial_buffer_count[0]     # Delete the block character count corresponding to the last 'ok'
                    otds = out_temp.decode('ascii').strip()
                    if len(otds):
                        if otds != "ok":
                            err = re.search("error:[1-9][0-9]?",otds)
                            if err and int(err.group()[6:]) in gc_errors.keys():
                                otds += " (" + gc_errors[int(err.group()[6:])] + ")"
                            print(otds)

    def status(self, delay):
        """
        write status request to grbl device and get response
        """
        print("Status report every", delay, "seconds")
        while not Grblbuffer.GRBLHUD_EXIT:
            if not Grblbuffer.STATUS_PAUZE:
                with Grblbuffer.serialio_lock:
                    # write direct command '?'
                    self.serial.write("?".encode())
                # read result
                self.grbl_count_io()
            sleep(delay)
        print("Status report exit")

    def buffer_not_empty(self):
        """
       	check if gcode buffer has elements
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

#END class Grblbuffer

def count_321():
    """
    Countdown
    """
    sleep(2)
    print("(press <enter> to abort)")
    try:
        stop = inputimeout(prompt = "run starts in 3 seconds ...",timeout=1)
    except TimeoutOccurred:
        stop = 'run'
        try:
            stop = inputimeout(prompt="\033[Arun starts in 2 seconds .. \r",timeout=1)
        except TimeoutOccurred:
            stop = 'run'
            try:
                stop = inputimeout(prompt="\033[Arun starts in 1 second  .  \r", timeout=1)
            except TimeoutOccurred:
                stop = 'run'

    if stop != 'run':
        print("\033[AAborted!                           ")
        return False

    print("\033[ARUN                                ")
    return True

def is_int(i):
    """
    Check if string is int
    """
    try:
        int(i)
    except ValueError:
        return False

    return True

def wait_on_line(ser):
    """
    Wait until '\n' 2 x
    """
    resp = ser.read_until().strip().decode('ascii')             # read until '\n'
    alrm = re.search("ALARM:[1-9][0-9]?",resp)
    if alrm and int(alrm.group()[6:]) in gc_alarm.keys():
        resp += " (" + gc_alarm[int(alrm.group()[6:])] + ")\n"
    resp_1 = ser.read_until().strip().decode('ascii')           # read until '\n'
    alrm = re.search("ALARM:[1-9][0-9]?",resp_1)
    if alrm and int(alrm.group()[6:]) in gc_alarm.keys():
        resp_1 += " (" + gc_alarm[int(alrm.group()[6:])] + ")"
    return resp + resp_1

def wait_for_it(ser):
    """
    Wait for grbl response (if any)
    """
    print(wait_on_line(ser), flush = True)

    # fallback if response is delayed
    # (note the read timeout set in machine_open())
    while ser.in_waiting:
        print(wait_on_line(ser), flush = True)

def machine_init(ser):
    """
    Wakeup, report its wakeup message (if any)
    """
    # Wake up grbl
    print ("Initializing grbl...")
    ser.write("\r\n\r\n".encode())

    # Wait for grbl to initialize and print startup text (if any)
    wait_for_it(ser)

    # flush input (stray 'ok's may ruin strict block counting)
    ser.reset_input_buffer()

def machine_open(device):
    """
    Open serial (grbl) device
    """
    ser = None
    while True:
        # try open serial device (grlb)
        try:
            ser = serial.Serial(port = device, baudrate = 115200, timeout = .5)
            print("Opened serial port", device, "at 115200 bauds (bits/s)")
            break
        except serial.SerialException:
            print("Cannot open serial port", device)
            print("Found the following serial usb device candidates:")
            filenames = next(os.walk("/dev"))[2]
            # get known serial device names (linux(es), macos, macold):
            # on iMac (2009): 				/dev/cu.wchusbserial410 	115200
            # on Mac mini (first Intel): 		/dev/cu.Repleo-CH341-0000105D 	115200
            # on linux (arm) (Manjaro linux kernel 6+): /dev/ttyUSB0			115200)

            known_serial_devices = ['/dev/' + item for item in filenames if re.match(".*(serial|usb|ch34)",item, re.IGNORECASE)]
            for dev in known_serial_devices:
                print("\t" + dev)
            device = input("Enter device name: ")
            if device:
                continue
            sys.exit()
    return ser

def machine_close(ser):
    """
    Close serial (grbl) device
    """
    ser.close()

def create_parser():
    """
    grblhud argument(s) parser
    """
    parser = argparse.ArgumentParser(
        description="Stream g-code using grbl's serial read buffer.")

    parser.add_argument('--serialdevice', default="/dev/ttyUSB0",
        metavar='/dev/<serial-tty-name>',
        help='serial device on linux (default: /dev/ttyUSB0 115200 baud)')

    parser.add_argument(
        '--status', '-s', type=argparse.FileType('w'), default=None,
        metavar='/dev/<terminal-tty-name>',
        help="grbl status output (default: no output)")

    return parser

def main():
    """
    grblhud main
    """
    # command history handling
    histfile = os.path.join(os.path.expanduser("~"), ".python_grblHUD_history")
    try:
        readline.read_history_file(histfile)
        # default history len is -1 (infinite), which may grow unruly
        readline.set_history_length(1000)
    except FileNotFoundError:
        pass

    atexit.register(readline.write_history_file, histfile)

    # get commandline arguments
    args = create_parser().parse_args()

    # buffered gcode file info ('load' and 'run' command)
    gcodeFile = { "name" : "", "bBox" : "", "buffer" : [], "WHILE" : {} }

    # init serial device
    ser = machine_open(args.serialdevice)
    # init device
    machine_init(ser)

    # terminal for status output (or None)
    terminal = args.status

    # create instance of Input class
    grblinput = lineinput.Input()

    # instantiate and run buffer thread (serial io to/from grbl device)
    grblbuffer = Grblbuffer(ser, grblinput, terminal)
    grblbuffer.start()

    while True:

        try:
            line = grblinput.line_input(grblbuffer.format_machinestatus() + " grbl> ")

            if len(line) == 1 and ord(line) == 4:
                with Grblbuffer.serialio_lock:
                    # <Ctrl><D>
                    Grblbuffer.STATUS_PAUZE = True

                    # flush input/output
                    ser.reset_input_buffer()
                    ser.reset_output_buffer()

                    print("FULL STOP")
                    grblbuffer.serial.write(b'\x84')

                    # get response
                    # Wait for grbl to initialize and print startup text (if any)
                    wait_for_it(ser)

                    # flush input/output
                    ser.reset_input_buffer()
                    ser.reset_output_buffer()
                    grblbuffer.init_buffer()

                    Grblbuffer.STATUS_PAUZE = False
                continue

            if line == 'exit':
                print("Wait for program exit ....")
                Grblbuffer.GRBLHUD_EXIT = True
                grblbuffer.grblstatus.join()
		# put something to get run loop out of waiting
                grblbuffer.put(";")
                grblbuffer.join()
                break

            if line.find("help") >= 0:
                print("Type one of the following commands:")
                print("   (<Ctrl><D>)   FULL STOP                           (continue: (soft)reset)")
                print()
                print(" - cls                                               (clear screen)")
                print(" - load <filename>                                   (load file to buffer)")
                print(" - run [LOOP] <(file/loop)name> [F<eed>] [S<peed>]   (run from buffer)")
                print(" - S+10, S+1, S-10, S-1                              (Speed up/down 10% 1%)")
                print(" - F+10, F+1, F-10, F-1                              (Feed up/down 10% 1%)")
                print(" - softreset                                         (Issue soft reset command)")
                print(" - hardreset                                         (Hard reset: close/open serial port)")
                print(" - sleep                                             ($SLP command)")
                print(" - dryrun                                            ($C check mode)")
                print(" - Stoggle                                           (S toggle, in 'Hold' state only)")
                print(" - setting [<nr>]                                    (get setting for specific <nr>)")
                print(" - grbl/gcode (direct) command:")
                print("     -- '!' feed hold, ")
                print("     -- '~' start/resume, ")
                print("     -- '?' status, ")
                print("     -- 'ctrl-x' or 'command + x' soft reset!")
                continue

            if line.find("cls") >= 0:
                os.system('cls' if os.name == 'nt' else 'clear')
                continue
            if line.find("setting") >= 0:
                set_nr = re.search("[0-9]+",line)
                if set_nr:
                    set_nr = set_nr.group()
                    if int(set_nr) in gc_settings.keys():
                        print("$" + set_nr + ": " + gc_settings[int(set_nr)])
                    else:
                        print("unknown setting: $" + set_nr)
                else:
                    for k in gc_settings.keys():
                        print("$" + str(k) + ": " + gc_settings[k])
                continue
            if line.find("softreset") >= 0:
                # direct command: soft reset
                with Grblbuffer.serialio_lock:
                    sr = input("Issue a soft reset (yes/no)? ")
                    if sr.find("yes") >= 0:
                        Grblbuffer.STATUS_PAUZE = True

                        # flush input/output
                        ser.reset_input_buffer()
                        ser.reset_output_buffer()

                        # send softreset to device
                        ser.write(b'\x18')

                        # get response
                        wait_for_it(ser)

                        # flush input/output (stray 'ok's may ruin strict block counting)
                        ser.reset_input_buffer()
                        ser.reset_output_buffer()
                        grblbuffer.init_buffer()

                        Grblbuffer.STATUS_PAUZE = False
                continue

            if line.find("hardreset") >= 0:
                # hard reset
                with Grblbuffer.serialio_lock:
                    sr = input("Issue a hard reset (yes/no)? ")
                if sr.find("yes") >= 0:

                    # close grblstatus loop and Grblbuffer
                    Grblbuffer.GRBLHUD_EXIT = True
                    grblbuffer.grblstatus.join()
		    # put someting to get run loop out of waiting
                    grblbuffer.put(";")
                    grblbuffer.join()

                    # close serial port (and device)
                    machine_close(grblbuffer.serial)
                    sleep(.5)

                    # open serial port (and device)
                    ser = machine_open(args.serialdevice)
                    machine_init(ser)

                    # enable run
                    Grblbuffer.GRBLHUD_EXIT = False
                    # instantiate and run buffer thread (serial io to/from grbl device)
                    with Grblbuffer.serialio_lock:
                        grblbuffer = Grblbuffer(ser, grblinput, terminal)
                        sleep(1)
                    grblbuffer.start()

                continue

            if line == "Stoggle":
                with Grblbuffer.serialio_lock:
                    Grblbuffer.STATUS_PAUZE = True
                    # check machine state
                    if grblbuffer.machinestatus["state"] != "Hold":
                        print("machinestate must be 'Hold' to toggle Spindle")
                    else:
                        print("Spindle On/Off ")
                        grblbuffer.serial.write(b'\x9E') # 0x9E:ToggleSpindleStop

                        # get response
                        wait_for_it(ser)
                    Grblbuffer.STATUS_PAUZE = False
                continue

            if line == "sleep":
                if grblbuffer.machinestatus["state"] != "Idle":
                    print("machinestate must be 'Idle' to be able to sleep")
                else:
                    with Grblbuffer.serialio_lock:
                        print("Sleep 'zzzzz' ")
                        grblbuffer.serial.write("$SLP\n".encode())     # $SLP: zzzz
                continue

            if line == "dryrun":
                with Grblbuffer.serialio_lock:
                    if grblbuffer.machinestatus["state"] != "Check":
                        print("Commands run Dry Run mode now (issue command again to toggle)")
                    else:
                        print("Commands run for REAL now (issue command again to taggle)")
                    grblbuffer.serial.write("$C\n".encode())       # $C: G-Code Check mode
                continue

            if re.search("^load +[^<>:;,*|\"]+$", line):
                # load file: 'load <filename>'
                if grblbuffer.machinestatus["state"] != "Idle":
                    print("machinestate must be 'Idle' to load a file")
                    continue
                filePath = line[line.find(' ') + 1:]
                try:
                    with open(filePath, "r") as f:
                        gcodeFile = { "name" : "", "bBox" : "", "buffer" : [], "WHILE" : {} }
                        gcodeFile["name"] = os.path.basename(filePath)
                        # do not do that gcodeFile["buffer"].append('; ' + gcodeFile["name"])
                        print("Loading file", gcodeFile["name"], "into memory buffer ...\n")
                        #for line in f:
                        for i, line in enumerate(f):
                            print("[" + str(i) + "]\t", line, end = '')
                            # get bbox if any
                            # find line like: '; Boundingbox: (X7.231380,Y8.677330) to (X78.658588,Y24.579710)'
                            if line.find("Boundingbox") >= 0:
                                gcodeFile["bBox"] = line[line.find("Boundingbox"):].strip()

                            #    #100 = 1
                            #    WHILE [#100 LE 5] DO1
                            #    (Some G-Code Blocks Go Here to Be Repeated Each Loop)
                            #    #100 = #100 + 1 (Increase #100 by 1 each iteration of the loop)
                            #    END1

                            # Simulate gcode WHILE DO instructions (above) like this:
                            #    ; WHILE <count> <loopname>' example: '; WHILE 23 aloop123'
                            #    (Some G-Code Blocks Go Here to Be Repeated Each Loop)
                            #    ; DO <loopname>' example: '; DO aloop123'
                            #
                            # Note that this is an annotation (quoted out so the grbl controller does not see it)
                            # Note also that loopnames are all lowercase! And have a number (if any) at the end:
                            # in regex '[a-z]+[0-9]*'

                            # get while loop info
                            if line.find("; WHILE") >= 0:
                                # WHILE format: '; WHILE <int> <loopname>' example: '; WHILE 23 Aloop123'
                                # save buffer start index for this while (should be a loop name)
                                while_loopname = line[re.search(" [a-z]+[0-9]*",line).start() + 1:].strip()
                                while_count = int(line[re.search(" [0-9]+",line).start() + 1:re.search(" [0-9]+",line).end()])
                                gcodeFile["WHILE"][while_loopname] = {"pcstart" : i+1, "pcend" : 0, "count" : while_count }
                            elif line.find("; DO") >= 0:
                                # do format: '; DO <loopname>' example: '; DO Aloop123'
                                do_loopname = line[re.search(" [a-z]+[0-9]*",line).start() + 1:].strip()
                                # find corresponding 'WHILE DO' save buffer 'end' index for this
                                if do_loopname in gcodeFile["WHILE"]:
                                    gcodeFile["WHILE"][do_loopname]["pcend"] = i-1
                                    # check loop overlap
                                    overlap = False
                                    for loop in gcodeFile['WHILE']:
                                        if gcodeFile['WHILE'][loop]['pcend'] == 0 and \
                                           gcodeFile['WHILE'][loop]['pcstart'] > gcodeFile["WHILE"][do_loopname]["pcstart"]:
                                            print("WHILE loops '" + loop + "' and '" + do_loopname + "' overlap!, abort load.")
                                            # clear buffer/loop info
                                            gcodeFile = { "name" : "", "bBox" : "", "buffer" : [], "WHILE" : {} }
                                            overlap = True
                                    if overlap:
                                        break
                                else:
                                    print("WHILE info isn't consistent: cannot find WHILE label '" + do_loopname + "'!, abort load." )
                                    # clear buffer/loop info
                                    gcodeFile = { "name" : "", "bBox" : "", "buffer" : [], "WHILE" : {} }
                                    break

                            gcodeFile["buffer"].append(line)

                        # give load summary
                        if len(gcodeFile["buffer"]) > 0:
                            print("\nFile loaded", len(gcodeFile["buffer"]) - 1, "lines", gcodeFile["bBox"])
                        if gcodeFile["WHILE"]:
                            print("Detected the following loop(s):")
                            for loop in gcodeFile['WHILE']:
                                # {'pcstart': 13, 'pcend': 16, 'count': 2}
                                print("    " + loop + ": ", gcodeFile['WHILE'][loop]['count'], " X [", gcodeFile['WHILE'][loop]['pcstart'],
                                      "]-[", gcodeFile['WHILE'][loop]['pcend'], "]", sep = '')
                            print("    (Note that loops can be run separately using 'run LOOP <loopname> [F<feed>] [S<speed>]')\n")

                except OSError:
                    print("could not open file:", filePath)
                continue

            if re.search("^run +[^<>:;,*|\"]+$", line):
                # run file: 'run [LOOP] <(file)name> [F<eed>] [S<peed>]'
                if grblbuffer.machinestatus["state"] != "Idle":
                    print("machinestate must be 'Idle' to run a file")
                    continue

                FS_update = ''
                feed = None
                speed = None
                # find Speed and/or Feed parameters
                if re.search(" [FS][0-9]+",line):

                    feed = re.search(" F[0-9]+",line)
                    speed = re.search(" S[0-9]+",line)

                    if feed:
                        feed = feed.group()[1:]
                        FS_update = feed
                        # remove F<nr> from line
                        line = re.sub(" F[0-9]+", "", line)
                    if speed:
                        speed = speed.group()[1:]
                        FS_update = speed if FS_update == '' else FS_update + " " + speed
                        # remove S<nr> from line
                        line = re.sub(" S[0-9]+", "", line)

                if line.find(" LOOP ") >= 0:
                    # run loop
                    loopname = re.search(" [a-z]+[0-9]*",line)
                    if not loopname:
                        print("No loopname given!")
                        continue

                    loopname = line[re.search(" [a-z]+[0-9]*",line).start() + 1:].strip()

                    if loopname in gcodeFile["WHILE"]:
                        with Grblbuffer.serialio_lock:
                            count = gcodeFile["WHILE"][loopname]["count"]
                            setcount = input("Loop how many times? (default = " + str(gcodeFile["WHILE"][loopname]["count"]) + ")? ")
                            if setcount != '':
                                if is_int(setcount):
                                    count = int(setcount)
                                else:
                                    print("Entered invalid loop count:", setcount)
                                    continue

                            if count <= 0:
                                print("Invalid loop count must be > 0:", count)
                                continue

                            print("Run loop '" + loopname + "'", count, "X,", FS_update + ",", gcodeFile["bBox"])
                            if not count_321():
                                # abort
                                continue

                            if FS_update:
                                # make sure F and S are set correctly (before loop start)
                                grblbuffer.put("M4 " + FS_update)
                                print("<  >\t", "M4 " + FS_update)
                            # unroll loop(s);
                            for loopcount in range(int(count)):
                                grblbuffer.put("; " + loopname + " iterate nr: " + str(loopcount + 1))
                                print("<  >\t", "; " + loopname + " iterate nr: " + str(loopcount + 1))
                                for li in range(gcodeFile["WHILE"][loopname]["pcstart"], gcodeFile["WHILE"][loopname]["pcend"] + 1):
                                    gcline = gcodeFile["buffer"][li]
                                    if feed:
                                        # replace F<nr> in this line of code (if any)
                                        gcline = re.sub("F[0-9]+", feed, gcline)
                                    if speed:
                                        # replace S<nr> in this line of code (if any)
                                        gcline = re.sub("S[0-9]+", speed, gcline)

                                    grblbuffer.put(gcline)
                                    print("<" + str(li) + ">\t", gcline, end = '')
                    else:
                        print("cannot find loop with label '" + loopname + "'")
                    continue

                filePath = line[line.find(' ') + 1:]
                fileName = os.path.basename(filePath)
                if fileName == gcodeFile["name"]:
                    with Grblbuffer.serialio_lock:
                        print("Run", fileName, FS_update, gcodeFile["bBox"])
                        if not count_321():
                            # abort
                            continue

                        # unroll loop(s);
                        # get while loop info
                        for i, line in enumerate(gcodeFile["buffer"]):
                            # put gcode block, substitute set 'speed' and 'feed'
                            if feed:
                                # replace F<nr> in this line of code (if any)
                                line = re.sub("F[0-9]+", feed, line)

                            if speed:
                                # replace S<nr> in this line of code (if any)
                                line = re.sub("S[0-9]+", speed, line)

                            grblbuffer.put(line)
                            print("<" + str(i) + ">\t", line, end = '')

                            #find DO's get information from label and repeat code
                            if line.find("; DO") >= 0:
                                # do format: '; DO <loopname>' example: '; DO Aloop123'
                                do_loopname = line[re.search(" [a-z]+[0-9]*",line).start() + 1:].strip()
                                # find corresponding 'WHILE' and get loop start and end address
                                if do_loopname in gcodeFile["WHILE"]:
                                    for loopcount in range(gcodeFile["WHILE"][do_loopname]["count"]):
                                        grblbuffer.put("; " + do_loopname + " iterate nr: " + str(loopcount + 1))
                                        print("[" + str(i) + "]\t", "; " + do_loopname + " iterate nr: " + str(loopcount + 1))
                                        for li in range(gcodeFile["WHILE"][do_loopname]["pcstart"], gcodeFile["WHILE"][do_loopname]["pcend"] + 1):
                                            gcline = gcodeFile["buffer"][li]

                                            if feed:
                                                # replace F<nr> in this line of code (if any)
                                                gcline = re.sub("F[0-9]+", feed, gcline)

                                            if speed:
                                                # replace S<nr> in this line of code (if any)
                                                gcline = re.sub("S[0-9]+", speed, gcline)

                                            grblbuffer.put(gcline)
                                            print("<" + str(li) + ">\t", gcline, end = '')
                                else:
                                    print("WHILE info isn't consistent: cannot find WHILE label '" + do_loopname + "', Abort run!")
                                    break
                    continue

                print("Run error: memory buffer contains ", end='')
                if gcodeFile["name"] == '':
                    print("no file")
                else: print("file", gcodeFile["name"])
                continue

            # direct commands
            if line == "!":
                with Grblbuffer.serialio_lock:
                    # write direct command '!' 'feed hold'
                    grblbuffer.serial.write("!".encode())
                    sleep(0.02)
                continue
            if line == "~":
                with Grblbuffer.serialio_lock:
                    # write direct command '~' 'resume'
                    grblbuffer.serial.write("~".encode())
                    sleep(0.02)
                continue

            # set 'realitime' Speed up down 'S+10', 'S+1', 'S-10', 'S-1' command
            if re.search("^S[\+\-](10|1)?",line):
                # Spindle speed override

                # isolate writing and response sequence
                with Grblbuffer.serialio_lock:
                    if '+' in line:
                        if '10' in line:
                            # Increase10%
                            grblbuffer.serial.write(b'\x9A')
                        elif '1' in line:
                            # Increase1%
                            grblbuffer.serial.write(b'\x9C')
                        else:
                            # Set100%
                            grblbuffer.serial.write(b'\x99')
                    else:
                        # '-' in line
                        if '10' in line:
                            # Decrease10%
                            grblbuffer.serial.write(b'\x9B')
                        elif '1' in line:
                            # Decrease1%
                            grblbuffer.serial.write(b'\x9D')
                        else:
                            # Set100%
                            grblbuffer.serial.write(b'\x99')
                    sleep(0.02)
                continue


            # set 'realitime' Feed up down 'F+10', 'F+1', 'F-10', 'F-1' command
            if re.search("^F[\+\-](10|1)?",line):
                # Feed override command binary code

                # isolate writing and response sequence
                with Grblbuffer.serialio_lock:
                    if '+' in line:
                        if '10' in line:
                            # Increase10%
                            grblbuffer.serial.write(b'\x91')
                        elif '1' in line:
                            # Increase1%
                            grblbuffer.serial.write(b'\x93')
                        else:
                            # Set100%
                            grblbuffer.serial.write(b'\x90')
                    else:
                        # '-' in line
                        if '10' in line:
                            # Decrease10%
                            grblbuffer.serial.write(b'\x92')
                        elif '1' in line:
                            # Decrease1%
                            grblbuffer.serial.write(b'\x94')
                        else:
                            # Set100%
                            grblbuffer.serial.write(b'\x90')
                    sleep(0.02)
                continue

            # pauze status report
            Grblbuffer.STATUS_PAUZE = True

            # Need some sleep to get the command result.
            # Note that this command might be delayed
            # because other commands are pending (queued
            # in the serial buffer). In that case the
            # result displayed does not correspond to
            # the command issued here! I.e. it belongs
            # to a command issued earlier.
            grblbuffer.put(line, prepend = True)
            # get result (ok) when possible
            grblbuffer.put('', prepend = True)

            # resume status report
            Grblbuffer.STATUS_PAUZE = False

        except EOFError:
            break

    print("Exit program")

    # close serial port, status terminal
    machine_close(grblbuffer.serial)
    if terminal:
        terminal.close()

#
#
# RUN

if __name__ == '__main__':
    main()
