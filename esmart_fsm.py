#!/usr/bin/python3
# -*- coding: utf-8 -*-

import esmart
import time
import datetime
from transitions import Machine
import signal
import sys

TICK_SECS = 5
FULL_VOLT = 28.4
FULL_CUR = 20
LOW_VOLT = 24.8

HOST='localhost'
PORT=8888

class esmartfsm(object):
    states  = ['off', 'on', 'delayed']

    transitions = [
        { 'trigger': 'full',    'source': 'off',     'dest': 'on',      'after': 'request_esmart_data' },
        { 'trigger': 'full',    'source': 'on',      'dest': 'on',      'after': 'request_esmart_data' },
        { 'trigger': 'low',     'source': 'on',      'dest': 'delayed', 'after': 'start_delay_timer'  },
        { 'trigger': 'low',     'source': 'off',     'dest': 'off',     'after': 'request_esmart_data'  },
        { 'trigger': 'timeout', 'source': 'delayed', 'dest': 'off',     'after': 'request_esmart_data' },
        { 'trigger': 'tick',    'source': 'off',     'dest': 'off',     'after': 'request_esmart_data' },
        { 'trigger': 'tick',    'source': 'on',      'dest': 'on',      'after': 'request_esmart_data' }
    ]

    def __init__(self):
        self.e = esmart.esmart()
        #self.e.open("/dev/ttyUSB0")
        self.e.connect((HOST, PORT))

        self.machine = Machine(model=self, states=esmartfsm.states, transitions=esmartfsm.transitions, initial='off')

    def request_esmart_data(self):
        time.sleep(TICK_SECS)
        data = self.e.read()

        charge_mode = esmart.DEVICE_MODE[data['chg_mode']]
        time_now = datetime.datetime.now().replace(microsecond=0).isoformat()
        if ( charge_mode in ['CV', 'FLOAT'] ) or \
           ( charge_mode == 'CC' and data['bat_volt'] == FULL_VOLT and d['chg_cur'] < FULL_CUR):
            print('%s Charge mode: %s Battery %.1fV %.1fA - FULL' % (time_now, charge_mode, data['bat_volt'], data['chg_cur']))
            fsm.full()
        elif data['bat_volt'] < LOW_VOLT:
            print('%s Charge mode: %s Battery %.1fV %.1fA - LOW' % (time_now, charge_mode, data['bat_volt'], data['chg_cur']))
            fsm.low()
        else:
            print('%s Charge mode: %s Battery %.1fV %.1fA - TICK' % (time_now, charge_mode, data['bat_volt'], data['chg_cur']))
            fsm.tick()

    def start_delay_timer(self):
        time.sleep(DELAY_SECS)
        self.timeout()

    def on_enter_on(self):
        print("TURN PUMP ON")

    def off_delayed_on(self):
        print("TURN PUMP OFF")

def sigint_handler(sig, frame):
        print('EXIT')
        sys.exit(0)

signal.signal(signal.SIGINT, sigint_handler)
fsm = esmartfsm()
fsm.tick()
