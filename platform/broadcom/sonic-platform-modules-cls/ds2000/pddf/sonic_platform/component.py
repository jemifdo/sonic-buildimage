#!/usr/bin/env python

#############################################################################
# Celestica
#
# Component contains an implementation of SONiC Platform Base API and
# provides the components firmware management function
#
#############################################################################

import shlex
import subprocess
import re
import traceback

try:
    from sonic_platform_base.component_base import ComponentBase
except ImportError as e:
    raise ImportError(str(e) + "- required module not found")

COMPONENT_LIST = [
    ("BIOS",       "Basic input/output System"),
    ("ONIE",       "Open Network Install Environment"),
    ("BMC",        "Baseboard Management Controller"),
    ("FPGA",       "FPGA for transceiver EEPROM access and other component I2C access"),
    ("CPLD COMe",  "COMe board CPLD"),
    ("CPLD BASE",  "CPLD for board functions, fan control and watchdog"),
    ("CPLD SW1",   "CPLD for port control SFP(1-24)"),
    ("CPLD SW2",   "CPLD for port control SFP(25-48), QSFP(49-56)"),
    ("ASIC PCIe",  "ASIC PCIe Firmware"),
    ("SSD",        "Solid State Drive - {}")
]
NAME_INDEX = 0
DESCRIPTION_INDEX = 1

BIOS_VERSION_CMD = "dmidecode -s bios-version"
FPGA_VERSION_PATH = "/sys/bus/platform/devices/fpga_sysfs/version"
SWCPLD1_VERSION_CMD = "i2cget -y -f 102 0x30 0x0"
SWCPLD2_VERSION_CMD = "i2cget -y -f 102 0x31 0x0"
GETREG_PATH="/sys/devices/platform/sys_cpld/getreg"
SSD_VERSION_CMD = "smartctl -i /dev/sda"

UNKNOWN_VER = "Unknown"

