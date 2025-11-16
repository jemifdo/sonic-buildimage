#!/bin/bash
REBOOT_CAUSE_DIR="/host/reboot-cause"
HW_REBOOT_CAUSE_FILE="/host/reboot-cause/hw-reboot-cause.txt"
REBOOT_TIME=$(date)

if [ $# -lt 1 ]; then
    echo "Require reboot type"
    exit 1
fi

if [ ! -d "$REBOOT_CAUSE_DIR" ]; then
    mkdir $REBOOT_CAUSE_DIR
fi

echo "Reason:$1,Time:${REBOOT_TIME}" > ${HW_REBOOT_CAUSE_FILE}

# Best effort to write buffered data onto the disk
sync ; sync ; sync ; sleep 3

# Set System LED to booting pattern
echo "alternate_blink_4hz" > /sys/bus/platform/devices/sys_cpld/sys_led

# CPLD CPU cold power-cycle
if [ $# -eq 2 ] && [ "$2" == "skip-poe" ]; then
    i2cset -f -y 1 0x32 0x56 0x01
    i2cset -f -y 1 0x32 0x18 0x06
else
    i2cset -f -y 1 0x32 0x18 0x06
fi

# System should reboot by now and avoid the script returning to caller
sleep 10

exit 0
