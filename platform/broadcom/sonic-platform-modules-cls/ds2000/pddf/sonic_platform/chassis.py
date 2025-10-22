#############################################################################
# PDDF
# Module contains an implementation of SONiC Chassis API
#
#############################################################################

try:
    from sonic_platform_pddf_base.pddf_chassis import PddfChassis
    import sys
    import subprocess
    import time
    import os
    import re
    import shutil
    from . import helper
except ImportError as e:
    raise ImportError(str(e) + "- required module not found")

GETREG_PATH="/sys/devices/platform/sys_cpld/getreg"
SETREG_PATH="/sys/devices/platform/sys_cpld/setreg"
SET_SYS_STATUS_LED="echo {} {} > {}"
SET_SYS_STATUS_LED_IPMI="0x3A 0x39 0x02 0x00 {}"
GET_REBOOT_CAUSE="echo '0xA107' > {} && cat {}".format(GETREG_PATH, GETREG_PATH)

ORG_HW_REBOOT_CAUSE_FILE="/host/reboot-cause/hw-reboot-cause.txt"
TMP_HW_REBOOT_CAUSE_FILE="/tmp/hw-reboot-cause.txt"
SYS_LED_SYSFS_PATH = "/sys/bus/platform/devices/sys_cpld/sys_led"

BMC_EXIST = helper.APIHelper().is_bmc_present()

class Chassis(PddfChassis):
    """
    PDDF Platform-specific Chassis class
    """
    sfp_status_dict={}

    def __init__(self, pddf_data=None, pddf_plugin_data=None):
        PddfChassis.__init__(self, pddf_data, pddf_plugin_data)

        for port_idx in range(1, self.platform_inventory['num_ports'] + 1):
            self.sfp_status_dict[port_idx] = self.get_sfp(port_idx).get_presence()
        
        # Component firmware version initialization
        from sonic_platform.component import Component
        if BMC_EXIST:
            NUM_COMPONENT = 10
        else:
            NUM_COMPONENT = 7
        for i in range(0, NUM_COMPONENT):
            component = Component(i)
            self._component_list.append(component)
    
    def _getstatusoutput(self, cmd):
        status = 0
        ret, data = subprocess.getstatusoutput(cmd)
        if ret != 0:
            status = ret
        else:
            return data

        return status, data

    def initizalize_system_led(self):
        return True

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
        # Newer baseboard CPLD to get reboot cause from CPLD register
        hw_reboot_cause = ""
        status, hw_reboot_cause = self._getstatusoutput(GET_REBOOT_CAUSE)
        if status != 0:
            pass

        # This tmp copy is to retain the reboot-cause only for the current boot
        if os.path.isfile(ORG_HW_REBOOT_CAUSE_FILE):
            shutil.move(ORG_HW_REBOOT_CAUSE_FILE, TMP_HW_REBOOT_CAUSE_FILE)

        if hw_reboot_cause == "0x33" and os.path.isfile(TMP_HW_REBOOT_CAUSE_FILE):
            with open(TMP_HW_REBOOT_CAUSE_FILE) as hw_cause_file:
                reboot_info = hw_cause_file.readline().rstrip('\n')
                match = re.search(r'Reason:(.*),Time:(.*)', reboot_info)
                if match is not None:
                    if match.group(1) == 'system':
                        reboot_cause = self.REBOOT_CAUSE_NON_HARDWARE
                        description = 'System cold reboot'
                        return (reboot_cause, description)

        if hw_reboot_cause == "0x77":
            reboot_cause = self.REBOOT_CAUSE_POWER_LOSS
            description = 'Power Cycle Reset'
        elif hw_reboot_cause == "0x66":
            reboot_cause = self.REBOOT_CAUSE_WATCHDOG
            description = 'Hardware Watchdog Reset'
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
            description = 'Power On Reset'
        else:
            reboot_cause = self.REBOOT_CAUSE_HARDWARE_OTHER
            description = 'Hardware reason'

        return (reboot_cause, description)

    def get_change_event(self, timeout=0):
        sfp_dict = {} 
                      
        start_time = time.time()
        time_period = timeout/float(1000) #Convert msecs to secs
                      
        while time.time() < (start_time + time_period) or timeout == 0:
            for port_idx in range(1, self.platform_inventory['num_ports'] + 1):
                presence = self.get_sfp(port_idx).get_presence()
                if self.sfp_status_dict[port_idx] != presence:                                                                                                                                                           
                    self.sfp_status_dict[port_idx] = presence       
                    sfp_dict[port_idx] = '1' if presence else '0'
                      
            if sfp_dict:
                return True, {'sfp':sfp_dict}
                      
            time.sleep(0.5)
                      
        return True, {'sfp':{}} # Timeout 
	
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
                # Create the watchdog Instance
                self._watchdog = Watchdog()
            
        except Exception as e:                                                                                                                                                                                                       
            print("Fail to load watchdog due to {}".format(e))
        return self._watchdog

    def get_revision(self):
        """
        Retrieves the hardware revision for the chassis
        Returns:
            A string containing the hardware revision for this chassis.
        """
        return self._eeprom.revision_str().encode('utf-8').hex()
