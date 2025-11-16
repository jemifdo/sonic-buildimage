try:
    from sonic_platform_pddf_base.pddf_fan import PddfFan
    from sonic_py_common import device_info

    import subprocess
except ImportError as e:
    raise ImportError(str(e) + "- required module not found")
# ------------------------------------------------------------------
# HISTORY:
#    5/1/2022 (A.D.)
#    add function:set_status_led,
#    Solve the problem that when a fan is pulled out, the Fan LED on the front panel is still green Issue-#11525
# ------------------------------------------------------------------

MIN_SPEED = 30

class Fan(PddfFan):
    """PDDF Platform-Specific Fan class"""
    PLATFORM_POE_PSU_CAPACITY = "1600"

    def __init__(self, tray_idx, fan_idx=0, pddf_data=None, pddf_plugin_data=None, is_psu_fan=False, psu_index=0):
        # idx is 0-based
        PddfFan.__init__(self, tray_idx, fan_idx, pddf_data, pddf_plugin_data, is_psu_fan, psu_index)

        self.fan_led_status = "green"
        if psu_index == 1:
            psu_model = open("/sys/bus/i2c/devices/4-0058/psu_model_name", 'r')
        else:
            psu_model = open("/sys/bus/i2c/devices/8-0059/psu_model_name", 'r')

        if is_psu_fan:
            model_name = psu_model.read()
            if self.PLATFORM_POE_PSU_CAPACITY in model_name:
                self.max_speed_rpm = 26000 
            else:
                self.max_speed_rpm = 18000 

    def get_speed_tolerance(self):
        """
        Retrieves the speed tolerance of the fan

        Returns:
            An integer, the percentage of variance from target speed which is
                 considered tolerable
        """
        if not self.is_psu_fan:
            return 25 #As specified in HW spec and Thermal Threshold spec
        else:
            return 15 #550/920/1600W PSUs have the same tolerance

    def get_presence(self):
        if self.is_psu_fan:
            #For PSU, FAN must be present when PSU is present
            try:
                cmd = ['i2cget', '-y', '-f', '0x2', '0x32', '0x41']
                p = subprocess.Popen(cmd, stdout=subprocess.PIPE, universal_newlines=True)
                data = p.communicate()
                status = int(data[0].strip(), 16)
                if (self.fans_psu_index == 1 and (status & 0x10) == 0) or \
                    (self.fans_psu_index == 2 and (status & 0x20) == 0):
                    return True
            except (IOError, ValueError):
                pass

            return False
        else:
            # System fans are fixed. so considered as always present.
            return True

    def get_direction(self):
        """
        Retrieves the direction of fan

        Returns:
            A string, either FAN_DIRECTION_INTAKE or FAN_DIRECTION_EXHAUST
            depending on fan direction
        """
        if self.is_psu_fan:
            # PSU module only has EXHAUST fan
            return "EXHAUST"
        else:
            return super().get_direction()

    def get_status_led(self):
        """
        Gets the state of the fan status LED

        Returns:
            A string, one of the predefined STATUS_LED_COLOR_* strings above
        """
        if self.is_psu_fan:
            return "N/A"
        # Returning the cached per fan status and not the global fan status 
        return self.fan_led_status

    def set_status_led(self, color):
        """
        Sets the Global state of the fan module status LED

        Args:
            color: A string representing the color with which to set the
                   fan module status LED

        Returns:
            bool: True if status LED state is set successfully, False if not
        """
        if self.is_psu_fan:
            return False

        self.fan_led_status = color
        return self._chassis.set_global_fan_led_status()

    def set_chassis(self, driver):
        self._chassis = driver

    def get_fan_led_status(self):
        return self.fan_led_status

    def get_status(self):
        if not self.is_psu_fan:
            if not self.get_presence():
                return False

            # FANs must not be operated below MIN_SPEED
            target_speed = self.get_target_speed()
            if target_speed < MIN_SPEED:
                return False

            return True

        return super().get_status()

