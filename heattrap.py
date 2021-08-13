# Library for communicating with Heat Trap hot water system
# Copyright 2020 Jonathan Schultz

import re, sys, time, select
try:
    import serial
except ModuleNotFoundError:
    pass


EOLCHARS = b'\r\n'

tempregex = re.compile(r"THx,\s*(\S+),\s*(\S+),\s*(\S+),\s*(\S+),\s*(\S+),\s*(\S+),\s*(\S+),\s*(\S+)")

class heattrapError(Exception):
    pass

class heattrap:
    def __init__(self, port):
        self.serial = serial.Serial(port, baudrate=9600, timeout=0) if 'serial' in sys.modules else None
        self.line = bytearray()

    def __del__(self):
        self.close()

    def close(self):
        try:
            if self.serial:
                self.serial.close()
                self.serial = None
        except AttributeError:
            pass

    def read(self, timeout=None):
        tempsensors = None
        if self.serial:
            readable, writable, exceptional = select.select([self.serial], [], [], timeout)

            if readable:
                c = self.serial.read(1)
                while c:
                    if c in EOLCHARS:
                        try:
                            linematch = tempregex.match(self.line.decode('utf-8'))
                        except UnicodeDecodeError:
                            linematch = None
                            pass
                        if linematch:
                            tempsensors = [int(linematch.group(i)) for i in [2,3,8,1]]

                        self.line = bytearray()
                    else:
                        self.line += c

                    c = self.serial.read(1)
        else:
            time.sleep(timeout)

        return tempsensors
