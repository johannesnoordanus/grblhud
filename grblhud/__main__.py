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
        description="Interactive grbl1.1 control center. Type 'grblhud<enter>' to start the 'hud'.")

    parser.add_argument('--serialdevice', default="/dev/ttyUSB0",
        metavar='/dev/ttyUSB0',
        help='serial device of your machine (115200 baud)')

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
