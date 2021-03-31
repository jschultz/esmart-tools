#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# eSmart USB to TCP server
#
# Copyright (2019) Jonathan Schultz
#

import serial
import socket
import select
import queue

HOST=''
PORT=8888
ESMART="/dev/ttyUSB{}"

n = 0
while True:
    try:
        serdevice = ESMART.format(n)
        ser = serial.Serial(serdevice, 9600, timeout=0.1)
        break
    except serial.serialutil.SerialException:
        n += 1
        if n == 10: # Arbitrary
            raise RuntimeError('Can''t connect to eSmart.')

server = socket.socket()
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind((HOST, PORT))
server.listen(5)

inputs = [server]
outputs = []
message_queues = {}

while inputs:
    readable, writable, exceptional = select.select(inputs, outputs, inputs)
    for s in readable:
        if s is server:
            connection, client_address = s.accept()
            connection.setblocking(0)
            inputs.append(connection)
            message_queues[connection] = queue.Queue()
        else:
            data = s.recv(1024)
            if data:
                try:
                    ser.write(data)
                except serial.serialutil.SerialException:
                    # https://stackoverflow.com/questions/33441579/io-error-errno-5-with-long-term-serial-connection-in-python
                    ser.close()
                    ser = serial.Serial(serdevice, 9600, timeout=0.1)
                    ser.write(data)

                reply = ser.read(1024)
                message_queues[s].put(reply)
                if s not in outputs:
                    outputs.append(s)
            else:
                if s in outputs:
                    outputs.remove(s)
                inputs.remove(s)
                s.close()
                del message_queues[s]

    for s in writable:
        try:
            next_msg = message_queues[s].get_nowait()
        except queue.Empty:
            outputs.remove(s)
        else:
            s.send(next_msg)

    for s in exceptional:
        inputs.remove(s)
        if s in outputs:
            outputs.remove(s)
        s.close()
        del message_queues[s]

server.close()