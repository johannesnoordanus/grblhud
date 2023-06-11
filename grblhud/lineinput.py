"""
lineinput: unblocked, unbuffered, raw input with internal state exposed
"""

import os
import atexit
import threading
import readline

from time import sleep
#from unblockedgetch import UnblockedGetch
#import UnblockedGetch
from grblhud.unblockedgetch import UnblockedGetch

class Input():
    """
    Input: unblocked, unbuffered, raw input with internal state exposed
    """

    # class variables
    line = ''
    line_pos = 0

    # getch function
    unblkGetch = UnblockedGetch().getch

    # lock
    display_lock = threading.Lock()

    # terminal control codes:
    # https://en.wikipedia.org/wiki/ANSI_escape_code
    CR                  = '\x0D'        # or '/r'
    ESCAPE              = '\x1b'        # or '\033' (note \0ctal escape code, decimal value: 27)
    CSI                 = ESCAPE + '['
    CURSOR_UP           = CSI + 'A'
    CURSOR_DOWN         = CSI + 'B'
    CURSOR_FORWARD      = CSI + 'C'
    CURSOR_BACK         = CSI + 'D'     # or '/b'
    BACKSPACE           = '\x7f'
    ERASE_TO_EOL        = '\033[J'
    BEL                 = '\x07'        # when send to stdout: ring bell (if terminal bel is set on)

    def __init__(self, prefix = ''):
        self.set_line_prefix(prefix, len(prefix))

    def set_line_prefix(self, prefix, prefix_length = 0):
        """
        set prefix (input prompt)
        """
        self.prefix = prefix
        self.prefix_length = prefix_length if prefix_length != 0 else len(prefix)

    def display_line(self, prefix = '', prefix_length = 0):
        """
        (re)draw input line
        """
        with Input.display_lock:
            if prefix or prefix_length:
                self.set_line_prefix(prefix, prefix_length)

            # clear the display line (CR,ED) and write the updated line from the start
            print('\r' + Input.ERASE_TO_EOL + self.prefix + Input.line, end = '', flush = True)
            # go to the start of the display line and set correct cursor position (CHA:'CSI <n> G').
            print('\r' + Input.CSI + str(Input.line_pos + self.prefix_length) + 'G', end = '', flush = True)

    def line_input(self, prefix = '', prefix_length = 0):
        """
        read input line: unblocked, raw (uncooked)
        """
        if prefix or prefix_length:
            self.set_line_prefix(prefix, prefix_length)
            print(prefix, end = '', flush = True)

        # input string
        Input.line = ''

        # input save
        saveline = None
        savepos = None

        # highest history index
        hendindex = readline.get_current_history_length()
        # current history index initialy pointing to the new input line
        hindex = hendindex + 1

        Input.line_pos = 1

        while True:
            c = Input.unblkGetch()

            if ord(c) == 4:
                # <Ctrl><D> break off
                # Discard previous input and return immediately
                return c

            if c == Input.ESCAPE:
                c1 = Input.unblkGetch()
                if c1 == '[':
                    c2 = Input.unblkGetch()
                    if c2 == 'A':
                        # CURSOR_UP
                        if hendindex:
                            if hindex > 1:
                                hindex -= 1
                                if hindex == hendindex:
                                    # save edit line
                                    saveline = Input.line
                                    savepos = Input.line_pos

                                upline = readline.get_history_item(hindex)
                                Input.line = upline
                                Input.line_pos = len(Input.line) + 1
                                # write updated line to display
                                self.display_line()

                    elif c2=='B':
                        # CURSOR_DOWN
                        if hendindex:
                            if hindex <= hendindex:
                                hindex += 1
                                if hindex == hendindex + 1:
                                    Input.line = saveline
                                    Input.line_pos = savepos
                                else:
                                    downline = readline.get_history_item(hindex)
                                    Input.line = downline
                                    Input.line_pos = len(Input.line) + 1
                                # write updated line to display
                                self.display_line()

                    elif c2 =='C':
                        # CURSOR_FORWARD
                        if Input.line_pos <= len(Input.line):
                            print(Input.CURSOR_FORWARD, end = '', flush = True)
                            Input.line_pos += 1
                    elif c2 =='D':
                        # CURSOR_BACK ('CSI <n> D')
                        if Input.line_pos > 1:
                            print(Input.CURSOR_BACK, end = '', flush = True)
                            Input.line_pos -= 1
                continue

            if c == Input.BACKSPACE:
                # backspace handling
                if Input.line_pos > 1:
                    # backspace has to clear one char, so
                    if len(Input.line) == Input.line_pos - 1:
                        #print("b")
                        # backspace has to clear one char, so
                        #print('\b \b', end = '', flush = True)

                        # update admin (remove last char from line)
                        Input.line = Input.line[:-1]
                        Input.line_pos -= 1

                    else:
                        # remove char from input line, update admin
                        Input.line_pos -= 1
                        Input.line = Input.line[:Input.line_pos - 1] + Input.line[Input.line_pos:]

                    # write updated line to display
                    self.display_line()

                continue

            if c == '\n':
                print(c, end = '', flush=True)
                # return input line
                break

            # not a special key
            if len(Input.line) == Input.line_pos - 1:
                Input.line += c
                print(c, end = '', flush=True)
            else:
                # insert char in line, update admin
                Input.line = Input.line[:Input.line_pos-1] + c + Input.line[Input.line_pos-1:]
            Input.line_pos += 1

            # write updated line to display
            self.display_line()

        line = ''
        if Input.line:
            readline.add_history(Input.line)
            line = Input.line
            Input.line_pos = 1
            Input.line = ''

        return line

# END CLASS Input

def main():
    # set command line history handling
    histfile = os.path.join(os.path.expanduser("~"), ".python_grblhud_history")
    try:
        readline.read_history_file(histfile)
        # default history len is -1 (infinite), which may grow unruly
        readline.set_history_length(1000)
    except FileNotFoundError:
        pass

    atexit.register(readline.write_history_file, histfile)

    # Exit (thread) global
    E = False

    # test thread
    def status(delay, display):
        print("start status")
        while not E:
            display("status> ")
            #print("\rstatus:", delay, "seconds", end = '', flush = True)
            sleep(delay)
        print("end status")

    # create instance of Input class
    grblinput = Input()

    # start test thread
    grblstatus = threading.Thread(target=status, args=(2,grblinput.display_line))
    grblstatus.start()

    # start input test
    while True:
        # get input line
        line = grblinput.line_input(" grbl > ")

        if 'exit' in line:
            E = True
            print('exit')
            break
        if len(line) == 1 and ord(line) == 4:
            print("break off")

if __name__ == '__main__':
    main()
