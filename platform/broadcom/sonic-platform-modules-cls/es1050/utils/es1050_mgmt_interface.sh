#!/bin/bash

#Due to the hardware design, this platform uses "eth2" instead of "eth0" as management interface.
#Rename eth2 to eth0 using udev

systemctl start systemd-udevd

/etc/init.d/netfilter-persistent stop
udevadm control --reload-rules
udevadm trigger
/etc/init.d/netfilter-persistent start
