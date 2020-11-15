#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# eSmart USB to TCP server
#
# Copyright (2019) Jonathan Schultz
#

import esmart

ESMART_PORT='/dev/ttyUSB0'

esmart = esmart.esmart()
esmart.open(ESMART_PORT)
data = esmart.read()
print(data)
