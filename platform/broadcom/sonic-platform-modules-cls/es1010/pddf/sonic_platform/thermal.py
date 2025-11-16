try:
    from sonic_platform_pddf_base.pddf_thermal import PddfThermal
    from sonic_platform import platform
except ImportError as e:
    raise ImportError(str(e) + "- required module not found")

import subprocess

HIGH_THRESHOLD = 0
LOW_THRESHOLD = 1
HIGH_CRIT_THRESHOLD = 2
LOW_CRIT_THRESHOLD = 3
NUM_SENSORS = 4
CPU_SENSOR_STR = "CPU core temp"

#Thermal limits for air intake chassis
thermal_limits_F2B = {
    # <sensor-name>: <high_thresh>, <low_thresh>, <high_crit_thresh>, <low_crit_thresh>
    #LM75_U10
    'System Front Left Temp':  [55.0, -5,   None, None],
    #LM75_U4
    'System Front Right Temp': [55.0, -5,   None, None],
    #LM75_U7
    'System Rear Right Temp':  [72.0, -5,   None, None],
    #LM75_U60
    'ASIC External Temp':      [72,   -5,   None,   None],
    CPU_SENSOR_STR:            [89.0, -5, None, None]
}

#Thermal limits for air exhaust chassis
thermal_limits_B2F = {
    # <sensor-name>: <high_thresh>, <low_thresh>, <high_crit_thresh>, <low_crit_thresh>
    #LM75_U10
    'System Front Left Temp':  [72.0, -5,   None, None],
    #LM75_U4
    'System Front Right Temp': [72.0, -5,   None, None],
    #LM75_U7
    'System Rear Right Temp':  [55.0, -5,   None, None],
    #LM75_U60
    'ASIC External Temp':      [72,   -5,   None, None],
    CPU_SENSOR_STR:            [89.0, -5, None, None]
}

psu_thermal_limits_550w = {
    # <sensor-name>: <high_thresh>, <low_thresh>, <high_crit_thresh>, <low_crit_thresh>, <thermal_index>, <psu_index>
    'PSU 1 Ambient Temp': [60,-35,None,None,1,1],
    'PSU 1 SR Temp':      [108,-35,None,None,2,1],
    'PSU 1 PFC Temp':     [95,-35,None,None,3,1],
    'PSU 2 Ambient Temp': [60,-35,None,None,1,2],
    'PSU 2 SR Temp':      [108,-35,None,None,2,2],
    'PSU 2 PFC Temp':     [95,-35,None,None,3,2]
}

