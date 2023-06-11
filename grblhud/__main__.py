#!/usr/bin/env python3
"""
grblhub: a command line tool to handle grbl code.
"""

import os
import atexit
import argparse
import readline
from grblhud import __version__
from grblhud.grblhudloop import grblhudloop

def create_parser():
    """
    grblhud argument(s) parser
    """
    parser = argparse.ArgumentParser(
        description="Stream g-code using grbl's serial read buffer.")

    parser.add_argument('--serialdevice', default="/dev/ttyUSB0",
        metavar='/dev/<serial-tty-name>',
        help='serial device on linux (default: /dev/ttyUSB0 115200 baud)')

    parser.add_argument( '--status', '-s', type=argparse.FileType('w'), default=None, metavar='/dev/<terminal-tty-name>',
        help="grbl status output (default: no output)")

    parser.add_argument('-V', '--version', action='version', version='%(prog)s ' + __version__,
        help="show version number and exit")

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

    grblhudloop(args)

if __name__ == '__main__':
    main()
