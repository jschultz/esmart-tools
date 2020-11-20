#!/usr/bin/python3
# -*- coding: utf-8 -*-

import esmart
import heattrap
import time
import datetime
from transitions import Machine
import sys
import re
import traceback
import logging
try:
    import pifacedigitalio
except ModuleNotFoundError:
    pass

# 48V setup
CELLS = 24

TICK_SECS = 5
FULL_VOLT = 14.2
FULL_VOLT_CV = 13.8
FULL_POWER = 600
LOW_VOLT = 12.4
CRITICAL_VOLT = 12.0
LOW_BATTERY_TIMEOUT = 120
CIRCULATION_DELAY_SECS = 30
RESTART_DELAY_SECS = 300
RETRY_SLEEP_SECS = 30
HOT_DEGREES = 55
COLD_DEGREES = 54

HEAT_PUMP_RELAY = 1
CIRCULATION_PUMP_RELAY = 0

ESMART_HOST='containerpi4.local'
ESMART_PORT=8888

HEATTRAP_PORT = "/dev/ttyACM0"

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logging.getLogger('transitions').setLevel(logging.WARNING)  # Set to INFO to see transitions logging

class esmartfsm(object):
    states  = ['off', 'on', 'starting circulation pump', 'waiting before stopping', 'stopping circulation pump low', 'waiting before restart low', 'stopping circulation pump hot', 'waiting before restart hot', 'hot']
    transitions = [
        { 'source': 'off', 'trigger': 'full',     'dest': 'starting circulation pump', 'after': ['turn_heat_pump_on', 'set_circulation_delay_timer'] },
        { 'source': 'off', 'trigger': 'low',      'dest': 'off' },
        { 'source': 'off', 'trigger': 'critical', 'dest': 'off' },
        { 'source': 'off', 'trigger': 'tick',     'dest': 'off' },
        { 'source': 'off', 'trigger': 'hot',      'dest': 'hot' },
        { 'source': 'off', 'trigger': 'cold',     'dest': 'off' },

        { 'source': 'starting circulation pump', 'trigger': 'full',     'dest': 'starting circulation pump' },
        { 'source': 'starting circulation pump', 'trigger': 'low',      'dest': 'starting circulation pump' },
        { 'source': 'starting circulation pump', 'trigger': 'critical', 'dest': 'off',                       'after': ['cancel_timer', 'turn_heat_pump_off'] },
        { 'source': 'starting circulation pump', 'trigger': 'tick',     'dest': 'starting circulation pump' },
        { 'source': 'starting circulation pump', 'trigger': 'hot',      'dest': 'hot',                       'after': ['cancel_timer', 'turn_heat_pump_off'] },
        { 'source': 'starting circulation pump', 'trigger': 'cold',     'dest': 'starting circulation pump' },
        { 'source': 'starting circulation pump', 'trigger': 'timeout',  'dest': 'on',                        'after': ['turn_circulation_pump_on'] },

        { 'source': 'on',  'trigger': 'full',     'dest': 'on' },
        { 'source': 'on',  'trigger': 'low',      'dest': 'waiting before stopping',       'after': ['set_low_battery_timer'] },
        { 'source': 'on',  'trigger': 'critical', 'dest': 'stopping circulation pump low', 'after': ['turn_heat_pump_off', 'set_circulation_delay_timer'] },
        { 'source': 'on',  'trigger': 'tick',     'dest': 'on' },
        { 'source': 'on',  'trigger': 'hot',      'dest': 'stopping circulation pump hot', 'after': ['turn_heat_pump_off', 'set_circulation_delay_timer'] },
        { 'source': 'on',  'trigger': 'cold',     'dest': 'on' },

        { 'source': 'waiting before stopping', 'trigger': 'full',     'dest': 'on',                            'after': ['cancel_timer'] },
        { 'source': 'waiting before stopping', 'trigger': 'low',      'dest': 'waiting before stopping' },
        { 'source': 'waiting before stopping', 'trigger': 'critical', 'dest': 'stopping circulation pump low', 'after': ['turn_heat_pump_off', 'set_circulation_delay_timer'] },
        { 'source': 'waiting before stopping', 'trigger': 'tick',     'dest': 'on',                            'after': ['cancel_timer'] },
        { 'source': 'waiting before stopping', 'trigger': 'hot',      'dest': 'stopping circulation pump hot', 'after': ['turn_heat_pump_off', 'set_circulation_delay_timer'] },
        { 'source': 'waiting before stopping', 'trigger': 'cold',     'dest': 'waiting before stopping' },
        { 'source': 'waiting before stopping', 'trigger': 'timeout',  'dest': 'stopping circulation pump low', 'after': ['turn_heat_pump_off', 'set_circulation_delay_timer'] },

        { 'source': 'stopping circulation pump low', 'trigger': 'full',     'dest': 'stopping circulation pump low' },
        { 'source': 'stopping circulation pump low', 'trigger': 'low',      'dest': 'stopping circulation pump low' },
        { 'source': 'stopping circulation pump low', 'trigger': 'critical', 'dest': 'stopping circulation pump low' },
        { 'source': 'stopping circulation pump low', 'trigger': 'tick',     'dest': 'stopping circulation pump low' },
        { 'source': 'stopping circulation pump low', 'trigger': 'hot',      'dest': 'stopping circulation pump low' },
        { 'source': 'stopping circulation pump low', 'trigger': 'cold',     'dest': 'stopping circulation pump low' },
        { 'source': 'stopping circulation pump low', 'trigger': 'timeout',  'dest': 'waiting before restart low', 'after': ['turn_circulation_pump_off', 'set_restart_delay_timer'] },

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
        { 'source': 'stopping circulation pump hot', 'trigger': 'timeout',  'dest': 'waiting before restart hot', 'after': ['turn_circulation_pump_off', 'set_restart_delay_timer'] },

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

        self.piface = pifacedigitalio.PiFaceDigital() if 'pifacedigitalio' in sys.modules else None

        self.turn_heat_pump_off()
        self.turn_circulation_pump_off()

        self.heattrap = heattrap.heattrap(HEATTRAP_PORT)

        self.esmart = esmart.esmart()
        self.esmart.connect((ESMART_HOST, ESMART_PORT))

        self.machine = Machine(model=self, states=esmartfsm.states, transitions=esmartfsm.transitions, initial='off')

        self.ticker = 0
        self.timer = None

    def request_data(self):
        if self.timer and time.time() >= self.timer:
            logging.info('DELAY EXPIRED')
            self.timer = None
            self.timeout()
        else:
            timebefore = time.time()
            tempsensors = self.heattrap.read(self.ticker)
            self.ticker -= time.time() - timebefore
            if tempsensors:

                def log_temp_sensors(status):
                    logging.info('Temperature sensors: %s - %s' % (tempsensors, status))

                if tempsensors[1] >= HOT_DEGREES:
                    log_temp_sensors('HOT')
                    self.hot()
                elif tempsensors[1] <= COLD_DEGREES:
                    log_temp_sensors('COLD')
                    self.cold()
                else:
                    log_temp_sensors('')
            else:
                if self.ticker <= 0:
                    data = self.esmart.read()
                    print(data)

                    charge_mode = esmart.DEVICE_MODE[data['chg_mode']]

                    def log_charge_status(status):
                        logging.info('Charge mode: %s Battery %.1fV %.1fA - %s' % (charge_mode, data['bat_volt'], data['chg_cur'], status))

                    if ( ( charge_mode == 'CV' and data['bat_volt'] >= FULL_VOLT_CV * CELLS / 6 ) or data['bat_volt'] >= FULL_VOLT * CELLS / 6 ) and data['chg_cur'] < FULL_POWER / (CELLS * 2.0):
                        log_charge_status('FULL')
                        self.full()
                    elif data['bat_volt'] < CRITICAL_VOLT * CELLS / 6:
                        log_charge_status('CRITICAL')
                        self.critical()
                    elif data['bat_volt'] < LOW_VOLT * CELLS / 6:
                        log_charge_status('LOW')
                        self.low()
                    else:
                        log_charge_status('TICK')
                        self.tick()

                    self.ticker = TICK_SECS

    def turn_heat_pump_on(self):
        logging.info('TURN HEAT PUMP ON')
        if self.piface:
            self.piface.relays[HEAT_PUMP_RELAY].value = 1

    def set_circulation_delay_timer(self):
        logging.info('SET CIRCULATION DELAY TIMER')
        self.timer = time.time() + CIRCULATION_DELAY_SECS

    def turn_circulation_pump_on(self):
        logging.info('TURN CIRCULATION PUMP ON')
        if self.piface:
            self.piface.relays[CIRCULATION_PUMP_RELAY].value = 1

    def turn_heat_pump_off(self):
        logging.info('TURN HEAT PUMP OFF')
        if self.piface:
            self.piface.relays[HEAT_PUMP_RELAY].value = 0

    def turn_circulation_pump_off(self):
        logging.info('TURN CIRCULATION PUMP OFF')
        if self.piface:
            self.piface.relays[CIRCULATION_PUMP_RELAY].value = 0

    def set_restart_delay_timer(self):
        logging.info('SET RESTART DELAY TIMER')
        self.timer = time.time() + RESTART_DELAY_SECS

    def set_low_battery_timer(self):
        logging.info('SET LOW BATTERY TIMER')
        self.timer = time.time() + LOW_BATTERY_TIMEOUT

    def cancel_timer(self):
        logging.info('CANCELLING TIMER')
        self.timer = None

fsm = None
logging.info('STARTING DAEMON')
while True:
    try:
        if not fsm:
            fsm = esmartfsm()
        fsm.request_data()

    except Exception as exception:
        if fsm:
            fsm.turn_heat_pump_off()
            fsm.turn_circulation_pump_off()
            #fsm.piface.relays[HEAT_PUMP_RELAY].value = 0
            #fsm.piface.relays[CIRCULATION_PUMP_RELAY].value = 0
            del(fsm)
            fsm = None

        logging.info(traceback.format_exc())
        logging.info(exception)
        logging.info('SLEEPING BEFORE RETRYING')
        time.sleep(RETRY_SLEEP_SECS)
        continue
