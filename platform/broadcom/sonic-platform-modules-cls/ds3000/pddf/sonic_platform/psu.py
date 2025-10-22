try:
    from sonic_platform_pddf_base.pddf_psu import PddfPsu
    from .helper import APIHelper
except ImportError as e:
    raise ImportError (str(e) + "- required module not found")

LPC_GETREG_PATH = "/sys/bus/platform/devices/baseboard/getreg"
LPC_PSU_STATUS_REG = '0xa160'
LPC_PSU_POWER_STATUS_OFFSET = 0
LPC_PSU_PRES_STATUS_OFFSET = 2
BMC_EXIST = APIHelper().is_bmc_present()

class Psu(PddfPsu):
    """PDDF Platform-Specific PSU class"""

    def __init__(self, index, pddf_data=None, pddf_plugin_data=None):
        PddfPsu.__init__(self, index, pddf_data, pddf_plugin_data)
        self._api_helper = APIHelper()

    # Provide the functions/variables below for which implementation is to be overwritten
    def get_capacity(self):
        return 550

    def get_type(self):
        return 'AC'

    def get_revision(self):
        """
        Retrieves the revision of the device
        Returns:
            string: revision of device
        """
        if not self.get_presence():
            return 'N/A'

        if self._api_helper.is_bmc_present():
            cmd = "ipmitool fru list {} | grep 'Product Version'".format(5 - self.psu_index)
            status, output = self._api_helper.get_cmd_output(cmd)
            if status == 0:
                rev = output.split()[-1]
                return rev
        else:
            # Get the revision information from FRU
            cmd = "i2cget -y -f {} {} 0x2d w".format(42 + self.psu_index - 1, hex(0x52 + self.psu_index - 1))
            status, output = self._api_helper.get_cmd_output(cmd)
            if status == 0:
                rev = bytes.fromhex(output.strip('0x')).decode('utf-8')
                # swap to change the endian difference
                return rev[::-1]
        return 'N/A'

    def get_input_voltage(self):
        if not self.get_status():
            return 0

        if BMC_EXIST:
            device = "PSU{}".format(self.psu_index)
            output = self.pddf_obj.get_attr_name_output(device, "psu_v_in")
            if not output:
                return 0.0

            v_in = output['status']
            return int(v_in)/10
        else:
            return super().get_input_voltage()
