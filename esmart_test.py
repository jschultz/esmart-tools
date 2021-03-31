#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# eSmart USB to TCP server
#
# Copyright (2020) Jonathan Schultz
#

import sys
import esmart

if len(sys.argv) > 1:
    ESMART_PORT=sys.argv[1]
else:
    ESMART_PORT = '/dev/ttyUSB1'

esmart = esmart.esmart()
esmart.open(ESMART_PORT)
data = esmart.read()
print(data)
