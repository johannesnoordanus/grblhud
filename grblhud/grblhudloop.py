#!/usr/bin/env python3
"""
grblhub: a command line tool to handle grbl code.
(https://www.diymachining.com/downloads/GRBL_Settings_Pocket_Guide_Rev_B.pdf)
"""

import os
import sys
import re
from time import sleep
from argparse import Namespace
# needs pyserial!
import serial

from inputimeout import inputimeout, TimeoutOccurred
from grblhud import lineinput
from grblhud.grblbuffer import Grblbuffer
from grblhud.grblmessages import grbl_alarm
from grblhud.unblockedgetch import UnblockedGetch

GCODE2IMAGE = True
try:
    from gcode2image import gcode2image
    from PIL import Image
    import numpy as np

except ImportError:
    GCODE2IMAGE = False

SERIALDEVICE = ''
NO_OF_LINES_SHOWN = 40

gcode_pattern = "^ *(G0|G1|X|Y|M4|M3|M5|M2|S|F|;|\$|~|!|\?)"

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
    if alrm and int(alrm.group()[6:]) in grbl_alarm.keys():
        resp += " (" + grbl_alarm[int(alrm.group()[6:])] + ")\n"
    resp_1 = ser.read_until().strip().decode('ascii')           # read until '\n'
    alrm = re.search("ALARM:[1-9][0-9]?",resp_1)
    if alrm and int(alrm.group()[6:]) in grbl_alarm.keys():
        resp_1 += " (" + grbl_alarm[int(alrm.group()[6:])] + ")"
    return resp + resp_1

def wait_for_it(ser):
    """
    Wait for grbl response (if any)
    """
    resp = wait_on_line(ser)
    if resp:
        print(resp, flush = True)
    else:
        # fallback if response is delayed
        # (note the read timeout set in machine_open())
        sleep(1)
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
    global SERIALDEVICE
    ser = None
    while True:
        # try open serial device (grlb)
        try:
            ser = serial.Serial(port = device, baudrate = 115200, timeout = .5)
            print("Opened serial port", device, "at 115200 bauds (bits/s)")
            SERIALDEVICE = device
            break
        except serial.SerialException:
            print("Cannot open serial port", device)
            filenames = next(os.walk("/dev"))[2]

            # get known serial device names (linux(es), macos, macold):
            # on iMac (2009): 				/dev/cu.wchusbserial410 	115200
            # on Mac mini (first Intel): 		/dev/cu.Repleo-CH341-0000105D 	115200
            # on linux (arm) (Manjaro linux kernel 6+): /dev/ttyUSB0			115200)
            known_serial_devices = ['/dev/' + item for item in filenames if re.match(".*(serial|usb|ch34)",item, re.IGNORECASE)]

            if known_serial_devices != []:
                print("Found the following serial usb device candidates:")
                for dev in known_serial_devices:
                    print("\t" + dev)
            device = input("Enter device name: ")
            if device:
                continue
            print("no serial device name given, program abort")
            sys.exit()
    return ser

def machine_close(ser):
    """
    Close serial (grbl) device
    """
    ser.close()

