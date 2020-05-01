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
CRITICAL_VOLT = 24.0
LOW_BATTERY_TIMEOUT = 120
CIRCULATION_DELAY_SECS = 30
RESTART_DELAY_SECS = 300
HOT_DEGREES = 50
COLD_DEGREES = 45

HEATTRAP = "/dev/ttyACM0"
EOLCHARS = b'\r\n'

HEAT_PUMP_RELAY = 1
CIRCULATION_PUMP_RELAY = 0

ESMART_HOST='containerpi.local'
ESMART_PORT=8888

class esmartfsm(object):
    states  = ['off', 'on', 'waiting before stopping', 'stopping circulation pump low', 'waiting before restart low', 'stopping circulation pump hot', 'waiting before restart hot', 'hot']
    transitions = [
        { 'source': 'off', 'trigger': 'full',     'dest': 'on', 'after': 'turn_pumps_on' },
        { 'source': 'off', 'trigger': 'low',      'dest': 'off' },
        { 'source': 'off', 'trigger': 'critical', 'dest': 'off' },
        { 'source': 'off', 'trigger': 'tick',     'dest': 'off' },
        { 'source': 'off', 'trigger': 'hot',      'dest': 'hot' },
        { 'source': 'off', 'trigger': 'cold',     'dest': 'off' },

        { 'source': 'on',  'trigger': 'full',     'dest': 'on' },
        { 'source': 'on',  'trigger': 'low',      'dest': 'waiting before stopping',       'after': 'set_low_battery_timer' },
        { 'source': 'on',  'trigger': 'critical', 'dest': 'stopping circulation pump low', 'after': 'turn_heat_pump_off' },
        { 'source': 'on',  'trigger': 'tick',     'dest': 'on' },
        { 'source': 'on',  'trigger': 'hot',      'dest': 'stopping circulation pump hot', 'after': 'turn_heat_pump_off' },
        { 'source': 'on',  'trigger': 'cold',     'dest': 'on' },

        { 'source': 'waiting before stopping', 'trigger': 'full',     'dest': 'on', 'after': 'cancel_timer' },
        { 'source': 'waiting before stopping', 'trigger': 'low',      'dest': 'waiting before stopping' },
        { 'source': 'waiting before stopping', 'trigger': 'critical', 'dest': 'waiting before restart low',    'after': 'turn_heat_pump_off' },
        { 'source': 'waiting before stopping', 'trigger': 'tick',     'dest': 'on', 'after': 'cancel_timer' },
        { 'source': 'waiting before stopping', 'trigger': 'hot',      'dest': 'stopping circulation pump hot', 'after': 'turn_heat_pump_off' },
        { 'source': 'waiting before stopping', 'trigger': 'cold',     'dest': 'waiting before stopping' },
        { 'source': 'waiting before stopping', 'trigger': 'timeout',  'dest': 'waiting before restart low',    'after': 'turn_heat_pump_off' },

        { 'source': 'stopping circulation pump low', 'trigger': 'full',     'dest': 'stopping circulation pump low' },
        { 'source': 'stopping circulation pump low', 'trigger': 'low',      'dest': 'stopping circulation pump low' },
        { 'source': 'stopping circulation pump low', 'trigger': 'critical', 'dest': 'stopping circulation pump low' },
        { 'source': 'stopping circulation pump low', 'trigger': 'tick',     'dest': 'stopping circulation pump low' },
        { 'source': 'stopping circulation pump low', 'trigger': 'hot',      'dest': 'stopping circulation pump low' },
        { 'source': 'stopping circulation pump low', 'trigger': 'cold',     'dest': 'stopping circulation pump low' },
        { 'source': 'stopping circulation pump low', 'trigger': 'timeout',  'dest': 'waiting before restart low', 'after': 'turn_circulation_pump_off' },

        { 'source': 'waiting before restart low',    'trigger': 'full',     'dest': 'waiting before restart low' },
        { 'source': 'waiting before restart low',    'trigger': 'low',      'dest': 'waiting before restart low' },
        { 'source': 'waiting before restart low',    'trigger': 'critical', 'dest': 'waiting before restart low' },
        { 'source': 'waiting before restart low',    'trigger': 'tick',     'dest': 'waiting before restart low' },
        { 'source': 'waiting before restart low',    'trigger': 'hot',      'dest': 'waiting before restart low' },
        { 'source': 'waiting before restart low',    'trigger': 'cold',     'dest': 'waiting before restart low' },
        { 'source': 'waiting before restart low',    'trigger': 'timeout',  'dest': 'off' },

        { 'source': 'stopping circulation pump hot', 'trigger': 'full',     'dest': 'stopping circulation pump hot' },
        { 'source': 'stopping circulation pump hot', 'trigger': 'low',      'dest': 'stopping circulation pump hot' },
        { 'source': 'stopping circulation pump hot', 'trigger': 'critical', 'dest': 'stopping circulation pump hot' },
        { 'source': 'stopping circulation pump hot', 'trigger': 'tick',     'dest': 'stopping circulation pump hot' },
        { 'source': 'stopping circulation pump hot', 'trigger': 'hot',      'dest': 'stopping circulation pump hot' },
        { 'source': 'stopping circulation pump hot', 'trigger': 'cold',     'dest': 'stopping circulation pump hot' },
        { 'source': 'stopping circulation pump hot', 'trigger': 'timeout',  'dest': 'waiting before restart hot', 'after': 'turn_circulation_pump_off' },

        { 'source': 'waiting before restart hot',    'trigger': 'full',     'dest': 'waiting before restart hot' },
        { 'source': 'waiting before restart hot',    'trigger': 'low',      'dest': 'waiting before restart hot' },
        { 'source': 'waiting before restart hot',    'trigger': 'critical', 'dest': 'waiting before restart hot' },
        { 'source': 'waiting before restart hot',    'trigger': 'tick',     'dest': 'waiting before restart hot' },
        { 'source': 'waiting before restart hot',    'trigger': 'hot',      'dest': 'waiting before restart hot' },
        { 'source': 'waiting before restart hot',    'trigger': 'cold',     'dest': 'waiting before restart hot' },
        { 'source': 'waiting before restart hot',    'trigger': 'timeout',  'dest': 'hot' },

        { 'source': 'hot', 'trigger': 'full',     'dest': 'hot' },
        { 'source': 'hot', 'trigger': 'low',      'dest': 'hot' },
        { 'source': 'hot', 'trigger': 'critical', 'dest': 'hot' },
        { 'source': 'hot', 'trigger': 'tick',     'dest': 'hot' },
        { 'source': 'hot', 'trigger': 'hot',      'dest': 'hot' },
        { 'source': 'hot', 'trigger': 'cold',     'dest': 'off' },
    ]

    def __init__(self):
        self.e = esmart.esmart()
        self.e.connect((ESMART_HOST, ESMART_PORT))


        self.machine = Machine(model=self, states=esmartfsm.states, transitions=esmartfsm.transitions, initial='off')
        self.heattrap = serial.Serial(HEATTRAP, baudrate=9600, timeout=0)
        self.piface = pifacedigitalio.PiFaceDigital()

        self.piface.relays[HEAT_PUMP_RELAY].value = 0
        self.piface.relays[CIRCULATION_PUMP_RELAY].value = 0

        self.line = bytearray()
        self.ticker = 0
        self.timer = None

    def request_data(self):
        if self.timer and time.time() >= self.timer:
            print("DELAY EXPIRED", flush=True)
            self.timer = None
            self.timeout()
        else:
            timebefore = time.time()
            readable, writable, exceptional = select.select([self.heattrap], [], [], self.ticker)

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
                    self.hot()
                elif tempsensors[1] <= COLD_DEGREES:
                    self.cold()
                else:
                    self.tick()
            else:
                self.ticker -= time.time() - timebefore
                if self.ticker > 0:
                    self.tick()
                else:
                    data = self.e.read()

                    charge_mode = esmart.DEVICE_MODE[data['chg_mode']]
                    time_now = datetime.datetime.now().replace(microsecond=0).isoformat()

                    def print_charge_status(status):
                        print('%s Charge mode: %s Battery %.1fV %.1fA - %s' % (time_now, charge_mode, data['bat_volt'], data['chg_cur'], status), flush=True)

                    if ( charge_mode == 'FLOAT' ) or \
                    ( data['bat_volt'] >= FULL_VOLT and data['chg_cur'] < FULL_CUR):
                        print_charge_status('FULL')
                        self.full()
                    elif data['bat_volt'] < CRITICAL_VOLT:
                        print_charge_status('CRITICAL')
                        self.critical()
                    elif data['bat_volt'] < LOW_VOLT:
                        print_charge_status('LOW')
                        self.low()
                    else:
                        print_charge_status('TICK')
                        self.tick()

                    self.ticker = TICK_SECS


    def turn_pumps_on(self):
        print("TURN PUMP ON", flush=True)
        self.piface.relays[CIRCULATION_PUMP_RELAY].value = 1
        self.piface.relays[HEAT_PUMP_RELAY].value = 1

    def turn_heat_pump_off(self):
        print("TURN HEAT PUMP OFF", flush=True)
        self.piface.relays[HEAT_PUMP_RELAY].value = 0
        self.timer = time.time() + CIRCULATION_DELAY_SECS

    def turn_circulation_pump_off(self):
        print("TURN CIRCULATION PUMP OFF", flush=True)
        self.piface.relays[CIRCULATION_PUMP_RELAY].value = 0
        self.timer = time.time() + RESTART_DELAY_SECS

    def set_low_battery_timer(self):
        print("SETTING LOW BATTERY TIMEOUT", flush=True)
        self.timer = time.time() + LOW_BATTERY_TIMEOUT

    def cancel_timer(self):
        self.timer = None

def sigint_handler(sig, frame):
    print('EXIT', flush=True)
    self.piface.relays[HEAT_PUMP_RELAY].value = 0
    self.piface.relays[CIRCULATION_PUMP_RELAY].value = 0
    sys.exit(0)

signal.signal(signal.SIGINT, sigint_handler)
fsm = esmartfsm()
try:
    while True:
        fsm.request_data()
except:
    print('EXCEPTION', flush=True)
    fsm.piface.relays[HEAT_PUMP_RELAY].value = 0
    fsm.piface.relays[CIRCULATION_PUMP_RELAY].value = 0
