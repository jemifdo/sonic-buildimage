#!/usr/bin/env python

#############################################################################
# Celestica
#
# Component contains an implementation of SONiC Platform Base API and
# provides the sfp management function
#
#############################################################################

try:
    from sonic_platform.cls_sfp import ClsPddfSfp
except ImportError as e:
    raise ImportError (str(e) + "- required module not found")


class Sfp(ClsPddfSfp):
    """
    PDDF Platform-Specific Sfp class
    """

    def __init__(self, index, pddf_data=None, pddf_plugin_data=None):
        self.index = index+1
        ClsPddfSfp.__init__(self, index, pddf_data, pddf_plugin_data)

    # Provide the functions/variables below for which implementation is to be overwritten

    def get_error_description(self):
        """
        Retrives the error descriptions of the SFP module
        Returns:
            String that represents the current error descriptions of vendor specific errors
            In case there are multiple errors, they should be joined by '|',
            like: "Bad EEPROM|Unsupported cable"
        """
        if not self.get_presence():
            return self.SFP_STATUS_UNPLUGGED
        return self.SFP_STATUS_OK

    def get_port_or_cage_type(self):
        if self.port_index >= 1 and self.port_index <= 48:
            return self.SFP_CAGE_TYPE_RJ45
        elif self.port_index >= 49 and self.port_index <= 56:
            return self.SFP_CAGE_TYPE_SFP
        else:
            return "N/A"
