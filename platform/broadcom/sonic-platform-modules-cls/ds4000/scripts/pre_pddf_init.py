#!/usr/bin/env python
# -*- coding: UTF-8 -*-
# @Time    : 2023/7/24 9:34
# @Mail    : yajiang@celestica.com
# @Author  : jiang tao
# @Function: Load pddf_custom_lpc_basecpld.ko, after confirming the BMC is in place,
#            load different configuration files, and finally remove the driver.

import subprocess
import os
import os.path
from sonic_py_common import device_info
(platform_name, _) = device_info.get_platform_and_hwsku()


class PrePddfInit(object):
    def __init__(self):
        self.ker_path = "/usr/lib/modules/{}/extra"
        self.lpc_basecpld_name = "custom_lpc_basecpld"
        self.bmc_exist_cmd = "/sys/bus/platform/devices/sys_cpld/bmc_present"
        self.bmc_present = False

    @staticmethod
    def run_command(cmd):
        status = True
        result = ""
        ret, data = subprocess.getstatusoutput(cmd)
        if ret != 0:
            status = False
        else:
            result = data

        return status, result

    def get_kernel_path(self):
        """
        get the kernel object complete path
        :return:
        """
        sta_, res_ = self.run_command("uname -r")
        if sta_:
            return self.ker_path.format(res_)
        else:
            return None

    def install_lpc_basecpld(self):
        """
        install lpc basecpld driver
        """
        self.run_command("modprobe %s" % (self.lpc_basecpld_name))

    def get_bmc_status(self):
        """
        get bmc status
        """
        if os.path.exists(self.bmc_exist_cmd):
            # "1": "absent", "0": "present"
            sta, res = self.run_command("cat %s" % self.bmc_exist_cmd)
            self.bmc_present = False if res == "1" else True

    def choose_pddf_device_json(self):
        """
        Depending on the state of the BMC, different pddf-device.json file configurations will be used:
        1.BMC exist: cp pddf-device.json-bmc pddf-device.json
        2.None BMC : cp pddf-device.json-nonebmc pddf-device.json
        """
        device_name = "pddf-device.json-bmc" if self.bmc_present else "pddf-device.json-nonebmc"
        device_path = "/usr/share/sonic/device/%s/pddf/" % platform_name
        self.run_command("cp %s%s %spddf-device.json" % (device_path, device_name, device_path))

    def choose_platform_components(self):
        """
        Depending on the state of the BMC, different platform_components.json file configurations will be used:
        1.BMC exist: cp platform_components.json-bmc platform_components.json
        2.None BMC : cp platform_components.json-nonebmc platform_components.json
        """
        device_name = "platform_components.json-bmc" if self.bmc_present else "platform_components.json-nonebmc"
        device_path = "/usr/share/sonic/device/%s/" % platform_name
        self.run_command("cp %s%s %splatform_components.json" % (device_path, device_name, device_path))

    def main(self):
        self.install_lpc_basecpld()
        if not os.path.isfile("/usr/share/sonic/device/%s/bmc_status" % platform_name):
            self.get_bmc_status()
            self.choose_pddf_device_json()
            self.choose_platform_components()
            with open("/usr/share/sonic/device/%s/bmc_status" % platform_name, 'w') as fp:
                fp.write(str(self.bmc_present))


if __name__ == '__main__':
    pre_init = PrePddfInit()
    pre_init.main()
