try:
    from sonic_platform_pddf_base.pddf_psu import PddfPsu
    from .helper import APIHelper
except ImportError as e:
    raise ImportError (str(e) + "- required module not found")

BMC_EXIST = APIHelper().is_bmc_present()

class Psu(PddfPsu):
    """PDDF Platform-Specific PSU class"""

    def __init__(self, index, pddf_data=None, pddf_plugin_data=None):
        PddfPsu.__init__(self, index, pddf_data, pddf_plugin_data)
        
    # Provide the functions/variables below for which implementation is to be overwritten
    def get_capacity(self):
        return 550

    def get_type(self):
        return 'AC'

    def get_voltage_low_threshold(self):
        return 4

    def get_voltage_high_threshold(self):
        return 13

    def get_status_led(self):
        if self.get_presence():
            if self.get_powergood_status():
                return self.STATUS_LED_COLOR_GREEN
            else:
                return self.STATUS_LED_COLOR_AMBER
        else:
            return self.STATUS_LED_COLOR_OFF

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
