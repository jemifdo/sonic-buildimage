#!/usr/bin/env python
# @Company ：Celestica
# @Time    : 2023/7/20  13:46
# @Mail    : yajiang@celestica.com
# @Author  : jiang tao
try:
    from sonic_platform_pddf_base.pddf_psu import PddfPsu
    import re
    import os
    from . import helper
except ImportError as e:
    raise ImportError(str(e) + "- required module not found")

BMC_EXIST = helper.APIHelper().get_bmc_status()


class Psu(PddfPsu):
    """PDDF Platform-Specific PSU class"""

    def __init__(self, index, pddf_data=None, pddf_plugin_data=None):
        PddfPsu.__init__(self, index, pddf_data, pddf_plugin_data)
        self.helper = helper.APIHelper()
        if BMC_EXIST:
            from . import sensor_list_config
            if not os.path.exists(sensor_list_config.Sensor_List_Info):
                cmd = "ipmitool sensor list > %s" % sensor_list_config.Sensor_List_Info
                self.helper.run_command(cmd)

    @staticmethod
    def get_capacity():
        return 550

    @staticmethod
    def get_type():
        return 'AC'

    @staticmethod
    def get_revision():
        """
        Get PSU HW Revision by read psu eeprom data.
        return: HW Revision or 'N/A'
        """
        return "N/A"

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
