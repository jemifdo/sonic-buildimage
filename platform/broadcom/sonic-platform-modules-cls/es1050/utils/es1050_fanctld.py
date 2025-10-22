#!/usr/bin/python3
#
# Copyright (C) Celestica Technology Corporation
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

# ------------------------------------------------------------------
# HISTORY:
#    9/16/2021 (A.D.)
# ------------------------------------------------------------------

try:
    import sys
    import getopt
    import subprocess
    import time
    import signal
    from sonic_platform import platform
    from sonic_py_common import daemon_base
except ImportError as e:
    raise ImportError('%s - required module not found' % repr(e))

# Constants
NOMINAL_TEMP = 30 # degree C
MODULE_NAME = 'es1050fanctld'
# Constants for SENSOR_PARAM dict
SP_LOW_TEMP = 0
SP_HIGH_TEMP = 1
SP_CRITICAL_TEMP = 2
SP_FATAL_TEMP = 3
SP_REF_TEMP = 4
SP_FAN_SPEED = 5
SP_VALIDATE = 6

VALID_MIN_TEMP = 0
VALID_MAX_TEMP = 130

# Daemon control platform specific constants
PDDF_INIT_WAIT = 30 #secs
POLL_INTERVAL = 3 #secs
CRITICAL_DURATION = 120 #secs
CRITICAL_LOG_INTERVAL = 60 #every 'n' secs
FAN_DUTY_MIN = 40 # percentage
FAN_DUTY_MAX = 100 #percentage
TEMP_HYST = 3 # degree C
NUM_FANS = 3

# Validation functions
def is_valid_inlet_sensor(fan_dir, sensor):
    if fan_dir == "FB" and sensor == "System Front Right Temp":
        return True
    if fan_dir == "BF" and sensor == "System Rear Right Temp":
        return True
    return False

def valid_always(fan_dir, sensor):
    return True

def valid_never(fan_dir, sensor):
    return False

# Core data for Thermal FAN speed evaluation
# {<thermal-name>:
#     [low_temp, high_temp, critical_temp, fatal_temp, current_temp, fanspeed, validate_function]}
SENSOR_PARAM = {
    #LM75_U10
    'System Front Left Temp': [34, 47, 55, None, NOMINAL_TEMP, FAN_DUTY_MIN, valid_never],
    #LM75_U4
    'System Front Right Temp': [32, 48, 55, None, NOMINAL_TEMP, FAN_DUTY_MIN, is_valid_inlet_sensor],
    #LM75_U7
    'System Rear Right Temp': [32, 48, 55, None, NOMINAL_TEMP, FAN_DUTY_MIN, is_valid_inlet_sensor],
    #LM75_U60
    'ASIC External Temp': [52, 70, 72, None, NOMINAL_TEMP, FAN_DUTY_MIN, valid_always],
    'CPU core temp': [67, 85, 89, None, NOMINAL_TEMP, FAN_DUTY_MIN, valid_always]
}

