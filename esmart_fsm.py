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
import pifacedigitalio

thermregexp = re.compile(r"THx,\s*(\S+),\s*(\S+),\s*(\S+),\s*(\S+),\s*(\S+),\s*(\S+),\s*(\S+),\s*(\S+)")

TICK_SECS = 5
FULL_VOLT = 28.4
FULL_CUR = 20
LOW_VOLT = 24.8
DELAY_SECS = 300
HOT_DEGREES = 50
COLD_DEGREES = 45

HEATTRAP="/dev/ttyACM0"
EOLCHARS = b'\r\n'

ESMART_HOST='192.168.120.2'
ESMART_PORT=8888

class esmartfsm(object):
    states  = ['off', 'on', 'stopping']
    transitions = [
        { 'source': 'off',          'trigger': 'full',    'dest': 'on',             'after': 'turn_pump_on' },
        { 'source': 'off',          'trigger': 'low',     'dest': 'off' },
        { 'source': 'off',          'trigger': 'tick',    'dest': 'off' },
        { 'source': 'off',          'trigger': 'hot',     'dest': 'hot' },
        { 'source': 'off',          'trigger': 'cold',    'dest': 'off' },

        { 'source': 'on',           'trigger': 'full',    'dest': 'on' },
        { 'source': 'on',           'trigger': 'low',     'dest': 'stopping low',   'after': 'turn_pump_off' },
        { 'source': 'on',           'trigger': 'tick',    'dest': 'on' },
        { 'source': 'on',           'trigger': 'hot',     'dest': 'stopping hot',   'after': 'turn_pump_off' },
        { 'source': 'on',           'trigger': 'cold',    'dest': 'on' },

        { 'source': 'stopping low', 'trigger': 'full',    'dest': 'stopping low',   'after': 'check_delay' },
        { 'source': 'stopping low', 'trigger': 'low',     'dest': 'stopping low',   'after': 'check_delay' },
        { 'source': 'stopping low', 'trigger': 'tick',    'dest': 'stopping low',   'after': 'check_delay' },
        { 'source': 'stopping low', 'trigger': 'hot',     'dest': 'stopping low' },
        { 'source': 'stopping low', 'trigger': 'cold',    'dest': 'stopping low' },
        { 'source': 'stopping low', 'trigger': 'resume',  'dest': 'off' },

        { 'source': 'stopping hot', 'trigger': 'full',    'dest': 'stopping hot',   'after': 'check_delay' },
        { 'source': 'stopping hot', 'trigger': 'low',     'dest': 'stopping hot',   'after': 'check_delay' },
        { 'source': 'stopping hot', 'trigger': 'tick',    'dest': 'stopping hot',   'after': 'check_delay' },
        { 'source': 'stopping hot', 'trigger': 'hot',     'dest': 'stopping hot' },
        { 'source': 'stopping hot', 'trigger': 'cold',    'dest': 'stopping hot' },
        { 'source': 'stopping hot', 'trigger': 'resume',  'dest': 'hot' },

        { 'source': 'hot',          'trigger': 'full',    'dest': 'hot' },
        { 'source': 'hot',          'trigger': 'low',     'dest': 'hot' },
        { 'source': 'hot',          'trigger': 'tick',    'dest': 'hot' },
        { 'source': 'hot',          'trigger': 'hot',     'dest': 'hot' },
        { 'source': 'hot',          'trigger': 'cold',    'dest': 'off' },
    ]

    def __init__(self):
        self.e = esmart.esmart()
        self.e.connect((ESMART_HOST, ESMART_PORT))

        self.machine = Machine(model=self, states=esmartfsm.states, transitions=esmartfsm.transitions, initial='off')
        self.heattrap = serial.Serial(HEATTRAP, baudrate=9600, timeout=0)
        self.piface = pifacedigitalio.PiFaceDigital()

        self.line = bytearray()
        self.timeout = 0

    def request_data(self):
        timebefore = time.time()
        readable, writable, exceptional = select.select([self.heattrap], [], [], self.timeout)

        tempsensors = None
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
                        tempsensors = [int(linematch.group(i)) for i in [2,3,8]]

                    self.line = bytearray()
                else:
                    self.line += c

                c = self.heattrap.read(1)

        if tempsensors:
            print(tempsensors, flush=True)
            if tempsensors[1] >= HOT_DEGREES:
                fsm.hot()
            elif tempsensors[1] <= COLD_DEGREES:
                fsm.cold()
            else:
                fsm.tick()
        else:
            self.timeout -= time.time() - timebefore
            if self.timeout > 0:
                fsm.tick()
            else:
                data = self.e.read()

                charge_mode = esmart.DEVICE_MODE[data['chg_mode']]
                time_now = datetime.datetime.now().replace(microsecond=0).isoformat()

                def print_charge_status(status):
                    print('%s Charge mode: %s Battery %.1fV %.1fA - %s' % (time_now, charge_mode, data['bat_volt'], data['chg_cur'], status), flush=True)


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
        print("TURN PUMP ON", flush=True)
        self.piface.relays[0].value=1
        self.piface.relays[1].value=1

    def turn_pump_off(self):
        print("TURN PUMP OFF", flush=True)
        self.piface.relays[0].value=0
        self.piface.relays[1].value=0
        self.delayend = time.time() + DELAY_SECS

    def check_delay(self):
        if time.time() >= self.delayend:
            del self.delayend
            fsm.resume()


def sigint_handler(sig, frame):
    print('EXIT', flush=True)
    sys.exit(0)

signal.signal(signal.SIGINT, sigint_handler)
fsm = esmartfsm()
while True:
    fsm.request_data()
