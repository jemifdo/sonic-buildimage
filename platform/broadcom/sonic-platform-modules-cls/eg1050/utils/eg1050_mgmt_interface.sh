#!/bin/bash

#Due to the hardware design, mamangement interface is set as "eth2"
#Rename eth2 to eth0 using udev

systemctl start systemd-udevd

/etc/init.d/netfilter-persistent stop
udevadm control --reload-rules
udevadm trigger
/etc/init.d/netfilter-persistent start
