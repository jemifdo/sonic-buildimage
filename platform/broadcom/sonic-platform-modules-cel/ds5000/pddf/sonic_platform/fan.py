#!/usr/bin/env python

#############################################################################
# Celestica
#
# Component contains an implementation of SONiC Platform Base API and
# provides the fan management function
#
#############################################################################

try:
    from sonic_platform_pddf_base.pddf_fan import PddfFan
    from .helper import APIHelper       
except ImportError as e:
    raise ImportError(str(e) + "- required module not found")

FAN_LED_SYSFS_PATH = "/sys/devices/platform/sys_cpld/fan{}_led"

class Fan(PddfFan):
    """PDDF Platform-Specific Fan class"""

    def __init__(self, tray_idx, fan_idx=0, pddf_data=None, pddf_plugin_data=None, is_psu_fan=False, psu_index=0):
        # idx is 0-based 
        PddfFan.__init__(self, tray_idx, fan_idx, pddf_data, pddf_plugin_data, is_psu_fan, psu_index)
        self._api_helper = APIHelper()
        self.target_speed = 0

    # Provide the functions/variables below for which implementation is to be overwritten

    # Open BMC does not support OEM command and unable to fetch below attributes
    # Hence the API override

    def get_direction(self):
        """
        Retrieves the direction of fan

        Returns:
            A string, either FAN_DIRECTION_INTAKE or FAN_DIRECTION_EXHAUST
            depending on fan direction
        """
        # DS5000 has only one FAN type
        return self.FAN_DIRECTION_EXHAUST

    def get_target_speed(self):
        """
        Retrieves the target (expected) speed of the fan

        Returns:
            An integer, the percentage of full fan speed, in the range 0 (off)
                 to 100 (full speed)
        """ 
        target_speed = 0
        fan_pwm_file = "/sys/devices/platform/sys_cpld/fan{}_pwm"
        if self.is_psu_fan:
            # Target speed not usually supported for PSU fans
            raise NotImplementedError
        else:
            try:
                with open(fan_pwm_file.format(self.fantray_index)) as fd:
                    data = fd.read()

                data = int(data, 16)
                if data > 0 and data < 255:
                    # pwm to percentage conversion
                    target_speed = (data * 100) / 255
            except (FileNotFoundError, IOError):
                pass

        return round(target_speed)

    def get_status_led(self):
        led_color = "unknown"
        try:
            with open(FAN_LED_SYSFS_PATH.format(self.fantray_index), "r") as fd:
                led_color = fd.read().strip()
        except (FileNotFoundError, IOError):
            pass

        return led_color

    def set_status_led(self, color):
        # BMC controls the FAN LEDs
        if self._api_helper.with_bmc():
            raise NotImplementedError

        try:
            with open(FAN_LED_SYSFS_PATH.format(self.fantray_index), "w") as fd:
                fd.write(color)
        except (FileNotFoundError, IOError):
            return False

        return True