class Es1050FanControl(daemon_base.DaemonBase):
    global MODULE_NAME
    global SENSOR_PARAM

    def __init__(self, log_level, fan_count):

        str_to_log_level = {
            'ERROR' : self.LOG_PRIORITY_ERROR, \
            'WARNING' : self.LOG_PRIORITY_WARNING, \
            'NOTICE': self.LOG_PRIORITY_NOTICE, \
            'INFO': self.LOG_PRIORITY_INFO, \
            'DEBUG': self.LOG_PRIORITY_DEBUG
        }
        self.fan_list = []
        self.thermal_list = []

        super(Es1050FanControl, self).__init__(MODULE_NAME)
        if log_level is not None:
            self.set_min_log_priority(str_to_log_level.get(log_level))
            self.log_info("Forcing to loglevel {}".format(log_level))
        self.log_info("Starting up...")

        self.log_debug("Waiting {} secs for PDDF driver initialization".format(PDDF_INIT_WAIT))
        time.sleep(PDDF_INIT_WAIT)

        try:
            self.critical_period = 0
            self.platform_chassis = platform.Platform().get_chassis()

            # Fetch FAN info
            self.fan_list = self.platform_chassis.get_all_fans()
            num_fans = len(self.fan_list)
            if num_fans < fan_count:
                self.log_error("Fans detected({}) is not same as expected({}), so exiting..."\
                               .format(len(self.fan_list), fan_count))
                sys.exit(1)
            self.log_notice("Number of fans is " + str(num_fans))

            # Check whether chassis fan direction and PSU fan direction match
            self.fan_dir = self.platform_chassis.chassis_fan_dir
            self.log_notice("Fans direction is {}".format(self.fan_dir))
            for psu in self.platform_chassis.get_all_psus():
                psu_fan_dir = psu.get_fan_dir()
                if self.fan_dir != psu_fan_dir:
                    self.log_error("{} fan direction is not same as chassis fan".format(psu.get_name()))
                self.log_notice("{} fan direction is {}".format(psu.get_name(), psu_fan_dir))

            # Fetch THERMAL info
            self.thermal_list = self.platform_chassis.get_all_thermals()
            if len(self.thermal_list) != len(SENSOR_PARAM):
                self.log_error("Thermals detected({}) is not same as expected({}), so exiting..."\
                               .format(len(self.thermal_list), len(SENSOR_PARAM)))
                sys.exit(1)

            # Initialize the thermal temperature dict
            # {<thermal-name>: [thermal_temp, fanspeed]}
            for thermal in self.thermal_list:
                thermal_name = thermal.get_name()
                SENSOR_PARAM[thermal_name][SP_REF_TEMP] = thermal.get_temperature()

        except Exception as e:
            self.log_error("Failed to init Es1050FanControl due to {}, so exiting...".format(repr(e)))
            sys.exit(1)

    # Signal handler
    def signal_handler(self, sig, frame): # pylint: disable=unused-argument
        if sig == signal.SIGHUP:
            self.log_notice("Caught SIGHUP - ignoring...")
        elif sig == signal.SIGINT:
            self.log_warning("Caught SIGINT - Setting all FAN speed to max({}%) and exiting... ".format(FAN_DUTY_MAX))
            self.set_all_fan_speed(FAN_DUTY_MAX)
            sys.exit(0)
        elif sig == signal.SIGTERM:
            self.log_warning("Caught SIGTERM - Setting all FAN speed to max({}%) and exiting... ".format(FAN_DUTY_MAX))
            self.set_all_fan_speed(FAN_DUTY_MAX)
            sys.exit(0)
        else:
            self.log_notice("Caught unhandled signal '" + sig + "'")


    @staticmethod
    def is_fan_operational(fan):
        #System fan is considered operational only if the rpm is greater than 1000
        if fan.get_presence() and fan.get_status() and fan.get_speed_rpm() > 1000:
            return True

        return False

    @staticmethod
    def get_lb_speed_from_min_max(cur_temp, min_temp, max_temp, min_speed, max_speed, altitude_offset):
        multiplier = (max_speed - min_speed) / (max_temp - altitude_offset - min_temp - TEMP_HYST)
        speed = int(((cur_temp - min_temp + altitude_offset - TEMP_HYST) * multiplier) + min_speed)
        speed = speed if speed > 0 else 0

        return speed

    @staticmethod
    def get_ub_speed_from_min_max(cur_temp, min_temp, max_temp, min_speed, max_speed, altitude_offset):
        multiplier = (max_speed - min_speed) / (max_temp - altitude_offset - min_temp - TEMP_HYST)
        speed = int(((cur_temp - min_temp + altitude_offset) * multiplier) + min_speed)
        speed = speed if speed > 0 else 0

        return speed

    def thermal_shutdown(self, reason):
        cmd = ['/usr/local/bin/es1050_platform_shutdown.sh', reason]

        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, universal_newlines=True)
        proc.communicate()
        if proc.returncode == 0:
            return True
        else:
            self.log_error("Thermal {} shutdown failed with errorno {}"\
                           .format(reason, proc.returncode))
            return False

    def run_outlier(self, thermal, temp_t0, temp_prev):
        # Check for initial invalid reading
        if (temp_t0 is None or 
            not (VALID_MIN_TEMP <= temp_t0 <= VALID_MAX_TEMP) or 
            abs(temp_t0 - temp_prev) > 15):

            # Read temperature three times at 0.1s intervals
            readings = []
            for _ in range(3):
                try:
                    temp_t = thermal.get_temperature()
                    readings.append(temp_t)
                    time.sleep(0.1)
                except Exception as e:
                    self.log_error("Error reading sensor: {}".format(e))
                    readings.append(None)

            # Check if all subsequent readings are also invalid
            for i in range(len(readings) - 1):
                r1 = readings[i]
                r2 = readings[i + 1]
                if (r1 is None or r2 is None):
                    self.log_error("{} readings continue to be invalid. Set fan to full speed.".format(thermal.get_name()))
                    return None

                if (not (VALID_MIN_TEMP <= r1 <= VALID_MAX_TEMP) or 
                    not (VALID_MIN_TEMP <= r2 <= VALID_MAX_TEMP) or 
                    abs(r1 - r2) > 15):
                    self.log_error("{} readings continue to be invalid. Set fan to full speed.".format(thermal.get_name()))
                    return None

            # Calculate the average of valid readings
            avg_temp = sum(readings) / len(readings)
            self.notice("Outlier detected. Using average of valid readings: {}".format(avg_temp))
            return avg_temp

        else:
            # T0 is a valid reading
            return temp_t0

    def get_fan_speed_from_thermals(self):
        prominent_speed = FAN_DUTY_MIN

        for thermal in self.thermal_list:
            speed = prominent_speed
            thermal_name = thermal.get_name()
            curr_temp = thermal.get_temperature()
            thermal_info = SENSOR_PARAM[thermal_name]
            prev_temp = thermal_info[SP_REF_TEMP]
            prev_speed = SENSOR_PARAM[thermal_name][SP_FAN_SPEED]
            thermal_low = thermal_info[SP_LOW_TEMP]
            thermal_high = thermal_info[SP_HIGH_TEMP]
            thermal_critical = thermal_info[SP_CRITICAL_TEMP]

            if thermal_info[SP_VALIDATE](self.fan_dir, thermal_name):
                self.log_debug("{} temperature is {}C".format(thermal_name, curr_temp))
                curr_temp = self.run_outlier(thermal, curr_temp, prev_temp)
                if curr_temp is None:
                    return FAN_DUTY_MAX
                    
                if thermal_low and curr_temp <= thermal_low:
                    SENSOR_PARAM[thermal_name][SP_REF_TEMP] = thermal_low
                    speed = FAN_DUTY_MIN
                elif thermal_high and curr_temp >= thermal_high:
                    SENSOR_PARAM[thermal_name][SP_REF_TEMP] = thermal_high
                    speed = FAN_DUTY_MAX
                    #If critical temperature is reached and 
                    #one of the fans is not operational, shutdown!
                    if thermal_critical and curr_temp >= thermal_critical:
                        self.log_warning("'{}' temperature ({}C) is in critical limit ({}C)"
                                             .format(thermal_name, curr_temp, thermal_critical))
                        num_good_fans = 0
                        for fan in self.fan_list:
                            if self.is_fan_operational(fan):
                                num_good_fans = num_good_fans + 1
                        if num_good_fans != len(self.fan_list):
                            self.log_error("Restarting board")
                            self.thermal_shutdown('temp_critical')
                            sys.exit(0)
                else:
                    if curr_temp > prev_temp:
                        #Temperature is rising
                        speed = self.get_lb_speed_from_min_max(curr_temp, thermal_low, thermal_high,\
                                                            FAN_DUTY_MIN, FAN_DUTY_MAX, 0)
                        #Temp is rising and speed cannot decrease
                        speed = prev_speed if speed < prev_speed else speed
                    elif curr_temp < prev_temp:
                        speed = self.get_ub_speed_from_min_max(curr_temp, thermal_low, thermal_high,\
                                                            FAN_DUTY_MIN, FAN_DUTY_MAX, 0)
                        #Temp is falling and speed cannot increase
                        speed = prev_speed if speed > prev_speed else speed
                    else:
                        #Temperature is same. No change to fan speed.
                        speed = SENSOR_PARAM[thermal_name][SP_FAN_SPEED]

                self.log_debug("{} thermal speed is {}%".format(thermal_name, speed))
                #Record the sensor's temp and speed calc for next iteration
                SENSOR_PARAM[thermal_name][SP_REF_TEMP] = curr_temp
                SENSOR_PARAM[thermal_name][SP_FAN_SPEED] = speed
                prominent_speed = max(prominent_speed, speed)
                prominent_speed = FAN_DUTY_MAX if prominent_speed > FAN_DUTY_MAX else prominent_speed

        self.log_debug("Prominent thermal speed is {}%".format(prominent_speed))

        return prominent_speed

    def set_all_fan_speed(self, speed):
        for fan in self.fan_list:
            fan_name = fan.get_name()
            try:
                if fan.set_speed(speed):
                    self.log_debug("Set {} speed to {}%".format(fan_name, speed))
                else:
                    self.log_error("Set '{}' to speed {}% failed".format(fan_name, speed))
            except Exception as e:
                self.log_error("Set '{}' to speed {}% failed due to {}".format(fan_name, speed, repr(e)))

        return False

    def run(self):
        while True:
            is_fault = False
            is_psu_faulty = False
            num_good_fans = 0

            #Fans are fixed on this platform. So, fans cannot be validated as expected by this code
            for fan in self.fan_list:
                if self.is_fan_operational(fan):
                    num_good_fans = num_good_fans + 1
                else:
                    self.log_notice("FAN '{}' is broken or not inserted".format(fan.get_name()))

            #Check whether PSUs are present and mismatch in fan direction 
            for psu in self.platform_chassis.get_all_psus():
                if psu.get_presence() == False:
                    #If is 1 PSU is not present, air leak will cause internal temp to rise.
                    #So, run fan at full speed
                    self.log_warning("{} is not present!".format(psu.get_name()))
                    is_fault = True
                else: #PSU present
                    self.critical_period = 0
                    psu_fan_dir = psu.get_fan_dir()
                    if self.fan_dir != psu_fan_dir:
                        is_psu_faulty = True
                        if self.critical_period == 0 or self.critical_period == CRITICAL_LOG_INTERVAL:
                            self.log_error("{} fan direction is not same as chassis fan".format(psu.get_name()))
                            self.critical_period = 0
                    self.log_debug("{} fan direction is {}".format(psu.get_name(), psu_fan_dir))

            # Always evaluate the thermals irrespective of the FAN state
            speed = self.get_fan_speed_from_thermals()

            if is_psu_faulty:
                self.critical_period = self.critical_period + POLL_INTERVAL
            #If some fans are operational and there is some fault, run at 100%
            if num_good_fans and is_fault:
                self.set_all_fan_speed(FAN_DUTY_MAX)
            elif num_good_fans == len(self.fan_list): # Good FANs is equal to number of FANs
                self.set_all_fan_speed(speed)
            else:
                if not num_good_fans: # None of the FANs are operational
                    self.log_warning("Overheating hazard!! All FANs are broken or not inserted")
                else:
                    self.log_warning("Some FANs are broken or not inserted")
                    self.set_all_fan_speed(FAN_DUTY_MAX)

            time.sleep(POLL_INTERVAL)