def grblhudloop(args):
    """
    grblhud main loop
    """
    def hudloopbody(line) -> bool:
        nonlocal args
        nonlocal gcodeFile
        nonlocal ser
        nonlocal grblinput
        nonlocal grblbuffer

        if (len(line) == 1 and ord(line) == 4) or line == 'FSTOP':
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
            return False

        if line == 'exit':
            print("Wait for program exit ....")
            Grblbuffer.GRBLHUD_EXIT = True
            grblbuffer.grblstatus.join()
            # put something to get run loop out of waiting
            grblbuffer.put(";")
            grblbuffer.join()
            return True

        if line.find("help") >= 0:
            print("grblhud commands:")
            print("   <Ctrl><D> / FSTOP                                 (FULL MACHINE STOP (grbl1.1 state: 'Door'), issue softreset to continue)")
            print()
            print(" - OS <Unix command>                                 (run a Unix command)")
            print(" - stream <filename>                                 (stream file 'directly' to the machine (Note that WHILE loops, F and S settings are not possible)")
            print(" - load <filename>                                   (load file to buffer)")
            print(" - run [LOOP] [F<eed>] [S<pindlepeed/power>]         (run file or LOOP from buffer, and possibly set F and/or S for this run)")
            print(" - listgcode [<pcstart> [<pcend>]]                   (gcode listing, possibly set start [end] lines (for large files)")
            print(" - showgcode                                         (show image of the current gcode file (must be in the working directory))")
            print(" - setLOOP <loopname> <count> <pcstart> <pcend>      (set a WHILE LOOP)")
            print(" - S+10, S+1, S-10, S-1                              (Speed up/down 10% 1%)")
            print(" - F+10, F+1, F-10, F-1                              (Feed up/down 10% 1%)")
            print(" - softstop                                          (purge command buffer, but let machine buffer run till empty)")
            print(" - softreset                                         (issue soft reset command)")
            print(" - hardreset                                         (hard reset: close/open serial port)")
            print(" - sleep                                             ($SLP command)")
            print(" - Zprobe                                            (lower head until 'probe' contact is made)")
            print(" - origin [X<coord>][Y<coord>][Z<coord>]             (make current XYZ: [X<coord>][Y<coord>][Z<coord>] (shift work coordinates))")
            print(" - Bbox [(X<min>,Y<min>):(X<max>,Y<max>)] [F<eed>]   (draw a bounding box of the current gcode file (no argument) or a self defind box)")
            print(" - Stoggle                                           (Spindle on/off, in 'Hold' state only)")
            print()
            print("grbl commands:")
            print(" - $ (grbl help)")
            print("     $$ (view Grbl settings)")
            print("     $# (view # parameters)")
            print("     $G (view parser state)")
            print("     $I (view build info)")
            print("     $N (view startup blocks)")
            print("     $x=value (save Grbl setting)")
            print("     $Nx=line (save startup block)")
            print("     $C (check gcode mode)")
            print("     $X (kill alarm lock)")
            print("     $H (run homing cycle)")
            print("     ~ (cycle start)")
            print("     ! (feed hold)")
            print("     ? (current status)")
            print("     ctrl-x/command + x/softreset (reset Grbl)")
            print()
            return False

        if line == 'softstop':
            with Grblbuffer.serialio_lock:
                with Grblbuffer.bec:
                    print("Issued softstop (purged command buffer)")
                    # purge buffer
                    grblbuffer.init_buffer()
                # end grbl program (switch laser off)
                grblbuffer.serial.write("M2\n".encode())
            return False

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
            return False

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
                ser = machine_open(args.serial if SERIALDEVICE == '' else SERIALDEVICE)
                machine_init(ser)

                # enable run
                Grblbuffer.GRBLHUD_EXIT = False
                # instantiate and run buffer thread (serial io to/from grbl device)
                with Grblbuffer.serialio_lock:
                    grblbuffer = Grblbuffer(ser, grblinput)
                    sleep(1)
                grblbuffer.start()
            return False

        if line.find("Stoggle") >= 0 or line.find("stoggle") >= 0:
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
            return False

        if line == "sleep":
            if grblbuffer.machinestatus["state"] != "Idle":
                print("machinestate must be 'Idle' to be able to sleep")
            else:
                with Grblbuffer.serialio_lock:
                    print("Sleep 'zzzzz' ")
                    grblbuffer.serial.write("$SLP\n".encode())     # $SLP: zzzz
            return False

        if re.search("^load +[^<>:;,*|\"]+$", line):
            # load file: 'load <filename>'
            filePath = line[line.find(' ') + 1:]
            try:
                with open(filePath, "r") as f:
                    gcodeFile = { "name" : "", "bBox" : "", "buffer" : [], "WHILE" : {} }
                    gcodeFile["name"] = os.path.basename(filePath)
                    abort = False

                    with Grblbuffer.serialio_lock:
                        Grblbuffer.STATUS_PAUZE = True
                        print("Load file into memory buffer - wait for it to complete!\nPress <anykey> to abort!")
                        sr = input(f"Load file {filePath} (yes/no)? ")

                    if sr.find("yes") >= 0:
                        print("Loading file", gcodeFile["name"], "into memory buffer ...\n")
                        getch_nowait = UnblockedGetch().getch_nowait
                        # for line in f:
                        for i, line in enumerate(f):
                            try:
                                if i < NO_OF_LINES_SHOWN:
                                    print("[" + str(i) + "]\t", line, end = '')

                                if i == NO_OF_LINES_SHOWN:
                                    print("    ...\n    ...\n")

                                # check keypress every 1000 lines (to be able abort)
                                if i and i % 1000 == 0:
                                    with Grblbuffer.serialio_lock:
                                        sleep(.02)
                                        print("\033[ALoaded", i, "lines ...")
                                        if getch_nowait() != '':
                                            sr = input(f"Abort load of {filePath} (yes/no)? ")
                                            if sr.find("yes") >= 0:
                                                print(f"load of file {filePath} aborted!")
                                                abort = True
                                                break
                                            else:
                                                print("\n")

                                # get bbox if any
                                # find line like: '; Boundingbox: (X7.231380,Y8.677330) to (X78.658588,Y24.579710)'
                                if line.find("Boundingbox:") >= 0:
                                    gcodeFile["bBox"] = line[line.find("Boundingbox:") + len("Boundingbox:"):].strip()

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
                                    while_loopname = re.search(" [a-z]+[0-9]*",line)
                                    if not while_loopname:
                                        print("Missing loopname of '; WHILE' statement, abort load!")
                                        abort = True
                                        break
                                    while_loopname = while_loopname.group()[1:]
                                    while_count = re.search(" [0-9]+",line)
                                    if not while_count:
                                        print("Missing loop count of '; WHILE' statement, abort load!")
                                        abort = True
                                        break
                                    while_count = int(while_count.group()[1:])
                                    gcodeFile["WHILE"][while_loopname] = {"pcstart" : i+1, "pcend" : 0, "count" : while_count }
                                elif line.find("; DO") >= 0:
                                    # do format: '; DO <loopname>' example: '; DO Aloop123'
                                    do_loopname = re.search(" [a-z]+[0-9]*",line)
                                    if not do_loopname:
                                        print("Missing loopname of '; DO' statement, abort load!")
                                        abort = True
                                        break
                                    do_loopname = do_loopname.group()[1:]
                                    # find corresponding 'WHILE DO' save buffer 'end' index for this
                                    if do_loopname in gcodeFile["WHILE"]:
                                        gcodeFile["WHILE"][do_loopname]["pcend"] = i-1
                                        # check loop overlap
                                        for loop in gcodeFile['WHILE']:
                                            if gcodeFile['WHILE'][loop]['pcend'] == 0 and \
                                               gcodeFile['WHILE'][loop]['pcstart'] > gcodeFile["WHILE"][do_loopname]["pcstart"]:
                                                print("WHILE loops '" + loop + "' and '" + do_loopname + "' overlap!, abort load.")
                                                abort = True
                                                break
                                        if abort:
                                            break
                                    else:
                                        print("WHILE info isn't consistent: cannot find WHILE label '" + do_loopname + "'!, abort load!" )
                                        abort = True
                                        break

                                gcodeFile["buffer"].append(line)
                            except KeyboardInterrupt:
                                print(f"load of file {filePath} aborted!")
                                abort = True
                                break
                            except MemoryError:
                                print(f"Out of memory! Load of file {filePath} aborted!")
                                abort = True
                                break

                        if abort:
                            # clear buffer info
                            gcodeFile = { "name" : "", "bBox" : "", "buffer" : [], "WHILE" : {} }
                        else:
                            # give load summary
                            print("File loaded", len(gcodeFile["buffer"]) - 1, "lines, Bbox:", gcodeFile["bBox"] if gcodeFile["bBox"] else "none")
                            if gcodeFile["WHILE"]:
                                print("Detected the following loop(s):")
                                for loop in gcodeFile['WHILE']:
                                    # {'pcstart': 13, 'pcend': 16, 'count': 2}
                                    print("    " + loop + ": ", gcodeFile['WHILE'][loop]['count'], " X [", gcodeFile['WHILE'][loop]['pcstart'],
                                          "]-[", gcodeFile['WHILE'][loop]['pcend'], "]", sep = '')
                                print("    (Note that loops can be run separately using 'run LOOP <loopname> [F<feed>] [S<speed>]')\n")

                        Grblbuffer.STATUS_PAUZE = False

            except OSError:
                print("could not open file:", filePath)
            return False

        if re.search("^stream +[^<>:;,*|\"]+$", line):
            # stream file: 'stream <filename>'
            if grblbuffer.machinestatus["state"] != "Idle":
                print("machinestate must be 'Idle' to stream a file to the machine")
                return False
            filePath = line[line.find(' ') + 1:]
            try:
                with open(filePath, "r") as f:
                    abort = False

                    with Grblbuffer.serialio_lock:
                        Grblbuffer.STATUS_PAUZE = True
                        if args.gcode:
                            sr = "yes"
                        else:
                            print("Stream a file to the machine\nPress <anykey> to abort!")
                            sr = input(f"Stream file {filePath} (yes/no)? ")

                        if sr.find("yes") >= 0:
                            if not args.gcode:
                                print("streaming file to machine ...\n")
                            getch_nowait = UnblockedGetch().getch_nowait
                            # for line in f:
                            for i, line in enumerate(f):
                                try:
                                    if not args.gcode:
                                        if i < NO_OF_LINES_SHOWN:
                                            print("[" + str(i) + "]\t", line, end = '')

                                        if i == NO_OF_LINES_SHOWN:
                                            print("    ...\n    ...\n")

                                    # check keypress every 1000 lines (to be able abort)
                                    if i and i % 1000 == 0:
                                        with Grblbuffer.serialio_lock:
                                            sleep(.02)
                                            print("\033[ALoaded", i, "lines ...")
                                            if getch_nowait() != '':
                                                sr = input(f"Abort stream {filePath} (yes/no)? ")
                                                if sr.find("yes") >= 0:
                                                    print(f"Stream aborted!")
                                                    abort = True
                                                    break
                                                else:
                                                    print("\n")

                                    grblbuffer.put(line)
                                except KeyboardInterrupt:
                                    print(f"Stream {filePath} aborted!")
                                    abort = True
                                    break
                                except MemoryError:
                                    print(f"Out of memory! Stream {filePath} aborted!")
                                    abort = True
                                    break

                            if abort:
                                with Grblbuffer.bec:
                                    print("Issued softstop (purged command buffer)")
                                    # purge buffer
                                    grblbuffer.init_buffer()
                                # end grbl program (switch laser off)
                                grblbuffer.serial.write("M2\n".encode())
                            else:
                                # give stream summary
                                print("Stream send:", i, "lines, - wait for device to complete!")

                        Grblbuffer.STATUS_PAUZE = False

            except OSError:
                print("could not open file:", filePath)
            return False

        if line.find("run") >= 0:
            # run file: 'run [LOOP] [F<eed>] [S<peed>]'
            if grblbuffer.machinestatus["state"] != "Idle":
                print("Machinestate must be 'Idle' to be able to run")
                return False

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
                    print("No 'LOOP' name given; abort run!")
                    return False
                loopname = loopname.group()[1:]

                if loopname in gcodeFile["WHILE"]:
                    with Grblbuffer.serialio_lock:
                        count = gcodeFile["WHILE"][loopname]["count"]
                        setcount = input("Loop how many times? (default = " + str(gcodeFile["WHILE"][loopname]["count"]) + ")? ")
                        if setcount != '':
                            if is_int(setcount):
                                count = int(setcount)
                            else:
                                print("Entered invalid loop count:", setcount)
                                return False

                        if count <= 0:
                            print("Invalid loop count must be > 0:", count)
                            return False

                        print("Run loop '" + loopname + "'", count, "X,", FS_update + ", Bbox: ",  gcodeFile["bBox"] if gcodeFile["bBox"] else "none")
                        print("Make sure the work area is cleared and you wear glasses to be protected!")
                        if not count_321():
                            # abort
                            return False

                        if FS_update:
                            # make sure F and S are set correctly (before loop start)
                            grblbuffer.put("M4 " + FS_update)
                            print("<  >\t", "M4 " + FS_update)

                        nbr_of_lines = 0
                        # unroll loop(s);
                        for loopcount in range(int(count)):
                            grblbuffer.put("; " + loopname + " iterate nr: " + str(loopcount + 1))
                            if nbr_of_lines < NO_OF_LINES_SHOWN:
                                print("<  >\t", "; " + loopname + " iterate nr: " + str(loopcount + 1))
                                nbr_of_lines += 1
                            for li in range(gcodeFile["WHILE"][loopname]["pcstart"], gcodeFile["WHILE"][loopname]["pcend"] + 1):
                                gcline = gcodeFile["buffer"][li]
                                if feed:
                                    # replace F<nr> in this line of code (if any)
                                    gcline = re.sub("F[0-9]+", feed, gcline)
                                if speed:
                                    # replace S<nr> in this line of code (if any)
                                    gcline = re.sub("S[0-9]+", speed, gcline)

                                grblbuffer.put(gcline)
                                if nbr_of_lines < NO_OF_LINES_SHOWN:
                                    print("<" + str(li) + ">\t", gcline, end = '')
                                    nbr_of_lines += 1
                else:
                    print("Cannot find loop with label '" + loopname + "', abort run!")
                return False

            fileName = gcodeFile["name"]
            if fileName != '':
                with Grblbuffer.serialio_lock:
                    print("Run", fileName, FS_update, "Bbox: ",  gcodeFile["bBox"] if gcodeFile["bBox"] else "none")
                    print("Make sure the work area is cleared and you wear glasses to be protected!")
                    if not count_321():
                        # abort
                        return False

                    getch_nowait = UnblockedGetch().getch_nowait
                    nbr_of_lines = 0
                    abort = False
                    # unroll loop(s);
                    # get while loop info
                    for i, line in enumerate(gcodeFile["buffer"]):
                        try:

                            # put gcode block, substitute set 'speed' and 'feed'
                            if feed:
                                # replace F<nr> in this line of code (if any)
                                line = re.sub("F[0-9]+", feed, line)

                            if speed:
                                # replace S<nr> in this line of code (if any)
                                line = re.sub("S[0-9]+", speed, line)

                            grblbuffer.put(line)
                            if nbr_of_lines < NO_OF_LINES_SHOWN:
                                print("<" + str(i) + ">\t", line, end = '')
                                nbr_of_lines += 1
                            if i == NO_OF_LINES_SHOWN:
                                print("    ...\n    ...\n")
                            # check keypress every 1000 lines (to be able abort)
                            if i and i % 1000 == 0:
                                    sleep(.02)
                                    print("\033[ARun", i, "lines ...")
                                    if getch_nowait() != '':
                                        sr = input(f"Abort run of {fileName} (yes/no)? ")
                                        if sr.find("yes") >= 0:
                                            print(f"run of file {fileName} aborted!")
                                            with Grblbuffer.bec:
                                                print("Issued softstop (purged command buffer)")
                                                # purge buffer
                                                grblbuffer.init_buffer()
                                            # end grbl program (switch laser off)
                                            grblbuffer.serial.write("M2\n".encode())
                                            abort = True
                                            break
                                        else:
                                            print("\n")

                            #find DO's get information from label and repeat code
                            if line.find("; DO") >= 0:
                                # do format: '; DO <loopname>' example: '; DO Aloop123'
                                do_loopname = re.search(" [a-z]+[0-9]*",line)
                                if not do_loopname:
                                    print("No 'DO' loopname given; abort run!")
                                    abort = True
                                    break
                                do_loopname = do_loopname.group()[1:]
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
                                            if nbr_of_lines < NO_OF_LINES_SHOWN:
                                                print("<" + str(li) + ">\t", gcline, end = '')
                                                nbr_of_lines += 1
                                            if i == NO_OF_LINES_SHOWN:
                                                print("    ...\n    ...\n")
                                            # check keypress every 1000 lines (to be able abort)
                                            if i and i % 1000 == 0:
                                                    sleep(.02)
                                                    print("\033[ARun", i, "lines ...")
                                                    if getch_nowait() != '':
                                                        sr = input(f"Abort run of {fileName} (yes/no)? ")
                                                        if sr.find("yes") >= 0:
                                                            print(f"run of file {fileNAme} aborted!")
                                                            with Grblbuffer.bec:
                                                                print("Issued softstop (purged command buffer)")
                                                                # purge buffer
                                                                grblbuffer.init_buffer()
                                                            # end grbl program (switch laser off)
                                                            grblbuffer.serial.write("M2\n".encode())
                                                            abort = True
                                                            break
                                                        else:
                                                            print("\n")
                                else:
                                    print("WHILE info isn't consistent: cannot find WHILE label '" + do_loopname + "', Abort run!")
                                    break

                        except KeyboardInterrupt:
                            print(f"run of file {fileName} aborted!")
                            with Grblbuffer.bec:
                                print("Issued softstop (purged command buffer)")
                                # purge buffer
                                grblbuffer.init_buffer()
                            # end grbl program (switch laser off)
                            grblbuffer.serial.write("M2\n".encode())
                            abort = True
                            break
                        except MemoryError:
                            print(f"Out of memory! Run of file {fileName} aborted!")
                            with Grblbuffer.bec:
                                print("Issued softstop (purged command buffer)")
                                # purge buffer
                                grblbuffer.init_buffer()
                            # end grbl program (switch laser off)
                            grblbuffer.serial.write("M2\n".encode())
                            abort = True
                            break

                    if not abort:
                        # give run summary
                        print("send:", len(gcodeFile["buffer"]), "lines, - wait for device to complete!")
                return False

            print("Currently no gcode file is loaded. Use command 'load <filename>' to load a gcode file.")
            return False

        if line.find("listgcode") >= 0:
            if gcodeFile["name"] == '':
                print("Cannot list gcode file: currently no file loaded!")
                return False
            if not len(gcodeFile["buffer"]):
                print("Empty list!")
                return False

            pcstart = 0
            pcend = len(gcodeFile["buffer"]) - 1
            pcstart_pcend = re.search(" [0-9]+ +[0-9]+", line)
            if pcstart_pcend:
                pcstart_pcend = pcstart_pcend.group()

                pcstart = int(pcstart_pcend.split()[0])
                pcend = int(pcstart_pcend.split()[1])
            else:
                start = re.search(" [0-9]+", line)
                if start:
                    pcstart = int(start.group())

            with Grblbuffer.serialio_lock:
                Grblbuffer.STATUS_PAUZE = True
                sr = input(f"list [{pcstart}-{pcend}] (Press <anykey> to abort) (yes/no)? ")

                if sr.find("yes") >= 0:
                    getch_nowait = UnblockedGetch().getch_nowait
                    for i, line in enumerate(gcodeFile["buffer"]):
                        if i >= pcstart and i <= pcend:
                            print("[" + str(i) + "]\t", line, end = '')
                            # check keypress every 1000 lines (to be able abort)
                            if i and i % 1000 == 0:
                                    sleep(.02)
                                    print("\033[AListing", i, "lines ...")
                                    if getch_nowait() != '':
                                        sr = input(f"Abort gcode list (of {gcodeFile['name']} (yes/no)?")
                                        if sr.find("yes") >= 0:
                                            print(f"Listing aborted!")
                                            break
                                        else:
                                            print("\n")

                Grblbuffer.STATUS_PAUZE = False
            return False

        if line.find("setLOOP") >= 0 or line.find("setloop") > 0:
            if re.search("setLOOP +[a-z|A-Z]+[0-9]? +[0-9]+ +[0-9]+ +[0-9]+", line):
                # setLOOP <loopname> <count> <pcstart> <pcend>
                if grblbuffer.machinestatus["state"] != "Idle":
                    print("Machinestate must be 'Idle' to set a LOOP")
                    return False
                if gcodeFile["name"] == '':
                    print("Cannot set a LOOP: currently no file loaded!")
                    return False

                with Grblbuffer.serialio_lock:
                    loopname = re.search(" [a-z|A-Z]+[0-9]?", line).group()[1:]
                    count_pcstart_pcend = re.search(" [0-9]+ +[0-9]+ +[0-9]+", line).group()
                    count = int(count_pcstart_pcend.split()[0])
                    pcstart = int(count_pcstart_pcend.split()[1])
                    pcend = int(count_pcstart_pcend.split()[2])

                    if loopname in gcodeFile["WHILE"]:
                        print(f"NOTE that LOOP {loopname} with {count} iterations from line {pcstart} to line {pcend} ([{pcstart}:{pcend}]) already EXISTS!")
                    sr = input(f"Create LOOP {loopname}, {count} iterations from line {pcstart} to line {pcend} ([{pcstart}:{pcend}]) (yes/no)? ")
                    if sr.find("yes") >= 0:
                        gcodeFile["WHILE"][loopname] = {"pcstart" : pcstart, "pcend" : pcend, "count" : count }
                        print(f"LOOP created (use command 'run LOOP {loopname} [F<feed>] [S<speed>]' to run this loop)")
            else:
                print("setLOOP syntax error. Format: 'setLOOP <loopname> <count> <pcstart> <pcend>'")
            return False

        if line.find("OS") >= 0 or line.find("os") >= 0:
            with Grblbuffer.serialio_lock:
                Grblbuffer.STATUS_PAUZE = True
                #command = re.search(" +[a-z|A-Z|0-9 \-\+\.\|*]+", line)
                command = re.search(" +.*", line)
                if command:
                    print(f"execute command: '{command.group()[1:]}'")
                    rval = os.popen(command.group()[1:]).read()
                    print(rval)
                else:
                    print("No OS command found!")
                Grblbuffer.STATUS_PAUZE = False
            return False


        # G38.n Straight Probe (https://linuxcnc.org/docs/html/gcode/g-code.html)
        if line.find("Zprobe") >= 0 or line.find("zprobe") >= 0:
            # Z-axis probe command
            if "$32" in grblbuffer.machinesettings and int(grblbuffer.machinesettings["$32"]) == 1:
                print(f'Machine is in laser mode! (setting $32={grblbuffer.machinesettings["$32"]})')
                print("command aborted")
                return False
            with Grblbuffer.serialio_lock:
                Grblbuffer.STATUS_PAUZE = True
                print("Lower head until 'probe' contact is made.")
                print()
                print("Make sure a (double) wire is conected to the 'probe' contacts on the machine board and one")
                print("wire - on the other end - is connected to a metal object that is on top of the object you are")
                print("setting the origin Z0 to, while the other is connected to the router bit (or a point that is")
                print("in electric contact).")
                print("You can make a test run - using this command - to check if the machine halts when you connect the wires by hand.")
                print("After a successfull probe command, 'origin Z<metal_object_height>' can be used to make the probe point Z<metal_object_height>.")
                print()
                sr = input("Issue probe (enter <Ctrl><D> to abort) (yes/no)? ")
                if sr.find("yes") >= 0:
                    grblbuffer.serial.write("G38.2 Z-25 F24\n".encode())
                    print("\ngrbl> G38.2 Z-25 F24\n")
                else:
                    print("command aborted")
                Grblbuffer.STATUS_PAUZE = False
            return False

        # G92 Coordinate System Offset (https://linuxcnc.org/docs/html/gcode/g-code.html)
        if line.find("origin") >= 0:
            # get coordinates
            Xoffset = re.search("X[0-9]+(\.[0-9]+)?",line)
            Yoffset = re.search("Y[0-9]+(\.[0-9]+)?",line)
            Zoffset = re.search("Z[0-9]+(\.[0-9]+)?",line)
            if Xoffset:
                Xoffset = Xoffset.group()
            else:
                Xoffset = ""
            if Yoffset:
                Yoffset = Yoffset.group()
            else:
                Yoffset = ""
            if Zoffset:
                Zoffset = Zoffset.group()
            else:
                Zoffset = ""

            if not (Xoffset or Yoffset or Zoffset):
                print("At least one origin offset must be given!\nCommand aborted.")
                return False

            with Grblbuffer.serialio_lock:
                Grblbuffer.STATUS_PAUZE = True
                print("Set X<coord>Y<coord>Z<coord> to current point. (shift the Work Coordinate System)")
                print()
                print("For example: to make the top of a wood 'slab' to be CNC'd, the Z origin (Z0), a probe can be run (lowered)")
                print("that makes contact to a thin metal plate on top of it. If the plate thickness is 2.1 mm, command 'origin Z2.1'")
                print("will make the probe point Z2.1, which is 2.1 mm above the wood 'slab'. After removing the thin metal plate,")
                print("command 'G1 Z0 F24' (move to Z0 with low speed, to be carefull) will make the router bit just touch the top")
                print("of the 'slab'. Metal objects to be CNC'd can do with command 'origin Z0' (with 0 offset).")
                print()
                print("Note that status report coordinates at the start of each grblhud commandline reflect the new coordinate offset")
                print("because it uses Work Position (WPos).")
                print()
                sr = input(f"Issue command 'origin {Xoffset}{Yoffset}{Zoffset}' (yes/no)? ")
                if sr.find("yes") >= 0:
                    grblbuffer.serial.write((f"G92 {Xoffset}{Yoffset}{Zoffset}\n").encode())
                    print(f"\ngrbl> G92 {Xoffset}{Yoffset}{Zoffset}\n")
                else:
                    print("command aborted")
                Grblbuffer.STATUS_PAUZE = False
            return False

        # draw bounding box with low power laser setting
        # gcodeFile = { "name" : "", "bBox" : "", "buffer" : [], "WHILE" : {} }
        if line.find("Bbox") >= 0 or line.find("bbox") >= 0:
            if "$32" in grblbuffer.machinesettings and int(grblbuffer.machinesettings["$32"]) != 1:
                print(f'Machine is not in laser mode! (setting $32={grblbuffer.machinesettings["$32"]})')
                print("command aborted")
                return False

            with Grblbuffer.serialio_lock:
                Grblbuffer.STATUS_PAUZE = True

                fltPatt = "[\+|\-]?[0-9]+(\.[0-9]+)?"

                minX = ""
                minY = ""
                maxX = ""
                maxY = ""

                fromFile = ""

                feed = re.search(" F[0-9]+",line)
                if feed:
                    feed = feed.group()[1:]
                    # remove F<nr> from line
                    line = re.sub(" F[0-9]+", "", line)
                else:
                    feed = "F1000"

                bboxcoords = re.search(f' \(X{fltPatt},Y{fltPatt}\):\(X{fltPatt},Y{fltPatt}\)',line)
                if bboxcoords:
                    bboxcoords = bboxcoords.group()[1:]
                    minXY = re.search(f'\(X{fltPatt},Y{fltPatt}\)', bboxcoords).group()
                    minX = re.search(f'X{fltPatt}',minXY).group()[1:]
                    minY = re.search(f',Y{fltPatt}',minXY).group()[2:]

                    maxXY = re.search(f':\(X{fltPatt},Y{fltPatt}\)', bboxcoords).group()[1:]
                    maxX = re.search(f'X{fltPatt}',maxXY).group()[1:]
                    maxY = re.search(f',Y{fltPatt}',maxXY).group()[2:]
                elif len(line) > len("Bbox"):
                    print("Error in Bbox argument, format is: (X<min>,Y<min>):(X<max>,Y<max>)")
                else:
                    if gcodeFile["name"]:
                        if gcodeFile["bBox"]:
                            # bbox coordinates from the current gcode file
                            # format: '(X7.231380,Y8.677330):(X78.658588,Y24.579710)'
                            minXY = re.search(f'^\(X{fltPatt},Y{fltPatt}\)', gcodeFile["bBox"])
                            if minXY:
                                minX = re.search(f'X{fltPatt}',minXY.group()).group()[1:]
                                minY = re.search(f',Y{fltPatt}',minXY.group()).group()[2:]

                            maxXY = re.search(f':\(X{fltPatt},Y{fltPatt}\)', gcodeFile["bBox"])
                            if maxXY:
                                maxX = re.search(f'X{fltPatt}',maxXY.group()).group()[1:]
                                maxY = re.search(f',Y{fltPatt}',maxXY.group()).group()[2:]

                            fromFile = f'- from file {gcodeFile["name"]} -'
                        else:
                            print("No Bbox info found in current gcode file.")
                    else:
                        print("Currently no gcode file is loaded. Use 'load <filename>' command to load a gcode file.")

                # check bbox
                if minX and minY and maxX and maxY:
                    if float(minX) <= float(maxX) and float(minY) <= float(maxY):
                        low_laser_intensity = 10
                        if "$31" in grblbuffer.machinesettings and "$30" in grblbuffer.machinesettings:
                            minimum_laser_intensity = grblbuffer.machinesettings["$31"]
                            maximum_laser_intensity = grblbuffer.machinesettings["$30"]
                            # set laser intensity to < 1%
                            low_laser_intensity = (maximum_laser_intensity - minimum_laser_intensity)/100
                        else:
                            print(f"minimum and maximum laser intensity settings are unknown (type grbl command '$$'), set to default of {low_laser_intensity}")

                        print(f'Draw bounding box: (X{minX},Y{minY}):(X{maxX},Y{maxY}) {fromFile} with laser intensity set to {low_laser_intensity} and speed {feed}.')
                        print("Make sure the work area is cleared and you wear glasses to be protected!")
                        sr = input("Draw (yes/no)? ")
                        if sr.find("yes") >= 0:
                            grblbuffer.serial.write(("M5\n").encode())
                            grblbuffer.serial.write((f'G1 X{minX} Y{minY} {feed}\n').encode())
                            grblbuffer.serial.write(("M3\n").encode())
                            grblbuffer.serial.write((f'G1 X{maxX} {feed} S1\n').encode())
                            grblbuffer.serial.write((f'G1 Y{maxY} {feed} S1\n').encode())
                            grblbuffer.serial.write((f'G1 X{minX} {feed} S1\n').encode())
                            grblbuffer.serial.write((f'G1 Y{minY} {feed} S1\n').encode())
                            grblbuffer.serial.write(("M5\n").encode())
                            print("\ngrbl> M5")
                            print("grbl> " + f'G1 X{minX} Y{minY} {feed}')
                            print("grbl> M3")
                            print("grbl> " + f'G1 X{maxX} {feed} S1')
                            print("grbl> " + f'G1 Y{maxY} {feed} S1')
                            print("grbl> " + f'G1 X{minX} {feed} S1')
                            print("grbl> " + f'G1 Y{minY} {feed} S1')
                            print("grbl> M5\n")
                        else:
                            print("command aborted")
                    else:
                        print(f'Bbox info error: (X{minX},Y{minY}):(X{maxX},Y{maxY})\nCommand aborted.')

                Grblbuffer.STATUS_PAUZE = False
            return False

        if line.find("showgcode") >= 0:
            if not GCODE2IMAGE:
                print("showgcode needs gcode2image to be installed (pip install gcode2image), abort command!")
                return False

            if grblbuffer.machinestatus["state"] != "Idle":
                print("Machinestate must be 'Idle' to show gcode")
                return False
            if gcodeFile["name"] == '':
                print("Cannot show gcode: currently no file loaded!")
                return False
            with Grblbuffer.serialio_lock:
                Grblbuffer.STATUS_PAUZE = True
                try:
                    with open(gcodeFile["name"], "r") as fgcode:
                        # flip to raster image coordinate system
                        img = np.flipud(gcode2image(Namespace(gcode = fgcode, showG0 = False, resolution = .1, showorigin = True, grid = True)))

                        # convert to image
                        img = Image.fromarray(img)

                        # show image
                        img.show()
                except IOError:
                    print("file open error: file must be in the current directory, abort command!")

                Grblbuffer.STATUS_PAUZE = False
            return False

        # grbl direct commands
        if line == "!":
            with Grblbuffer.serialio_lock:
                # write direct command '!' 'feed hold'
                grblbuffer.serial.write("!".encode())
                sleep(0.02)
            return False
        if line == "~":
            with Grblbuffer.serialio_lock:
                # write direct command '~' 'resume'
                grblbuffer.serial.write("~".encode())
                sleep(0.02)
            return False
        if line == "?":
            # indicate 'plain' status report
            grblbuffer.status_plain = True
            return False

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
            return False

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
            return False

        if line != '' and not re.search(gcode_pattern,line):
            print(f"unknown grblhud command '{line}', type a GRBL command or one of:")
            print("  help, OS, stream, load, run, listgcode, showgcode, setLOOP, S+, S-, F+, F-, softstop, softreset, hardreset, sleep, Zprobe, origin, Bbox, Stoggle")
            return False

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

    def hudloopinteractive():
        nonlocal args
        nonlocal gcodeFile
        nonlocal ser
        nonlocal grblinput
        nonlocal grblbuffer

        # enter grblhud interactive mode
        print("\n**************************************************")
        print("Enter grblhud interactive mode:")
        print("  type 'help <enter>' for a command overview")
        print("  type 'exit <enter>' to leave")
        print("  command history:             type arrow up/down")
        print("  interrupt buffer load/run:   type <Ctrl><C>")
        print("  machine full stop:           type <Ctrl><D>")
        print("  machine halt:                type '~ <enter>'")
        print("  machine laser (Spindle) off: type 'M5<enter>'")
        print()
        print("Explanation of the realtime 'grbl>' prompt:")
        print(" 101|[Hold XYZ:00.050,51.049,00.000 FS:0,850 ] grbl> ~")
        print("  99|[Run  XYZ:59.268,19.031,00.000 FS:1050,0] grbl> hardreset")
        print("   0|[Idle XYZ:141.840,45.351,00.000 FS:0,850] grbl> $$")
        print("  ^    ^            ^                  ^                ^")
        print("  |    |            |                  |                |")
        print("  | 'grbl state'  'XYZ coordinates' 'Feed/Speed rates' '(grbl) commands you type'")
        print("  | ")
        print("'nbr of lines in buffer' (not the machine buffer!)")
        print("\n**************************************************\n")

        while True:
            try:
                line = grblinput.line_input(grblbuffer.format_machinestatus() + " grbl> ")
                if hudloopbody(line):
                    break
            except EOFError:
                break
            except KeyboardInterrupt:
                pass
            except MemoryError:
                print(f"Out of memory! Exit grblhud.")
                print("Wait for program exit ....")
                Grblbuffer.GRBLHUD_EXIT = True
                grblbuffer.grblstatus.join()
                # put something to get run loop out of waiting
                grblbuffer.put(";")
                grblbuffer.join()
                break

    # buffered gcode file info ('load' and 'run' command)
    gcodeFile = { "name" : "", "bBox" : "", "buffer" : [], "WHILE" : {} }

    # init serial device
    ser = machine_open(args.serial if SERIALDEVICE == '' else SERIALDEVICE)

    # init device
    machine_init(ser)

    # create instance of Input class
    grblinput = lineinput.Input()

    # instantiate and run buffer thread (serial io to/from grbl device)
    grblbuffer = Grblbuffer(ser, grblinput, False if args.gcode else True)
    grblbuffer.start()

    if args.gcode:
        hudloopbody("")
        sleep(.2)
        error_state = False
        for gc in args.gcode:
            #hudloopbody("OS ls -alrt\n")
            line = f"stream {gc.name}"
            print(line)
            if hudloopbody(line):
                # exit on 'exit'
                break

            sleep(.2)
            # wait for device ready
            while grblbuffer.buffer_not_empty() or (grblbuffer.machinestatus["state"] != "Idle"):
                if grblbuffer.machinestatus["state"] not in ["Idle", "Run"]:
                    # error state, exit
                    error_state = True
                    break
                sleep(.1)

            if error_state:
                break

        print("\nWait for program exit ....")
        Grblbuffer.GRBLHUD_EXIT = True
        grblbuffer.grblstatus.join()
        # put something to get run loop out of waiting
        grblbuffer.put(";")
        grblbuffer.join()
    else:
        # enter grblhud interactive mode
        hudloopinteractive()

    print("Exit program")

    # close serial port, status terminal
    machine_close(grblbuffer.serial)
