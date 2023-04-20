# grblhud
grblhub is a command line based tool to handle grbl code.

It features full control of the grbl (v1.1) device and supports 'realtime' direct commands and buffered streaming for other commands.
gcode files can be loaded and run with specific Feed and Speed settings.
Gcode loops are simulated (using a very simple WHILE DO syntax that must be annotated within the gcode) and can be run independently and (be) iterated at will.
This makes it easy to laser draw and cut without the need to (re)connect the device, so drawings and cuts have the full (relative) machine precision.

$ ./grblhud.py --help
usage: grblhud.py [-h] [--serialdevice /dev/<serial-tty-name>] [--status /dev/<terminal-tty-name>]

Stream g-code using grbl's serial read buffer.

options:
  -h, --help            show this help message and exit
  --serialdevice /dev/<serial-tty-name>
                        serial device on linux (default: /dev/ttyUSB0 115200 baud)
  --status /dev/<terminal-tty-name>, -s /dev/<terminal-tty-name>
                        grbl status output (default: no output)
Example run:
$ ./grblhud.py 
open serial port /dev/ttyUSB0 at 115200 bauds (bits/s)
Initializing grbl...
Grbl 1.1h ['$' for help]
Status report every 0.5 seconds
Start command queue
[     XY:00.000,00.000 FS:0,0] grbl> 
[Idle XY:00.000,00.000 FS:0,0] grbl> 
[Idle XY:00.000,00.000 FS:0,0] grbl> help
Type one of the following commands:
 - load <filename>                                   (load file to buffer)
 - run [LOOP] <(file/loop)name> [F<eed>] [S<peed>]   (run from buffer)
 - S+10, S+1, S-10, S-1                              (Speed up/down 10% 1%)
 - F+10, F+1, F-10, F-1                              (Feed up/down 10% 1%
 - softreset                                         (0x18(ctrl-x)
 - hardreset                                         (close/open serial port)
 - grbl/gcode (direct) command:
     -- '!' feed hold, 
     -- '~' start/resume, 
     -- '?' status, 
     -- 'ctrl-x' or 'command + x' soft reset!
[Idle XY:00.000,00.000 FS:0,0] grbl> exit

