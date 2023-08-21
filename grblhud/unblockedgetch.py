"""
UnblockedGetch: unbuffered, unblocked, raw (uncooked) character input
"""

import sys
import tty
import select
import termios
from time import sleep

class UnblockedGetch:
    """
    UnblockedGetch: unbuffered, unblocked, raw (uncooked) character input
    """
    # set at program start
    prevStdinAttributes = termios.tcgetattr(sys.stdin)

    def __init__(self):
        pass
        # restore attributes at program exit

    def set_stdin_cbreak(self):
        """
        set cbreak mode:
        """
        # "Enter cbreak mode. In cbreak mode (sometimes called “rare” mode) normal tty line buffering
        #  is turned off and characters are available to be read one by one. However, unlike raw mode,
        #  special characters (interrupt, quit, suspend, and flow control) retain their effects on the
        #  tty driver and calling program. Calling first raw() then cbreak() leaves the terminal in cbreak mode."
        tty.setcbreak(sys.stdin, when = termios.TCSANOW)

    def restore_stdin_io(self):
        """
        restore stdin attributes
        """
        if UnblockedGetch.prevStdinAttributes:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, UnblockedGetch.prevStdinAttributes)

    def stdinHasData(self):
        """
        check if stdin has data waiting
        """
        return select.select([sys.stdin], [], [], 0) == ([sys.stdin], [], [])

    def getch(self):
        """
        unbuffered, unblocked, raw (uncooked) character input
        """
        # cbreak mode
        self.set_stdin_cbreak()

        c = b''
        while True:
            if self.stdinHasData():

                # Input in cbreak mode seems to be buffered. When reading the arrow keys (for example)
                # As a consequence of the three byte encoding of the arrow keys only one byte can be
                # received (esc) and the rest gets 'stuck' until other key(s) are entered (and the two
                # bytes left come out). After a lot of tests my conclusion is that none of the solutions
                # given on the internet seem to work. Changing stdin buffering to 0, flushing(?), etc
                # does not work. However, switching to the solution below (raw mode) in cbreak did work:

                # https://stackoverflow.com/questions/75218737/python-sys-stdin-buffer-size-detection:
                c = sys.stdin.buffer.read1(1)
                # c = sys.stdin.buffer.raw.read(10) # Note this indeed does not block for 3 byte
                                                    # key input (<-, ->, ^, down arrow) for example.
                break
            sleep(.02)

        # clear cbreak
        self.restore_stdin_io()

        return chr(c[0])

    def getch_nowait(self):
        """
        unbuffered, unblocked, nowait, raw (uncooked) character input
        """
        # cbreak mode
        self.set_stdin_cbreak()

        c = b''
        if self.stdinHasData():

                # Input in cbreak mode seems to be buffered. When reading the arrow keys (for example)
                # As a consequence of the three byte encoding of the arrow keys only one byte can be
                # received (esc) and the rest gets 'stuck' until other key(s) are entered (and the two
                # bytes left come out). After a lot of tests my conclusion is that none of the solutions
                # given on the internet seem to work. Changing stdin buffering to 0, flushing(?), etc
                # does not work. However, switching to the solution below (raw mode) in cbreak did work:

                # https://stackoverflow.com/questions/75218737/python-sys-stdin-buffer-size-detection:
            c = sys.stdin.buffer.read1(1)
                # c = sys.stdin.buffer.raw.read(10) # Note this indeed does not block for 3 byte
                                                    # key input (<-, ->, ^, down arrow) for example.
        # clear cbreak
        self.restore_stdin_io()

        return chr(c[0]) if c != b'' else ''

def main():
    print("type 'z' to exit!")
    unblkgetch = UnblockedGetch().getch
    while True:
        c = unblkgetch()
        print(c, end = '', flush = True)
        if c == 'z':
            print()
            break

if __name__ == '__main__':
    main()
