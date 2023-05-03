# grblhub
Grblhub is a command line based tool to handle grbl code.

It features full control of the grbl (v1.1) device and supports 'realtime' direct commands and buffered streaming for other commands.</br>
Grbl state is in line viewable and in color!</br>
Spindle and Feed 'speed' can be updated realtime while gcode (G1) is running; gcode programs can be loaded and run with specific Spindle and Feed settings.</br>
Gcode loops are simulated (using a very simple WHILE DO syntax that must be annotated within the gcode) and can be run independently and (be) iterated at will.
This makes it easy to laser draw and cut without the need to (re)connect the device, so drawings and cuts have the full (relative) machine precision.</br>

Grblhub is tested on several platforms - arm64/intel - and operating systems - Linux/macosx and two grbl v1.1 devices (a lasercutter and a CNC router)

Information on grbl commands: https://github.com/gnea/grbl/blob/master/doc/markdown/commands.md

WHILE DO syntax:
```
    # Gcode:
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
```
Installation note:
``` 
    - pyserial must be installed first ('pip install pyserial')
    - lineinput.py and unblockedgetch.py must be in the same directory (as grblhud.py) or in python path
    - run 'python3 grblhud.py' or 'chmod u+x grblhud.py' (once) and './grblhud.py' to execute.
      (when in $PATH, 'grblhud.py' suffice)
```
Grblhud help:
```
    $ ./grblhud.py --help
    usage: grblhud.py [-h] [--serialdevice /dev/<serial-tty-name>] [--status /dev/<terminal-tty-name>]

    Stream g-code using grbl's serial read buffer.

    options:
      -h, --help            show this help message and exit
      --serialdevice /dev/<serial-tty-name>
                            serial device on linux (default: /dev/ttyUSB0 115200 baud)
      --status /dev/<terminal-tty-name>, -s /dev/<terminal-tty-name>
                            grbl status output (default: no output)
```
Example run:
``` $ ./grblhud.py 
    open serial port /dev/ttyUSB0 at 115200 bauds (bits/s)
    Initializing grbl...
    Grbl 1.1h ['$' for help]
    Status report every 0.5 seconds
    Start command queue
    [     XY:00.000,00.000 FS:0,0] grbl> 
    [Idle XY:00.000,00.000 FS:0,0] grbl> 
    [Idle XY:00.000,00.000 FS:0,0] grbl> help
    Type one of the following commands:
       (<Ctrl><D>)   FULL STOP                           (continue: (soft)reset)
       
     - load <filename>                                   (load file to buffer)
     - run [LOOP] <(file/loop)name> [F<eed>] [S<peed>]   (run from buffer)
     - S+10, S+1, S-10, S-1                              (Speed up/down 10% 1%)
     - F+10, F+1, F-10, F-1                              (Feed up/down 10% 1%
     - softreset                                         (Issue soft reset command to device
     - hardreset                                         (Hard reset: close/open serial port)
     - SToggle                                           (Spindle Toggle)
     - grbl/gcode (direct) command:
         -- '!' feed hold, 
         -- '~' start/resume, 
         -- '?' status, 
         -- 'ctrl-x' or 'command + x' soft reset!
    [Idle XY:00.000,00.000 FS:0,0] grbl> exit
```