class Component():
    """Platform-specific Component class"""

    DEVICE_TYPE = "component"

    def __init__(self, component_index):
        ComponentBase.__init__(self)
        self.index = component_index
        self.name = self.get_name()

    def __get_cpld_ver(self):
        cpld_version_dict = dict()
        cpld_ver_info = {
            'CPLD BASE': self.__get_basecpld_ver(),
            'CPLD SW1': self.__get_swcpld1_ver(),
            'CPLD SW2': self.__get_swcpld2_ver(),
            'CPLD COMe': self.__get_comecpld_ver()
        }
        for cpld_name, cpld_ver in cpld_ver_info.items():
            cpld_ver_str = "{}.{}".format(int(cpld_ver[2], 16), int(
                cpld_ver[3], 16)) if cpld_ver else UNKNOWN_VER
            cpld_version_dict[cpld_name] = cpld_ver_str

        return cpld_version_dict

    def __get_asic_pcie_ver(self): 
        cmd = ["/usr/bin/bcmcmd", "pciephy fw version"] 
        status, output = self.run_command(cmd)
        if not status:
            return UNKNOWN_VER

        for line in output.splitlines():
            if "PCIe FW version" in line: 
                try:
                    return line.split()[3] 
                except IndexError:
                    return UNKNOWN_VER 

        return UNKNOWN_VER 

    def __get_bios_ver(self): 
        status, raw_ver=self.run_command(BIOS_VERSION_CMD)
        if status:
            return raw_ver
        else:
            return UNKNOWN_VER

    def __get_comecpld_ver(self): 
        try:
            with open("/sys/devices/platform/sys_cpld/come_cpld_version", "r") as f:
                raw_ver = f.read().strip()  # Read and strip any trailing whitespace or newline
            return raw_ver
        except Exception as e:
            return UNKNOWN_VER

    def __get_basecpld_ver(self): 
        try:
            with open(GETREG_PATH, "w+") as f:
                f.write("0xA100")
                f.flush()
                f.seek(0)
                raw_ver = f.read().strip()

            return raw_ver
        except Exception as e:
            return UNKNOWN_VER

    def __get_swcpld1_ver(self): 
        SWCPLD1_VERSION_CMD = ["i2cget", "-y", "-f", "102", "0x30", "0x0"]
        status, raw_ver=self.run_command(SWCPLD1_VERSION_CMD)
        if status:
            return raw_ver
        else:
            return UNKNOWN_VER

    def __get_swcpld2_ver(self): 
        SWCPLD2_VERSION_CMD = ["i2cget", "-y", "-f", "102", "0x31", "0x0"]
        status, raw_ver=self.run_command(SWCPLD2_VERSION_CMD)
        if status:
            return raw_ver
        else:
            return UNKNOWN_VER

    def __get_bmc_presence(self): 
        try:
            with open(GETREG_PATH, "w+") as f:
                f.write("0xA108")
                f.flush()
                f.seek(0)
                raw_ver = f.read().strip()
            
            return raw_ver
        except Exception as e:
            return UNKNOWN_VER

    def __get_bmc_ver(self): 
        cmd = "ipmitool mc info"
        status, raw_ver = self.run_command(cmd)
        if status:
            for line in raw_ver.splitlines():
                if "Firmware Revision" in line:
                    bmc_ver = line.split(':')[-1].strip()
                    return {"BMC": bmc_ver}
        return {"BMC": "N/A"} 

    def __get_fpga_version(self): 
        try:
            with open(FPGA_VERSION_PATH, "r") as f:
                fpga_version = f.read().strip()
            return fpga_version.replace("0x", "")
        except Exception as e:
            return UNKNOWN_VER

    def __get_onie_ver(self): 
        onie_ver = "N/A"
        try:
            with open("/host/machine.conf", "r") as f:
                raw_onie_data = f.read()
            ret = re.search(r"(?<=onie_version=).+[^\n]", raw_onie_data)
            if ret is not None:
                onie_ver = ret.group(0)
        except Exception as e:
            print(f"Error reading ONIE version: {e}")
        return onie_ver

    def __get_ssd_ver(self): 
        ssd_ver = "N/A"
        status, raw_ssd_data = self.run_command(SSD_VERSION_CMD)
        if status:
            ret = re.search(r"Firmware Version: +(.*)[^\\]", raw_ssd_data)
            if ret != None:
                ssd_ver = ret.group(1)
        return ssd_ver

    def __get_ssd_desc(self, desc_format): 
        description = "N/A"
        status, raw_ssd_data = self.run_command(SSD_VERSION_CMD)
        if status:
            ret = re.search(r"Device Model: +(.*)[^\\]", raw_ssd_data)
            if ret != None:
                try:
                    description = desc_format.format(ret.group(1))
                except (IndexError):
                    pass
        return description

    def get_name(self):
        """
        Retrieves the name of the component
         Returns:
            A string containing the name of the component
        """
        return COMPONENT_LIST[self.index][NAME_INDEX]

    def get_description(self):
        """
        Retrieves the description of the component
            Returns:
            A string containing the description of the component
        """
        # For SSD get the model name from device
        if self.get_name() == "SSD":
            return self.__get_ssd_desc(COMPONENT_LIST[self.index][1])

        return COMPONENT_LIST[self.index][DESCRIPTION_INDEX]

    def get_firmware_version(self):
        """
        Retrieves the firmware version of module
        Returns:
            string: The firmware versions of the module
        """
        try:
            fw_version_info = {
                "ONIE": self.__get_onie_ver(),
                "SSD": self.__get_ssd_ver(),
                "BIOS": self.__get_bios_ver(),
                "FPGA": self.__get_fpga_version(),
                "ASIC PCIe": self.__get_asic_pcie_ver(),
            }
            fw_version_info.update(self.__get_cpld_ver())
            if self.__get_bmc_presence():
                fw_version_info.update(self.__get_bmc_ver())
            return fw_version_info.get(self.name, UNKNOWN_VER)
        except Exception as e:
            traceback.print_exc()
            raise e 
   
    def run_command(self, cmd): 
        status = True
        result = ""
        try:
            if isinstance(cmd, list):
                raw_data = subprocess.check_output(cmd, universal_newlines=True, stderr=subprocess.STDOUT)
            else:
                raw_data = subprocess.check_output(shlex.split(cmd), universal_newlines=True, stderr=subprocess.STDOUT)
            result = raw_data.strip()

        except:
            status = False
        return status, result
