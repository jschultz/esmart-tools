# Library for communicating with eSmart 3 MPPT charger
# Copyright 2020 Jonathan Schultz
# skagmo.com, 2018

#import struct, time, serial, socket, requests
import importlib, time, sys, select
try:
    import serial
except ModuleNotFoundError:
    pass
try:
    import socket
except ModuleNotFoundError:
    pass

# States
STATE_START = 0
STATE_DATA = 1

REQUEST_MSG0 = b"\xaa\x01\x01\x01\x00\x03\x00\x00\x1e\x32"
LOAD_OFF = b"\xaa\x01\x01\x02\x04\x04\x01\x00\xfe\x13\x38"
LOAD_ON = b"\xaa\x01\x01\x02\x04\x04\x01\x00\xfd\x13\x39"

DEVICE_MODE = ["IDLE", "CC", "CV", "FLOAT", "STARTING"]

class esmartError(Exception):
    pass

class esmart:
    def __init__(self):
        self.serial = None
        self.port = ""
        self.timeout = 0
        self.socket = None

    def __del__(self):
        self.close()

    def open(self, port):
        if 'serial' in sys.modules:
            self.serial = serial.Serial(port,9600,timeout=0.1)
            self.port = port
        else:
            raise esmartError("Missing module: serial")

    def connect(self, address):
        if 'socket' in sys.modules:
            self.socket = socket.create_connection(address)
            self.socket.setblocking(0)
            self.address = address
        else:
            raise esmartError("Missing module: socket")

    def close(self):
        try:
            if self.serial:
                self.serial.close()
                self.serial = None
            if self.socket:
                self.socket.close()
                self.socket = None
        except AttributeError:
            pass

    def read(self, timeout=None):
        try:
            data = None
            if self.serial:
                self.serial.write(REQUEST_MSG0)
                ready = select.select([self.serial], [], [], timeout)
                if ready[0]:
                    data = self.serial.read(1024)
            elif self.socket:
                self.socket.send(REQUEST_MSG0)
                ready = select.select([self.socket], [], [], timeout)
                if ready[0]:
                    data = self.socket.recv(1024)

            #print("Read: ", [hex(data[idx]) for idx in range(len(data))])
            idx = data.find(0xaa) if data else -1
            if idx == -1:
                raise esmartError("No data from eSmart device")
            data = data[idx:]
            if len(data) < 5:
                raise esmartError("Insufficient data from eSmart device")
            if (data[0] != 0xaa):
                raise esmartError("Incorrect start character: ", [hex(data[idx]) for idx in range(len(data))])
            if (data[3] != 3):
                raise esmartError("Source is not MPPT device")
            if (data[4] != 0):
                raise esmartError("Packet type is not 0")

            fields = {}
            fields['chg_mode']   = int.from_bytes(data[8:10],  byteorder='little')
            if fields['chg_mode'] < 0 or fields['chg_mode'] >= len(DEVICE_MODE):
                raise esmartError("Charge mode out of range: ", str(fields['chg_mode']))
            
            fields['pv_volt']    = int.from_bytes(data[10:12], byteorder='little') / 10.0
            fields['bat_volt']   = int.from_bytes(data[12:14], byteorder='little') / 10.0
            fields['chg_cur']    = int.from_bytes(data[14:16], byteorder='little') / 10.0
            fields['load_volt']  = int.from_bytes(data[18:20], byteorder='little') / 10.0
            fields['load_cur']   = int.from_bytes(data[20:22], byteorder='little') / 10.0
            fields['chg_power']  = int.from_bytes(data[22:24], byteorder='little')
            fields['load_power'] = int.from_bytes(data[24:26], byteorder='little')
            fields['bat_temp']   = data[26]
            fields['int_temp']   = data[28]
            fields['soc']        = data[30]
            fields['co2_gram']   = int.from_bytes(data[34:36], byteorder='little')

            return fields

        except IOError:
            #print("Serial port error, fixing")
            self.serial.close()
            opened = 0
            while not opened:
                try:
                    self.ser = serial.Serial(self.port,38400,timeout=0)
                    time.sleep(0.5)
                    if self.serial.read(100):
                        opened = 1
                    else:
                        self.serial.close()
                except serial.serialutil.SerialException:
                    time.sleep(0.5)
                    self.serial.close()
            #print("Error fixed")

