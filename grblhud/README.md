# grblhub
Grblhud is an interactive grbl1.1 control center. It is easy to install and needs python version 3.7 or above. 

**Grblhud** can run as a commandline program to stream gcode files directly to a grbl1.1 compatible machine. Just type 'grblhud gcodefile'.

Streaming is done via a buffer counting protocol as described by the grbl standard and is error free and fast.

**Grblhud** can run in interactive mode. Just type 'grblhud<enter>'.

This mode features full control of the grbl v1.1 device and supports <i>realtime</i> direct commands and buffered streaming of commands and programs.

Grbl state is realtime in line viewable, showing head location (XYZ) and the machine state *Idle, Run, Hold, Jog, Alarm, Door, Check, Home, Sleep* in color. State also includes current buffered (pending) gcode blocks (and no scrolling *ok's*).

Grbl v1.1 error and Alarm code definitions are shown when they occur.

Spindle and Feed settings can be updated realtime while gcode is running; gcode programs can be loaded and run with specific *Spindle* and *Feed* settings.

It is possible to easily draw a bounding box of a gcode program and set a new origin (workspace coordinates).

CNC machines can do a Z probe to easily put the bit right on top of the object (to be CNC'd).

Gcode loops are simulated (using a very simple WHILE DO syntax that must be annotated within the gcode) and can be run separately and (be) iterated at will.

Soft and hard-resets can be issued and *Ctrl-D* makes a full stop (to machine state *Door*).

This makes it easy to laser draw and cut without the need to (re)connect the device, so drawings and cuts have full (relative) machine precision.

**Grblhub** is tested on several platforms - arm64/intel - and operating systems - Linux/macosx and two grbl v1.1 devices (a lasercutter and a CNC router)

Information on grbl commands: https://github.com/gnea/grbl/blob/master/doc/markdown/commands.md

Note that *image2gcode* and *svg2gcode* can be used to convert images and vector graphics to gcode at the highest quality. *gcode2image* can be used to validate these conversions and verify the layout before using *grblhud* to send the code to your lasercutter or cnc machine. https://github.com/johannesnoordanus?tab=repositories

Also: *grblhud* now has a *showgcode* command, that runs *gcode2image* to show the currently loaded gcode (this includes the origin, size and orientation of the image). Note that *gcode2image* must be *pip* installed first (a lot of python library code is needed for this to run, which might be too much for small computers having a low network bandwidth)

### First run:
As shown below. If you do not specify a serial device, *grblhud* will open a default one and on error show a list of possible candidates you can choose one from, or type a device name you know.
It then starts a status report and run loop.

If you add file names to the command, *grblhud* will stream the files directly to the device in non interactive mode. It does show a realime status report as mentioned below.

Without file names grblhud enters interactive mode. 
You can enter grbl(hud) commands from that point.

The prompt shows realtime status information of the machine you are connected to (see the explanation of the *grblhud>* prompt below).

It is possible to 'stream' a gcode file 'directly' to the machine (via command *stream <file>*) or via a buffer (via commands *load <file>* and *run*.
The buffered approach makes additional features available, like running LOOPs and bounding boxes and updating F and S values for a specific gcode run.

To exit, type *exit*.

Look at the short command summary below, so you are able the control the laser machine directly.
Note that *load* and *run* commands can take a while on large gcode files, do not panic, realtime load/run information is shown and load/run can be aborted via *anykey* or ```<Ctrl><C>```.</br>
When you do panic, because your laser machine is hitting walls etc, type ```<Ctrl><D>```, (or ```<Ctrl><C>``` first when commands *run* or *load* are executing)!

```
$ grblhud --serial /dev/ttyUSB0
Opened serial port /dev/ttyUSB0 at 115200 bauds (bits/s)
Initializing grbl...
okok
Status report every 0.1 seconds (WPos coordinates)
Start command queue

**************************************************
Enter grblhud interactive mode:
  type 'help <enter>' for a command overview
  type 'exit <enter>' to leave
  command history:             type arrow up/down
  interrupt buffer load/run:   type <Ctrl><C>
  machine full stop:           type <Ctrl><D>
  machine halt:                type '~ <enter>'
  machine laser (Spindle) off: type 'M5<enter>'

Explanation of the realtime 'grbl>' prompt:
 101|[Hold XYZ:00.050,51.049,00.000 FS:0,850 ] grbl> ~
  99|[Run  XYZ:59.268,19.031,00.000 FS:1050,0] grbl> hardreset
   0|[Idle XYZ:141.840,45.351,00.000 FS:0,850] grbl> $$
  ^    ^            ^                  ^                ^
  |    |            |                  |                |
  | 'grbl state'  'XYZ coordinates' 'Feed/Speed rates' '(grbl) commands you type'
  | 
'nbr of lines in buffer' (not the machine buffer!)

**************************************************

0|[Idle XYZ:-6.513,09.283,-0.500 FS:0,0] grbl> 
```
### Grblhud help:
See notes below.
```
$ grblhud --help
usage: grblhud [-h] [--serial <default:/dev/ttyUSB0>] [-V] [gcode ...]

Interactive grbl1.1 control center.
  Type 'grblhud file' to stream file(s) to your machine
  Type 'grblhud<enter>' to start the interactive 'hud'.

positional arguments:
  gcode                 gcode file(s) to stream to your machine

options:
  -h, --help            show this help message and exit
  --serial <default:/dev/ttyUSB0>
                        serial device of your machine (115200 baud)
  -V, --version         show version number and exit
```
You can also store the device setting in ~/.config/grblhud.toml, eg:
```
serial = "/dev/ttyUSB0
```
It can be used with any parameter which takes a value, and alows to persist your laser settings.

### Example runs:
**commandline**
```
$ grblhud ring10.gc ring70.gc
Opened serial port /dev/ttyUSB0 at 115200 bauds (bits/s)
Initializing grbl...
Grbl 1.1h ['$' for help]
Status report every 0.1 seconds (WPos coordinates)
Start command queue
0|[Idle XYZ:-0.700,-0.400,-1.000 FS:0,0] # stream ring10.gc
Stream send: 118 lines, - wait for device to complete!
0|[Run  XYZ:139.363,45.000,-1.000 FS:1000,0] # [MSG:Pgm End]
0|[Idle XYZ:140.313,45.013,-1.000 FS:0,0] # stream ring70.gc
Stream send: 224 lines, - wait for device to complete!
0|[Run  XYZ:50.688,22.500,-1.000 FS:501,0] # [MSG:Pgm End]
0|[Idle XYZ:50.000,22.500,-1.000 FS:0,0] #  
Wait for program exit ....
Status report exit
End command queue
Exit program
```
**interactive**
```
grblhud --serialdevice /dev/cu.wchusbserial620
0|[Idle XYZ:-6.513,09.283,-0.500 FS:0,0] grbl> help
grblhud commands:
   <Ctrl><D> / FSTOP                                 (FULL MACHINE STOP (grbl1.1 state: 'Door'), issue softreset to continue)

 - OS <Unix command>                                 (run a Unix command)
 - stream <filename>                                 (stream file 'directly' to the machine (Note that WHILE loops, F and S settings are not possible)
 - load <filename>                                   (load file to buffer)
 - run [LOOP] [F<eed>] [S<pindlepeed/power>]         (run file or LOOP from buffer, and possibly set F and/or S for this run)
 - listgcode [<pcstart> [<pcend>]]                   (gcode listing, possibly set start [end] lines (for large files)
 - showgcode                                         (show image of the current gcode file (must be in the working directory))
 - setLOOP <loopname> <count> <pcstart> <pcend>      (set a WHILE LOOP)
 - S+10, S+1, S-10, S-1                              (Speed up/down 10% 1%)
 - F+10, F+1, F-10, F-1                              (Feed up/down 10% 1%)
 - softstop                                          (purge command buffer, but let machine buffer run till empty)
 - softreset                                         (issue soft reset command)
 - hardreset                                         (hard reset: close/open serial port)
 - sleep                                             ($SLP command)
 - Zprobe                                            (lower head until 'probe' contact is made)
 - origin [X<coord>][Y<coord>][Z<coord>]             (make current XYZ: [X<coord>][Y<coord>][Z<coord>] (shift work coordinates))
 - Bbox [(X<min>,Y<min>):(X<max>,Y<max>)] [F<eed>]   (draw a bounding box with laser set to low )
 - Stoggle                                           (Spindle on/off, in 'Hold' state only)

grbl commands:
 - $ (grbl help)
     $$ (view Grbl settings)
     $# (view # parameters)
     $G (view parser state)
     $I (view build info)
     $N (view startup blocks)
     $x=value (save Grbl setting)
     $Nx=line (save startup block)
     $C (check gcode mode)
     $X (kill alarm lock)
     $H (run homing cycle)
     ~ (cycle start)
     ! (feed hold)
     ? (current status)
     ctrl-x/command + x/softreset (reset Grbl)

0|[Idle XYZ:-6.513,09.283,-0.500 FS:0,0] grbl> 

```
### WHILE DO syntax:
Grblhud unrolls loops when files are loaded (via command *load <filename>*) and subsequently run (via command *run*)
Loops can be defined within a gcode file, as comments *;* using the syntax show below, or be defined by command *setLOOP*.
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
	- pip install grblhud 

	To install additional tools:
	- pip install gcode2image
	- pip install image2gcode
	- pip install svg2gcode
```
