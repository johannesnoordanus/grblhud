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
import lineinput

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

    def __init__(self, serial, grblinput, status_out = None):
        threading.Thread.__init__(self)
        self.serial = serial
        self.status_out = status_out

        self.grblinput = grblinput

        # device buffer count
        self.gcode_count = 0
        self.line_count = 0
        self.serial_buffer_count = []

        # initial buffer state: empty
        self.gcode_buffer = []

        self.machinestatus = { "state" : "", "X" : 0.0, "Y" : 0.0, "Z" : 0.0, "Feed" : 0, "Speed" : 0 }

        # create and start query process
        self.grblstatus = threading.Thread(target=self.status, args=(.5,))
        self.grblstatus.start()

    def update_machinestatus(self, status):
        """
        set machinestatus info from grbl status (result of grbl '?' command)
        """
        if status != '':
            # Sample status report:
            #   <Idle|MPos:0.000,0.000,-10.000|FS:0,0>
            # Note that this format should be part of the grbl specification (check!)
            self.machinestatus = {}
            self.machinestatus["state"] = status[re.search("^<[a-zA-Z]+",status).start()+1:re.search("^<[a-zA-Z]+",status).end()]

            mpos = status[re.search("MPos:[+\-]?[0-9.,+\-]+\|",status).start():re.search("MPos:[+\-]?[0-9.,+\-]+\|",status).end()]
            self.machinestatus["X"] = float(mpos[re.search("[+-]?[0-9.+\-]+", mpos).start(): re.search("[+-]?[0-9.+\-]+", mpos).end()])
            self.machinestatus["Y"] = float(mpos[re.search(",[+-]?[0-9.+\-]+", mpos).start()+1: re.search(",[+-]?[0-9.+\-]+", mpos).end()])
            self.machinestatus["Z"] = float(mpos[re.search(",[+-]?[0-9.+\-]+\|", mpos).start()+1: re.search(",[+-]?[0-9.+\-]+\|", mpos).end()-1])

            fs = status[re.search("FS:[0-9,]+",status).start():re.search("FS:[0-9,]+",status).end()]
            self.machinestatus["Feed"] = fs[3: re.search("[0-9]+", fs).end()]
            self.machinestatus["Speed"] = fs[re.search(",[0-9]+", fs).start()+1: re.search(",[0-9]+", fs).end()]

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

    def status(self, delay):
        """
        write status request to grbl device and get response
        """
        print("Status report every", delay, "seconds")
        while not Grblbuffer.GRBLHUD_EXIT:
            with Grblbuffer.serialio_lock:
                # write direct command '?'
                self.serial.write("?".encode())
                #read result
                while not Grblbuffer.GRBLHUD_EXIT and self.serial.in_waiting:
                    out_temp = self.serial.read_until().strip() # Wait for grbl response
                    if out_temp.find(b"ok") < 0 and out_temp.find(b"error") < 0 :
                        if re.search("^<.+>$", out_temp.decode('ascii')):
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

                            prompt_length = len(self.format_machinestatus() + " grbl> ")
                            self.grblinput.display_line(color + self.format_machinestatus() + Grblbuffer.EndCol + " grbl> ", prompt_length)
                            if self.status_out:
                                print("\r" + lineinput.Input.ERASE_TO_EOL + out_temp.decode('ascii').strip(), file=self.status_out, end = '')
                        #else:
                            #print(out_temp.decode('ascii').strip())
                    else :
                        self.gcode_count += 1 # Iterate g-code counter
                        del self.serial_buffer_count[0] # Delete the block character count corresponding to the last 'ok'
                        print(out_temp.decode('ascii').strip())
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

        verbose = False

        with Grblbuffer.serialio_lock:

            if line != '':
                self.line_count += 1 # Iterate line counter
                l_block = line.strip()
                self.serial_buffer_count.append(len(l_block)+1) # Track number of characters in grbl serial read buffer

            grbl_out = ''

            while not Grblbuffer.GRBLHUD_EXIT and ((sum(self.serial_buffer_count) >= Grblbuffer.RX_BUFFER_SIZE-1) or self.serial.in_waiting):
                out_temp = self.serial.read_until().strip() # Wait for grbl response
                if out_temp.find(b"ok") < 0 and out_temp.find(b"error") < 0 :
                    if re.search("^<.+>$", out_temp.decode('ascii')):
                        self.update_machinestatus(out_temp.decode('ascii'))
                        if self.status_out:
                            print("\r" + lineinput.Input.ERASE_TO_EOL + out_temp.decode('ascii').strip(), file=self.status_out, end = '')
                    else:
                        print(out_temp.decode('ascii').strip())
                else :
                    grbl_out += str(out_temp)
                    self.gcode_count += 1 # Iterate g-code counter
                    grbl_out += str(self.gcode_count) # Add line finished indicator
                    del self.serial_buffer_count[0] # Delete the block character count corresponding to the last 'ok'
                    print(out_temp.decode('ascii').strip())

            if line != '':
                if verbose: print("SND: " + str(self.line_count) + " : " + l_block)
                # check for special characters not needing a nl
                l_blockn = l_block + '\n'
                self.serial.write(l_blockn.encode()) # Send g-code block to grbl
                if verbose: print("BUF:",str(sum(self.serial_buffer_count)),"REC:",grbl_out)