psu_thermal_limits_1600w = {
    # <sensor-name>: <high_thresh>, <low_thresh>, <high_crit_thresh>, <low_crit_thresh>, <thermal_index>, <psu_index>
    'PSU 1 Ambient Temp': [67,-35,None,None,1,1],
    'PSU 1 SR Temp':      [95,-35,None,None,2,1],
    'PSU 1 PFC Temp':     [95,-35,None,None,3,1],
    'PSU 2 Ambient Temp': [67,-35,None,None,1,2],
    'PSU 2 SR Temp':      [95,-35,None,None,2,2],
    'PSU 2 PFC Temp':     [95,-35,None,None,3,2]
}
class Thermal(PddfThermal):
    """PDDF Platform-Specific Thermal class"""

    def __init__(self, index, pddf_data=None, pddf_plugin_data=None, is_psu_thermal=False, psu_index=0):
        # PDDF doesn't support CPU internal temperature sensor
        # Hence it is created from chassis init override and
        # handled appropriately in thermal APIs
        self.thermal_index = index + 1
        self.is_psu_thermal = is_psu_thermal

        if self.is_psu_thermal:
            self.psu_index = psu_index
        # AC5X Internal sensor, PSU SR and PSU PFC sensors are unaware to PDDF. Hence handled in platform code
        if self.thermal_index <= NUM_SENSORS and is_psu_thermal == False:
            PddfThermal.__init__(self, index, pddf_data, pddf_plugin_data, is_psu_thermal, psu_index)
        elif is_psu_thermal == True:
            if self.thermal_index == 1:
                PddfThermal.__init__(self, index, pddf_data, pddf_plugin_data, is_psu_thermal, psu_index)
                # Overriding the obj name for pddf created PSU thermal sensors only
                self.thermal_obj_name  = 'PSU {} Ambient Temp'.format(psu_index)
            else:
                self.thermals_psu_index = psu_index 


    # Provide the functions/variables below for which implementation is to be overwritten

    def get_thermal_limit(self):
        platform_chassis = platform.Platform().get_chassis()
        fan_dir = platform_chassis.chassis_fan_dir
        if fan_dir == "BF":
            return thermal_limits_B2F
        else:
            return thermal_limits_F2B

    def get_psu_thermal_limit(self):
        psu_limits = psu_thermal_limits_1600w
        platform_chassis = platform.Platform().get_chassis()
        psu=platform_chassis.get_psu(0)
        if psu.get_capacity() == "550":
            psu_limits = psu_thermal_limits_550w
        return psu_limits

    def get_name(self):
        if self.is_psu_thermal:
            return self.thermal_obj_name
        elif self.thermal_index <= NUM_SENSORS:
            return super().get_name()

        return CPU_SENSOR_STR

    def get_temperature(self):
        if self.is_psu_thermal:
            return self.__get_psu_temperature()
        elif self.thermal_index <= NUM_SENSORS:
            return super().get_temperature()

        temperature = 0.0
        cmd = ['cat', '/sys/devices/platform/coretemp.0/hwmon/hwmon1/temp1_input']
        try:
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, universal_newlines=True)
            data = p.communicate()
            temperature = int(data[0].strip())/1000.0
        except (IOError, ValueError):
            pass

        return temperature

    def get_low_threshold(self):
        if self.is_psu_thermal:
            psu_th_limit = self.get_psu_thermal_limit()
            psu_limit = psu_th_limit.get(self.get_name(), None)
            return psu_limit[LOW_THRESHOLD]

        thermal_limits = self.get_thermal_limit()
        thermal_limit = thermal_limits.get(self.get_name(), None)
        if thermal_limit != None:
            return thermal_limit[LOW_THRESHOLD]

        return None

    def psu_linear_data(self, data):
        data &= 0xFFFF
        expn = data >> 11
        data &= 0x7FF
        if (data & ( 1 << 10 )):
            val = float(data - 2048)
        else:
            val = float(data)

        if (expn & ( 1 << 4 )):
            res = val / (1 << (32 -expn))
        else:
            res = val * (1 << expn)
        return res

    def __get_psu_temperature(self):
        if self.thermal_index == 1:
            return super().get_temperature()
        thermal_temp = None
        try:
            # CPLD Issue in PSU where other register 0x8f  not working TBD
            bus = '4'
            addr = '0x58'
            if self.psu_index == 2:
                bus = '8'
                addr = '0x59'
            if self.get_name() in "Ambient":
                cmd = ['i2cget', '-y', '-f', bus, addr, '0x8d', 'w']
            elif self.get_name() in "SR":
                cmd = ['i2cget', '-y', '-f', bus, addr, '0x8e', 'w']
            else:
                cmd = ['i2cget', '-y', '-f', bus, addr, '0x8f', 'w']
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, universal_newlines=True)
            data = p.communicate()
            temp = int(data[0].strip(), 16)
            thermal_temp = self.psu_linear_data(temp)
        except (IOError, ValueError):
            pass

        return thermal_temp

    def __get_psu_high_threshold(self):
        thermal_limit = None
        try:
            if self.psu_index == 1:
                cmd = ['i2cget', '-y', '-f', '4', '0x58', '0x51', 'w']
            else:
                cmd = ['i2cget', '-y', '-f', '8', '0x59', '0x51', 'w']
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, universal_newlines=True)
            data = p.communicate()
            temp = int(data[0].strip(), 16)
            thermal_limit = self.psu_linear_data(temp)
        except (IOError, ValueError):
            pass

        return thermal_limit

    def get_high_threshold(self):
        if self.is_psu_thermal:
            psu_th_limit = self.get_psu_thermal_limit()
            psu_limit = psu_th_limit.get(self.get_name(), None)
            return psu_limit[HIGH_THRESHOLD]

        thermal_limits = self.get_thermal_limit()
        thermal_limit = thermal_limits.get(self.get_name(), None)
        if thermal_limit != None:
            return thermal_limit[HIGH_THRESHOLD]

        return None

    def get_low_critical_threshold(self):
        if self.is_psu_thermal:
            psu_th_limit = self.get_psu_thermal_limit()
            psu_limit = psu_th_limit.get(self.get_name(), None)
            return psu_limit[LOW_CRIT_THRESHOLD]

        thermal_limits = self.get_thermal_limit()
        thermal_limit = thermal_limits.get(self.get_name(), None)
        if thermal_limit != None:
            return thermal_limit[LOW_CRIT_THRESHOLD]

        return None

    def get_high_critical_threshold(self):
        if self.is_psu_thermal:
            psu_th_limit = self.get_psu_thermal_limit()
            psu_limit = psu_th_limit.get(self.get_name(), None)
            return psu_limit[HIGH_CRIT_THRESHOLD]

        thermal_limits = self.get_thermal_limit()
        thermal_limit = thermal_limits.get(self.get_name(), None)
        if thermal_limit != None:
            return thermal_limit[HIGH_CRIT_THRESHOLD]

        return None

    def set_high_threshold(self, temperature):
        raise NotImplementedError

    def set_low_threshold(self, temperature):
        raise NotImplementedError
