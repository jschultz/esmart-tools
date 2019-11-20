# esmart-tools

## Acknowledgements

This code is heavily based on the [work](https://github.com/skagmo/esmart_mppt) by @skagmo who did the hard work of figuring out how to communicate with the eSmart3 MPPT charger.

## What is this?

I have just written a few scripts to control my [Heat Trap Solar](heat-trap.com.au) hot water system based on the state of charge of my batteries as best it can be judged by the battery voltage and charging current revealed by the charger.

Since my charger and hot water system are not in the same location, I use the script [esmart_server.py](esmart_server.py) to accept socket connections and relay data to and from the charger over that connection. The script [esmart_fsm.py](esmart_fsm.py) runs a simply finite state machine to turn the hot water system and and off based on some simple parameters as follows:

1. If the charge mode is FLOAT or battery voltage is >= FULL_VOLT and the charge current is < FULL_CUR then the hot water system is turned on.
2. If the battery voltage falls below LOW_VOLT the hot water system is turned off, and cannot be turned on again before DELAY_SECS seconds have elapsed.