#END class Grblbuffer

def is_int(i):
    """
    check if string is int
    """
    try:
        int(i)
    except ValueError:
        return False

    return True

def machine_init(ser):
    """
    Wakeup, report its wakeup message (if any)
    """
    # Wake up grbl
    print ("Initializing grbl...")
    ser.write("\r\n\r\n".encode())

    # Wait for grbl to initialize and print startup text (if any)
    print(ser.read_until().strip().decode('ascii'), flush = True)
    print(ser.read_until().strip().decode('ascii'), flush = True)

    # fallback if response is delayed
    # (note the 2 second read timieout)
    while ser.in_waiting:
        print(ser.read_until().strip().decode('ascii'), flush = True) # read until '\n'
        print(ser.read_until().strip().decode('ascii'), flush = True) #

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
            ser = serial.Serial(port = device, baudrate = 115200, timeout = 2)
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
            if device: continue
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
    #grblbuffer.daemon = True
    grblbuffer.start()

    while True:

        try:
            #line = input('[' + str(grblbuffer.machinestatus) + "] grbl> ")
            #line = input(grblbuffer.format_machinestatus() + " grbl> ")
            line = grblinput.line_input(grblbuffer.format_machinestatus() + " grbl> ")
            #line = input(grblbuffer.format_machinestatus() + " grbl> ")

            if len(line) == 1 and ord(line) == 4:
                with Grblbuffer.serialio_lock:
                    # <Ctrl><D>
                    print("FULL STOP")
                    grblbuffer.serial.write(b'\x84')

                    # get response
                    print(ser.read_until().strip().decode('ascii'), flush = True) # read until '\n'
                    print(ser.read_until().strip().decode('ascii'), flush = True)

                    # Wait for grbl to initialize and print startup text (if any)
                    while ser.in_waiting:
                        print(ser.read_until().strip().decode('ascii'), flush = True) # read until '\n'
                        print(ser.read_until().strip().decode('ascii'), flush = True) #
                continue

            if line == 'exit':
                print("Wait for program exit ....")
                Grblbuffer.GRBLHUD_EXIT = True
                grblbuffer.grblstatus.join()
		# put someting to get run loop out of waiting
                grblbuffer.put(";")
                grblbuffer.join()
                break

            if line.find("help") >= 0:
                print("Type one of the following commands:")
                print("   (<Ctrl><D>)   FULL STOP                           (continue: (soft)reset)")
                print()
                print(" - load <filename>                                   (load file to buffer)")
                print(" - run [LOOP] <(file/loop)name> [F<eed>] [S<peed>]   (run from buffer)")
                print(" - S+10, S+1, S-10, S-1                              (Speed up/down 10% 1%)")
                print(" - F+10, F+1, F-10, F-1                              (Feed up/down 10% 1%")
                print(" - softreset                                         (Issue soft reset command to device")
                print(" - hardreset                                         (Hard reset: close/open serial port)")
                print(" - SToggle                                           (Spindle Toggle)")
                print(" - grbl/gcode (direct) command:")
                print("     -- '!' feed hold, ")
                print("     -- '~' start/resume, ")
                print("     -- '?' status, ")
                print("     -- 'ctrl-x' or 'command + x' soft reset!")
                continue

            if line.find("softreset") >= 0:
                # direct command: soft reset
                with Grblbuffer.serialio_lock:
                    sr = input("Issue a soft reset (yes/no)? ")
                    if sr.find("yes") >= 0:

                        # send softreset to device
                        ser.write(b'\x18')

                        # get response
                        print(ser.read_until().strip().decode('ascii'), flush = True) # read until '\n'
                        print(ser.read_until().strip().decode('ascii'), flush = True)

                        # Wait for grbl to initialize and print startup text (if any)
                        while ser.in_waiting:
                            print(ser.read_until().strip().decode('ascii'), flush = True) # read until '\n'
                            print(ser.read_until().strip().decode('ascii'), flush = True) #

                        # flush input (stray 'ok's may ruin strict block counting)
                        ser.reset_input_buffer()
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

            if line == "SToggle":
                with Grblbuffer.serialio_lock:
                    # <Ctrl><D>
                    print("Spindle on/off ")
                    grblbuffer.serial.write(b'\x9E') # 0x9E:ToggleSpindleStop

                    # get response
                    print(ser.read_until().strip().decode('ascii'), flush = True) # read until '\n'
                    print(ser.read_until().strip().decode('ascii'), flush = True)

                    # Wait for grbl to initialize and print startup text (if any)
                    while ser.in_waiting:
                        print(ser.read_until().strip().decode('ascii'), flush = True) # read until '\n'
                        print(ser.read_until().strip().decode('ascii'), flush = True) #
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
                                    if overlap: break
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
                                print("    " + loop + ": ", gcodeFile['WHILE'][loop]['count'], "X [", gcodeFile['WHILE'][loop]['pcstart'],
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
                        FS_update = "Feed set to " + feed
                        # remove F<nr> from line
                        line = re.sub(" F[0-9]+", "", line)
                    if speed:
                        speed = speed.group()[1:]
                        FS_update = "Speed set to " + speed if FS_update == '' else  "Feed set to " + feed + ", Speed set to " + speed
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

                            print("Run loop", loopname, count, "times", FS_update, gcodeFile["bBox"])
                            yesorno = input("Are you sure (checked bbox, Feed, Spindle rate and set M3/M4)? (yes/no) ")
                            if "yes" in yesorno:
                                print("run starts in 3 seconds .", end = '', flush = True)
                                sleep(1)
                                print("\rrun starts in 2 seconds ..", end = '', flush = True)
                                sleep(1)
                                print("\rrun starts in 1 seconds ...", end = '', flush = True)
                                sleep(1)
                                print(" run")

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
                        yesorno = input("Are you sure (checked bbox)? (yes/no) ")
                        if "yes" in yesorno:
                            print("run starts in 3 seconds .", end = '', flush = True)
                            sleep(1)
                            print("\rrun starts in 2 seconds ..", end = '', flush = True)
                            sleep(1)
                            print("\rrun starts in 1 seconds ...", end = '', flush = True)
                            sleep(1)
                            print(" run")

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

            # Need some sleep to get the command result.
            # Note that this command might be delayed
            # because other commands are pending (queued
            # in the serial buffer). In that case the
            # result displayed does not correspond to
            # the command issued here! I.e. it belongs
            # to a command issued earlier.
            grblbuffer.put(line, prepend = True)
            sleep(.1)
            # get result (ok) when possible
            grblbuffer.put('', prepend = True)
            sleep(.1)

        except EOFError:
            break

    print("Exit program")

    # close serial port, status terminal
    machine_close(grblbuffer.serial)
    if terminal: terminal.close()

#
#
# RUN

if __name__ == '__main__':
    main()
