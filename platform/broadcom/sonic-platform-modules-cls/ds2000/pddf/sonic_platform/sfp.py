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
        ClsPddfSfp.__init__(self, index, pddf_data, pddf_plugin_data)

    # Provide the functions/variables below for which implementation is to be overwritten
    def reset(self):
        if self.port_index > 0 and self.port_index < 49:
            return False
        return super().reset()

    def get_port_or_cage_type(self):
        if self.port_index >= 1 and self.port_index <= 48:
            return self.SFP_CAGE_TYPE_SFP
        elif self.port_index >= 49 and self.port_index <= 56:
            return self.SFP_CAGE_TYPE_QSFP
        else:
            return "N/A"
