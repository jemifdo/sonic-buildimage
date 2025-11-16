try:
    from sonic_platform_pddf_base.pddf_psu import PddfPsu
    from sonic_py_common import device_info
    from sonic_platform.thermal import Thermal
except ImportError as e:
    raise ImportError (str(e) + "- required module not found")

psu_thermal_sensors = {
    # <sensor-name>: <psu_thermal_index>
    'SR Temp': 1,
    'PFC Temp': 2,
}

PLATFORM_SPECIFIC_MODULE_NAME = "psuutil"
PLATFORM_SPECIFIC_CLASS_NAME = "PsuUtil"

class Psu(PddfPsu):
    """PDDF Platform-Specific PSU class"""
    
    PLATFORM_PSU_CAPACITY = "550"
    PLATFORM_POE_PSU_CAPACITY = "1600"

    def __init__(self, index, pddf_data=None, pddf_plugin_data=None):
        PddfPsu.__init__(self, index, pddf_data, pddf_plugin_data)
        (self.platform_name, self.hwsku) = device_info.get_platform_and_hwsku()

        for thermal_name, thermal_index in psu_thermal_sensors.items():
            psu_thermal = Thermal(thermal_index, None, None, True, self.psu_index)
            obj_name = "PSU {0} {1}"
            psu_thermal.thermal_obj_name = obj_name.format(self.psu_index, thermal_name)
            self._thermal_list.append(psu_thermal)

    # Provide the functions/variables below for which implementation is to be overwritten
    def get_capacity(self):
        """
        Gets the capacity (maximum output power) of the PSU in watts

        Returns:
            An integer, the capacity of PSU
        """
        model_name = super().get_model() 
        if self.PLATFORM_POE_PSU_CAPACITY in model_name:
            return (self.PLATFORM_POE_PSU_CAPACITY)
        else:
            return (self.PLATFORM_PSU_CAPACITY)

    def get_type(self):
        """
        Gets the type of the PSU

        Returns:
            A string, the type of PSU (AC/DC)
        """
        ptype = "AC"

        # This platform supports AC PSU
        return ptype

    def is_replaceable(self):
        """
        Indicate whether this device is replaceable.
        Returns:
            bool: True if it is replaceable.
        """
        return True

    def get_position_in_parent(self):
        """
        Retrieves the psu index number
        """
        return self.psu_index

    def get_revision(self):
        return "N/A"

    def temperature(self):
        return self.get_temperature()

    def get_voltage_high_threshold(self):
        """
        Retrieves the high threshold PSU voltage output
        Returns:
            A float number, the high threshold output voltage in volts,
            e.g. 12.1
        """
        model_name = super().get_model() 
        if self.PLATFORM_POE_PSU_CAPACITY in model_name:
            return 56.135
        else:
            return 12.6

    def get_voltage_low_threshold(self):
        """
        Retrieves the low threshold PSU voltage output
        Returns:
            A float number, the low threshold output voltage in volts,
            e.g. 12.1
        """
        model_name = super().get_model() 
        if self.PLATFORM_POE_PSU_CAPACITY in model_name:
            return 52.865
        else:
            return 11.4

    def set_status_led(self, color):
        index = str(self.psu_index-1)

        from sonic_py_common import daemon_base

        platform_psuutil = self.load_platform_util(PLATFORM_SPECIFIC_MODULE_NAME, PLATFORM_SPECIFIC_CLASS_NAME)
        num_psus = platform_psuutil.get_num_psus()
        count = 0;
        for psu_index in range(1, num_psus+1):
            if platform_psuutil.get_psu_presence(psu_index) is True:
                if self.get_psu_status(self, psu_index) is True:
                    count = count + 1

        color = "amber"

        if count == num_psus:
            color = "green"

        led_device_name = "PSU{}"+"_LED"

        result, msg = self.pddf_obj.is_supported_sysled_state(led_device_name, color)
        if result == False:
            print(msg)
            return (False)

        device_name = self.pddf_obj.data[led_device_name]['dev_info']['device_name']
        self.pddf_obj.create_attr('device_name', device_name,  self.pddf_obj.get_led_path())
        self.pddf_obj.create_attr('index', index, self.pddf_obj.get_led_path())
        self.pddf_obj.create_attr('color', color, self.pddf_obj.get_led_cur_state_path())
        self.pddf_obj.create_attr('dev_ops', 'set_status',  self.pddf_obj.get_led_path())
        return (True)

    def get_voltage(self):
        """
        Retrieves current PSU voltage output

        Returns:
            A float number, the output voltage in volts,
            e.g. 12.1
        """
        # When AC power is not plugged into one of the PSU, the FAN of
        # that PSU is driven using the power from the alternate PSU and
        # because of this the PSU VOUT might read a small voltage value
        # and it is misleading. Therefore the PSU VOUT is fetched from
        # HW only when PSU status is OK
        if self.get_status():
            return super().get_voltage()

        return 0.0

    def get_status_led(self):
        """
        Gets the state of the PSU status LED

        Returns:
            A string, one of the predefined STATUS_LED_COLOR_* strings above
        """
        if self.get_presence():
            if self.get_powergood_status():
                return self.STATUS_LED_COLOR_GREEN
            else:
                return self.STATUS_LED_COLOR_AMBER

        return self.STATUS_LED_COLOR_OFF

    def get_fan_dir(self):
        """
        Gets the direction of the PSU fan

        Returns:
            A string "FB" or "BF"
        """
        model_name = super().get_model()
        if len(model_name) > 0:
            direction = model_name[11]
            if direction == 'R':
                return "BF"
            return "FB"
        else:
            return "Unknown"

