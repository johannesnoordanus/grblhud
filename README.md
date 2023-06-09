# grblhub
Grblhub is a command line based tool to handle grbl code.

It features full control of the grbl v1.1 device and supports <i>realtime</i> direct commands and buffered streaming of commands and programs.</br>
Grbl state is in line viewable, showing (all) machine states i.e. <i>Idle, Run, Hold, Jog, Alarm, Door, Check, Home, Sleep</i> in color. State also includes current buffered (pending) gcode blocks (and no scrolling <i>ok's</i>)</br>
Grbl v1.1 error and Alarm code definitions are shown when they occur.
Spindle and Feed settings can be updated realtime while gcode (G1) is running; gcode programs can be loaded and run with specific <i>Spindle</i> and <i>Feed</i> settings.</br>
Gcode loops are simulated (using a very simple WHILE DO syntax that must be annotated within the gcode) and can be run separately and (be) iterated at will.
Soft and hard-resets can be issued and <i>Ctrl-D</i> makes a full stop (to machine state <i>Door</i>).
This makes it easy to laser draw and cut without the need to (re)connect the device, so drawings and cuts have full (relative) machine precision.</br>   

Grblhub is tested on several platforms - arm64/intel - and operating systems - Linux/macosx and two grbl v1.1 devices (a lasercutter and a CNC router)

Information on grbl commands: https://github.com/gnea/grbl/blob/master/doc/markdown/commands.md

Note that image2gcode and svg2gcode can be used to convert images and vector graphics to gcode at the highest quality. gcode2image can be used to validate these conversions and verify the layout before using grblhud to send the code to your lasercutter or cnc machine. https://github.com/johannesnoordanus?tab=repositories

### WHILE DO syntax:
```
    # Gcode:
    #    #100 = 1
    #    WHILE [#100 LE 5] DO1
    #    (Some G-Code Blocks Go Here to Be Repeated Each Loop)
    #    #100 = #100 + 1 (Increase #100 by 1 each iteration of the loop)
    #    END1
    
    # Simulate gcode WHILE DO instructions (above) like this:
    #    ; WHILE <count> <loopname>'    example: '; WHILE 23 aloop123'
    #    (Some G-Code Blocks Go Here to Be Repeated Each Loop)
    #    ; DO <loopname>'               example: '; DO aloop123'
    #
    # Note that this is an annotation (quoted out so the grbl controller does not see it)
    # Note also that loopnames are all lowercase! And have a number (if any) at the end:
    # in regex '[a-z]+[0-9]*'
```
### Installation note:
``` 
	- pyserial must be installed first ('pip install pyserial')
	- inputimeout must be installed ('pip install inputimeout')
	- pip install grblhud

	To install additional tools:
	- pip install image2gcode
	- pip install svg2gcode
	- pip install gcode2image 
```
### Grblhud help:
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
### Example run:
```
>
> grblhud
Opened serial port /dev/ttyUSB0 at 115200 bauds (bits/s)
Initializing grbl...

Status report every 0.1 seconds
Start command queue
[     XYZ:00.000,00.000,00.000 FS:0,0] grbl> Grbl 1.1h ['$' for help]
0|[Idle XYZ:00.000,00.000,00.000 FS:0,0] grbl> help
Type one of the following commands:
   (<Ctrl><D>) or FSTOP                              (FULL STOP to continue: softreset)

 - cls                                               (clear screen)
 - load <filename>                                   (load file to buffer)
 - run [LOOP] <(file/loop)name> [F<eed>] [S<peed>]   (run from buffer)
 - S+10, S+1, S-10, S-1                              (Speed up/down 10% 1%)
 - F+10, F+1, F-10, F-1                              (Feed up/down 10% 1%)
 - softstop                                          (purge command buffer, but let machine buffer run till empty)
 - softreset                                         (Issue soft reset command)
 - hardreset                                         (Hard reset: close/open serial port)
 - sleep                                             ($SLP command)
 - dryrun                                            ($C check mode)
 - Stoggle                                           (S toggle, in 'Hold' state only)
 - setting [<nr>]                                    (get setting for specific <nr>)
 - grbl/gcode (direct) command:
     -- '!' feed hold, 
     -- '~' start/resume, 
     -- '?' status, 
     -- 'ctrl-x' or 'command + x' soft reset!
0|[Idle XYZ:00.000,00.000,00.000 FS:0,0] grbl> 
```
