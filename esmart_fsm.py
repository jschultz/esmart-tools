#!/usr/bin/python3
# -*- coding: utf-8 -*-

import esmart
import time
import datetime
from transitions import Machine
import signal
import sys
import serial
import re
import select
import time

thermregexp = re.compile(r"THx,\s*(\S+),\s*(\S+),\s*(\S+),\s*(\S+),\s*(\S+),\s*(\S+),\s*(\S+),\s*(\S+)")

TICK_SECS = 5
FULL_VOLT = 28.4
FULL_CUR = 20
LOW_VOLT = 24.8
DELAY_SECS = 300
HEATTRAP="/dev/ttyACM0"
EOLCHARS = b'\r\n'

ESMART_HOST='192.168.120.2'
ESMART_PORT=8888

class esmartfsm(object):
    states  = ['off', 'on']
    transitions = [
        { 'trigger': 'full',    'source': 'off',     'dest': 'on',      'after': 'turn_pump_on' },
        { 'trigger': 'full',    'source': 'on',      'dest': 'on' },
        { 'trigger': 'low',     'source': 'on',      'dest': 'off',     'after': 'turn_pump_off_and_delay' },
        { 'trigger': 'low',     'source': 'off',     'dest': 'off' },
        { 'trigger': 'tick',    'source': 'off',     'dest': 'off' },
        { 'trigger': 'tick',    'source': 'on',      'dest': 'on' }
    ]

    def __init__(self):
        self.e = esmart.esmart()
        self.e.connect((ESMART_HOST, ESMART_PORT))

        self.machine = Machine(model=self, states=esmartfsm.states, transitions=esmartfsm.transitions, initial='off')
        self.heattrap = serial.Serial(HEATTRAP, baudrate=9600, timeout=0)

        self.line = bytearray()
        self.timeout = TICK_SECS

    def request_esmart_data(self):
        timebefore = time.time()
        readable, writable, exceptional = select.select([self.heattrap], [], [], self.timeout)

        if readable:
            c = self.heattrap.read(1)
            while c:
                if c in EOLCHARS:
                    try:
                        linematch = thermregexp.match(self.line.decode('utf-8'))
                    except UnicodeDecodeError:
                        linematch = None
                        pass
                    if linematch:
                        temp = [int(linematch.group(i)) for i in [2,3,8]]
                        print(temp)

                    self.line = bytearray()
                else:
                    self.line += c

                c = self.heattrap.read(1)

        self.timeout -= time.time() - timebefore
        if self.timeout > 0:
            fsm.tick()
        else:
            data = self.e.read()

            charge_mode = esmart.DEVICE_MODE[data['chg_mode']]
            time_now = datetime.datetime.now().replace(microsecond=0).isoformat()

            def print_charge_status(status):
                print('%s Charge mode: %s Battery %.1fV %.1fA - %s' % (time_now, charge_mode, data['bat_volt'], data['chg_cur'], status))


            if ( charge_mode == 'FLOAT' ) or \
            ( data['bat_volt'] >= FULL_VOLT and data['chg_cur'] < FULL_CUR):
                print_charge_status('FULL')
                fsm.full()
            elif data['bat_volt'] < LOW_VOLT:
                print_charge_status('LOW')
                fsm.low()
            else:
                print_charge_status('TICK')
                fsm.tick()

            self.timeout = TICK_SECS


    def turn_pump_on(self):
        print("TURN PUMP ON")

    def turn_pump_off_and_delay(self):
        print("TURN PUMP OFF")
        time.sleep(DELAY_SECS)

def sigint_handler(sig, frame):
    print('EXIT')
    sys.exit(0)

signal.signal(signal.SIGINT, sigint_handler)
fsm = esmartfsm()
while True:
    fsm.request_esmart_data()