def main(argv):
    log_level = None
    fan_count = NUM_FANS
    valid_log_levels = ['ERROR', 'WARNING', 'NOTICE', 'INFO', 'DEBUG']

    if len(sys.argv) != 1:
        try:
            opts, args = getopt.getopt(argv, 'hdl:f:', ['log-level='])
        except getopt.GetoptError:
            print('Usage: %s [-d] [-l <log_file>]' % sys.argv[0])
            sys.exit(1)
        for opt, arg in opts:
            if opt == '-h':
                print('Usage: %s [-d] [-l <log_level>]\nlog_level - ERROR, WARNING, NOTICE, INFO, DEBUG' % sys.argv[0])
                sys.exit(1)
            elif opt in ('-l', '--log-level'):
                log_level = arg
                if log_level not in valid_log_levels:
                    print('Invalid log level %s' % log_level)
                    sys.exit(1)
            elif opt == '-d':
                log_level = 'DEBUG'
            elif opt == '-f':
                fan_count = int(arg)

    fanctl = Es1050FanControl(log_level, fan_count)

    fanctl.log_debug("Start daemon main loop")
    # Loop forever, doing something useful hopefully:
    fanctl.run()
    fanctl.log_debug("Stop daemon main loop")

    sys.exit(0)

if __name__ == '__main__':
    main(sys.argv[1:])
