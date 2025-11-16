#############################################################################
# PDDF
# Module contains an implementation of SONiC Chassis API
#
#############################################################################

try:
    import os
    import re
    import shutil
    import subprocess
    import time
    from . import component
    from .helper import APIHelper
    from .thermal import ThermalMon, THERMAL_MONITOR_SENSORS
    from sonic_py_common import logger
    from sonic_platform_pddf_base.pddf_chassis import PddfChassis
except ImportError as e:
    raise ImportError(str(e) + "- required module not found")

RESET_SOURCE_OS_REG = '0xa106'
LPC_SYSLED_REG = '0xa162'
LPC_GETREG_PATH = "/sys/bus/platform/devices/baseboard/getreg"
LPC_SETREG_PATH = "/sys/bus/platform/devices/baseboard/setreg"
LED_CTRL_MODE_GET_CMD = "ipmitool raw 0x3a 0x42 0x01"

ORG_HW_REBOOT_CAUSE_FILE="/host/reboot-cause/hw-reboot-cause.txt"
TMP_HW_REBOOT_CAUSE_FILE="/tmp/hw-reboot-cause.txt"
SYS_LED_SYSFS_PATH = "/sys/bus/platform/devices/baseboard/sys_led"

SYSLOG_IDENTIFIER = "Chassis"
helper_logger = logger.Logger(SYSLOG_IDENTIFIER)

