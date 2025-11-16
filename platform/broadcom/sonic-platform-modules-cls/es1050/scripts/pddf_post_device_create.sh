#!/bin/bash
# Enable FAN WDT
#sudo i2cset -y -f 0 0x32 0x30 0x01

# Set all FAN speed to 40%
sudo i2cset -y -f 1 0x32 0x32 0x66
sudo i2cset -y -f 1 0x32 0x36 0x66
sudo i2cset -y -f 1 0x32 0x3a 0x66
sudo i2cset -y -f 1 0x32 0x3d 0x66

# Set FAN LED status to GREEN
sudo i2cset -y -f 1 0x32 0x33 0x1
sudo i2cset -y -f 1 0x32 0x37 0x1
sudo i2cset -y -f 1 0x32 0x3b 0x1
sudo i2cset -y -f 1 0x32 0x3e 0x1

# Set Alarm LED status to OFF, since it is unused in SONiC
sudo i2cset -y -f 1 0x32 0x44 0x00

# Set SYS LED status to GREEN
sudo i2cset -y -f 1 0x32 0x43 0xec

echo -2 | tee /sys/bus/i2c/drivers/pca954x/*-00*/idle_state

#Pressure sensor
echo "mpl3115 0x60" > /sys/bus/i2c/devices/i2c-17/new_device

# Unmasking PoE reset mask
sudo i2cset -y -f 1 0x32 0x56 0x00

# Setting Semi Automatic mode
sudo i2cset -y -f 1 0x32 0xa9 0x00
