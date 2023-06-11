#!/usr/bin/env python3
"""
grblhub: a command line tool to handle grbl code.
"""

import os
import sys
import re
from time import sleep
# needs pyserial!
import serial
from inputimeout import inputimeout, TimeoutOccurred
from grblhud import lineinput
from grblhud.grblbuffer import Grblbuffer
from grblhud.grblmessages import grbl_alarm
from grblhud.grblmessages import grbl_settings

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

def grblhudloop(args):
    """
    grblhud main loop
    """

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
                print("   (<Ctrl><D>) or FSTOP                              (FULL STOP to continue: softreset)")
                print()
                print(" - cls                                               (clear screen)")
                print(" - load <filename>                                   (load file to buffer)")
                print(" - run [LOOP] <(file/loop)name> [F<eed>] [S<peed>]   (run from buffer)")
                print(" - S+10, S+1, S-10, S-1                              (Speed up/down 10% 1%)")
                print(" - F+10, F+1, F-10, F-1                              (Feed up/down 10% 1%)")
                print(" - softstop                                          (purge command buffer, but let machine buffer run till empty)")
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
                print()
                continue

            if line.find("cls") >= 0:
                os.system('cls' if os.name == 'nt' else 'clear')
                continue
            if line.find("setting") >= 0:
                set_nr = re.search("[0-9]+",line)
                if set_nr:
                    set_nr = set_nr.group()
                    if int(set_nr) in grbl_settings.keys():
                        print("$" + set_nr + ": " + grbl_settings[int(set_nr)])
                    else:
                        print("unknown setting: $" + set_nr)
                else:
                    for k in grbl_settings.keys():
                        print("$" + str(k) + ": " + grbl_settings[k])
                continue

            if line == 'softstop':
                with Grblbuffer.serialio_lock:
                    with Grblbuffer.bec:
                        print("Issued softstop (purged command buffer)")
                        # purge buffer
                        grblbuffer.init_buffer()
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
                        abort = False
                        # do not do that gcodeFile["buffer"].append('; ' + gcodeFile["name"])
                        print("Loading file", gcodeFile["name"], "into memory buffer ...\n")
                        # for line in f:
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
                                            # clear buffer/loop info
                                            gcodeFile = { "name" : "", "bBox" : "", "buffer" : [], "WHILE" : {} }
                                            abort = True
                                            break
                                    if abort:
                                        break
                                else:
                                    print("WHILE info isn't consistent: cannot find WHILE label '" + do_loopname + "'!, abort load!" )
                                    # clear buffer/loop info
                                    gcodeFile = { "name" : "", "bBox" : "", "buffer" : [], "WHILE" : {} }
                                    abort = True
                                    break

                            gcodeFile["buffer"].append(line)

                        if not abort:
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
                    print("Machinestate must be 'Idle' to run a file")
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
                        print("No 'LOOP' name given; abort run!")
                        continue
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
                        print("Cannot find loop with label '" + loopname + "', abort run!")
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
                                do_loopname = re.search(" [a-z]+[0-9]*",line)
                                if not do_loopname:
                                    print("No 'DO' loopname given; abort run!")
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