class Chassis(PddfChassis):
    """
    PDDF Platform-specific Chassis class
    """
    sfp_status_dict = {}
  
    def __init__(self, pddf_data=None, pddf_plugin_data=None):
        PddfChassis.__init__(self, pddf_data, pddf_plugin_data)
        self._api_helper = APIHelper()

        for port_idx in range(1, self.platform_inventory['num_ports'] + 1):
            self.sfp_status_dict[port_idx] = self.get_sfp(port_idx).get_presence()

        for index in range(self.platform_inventory['num_component']):
            component_obj = component.Component(index)
            self._component_list.append(component_obj)

        if not self._api_helper.is_bmc_present():
            thermal_count = len(self._thermal_list)
            for idx, name in enumerate(THERMAL_MONITOR_SENSORS):
                thermal = ThermalMon(thermal_count + idx, name)
                self._thermal_list.append(thermal)

    def initizalize_system_led(self):
        """
        This function is not defined in chassis base class,
        system-health command would invoke chassis.initizalize_system_led(),
        add this stub function just to let the command sucessfully execute
        """
        pass

    def get_status_led(self):
        sys_led_color = "unknown"
        try:
            with open(SYS_LED_SYSFS_PATH, "r") as fd:
                sys_led_color = fd.read().rstrip('\n')
        except Exception as err:
            print(f"Failed to get status LED due to: {err}")
        return sys_led_color

    def set_status_led(self, color):     
        try:
            with open(SYS_LED_SYSFS_PATH, "w") as fd:
                fd.write(color)
        except Exception as err:
            print(f"Failed to set status LED due to: {err}")
            return False
        return True

    def get_sfp(self, index):
        """
        Retrieves sfp represented by (1-based) index <index>
        For Quanta the index in sfputil.py starts from 1, so override
        Args:
            index: An integer, the index (1-based) of the sfp to retrieve.
            The index should be the sequence of a physical port in a chassis,
            starting from 1.
        Returns:
            An object dervied from SfpBase representing the specified sfp
        """
        sfp = None

        try:
            if (index == 0):
                raise IndexError
            sfp = self._sfp_list[index-1]
        except IndexError:
            sys.stderr.write("override: SFP index {} out of range (1-{})\n".format(
                index, len(self._sfp_list)))

        return sfp
    # Provide the functions/variables below for which implementation is to be overwritten

    def get_reboot_cause(self):
        """
        Retrieves the cause of the previous reboot
        Returns:
            A tuple (string, string) where the first element is a string
            containing the cause of the previous reboot. This string must be
            one of the predefined strings in this class. If the first string
            is "REBOOT_CAUSE_HARDWARE_OTHER", the second string can be used
            to pass a description of the reboot cause.
        """
        hw_reboot_cause = self._api_helper.lpc_getreg(LPC_GETREG_PATH, RESET_SOURCE_OS_REG)
        
        if hw_reboot_cause == "0x33" and os.path.isfile(TMP_HW_REBOOT_CAUSE_FILE):
            with open(TMP_HW_REBOOT_CAUSE_FILE) as hw_cause_file:
               reboot_info = hw_cause_file.readline().rstrip('\n')
               match = re.search(r'Reason:(.*),Time:(.*)', reboot_info)
               description = 'CPU cold reset'
               if match is not None:
                  if match.group(1) == 'system':
                     return (self.REBOOT_CAUSE_NON_HARDWARE, 'System cold reboot')
        elif hw_reboot_cause == "0x99":
            reboot_cause = self.REBOOT_CAUSE_THERMAL_OVERLOAD_ASIC
            description = 'ASIC Overload Reboot'
        elif hw_reboot_cause == "0x88":
            reboot_cause = self.REBOOT_CAUSE_THERMAL_OVERLOAD_CPU
            description = 'CPU Overload Reboot'
        elif hw_reboot_cause == "0x66":
            reboot_cause = self.REBOOT_CAUSE_WATCHDOG
            description = 'Hardware Watchdog Reset'
        elif hw_reboot_cause == "0x55":
            reboot_cause = self.REBOOT_CAUSE_HARDWARE_OTHER
            description = 'CPU Cold Reset'
        elif hw_reboot_cause == "0x44":
            reboot_cause = self.REBOOT_CAUSE_NON_HARDWARE
            description = 'CPU Warm Reset'
        elif hw_reboot_cause == "0x33":
            reboot_cause = self.REBOOT_CAUSE_NON_HARDWARE
            description = 'Soft-Set Cold Reset'
        elif hw_reboot_cause == "0x22":
            reboot_cause = self.REBOOT_CAUSE_NON_HARDWARE
            description = 'Soft-Set Warm Reset'
        elif hw_reboot_cause == "0x11":
            reboot_cause = self.REBOOT_CAUSE_POWER_LOSS
            description = 'Power Off Reset'
        elif hw_reboot_cause == "0x00":
            reboot_cause = self.REBOOT_CAUSE_POWER_LOSS
            description = 'Power Cycle Reset'
        else:
            reboot_cause = self.REBOOT_CAUSE_HARDWARE_OTHER
            description = 'Hardware reason'

        return (reboot_cause, description)

    def get_watchdog(self):
        """
        Retreives hardware watchdog device on this chassis

        Returns:
            An object derived from WatchdogBase representing the hardware
            watchdog device
        """
        try:
            if self._watchdog is None:
                from sonic_platform.cpld_watchdog import Watchdog
                # Create the watchdog Instance from cpld watchdog
                self._watchdog = Watchdog()

        except Exception as e:
            helper_logger.log_error("Fail to load watchdog due to {}".format(e))
        return self._watchdog

    ##############################################################
    ###################### Event methods #########################
    ##############################################################
    def get_change_event(self, timeout=0):
        """
        Returns a nested dictionary containing all devices which have
        experienced a change at chassis level
        Args:
            timeout: Timeout in milliseconds (optional). If timeout == 0,
                this method will block until a change is detected.
        Returns:
            (bool, dict):
                - True if call successful, False if not;
                - A nested dictionary where key is a device type,
                  value is a dictionary with key:value pairs in the format of
                  {'device_id':'device_event'},
                  where device_id is the device ID for this device and
                        device_event,
                             status='1' represents device inserted,
                             status='0' represents device removed.
                  Ex. {'fan':{'0':'0', '2':'1'}, 'sfp':{'11':'0'}}
                      indicates that fan 0 has been removed, fan 2
                      has been inserted and sfp 11 has been removed.
        """
        # SFP event
        sfp_dict = {}

        start_time = time.time()
        time_period = timeout / float(1000)  # Convert msecs to secss

        while time.time() < (start_time + time_period) or timeout == 0:
            for port_idx in range(1, self.platform_inventory['num_ports'] + 1):
                presence = self.get_sfp(port_idx).get_presence()
                if self.sfp_status_dict[port_idx] != presence:
                   self.sfp_status_dict[port_idx] = presence
                   sfp_dict[port_idx] = '1' if presence else '0'

            if sfp_dict:
                return True, {'sfp': sfp_dict}

            time.sleep(0.5)

        return True, {'sfp': {}}  # Timeout

    def get_serial(self):
        """
        Retrieves the serial number of the chassis (Service tag)
        Returns:
            string: Serial number of chassis
        """
        return self._eeprom.serial_number_str()

    def get_revision(self):
        """
        Retrieves the hardware revision for the chassis
        Returns:
            A string containing the hardware revision for this chassis.
        """
        return self._eeprom.revision_str()

    def get_system_airflow(self):
        """
        Retrieve system airflow
        Returns:
            string: INTAKE or EXHAUST
        """
        airflow = self.get_serial()[5:8]
        if airflow == "B2F":
            return "INTAKE"
        elif airflow == "F2B":
            return "EXHAUST"
        return "Unknown"

    def get_thermal_manager(self):
        """
        Retrieves thermal manager class on this chasssis

        Returns:
            A class derived from ThermalManagerBase representing the
            specified thermal manager
        """
        if not self._api_helper.is_bmc_present():
            from .thermal_manager import ThermalManager
            return ThermalManager
        return None
