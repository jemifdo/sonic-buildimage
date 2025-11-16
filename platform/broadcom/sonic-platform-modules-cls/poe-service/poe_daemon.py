#!/usr/bin/env python3

import os
import sys
import time
import signal
import traceback
import json
import datetime
from threading import Thread, Event, Lock
from enum import Enum, IntEnum
import math

try:
    from sonic_py_common import device_info
    from sonic_py_common import daemon_base
    from sonic_py_common.logger import Logger
    from swsscommon import swsscommon
    from sonic_platform.poe_utils.poe_constants import PoeConfigDb, PoeStateDb, PoeApplDb, PoeLedState
    from sonic_platform.poe_utils.poe_driver_util import PoeDrvUtilHigh
except ImportError as e:
    raise ImportError(str(e) + "- required module not found")


POED_SERVICE_NAME = "poed"
POED_PLATFORM_CONFIG_PATH = "/usr/share/sonic/device/{}/poe_config.json"
POED_FIRMWARE_DEFAULT_PATH = "/usr/share/sonic/device/{}/poe_firmware.bin"
SELECT_TIMEOUT_MS = 2000 #milliseconds
DEFAULT_WAIT_PERIOD = 2 #seconds
PORT_MEASUREMENT_FREQ = 3
lock = Lock()
#PoE Error Numbers
class PoedErrno(IntEnum):
    NO_ERR = 0
    INIT_ERR = 1
    CONFIG_ERR = 2
    LLDP_ERR = 3
    STATE_ERR = 4

# PoE daemon stages
class PoedStage(Enum):
    UNKNOWN = "unknown"
    INIT = "init"
    INIT_DONE = "init-done"
    CONFIG = "config"
    CONFIG_DONE = "config-done"
    READY = "ready"

# PoE Exception classes
class PoeConfigTaskError(Exception):
    pass

class PoeStateTaskError(Exception):
    pass

# PoE daemon global variables
log_helper = None
poed_daemon_stage = PoedStage.UNKNOWN
poed_platform_config = {}

poed_gconfig_dict = {}
poed_pconfig_dict = {}

poed_gstate_dict = {}
poed_estate_dict = {}
poed_pstate_dict = {}
poed_pse_lldp_dict = {}
poed_pd_lldp_dict = {}
poed_counters_dict = {}

poed_drv_ctl = None
poed_errno = PoedErrno.NO_ERR
error_status_dict = {}
def poed_daemon_stage_set(stage):
    global poed_daemon_stage
    poed_daemon_stage = stage

def poed_daemon_stage_get():
    global poed_daemon_stage
    return poed_daemon_stage

class PoedThreadLogger():
    def __init__(self, log_prefix="Thread"):
        global log_helper
        self.log = log_helper
        self.log_prefix = log_prefix + ": "

    def log_error(self, msg):
        self.log.log_error(self.log_prefix + msg)

    def log_warning(self, msg):
        self.log.log_warning(self.log_prefix + msg)

    def log_notice(self, msg):
        self.log.log_notice(self.log_prefix + msg)

    def log_info(self, msg):
        self.log.log_info(self.log_prefix + msg)

    def log_debug(self, msg):
        self.log.log_debug(self.log_prefix + msg)

class PoedLldpUpdateTask(Thread, PoedThreadLogger):
    def __init__(self, svc_stop_event, stage_sync_event):
        Thread.__init__(self)
        self.setName("PoedLldpUpdateTask")
        PoedThreadLogger.__init__(self, self.getName())
        self.stage_sync_event = stage_sync_event
        self.svc_stop_event = svc_stop_event
        self.task_stop_event = Event()
        self.power_unknown = 1000.0 # Very large power value

        appl_db = swsscommon.DBConnector("APPL_DB", 0, False)
        self.lldp_appl_table = swsscommon.Table(appl_db, "LLDP_MDI_POWER")

    def join(self):
        self.log_info("Stop LLDP Update Task")
        self.task_stop_event.set()
        super(PoedLldpUpdateTask, self).join()

    def power_mode_val(self, power_up_mode):
        str_to_val = {\
            "dot3af": 0,\
            "high-inrush": 1,\
            "pre-dot3at": 2,\
            "dot3at": 3,\
            "pre-dot3bt": 4,\
            "dot3bt-type3": 5,\
            "dot3bt-type4": 6\
        }

        return str_to_val.get(power_up_mode, 0)

    def pd_class_max_power(self, port,pd_class):
        global poed_pconfig_dict
        power_up_mode = poed_pconfig_dict[port].get(PoeConfigDb.PORT_POWER_UP_MODE)
        power_threshold_type = poed_pconfig_dict[port].get(PoeConfigDb.PORT_POWER_THRESHOLD_TYPE)
        if power_threshold_type == "class-based":
            class_str_to_pwr = {\
                "Class0": 16.2,\
                "Class1": 4.2,\
                "Class2": 7.4,\
                "Class3": 16.2,\
                "Class4": 31.2,\
                "Class5": 48.6,\
                "Class6": 65,\
                "Class7": 81.2,\
                "Class8": 97\
            }
            if power_up_mode == "dot3bt-type3":
                class_str_to_pwr["Class6"] = 65
                class_str_to_pwr["Class7"] = 65
                class_str_to_pwr["Class8"] = 65
        elif power_threshold_type == "power-up-based":
            class_str_to_pwr = {\
                "Class0": 31.2,\
                "Class1": 31.2,\
                "Class2": 31.4,\
                "Class3": 31.2,\
                "Class4": 31.2,\
                "Class5": 31.2,\
                "Class6": 31.2,\
                "Class7": 31.2,\
                "Class8": 31.2\
            }
            if power_up_mode == "dot3bt-type3":
                class_str_to_pwr["Class5"] = 65
                class_str_to_pwr["Class6"] = 65
                class_str_to_pwr["Class7"] = 65
                class_str_to_pwr["Class8"] = 65
            if power_up_mode == "dot3bt-type4":
                class_str_to_pwr["Class5"] = 97
                class_str_to_pwr["Class6"] = 97
                class_str_to_pwr["Class7"] = 97
                class_str_to_pwr["Class8"] = 97
        else:
            user_power_threshold_value = poed_pconfig_dict[port].get(PoeConfigDb.PORT_USER_POWER_THRESHOLD)
            return user_power_threshold_value

        return class_str_to_pwr.get(pd_class, 0)

    def pd_to_pse_power(self, pd_power):
        # As per broadcom response adding 20 percent extra to the request to accomodate cable loss
        """
        power_dict = {\
                03.84: 04.00,\
                06.49: 07.00,\
                13.00: 15.40,\
                25.50: 30.00,\
                40.00: 45.00,\
                51.00: 60.00,\
                62.00: 75.00,\
                71.30: 90.00\
        }

        power = 3.84
        for key in power_dict.keys():
            if pd_power <= key:
                power = key
            else:
                break

        pse_power = (pd_power * power_dict[power]) / power
        self.log_info("PSE_power is {} power {}".format(pse_power,power))
        """
        pse_power = pd_power * 1.2
        pse_power = math.ceil(pse_power)
        return pse_power

    def pse_change_pd_requested_power(self, port, power,pse_powerup_mode):
        global poed_drv_ctl    
        pse_power = self.pd_to_pse_power(power)
        if pse_powerup_mode == "dot3bt-type3" or pse_powerup_mode == "dot3bt-type4":
            pse_power = pse_power / 2
        return poed_drv_ctl.set_dll_power_limit(port, pse_power)

    def disable_pse_lldp_send(self, key):
        global poed_pse_lldp_dict

        if len(poed_pse_lldp_dict[key]) > 0:
            self.lldp_appl_table.delete(key)
            poed_pse_lldp_dict[key] = {}

    def update_pd_lldp_cache(self, port, op, state_dict):
        global poed_pd_lldp_dict

        if op == "SET":
            poed_pd_lldp_dict[port] = state_dict
        elif op == "DEL":
            poed_pd_lldp_dict[port] = {}

    def update_pse_lldp_db_and_cache_state(self, port, cached_state, new_state):
        global poed_pse_lldp_dict
        if len(cached_state) == 0:
            fvp_list = []
            for state, value in new_state.items():
                fvp_list.append((state.field, value))
            timestamp = str(datetime.datetime.now())
            fvp_list.append(("timestamped",timestamp))
            fvp = swsscommon.FieldValuePairs(fvp_list)
        else:
            fvp_list = []
            for state, value in new_state.items():
                if cached_state.get(state, None) != value:
                    fvp_list.append((state.field, value))
            timestamp = str(datetime.datetime.now())
            fvp_list.append(("timestamped",timestamp))
            fvp = swsscommon.FieldValuePairs(fvp_list)
        self.lldp_appl_table.set(port, fvp)
        for entry in fvp_list:
            poed_pse_lldp_dict[port][entry[0]] = entry[1]

    def process_pd_lldp_negotiation(self, port):
        global poed_pd_lldp_dict
        global poed_pse_lldp_dict
        global poed_pstate_dict
        global poed_pconfig_dict

        new_pse_lldp_state = {}
        pd_pkt_type = poed_pd_lldp_dict[port].get("standard", "Unknown")
        pse_powerup_mode = poed_pstate_dict[port].get(PoeStateDb.PORT_POWER_UP_MODE, "Unknown")
        pse_channel_status = poed_pstate_dict[port].get(PoeStateDb.PORT_CHANNEL_STATUS, "P2CH")
        max_threshold_str = poed_pstate_dict[port].get(PoeStateDb.PORT_MAX_POWER_THRESHOLD, "0.0")
        pse_power_value = float(max_threshold_str)
        new_pse_lldp_state[PoeApplDb.LLDP_STANDARD] = pd_pkt_type
        new_pse_lldp_state[PoeApplDb.LLDP_POWER_SOURCE] = "Primary"
        new_pse_lldp_state[PoeApplDb.LLDP_POWER_PRIORITY] = poed_pstate_dict[port].get(PoeStateDb.PORT_PRIORITY, "Unknown")
        pd_req_power_pri_echo = ""
        pd_req_power_sec_echo = ""
        if pd_pkt_type == "af":
            new_pse_lldp_state[PoeApplDb.LLDP_POWER_TYPE] = "PSE"
            new_pse_lldp_state[PoeApplDb.LLDP_POWER_VALUE] = pse_power_value * 1000
        elif pd_pkt_type == "at" or\
            pd_pkt_type == "bt":
            if self.power_mode_val(pse_powerup_mode) < self.power_mode_val("dot3at"):
                new_pse_lldp_state[PoeApplDb.LLDP_POWER_TYPE] = "Type-1-PSE"
            else:
                new_pse_lldp_state[PoeApplDb.LLDP_POWER_TYPE] = "Type-2-PSE"

            new_pse_lldp_state[PoeApplDb.LLDP_MDI_POWER_SUPPORTED] = "True"
            # LLDP pkts are sent only when power is enabled
            new_pse_lldp_state[PoeApplDb.LLDP_MDI_POWER_SUPPORT_STATE] = "True" 
            new_pse_lldp_state[PoeApplDb.LLDP_PAIR_CONTROL] = "True"

            # Get power pair info
            if pse_channel_status.startswith("PS4CH"):
                new_pse_lldp_state[PoeApplDb.LLDP_POWER_PAIR] = "Both"
            elif pse_channel_status.startswith("S2CH"):
                new_pse_lldp_state[PoeApplDb.LLDP_POWER_PAIR] = "Secondary"
            else:
                new_pse_lldp_state[PoeApplDb.LLDP_POWER_PAIR] = "Primary"

            # Get power class info
            pd_class = poed_pstate_dict[port].get(PoeStateDb.PORT_CLASS, "Class0")
            if pd_class.startswith("Class"):
                class_num = ord(pd_class[5]) - 48 #ascii to int
                if class_num >= 4:
                    pd_at_class_echo = "Class4"
                    new_pse_lldp_state[PoeApplDb.LLDP_POWER_CLASS] = "Class4"
                else:
                    pd_at_class_echo = pd_class
                    new_pse_lldp_state[PoeApplDb.LLDP_POWER_CLASS] = pd_class
            else:
                # Class unknown is Class0
                pd_at_class_echo = "Class0"
                new_pse_lldp_state[PoeApplDb.LLDP_POWER_CLASS] = "Class0"
            # PD following AT standard will not advertise power-class. So PSE to derive it from requested/allocated power
            # PD following BT standard will not even fill this power-class  field
            #pd_at_class_echo = poed_pd_lldp_dict[port].get(PoeStateDb.LLDP_POWER_CLASS.field, None)
            #Get PSE allocated information from STATE_DB instead of relying on LLDP request
            if pd_pkt_type == "at":
                pd_req_power_echo = float(poed_pd_lldp_dict[port].get(PoeStateDb.LLDP_PD_REQUESTED_POWER.field, self.power_unknown)) * 0.001
                self.log_info("PD connected to port {} has requested power {} (via LLDP as advertised by PD)".format(port,pd_req_power_echo))
                pse_alloc_power_echo = float(poed_pd_lldp_dict[port].get(PoeStateDb.LLDP_PSE_ALLOCATED_POWER.field, self.power_unknown)) * 0.001
                self.log_info("PSE connected to port {} has allocated power {} (via LLDP as advertised by PD)".format(port,pse_alloc_power_echo))
                pd_req_power = float(poed_pd_lldp_dict[port].get(PoeApplDb.LLDP_PD_REQUESTED_POWER.field, self.power_unknown)) * 0.001
                pse_alloc_power = float(poed_pstate_dict[port].get(PoeApplDb.LLDP_PSE_ALLOCATED_POWER.field, self.power_unknown)) * 0.001
                self.log_info("Port {}, pd_req_power_echo {}, pse_alloc_power_echo {}, pd_req_power {}, pse_alloc_power {},PD at class echo {}, PSE alloc power echo {}, pse alloc power {}, pse power value {}".format(port,pd_req_power_echo,pse_alloc_power_echo,pd_req_power,pse_alloc_power,pd_at_class_echo,pse_alloc_power_echo,pse_alloc_power,pse_power_value))
                if pd_req_power_echo != self.power_unknown and\
                        pse_alloc_power_echo != self.power_unknown and\
                        pd_req_power != self.power_unknown and\
                        pse_alloc_power != self.power_unknown and\
                        pd_at_class_echo.startswith("Class") and\
                        pd_req_power_echo != pse_alloc_power_echo and\
                        pd_req_power_echo <= self.pd_class_max_power(port,pd_at_class_echo) and\
                        pd_req_power_echo <= pse_power_value:
                            # Negotiate
                    self.log_info("Invoking PSE change PD requested power for port {}".format(port))
                    dll_status = self.pse_change_pd_requested_power(port, pd_req_power_echo,pse_powerup_mode)
                    if dll_status is True:
                        new_pse_lldp_state[PoeApplDb.LLDP_PSE_ALLOCATED_POWER] = str(int(pd_req_power_echo * 1000))
                        self.log_info("DLL is allocated power {} for the port {}".format(pd_req_power_echo,port))
                    else:
                        self.log_info("Failed to allocate DLL power {} for the port {}".format(pd_req_power_echo,port))
                        new_pse_lldp_state[PoeApplDb.LLDP_PSE_ALLOCATED_POWER] = str(int(pse_power_value * 1000)) 
                else:
                    if pd_req_power_echo == pse_alloc_power_echo:
                        self.log_info("As per request from PD request power and allocated power are same. Hence not setting dynamic limit")
                    new_pse_lldp_state[PoeApplDb.LLDP_PSE_ALLOCATED_POWER] = str(int(pd_req_power_echo * 1000))
                new_pse_lldp_state[PoeApplDb.LLDP_PD_REQUESTED_POWER] = str(int(pd_req_power_echo * 1000))

            elif pd_pkt_type == "bt" and\
                self.power_mode_val(pse_powerup_mode) >= self.power_mode_val("dot3bt-type3"):
                if pse_powerup_mode == "dot3bt-type3":
                    new_pse_lldp_state[PoeApplDb.LLDP_POWER_TYPE_EXTENSION] = "Type-3-PSE"
                else:
                    new_pse_lldp_state[PoeApplDb.LLDP_POWER_TYPE_EXTENSION] = "Type-4-PSE"

                pd_signature = poed_pstate_dict[port].get(PoeStateDb.PORT_PD_SIGNATURE, "Unknown")
                if pd_signature == "Dual":
                    new_pse_lldp_state[PoeApplDb.LLDP_PSE_POWER_STATUS] = "4-pair-dual-signature-PD"
                elif pd_signature == "Single" and pse_channel_status.startswith("PS4CH"):
                    new_pse_lldp_state[PoeApplDb.LLDP_PSE_POWER_STATUS] = "4-pair-single-signature-PD"
                else:
                    new_pse_lldp_state[PoeApplDb.LLDP_PSE_POWER_STATUS] = "2-pair-powering"

                if pd_signature == "Dual":
                    pd_class_pri = poed_pstate_dict[port].get(PoeStateDb.PORT_PRIMARY_CLASS, "Ignore")
                    pd_class_sec = poed_pstate_dict[port].get(PoeStateDb.PORT_SECONDARY_CLASS, "Ignore")
                    new_pse_lldp_state[PoeApplDb.LLDP_POWER_CLASS_EXTENSION_PRIMARY] = pd_class_pri
                    new_pse_lldp_state[PoeApplDb.LLDP_POWER_CLASS_EXTENSION_SECONDARY] = pd_class_sec
                    new_pse_lldp_state[PoeApplDb.LLDP_POWER_CLASS_EXTENSION] = "Dual-signature-PD"
                else:
                    pd_class = poed_pstate_dict[port].get(PoeStateDb.PORT_CLASS, "Ignore")
                    new_pse_lldp_state[PoeApplDb.LLDP_POWER_CLASS_EXTENSION] = pd_class
                    new_pse_lldp_state[PoeApplDb.LLDP_POWER_CLASS_EXTENSION_PRIMARY] = "Single-signature-PD"
                    new_pse_lldp_state[PoeApplDb.LLDP_POWER_CLASS_EXTENSION_SECONDARY] = "Single-signature-PD"

                new_pse_lldp_state[PoeApplDb.LLDP_PSE_MAX_POWER] = str(pse_power_value * 1000)

                pd_bt_class_echo = poed_pd_lldp_dict[port].get(PoeStateDb.LLDP_POWER_CLASS_EXTENSION.field, "Ignore")
                pd_bt_class_pri_echo = poed_pd_lldp_dict[port].get(PoeStateDb.LLDP_POWER_CLASS_EXTENSION_PRIMARY.field, "Ignore")
                pd_bt_class_sec_echo = poed_pd_lldp_dict[port].get(PoeStateDb.LLDP_POWER_CLASS_EXTENSION_SECONDARY.field, "Ignore")
                pd_req_power = float(poed_pd_lldp_dict[port].get(PoeStateDb.LLDP_PD_REQUESTED_POWER.field, self.power_unknown)) * 0.001
                pd_req_power_echo = float(poed_pd_lldp_dict[port].get(PoeStateDb.LLDP_PD_REQUESTED_POWER.field, self.power_unknown)) * 0.001
                pse_alloc_power = float(poed_pd_lldp_dict[port].get(PoeStateDb.LLDP_PSE_ALLOCATED_POWER.field, self.power_unknown)) * 0.001
                # Single signature PD processing
                if pd_signature != "Dual" and pd_bt_class_echo.startswith("Class"):
                    self.log_info("Framing LLDP response for Single Signature PD")
                    #Using the values fetched from AT processing
                    #pse_alloc_power = float(poed_pd_lldp_dict[port].get(PoeApplDb.LLDP_PSE_ALLOCATED_POWER.field, self.power_unknown)) * 0.001
                    pse_alloc_power_echo = float(poed_pd_lldp_dict[port].get(PoeStateDb.LLDP_PSE_ALLOCATED_POWER.field, self.power_unknown)) * 0.001
                    self.log_info("Port {}, pd_req_power_echo {}, pse_alloc_power_echo {}, pd_req_power {}, pse_alloc_power {},PD BT class echo {}, PSE alloc power echo {}, pse alloc power {}, pse power value {},class max power {}".format(port,pd_req_power_echo,pse_alloc_power_echo,pd_req_power,pse_alloc_power,pd_bt_class_echo,pse_alloc_power_echo,pse_alloc_power,pse_power_value,self.pd_class_max_power(port,pd_bt_class_echo)))
                    if pd_req_power_echo != self.power_unknown and\
                        pse_alloc_power_echo != self.power_unknown and\
                        pd_req_power != self.power_unknown and\
                        pse_alloc_power != self.power_unknown and\
                        pd_req_power_echo != pse_alloc_power_echo and\
                        pd_req_power_echo <= self.pd_class_max_power(port,pd_bt_class_echo) and\
                        pd_req_power_echo <= pse_power_value:
                        # Negotiate
                        self.log_info("Single Signature PD requested power is {}. Configuring MCU LLDP now ".format(pd_req_power_echo))
                        dll_status = self.pse_change_pd_requested_power(port, pd_req_power_echo,pse_powerup_mode)
                        if dll_status is True:
                            new_pse_lldp_state[PoeApplDb.LLDP_PSE_ALLOCATED_POWER] = str(int(pd_req_power_echo * 1000))
                            pd_requested_pri = float(poed_pd_lldp_dict[port].get(PoeStateDb.LLDP_PD_REQUESTED_POWER_PRIMARY.field, self.power_unknown))
                            pd_requested_sec = float(poed_pd_lldp_dict[port].get(PoeStateDb.LLDP_PD_REQUESTED_POWER_SECONDARY.field, self.power_unknown))
                            new_pse_lldp_state[PoeApplDb.LLDP_PSE_ALLOCATED_POWER_PRIMARY] = str(pd_requested_pri)
                            new_pse_lldp_state[PoeApplDb.LLDP_PSE_ALLOCATED_POWER_SECONDARY] = str(pd_requested_sec)
                            self.log_info("Port {} is allocated dynamic power limit {}  where primary pair allocated is {} and secondary pair allocated is {}".format(port,pd_req_power_echo,pd_requested_pri,pd_requested_sec))
                        else:
                            self.log_info("Failed to allocate dynamic power limit {} for the port {}".format(pd_req_power_echo,port))
                            new_pse_lldp_state[PoeApplDb.LLDP_PSE_ALLOCATED_POWER] = str(int(pse_power_value * 1000)) 
                            pd_requested_pri = float(poed_pd_lldp_dict[port].get(PoeStateDb.LLDP_PD_REQUESTED_POWER_PRIMARY.field, self.power_unknown))
                            pd_requested_sec = float(poed_pd_lldp_dict[port].get(PoeStateDb.LLDP_PD_REQUESTED_POWER_SECONDARY.field, self.power_unknown))
                            new_pse_lldp_state[PoeApplDb.LLDP_PSE_ALLOCATED_POWER_PRIMARY] = str(pd_requested_pri)
                            new_pse_lldp_state[PoeApplDb.LLDP_PSE_ALLOCATED_POWER_SECONDARY] = str(pd_requested_sec)
                            """
                            pd_allocated_pri = float(float(pse_power_value/2) * 1000)
                            new_pse_lldp_state[PoeApplDb.LLDP_PSE_ALLOCATED_POWER_PRIMARY] = str(int(pd_allocated_pri))
                            new_pse_lldp_state[PoeApplDb.LLDP_PSE_ALLOCATED_POWER_SECONDARY] = str(int(pd_allocated_pri))
                            """
                    else:
                        if pd_req_power_echo == pse_alloc_power_echo:
                            self.log_info("As per PD request, requested power and allocated power are same. Hence not setting dynamic power limit")
                        else:
                            self.log_info("Single signature BT conditions not met for providing dynamic power limit")
                        new_pse_lldp_state[PoeApplDb.LLDP_PSE_ALLOCATED_POWER] = str(float(poed_pd_lldp_dict[port].get(PoeStateDb.LLDP_PD_REQUESTED_POWER.field, self.power_unknown)))
                        pd_requested_pri = float(poed_pd_lldp_dict[port].get(PoeStateDb.LLDP_PD_REQUESTED_POWER_PRIMARY.field, self.power_unknown))
                        pd_requested_sec = float(poed_pd_lldp_dict[port].get(PoeStateDb.LLDP_PD_REQUESTED_POWER_SECONDARY.field, self.power_unknown))
                        new_pse_lldp_state[PoeApplDb.LLDP_PSE_ALLOCATED_POWER_PRIMARY] = str(pd_requested_pri)
                        new_pse_lldp_state[PoeApplDb.LLDP_PSE_ALLOCATED_POWER_SECONDARY] = str(pd_requested_sec)
                        """
                        pd_allocated_pri = float(float(pse_power_value/2) * 1000)
                        new_pse_lldp_state[PoeApplDb.LLDP_PSE_ALLOCATED_POWER_PRIMARY] = str(pd_allocated_pri)
                        new_pse_lldp_state[PoeApplDb.LLDP_PSE_ALLOCATED_POWER_SECONDARY] = str(pd_allocated_pri)
                        """

                # Dual signature PD processing
                if pd_signature == "Dual" and pd_bt_class_pri_echo.startswith("Class") and pd_bt_class_sec_echo.startswith("Class"):
                    pd_req_power_pri_echo = float(poed_pd_lldp_dict[port].get(PoeStateDb.LLDP_PD_REQUESTED_POWER_PRIMARY.field, self.power_unknown)) * 0.001
                    pd_req_power_sec_echo = float(poed_pd_lldp_dict[port].get(PoeStateDb.LLDP_PD_REQUESTED_POWER_SECONDARY.field, self.power_unknown)) * 0.001
                    pse_alloc_power_pri_echo = float(poed_pd_lldp_dict[port].get(PoeStateDb.LLDP_PSE_ALLOCATED_POWER_PRIMARY.field, self.power_unknown)) * 0.001
                    pse_alloc_power_sec_echo = float(poed_pd_lldp_dict[port].get(PoeStateDb.LLDP_PSE_ALLOCATED_POWER_SECONDARY.field, self.power_unknown)) * 0.001
                    pd_req_power_pri = float(poed_pd_lldp_dict[port].get(PoeApplDb.LLDP_PD_REQUESTED_POWER_PRIMARY.field, self.power_unknown)) * 0.001
                    pd_req_power_sec = float(poed_pd_lldp_dict[port].get(PoeApplDb.LLDP_PD_REQUESTED_POWER_SECONDARY.field, self.power_unknown)) * 0.001
                    pse_alloc_power_pri = float(poed_pd_lldp_dict[port].get(PoeApplDb.LLDP_PSE_ALLOCATED_POWER_PRIMARY.field, self.power_unknown)) * 0.001
                    pse_alloc_power_sec = float(poed_pd_lldp_dict[port].get(PoeApplDb.LLDP_PSE_ALLOCATED_POWER_SECONDARY.field, self.power_unknown)) * 0.001
                    if pd_req_power_pri_echo != self.power_unknown and\
                        pd_req_power_sec_echo != self.power_unknown and\
                        pse_alloc_power_pri_echo != self.power_unknown and\
                        pse_alloc_power_sec_echo != self.power_unknown and\
                        pd_req_power_pri != self.power_unknown and\
                        pd_req_power_sec != self.power_unknown and\
                        pse_alloc_power_pri != self.power_unknown and\
                        pse_alloc_power_sec != self.power_unknown and\
                        pse_alloc_power_pri_echo != pd_req_power_pri_echo and\
                        pse_alloc_power_sec_echo != pd_req_power_sec_echo and\
                        pd_req_power_pri_echo <= self.pd_class_max_power(port,pd_bt_class_pri_echo) and\
                        pd_req_power_sec_echo <= self.pd_class_max_power(port,pd_bt_class_sec_echo) and\
                        (pd_req_power_pri_echo + pd_req_power_sec_echo) <= pse_power_value:
                        # Negotiate
                        to_be_allocated = pd_req_power_pri_echo + pd_req_power_sec_echo
                        self.log_info("Dual Signature PD : Invoke pse change pd requested power for port {} with the power demand {}".format(port,to_be_allocated))
                        dll_status = self.pse_change_pd_requested_power(port,to_be_allocated,pse_powerup_mode)
                        if dll_status is True:
                            new_pse_lldp_state[PoeApplDb.LLDP_PSE_ALLOCATED_POWER_PRIMARY] = str(int(pd_req_power_pri_echo * 1000))
                            new_pse_lldp_state[PoeApplDb.LLDP_PSE_ALLOCATED_POWER_SECONDARY] = str(int(pd_req_power_sec_echo * 1000))
                            self.log_info("DLL is allocated power {} for the port {}".format(to_be_allocated,port))
                        else:
                            self.log_info("Failed to allocate DLL power {} for the port {}".format(to_be_allocated * 1000,port))
                            pd_allocated_pri = float(poed_pd_lldp_dict[port].get(PoeStateDb.LLDP_PSE_ALLOCATED_POWER_PRIMARY.field, self.power_unknown))
                            pd_allocated_sec = float(poed_pd_lldp_dict[port].get(PoeStateDb.LLDP_PSE_ALLOCATED_POWER_SECONDARY.field, self.power_unknown))
                            new_pse_lldp_state[PoeApplDb.LLDP_PSE_ALLOCATED_POWER_PRIMARY] = str(int(pd_allocated_pri))
                            new_pse_lldp_state[PoeApplDb.LLDP_PSE_ALLOCATED_POWER_SECONDARY] = str(int(pd_allocated_sec))
                    else:
                        if pd_req_power_pri_echo == pse_alloc_power_pri_echo and pd_req_power_sec_echo == pse_alloc_power_sec_echo:
                            self.log_info("As per PD request requested power and allocated power are same. Hence not configuring dynamic limit")
                        else:
                            self.log_info("Dual Signature PD. Conditions not met for configuring dynamic power limit")
                        pd_allocated_pri = float(poed_pd_lldp_dict[port].get(PoeStateDb.LLDP_PSE_ALLOCATED_POWER_PRIMARY.field, self.power_unknown))
                        pd_allocated_sec = float(poed_pd_lldp_dict[port].get(PoeStateDb.LLDP_PSE_ALLOCATED_POWER_SECONDARY.field, self.power_unknown))
                        new_pse_lldp_state[PoeApplDb.LLDP_PSE_ALLOCATED_POWER_PRIMARY] = str(int(pd_allocated_pri))
                        new_pse_lldp_state[PoeApplDb.LLDP_PSE_ALLOCATED_POWER_SECONDARY] = str(int(pd_allocated_sec))
                    new_pse_lldp_state[PoeApplDb.LLDP_PSE_ALLOCATED_POWER] = str(float(poed_pd_lldp_dict[port].get(PoeStateDb.LLDP_PSE_ALLOCATED_POWER.field,self.power_unknown)))
                new_pse_lldp_state[PoeApplDb.LLDP_PD_REQUESTED_POWER] = str(float(poed_pd_lldp_dict[port].get(PoeStateDb.LLDP_PD_REQUESTED_POWER.field,self.power_unknown)))
                pd_req_power_pri_echo = float(poed_pd_lldp_dict[port].get(PoeStateDb.LLDP_PD_REQUESTED_POWER_PRIMARY.field, self.power_unknown))
                pd_req_power_sec_echo = float(poed_pd_lldp_dict[port].get(PoeStateDb.LLDP_PD_REQUESTED_POWER_SECONDARY.field, self.power_unknown))
                if pd_req_power_pri_echo != "":
                    new_pse_lldp_state[PoeApplDb.LLDP_PD_REQUESTED_POWER_PRIMARY] = str(pd_req_power_pri_echo)
                if pd_req_power_sec_echo != "":
                    new_pse_lldp_state[PoeApplDb.LLDP_PD_REQUESTED_POWER_SECONDARY] = str(pd_req_power_sec_echo)
            self.log_info("poed_pd_lldp_negotiation new_pse_lldp_state {}".format(new_pse_lldp_state))
            self.update_pse_lldp_db_and_cache_state(port, poed_pse_lldp_dict[port], new_pse_lldp_state)

    def taskworker(self):
        global poed_pconfig_dict
        global poed_pstate_dict
        global poed_pse_lldp_dict

        self.log_info("Start LLDP Update Task")
        # Should always check self.task_stop_event.isSet at least for every second

        state_db = swsscommon.DBConnector("STATE_DB", 0, False)
        pstate_sst = swsscommon.SubscriberStateTable(state_db, "LLDP_MDI_POWER")

        sel = swsscommon.Select()
        sel.addSelectable(pstate_sst)

        #Wait until PoE Daemon get to PoedStage.READY
        while True:
            if self.stage_sync_event.wait(DEFAULT_WAIT_PERIOD):
                if poed_daemon_stage_get() == PoedStage.READY:
                    break
                else:
                    time.sleep(DEFAULT_WAIT_PERIOD)

            if self.task_stop_event.isSet():
                return

        self.log_info("LLDP Update Task Ready")
        while True:
            (state, sel_obj) = sel.select(SELECT_TIMEOUT_MS)
            if self.task_stop_event.isSet():
                return

            if state == swsscommon.Select.TIMEOUT:
                continue
            elif state == swsscommon.Select.OBJECT:
                if sel_obj.getFd() == pstate_sst.getFd():
                    (key, op, fvp) = pstate_sst.pop()
                    while key != "":
                        new_state = {}
                        fvp_dict = dict(fvp)
                        port_lldp_state = poed_pconfig_dict[key].get(PoeConfigDb.PORT_LLDP_STATE, "Disabled")
                        if port_lldp_state != "enabled":
                            # ignore the LLDP pkt from PD
                            self.update_pd_lldp_cache(key, op, fvp_dict)
                            self.disable_pse_lldp_send(key)
                        else:
                            if op == "SET":
                                pse_power_state = poed_pstate_dict[key].get(PoeStateDb.PORT_STATE, "Unknown")
                                pd_category = poed_pstate_dict[key].get(PoeStateDb.PORT_CATEGORY, "Unknown")
                                self.log_info("PD category is {}".format(pd_category))
                                self.update_pd_lldp_cache(key, op, fvp_dict)
                                if pse_power_state == "Delivering Power" and\
                                    (pd_category == "IEEE PD" or pd_category == "Ext range PD"):
                                    self.log_info("Processing negotiation with PD connected to port {}".format(key))
                                    # Only negotiate and send LLDP when PSE is delivering power and PD is IEEE std.
                                    self.process_pd_lldp_negotiation(key)
                                else:
                                    self.disable_pse_lldp_send(key)
                            elif op == "DEL":
                                # Delete APPL_DB table entry
                                self.update_pd_lldp_cache(key, op, fvp_dict)
                                self.disable_pse_lldp_send(key)

                        if self.task_stop_event.isSet():
                            return
                        (key, op, fvp) = pstate_sst.pop()
            else:
                poed_errno = PoedErrno.LLDP_ERR
                raise PoeConfigTaskError("Select wait error!")

    def run(self):
        try:
            self.taskworker()
        except Exception as e:
            self.log_error("Exception occured at {} thread due to {}".format("Lldpthread", repr(e)))
            exc_type, exc_value, exc_traceback = sys.exc_info()
            msg = traceback.format_exception(exc_type, exc_value, exc_traceback)
            for tb_line in msg:
                for tb_line_split in tb_line.splitlines():
                    self.log_error(tb_line_split)
            self.svc_stop_event.set()

class PoedConfigUpdateTask(Thread, PoedThreadLogger):
    def __init__(self, svc_stop_event, stage_sync_event):
        Thread.__init__(self)
        self.setName("PoedConfigUpdateTask")
        PoedThreadLogger.__init__(self, self.getName())
        self.stage_sync_event = stage_sync_event
        self.svc_stop_event = svc_stop_event
        self.task_stop_event = Event()

    def join(self):
        self.log_info("Stop Config Update Task")
        self.task_stop_event.set()
        super(PoedConfigUpdateTask, self).join()

    def taskworker(self):
        global poed_drv_ctl
        global poed_errno
        global poed_gconfig_dict
        global poed_pconfig_dict
        global poed_platform_config
        global error_status_dict

        self.log_info("Start Config Update Task")
        # Should always check self.task_stop_event.isSet at least for every second

        #Wait until PoE Daemon get to PoedStage.INIT_DONE
        while True:
            self.log_debug("stage_sync_event.wait")
            if self.stage_sync_event.wait(DEFAULT_WAIT_PERIOD):
                self.log_debug("{} == {}".format(poed_daemon_stage_get(), PoedStage.INIT_DONE))
                if poed_daemon_stage_get() == PoedStage.INIT_DONE:
                    self.stage_sync_event.clear()
                    break
                else:
                    self.log_debug("time.sleep")
                    time.sleep(DEFAULT_WAIT_PERIOD)

            if self.task_stop_event.isSet():
                return

        if self.task_stop_event.isSet():
            return
        poed_daemon_stage_set(PoedStage.CONFIG)
        self.log_debug("PoE stage CONFIG")

        config_db = swsscommon.DBConnector("CONFIG_DB", 0, False)
        gconfig_table = swsscommon.Table(config_db, "POE_GLOBAL")
        pconfig_table = swsscommon.Table(config_db, "POE_PORT")
        appl_db = swsscommon.DBConnector("APPL_DB",0,False)
        # Fetch current config from DB
        valid, configs = gconfig_table.get("global")
        if valid:
            config_dict = {}
            for field, value in dict(configs).items():
                value = value.lower()
                try:
                    config_enum = PoeConfigDb.__getitem__("GLOBAL_" + field.replace('-','_').upper())
                    config_dict[config_enum] = value
                except KeyError:
                    self.log_info("Skipping unknown global config {}={} set "\
                                  .format(field, value))
                    continue
            poed_gconfig_dict = config_dict

        ports = pconfig_table.getKeys()
        for port in ports:
            valid, configs = pconfig_table.get(port)
            if valid:
                config_dict = {}
                for field, value in dict(configs).items():
                    value = value.lower()
                    try:
                        config_enum = PoeConfigDb.__getitem__("PORT_" + field.replace('-','_').upper())
                        config_dict[config_enum] = value
                    except KeyError:
                        self.log_info("Skipping unknown {} config {}={} set "\
                                      .format(port, field, value))
                        continue
                poed_pconfig_dict[port] = config_dict

        # Disable the PSE only if MCU is reset else skip
        if poed_drv_ctl.is_controller_reset():
            if not poed_drv_ctl.set_system_config(PoeConfigDb.GLOBAL_ENABLE,"false"):
                self.log_error("Global config enable=false set failed!")
                poed_errno = PoedErrno.CONFIG_ERR
                raise PoeConfigTaskError("Global config enable=false set failed!")

            # If Global PSE is not enabled it is safe to allocate Total power
            # Else it has been allocated already
            poed_drv_ctl.set_system_total_power(poed_platform_config["psu-total-power"]["default"])

        # Update MCU, if DB config different from MCU config
        (status, mcu_config_dict) = poed_drv_ctl.get_all_system_config()
        if not status:
            poed_errno = PoedErrno.CONFIG_ERR
            raise PoeConfigTaskError("Get all global config failed!")

        db_pse_config = "false"
        mcu_pse_config = "false"
        for config_enum, config_value in poed_gconfig_dict.items():
            if config_enum.is_mcu():
                mcu_value = mcu_config_dict.get(config_enum, None)
                if config_enum == PoeConfigDb.GLOBAL_ENABLE:
                    db_pse_config = config_value
                    mcu_pse_config = mcu_value
                    continue
                if config_value != mcu_value and\
                    not poed_drv_ctl.set_system_config(config_enum, config_value):
                    self.log_error("Global config {}={} set failed!"\
                                   .format(config_enum.field, config_value))
                    poed_errno = PoedErrno.CONFIG_ERR
                    raise PoeConfigTaskError("Global config {}={} set failed!"\
                                         .format(config_enum.field, config_value))
        for port in poed_pconfig_dict.keys():
            (status, mcu_config_dict) = poed_drv_ctl.get_all_port_config(port)
            if not status:
                raise PoeConfigTaskError("Get all port config failed!")

            for config_enum, config_value in poed_pconfig_dict[port].items():
                if config_enum.is_mcu():
                    mcu_value = mcu_config_dict.get(config_enum, None)
                    if config_value != mcu_value and\
                        not poed_drv_ctl.set_port_config(config_enum, port, config_value):
                        self.log_error("{} config {}={} set failed!"\
                                       .format(port, config_enum.field, config_value))
                        poed_errno = PoedErrno.CONFIG_ERR
                        raise PoeConfigTaskError("{} config {}={} set failed!"\
                                             .format(port, config_enum.field, config_value))

        sel = swsscommon.Select()
        gconfig_sst = swsscommon.SubscriberStateTable(config_db, "POE_GLOBAL")
        sel.addSelectable(gconfig_sst)
        pconfig_sst = swsscommon.SubscriberStateTable(config_db, "POE_PORT")
        sel.addSelectable(pconfig_sst)
        counter_nc = swsscommon.NotificationConsumer(appl_db,"CLEAR_POE_COUNTER")
        sel.addSelectable(counter_nc)
        error_status_nc = swsscommon.NotificationConsumer(appl_db,"CLEAR_POE_ERROR_STATUS")
        sel.addSelectable(error_status_nc)
        poed_daemon_stage_set(PoedStage.CONFIG_DONE)
        self.log_debug("PoE stage CONFIG_DONE")
        self.stage_sync_event.set()
 
        #Wait until PoE Daemon get to PoedStage.READY
        while True:
            if self.stage_sync_event.wait(DEFAULT_WAIT_PERIOD):
                if poed_daemon_stage_get() == PoedStage.READY:
                    break
                else:
                    time.sleep(DEFAULT_WAIT_PERIOD)

            if self.task_stop_event.isSet():
                return
        self.log_info("MCU_PSE_Config is {}".format(mcu_pse_config))
        poed_drv_ctl.set_system_total_power(poed_platform_config["psu-total-power"]["default"])

        if db_pse_config != mcu_pse_config:
            if not poed_drv_ctl.set_system_config(PoeConfigDb.GLOBAL_ENABLE,"true"):
                self.log_error("Global config enable={} set failed!".format(db_pse_config))
                poed_errno = PoedErrno.CONFIG_ERR
                raise PoeConfigTaskError("Global config enable={} set failed!".format(db_pse_config))

        self.log_info("Config Update Task Ready")
        while True:
            (state, sel_obj) = sel.select(SELECT_TIMEOUT_MS)
            if self.task_stop_event.isSet():
                return

            if state == swsscommon.Select.TIMEOUT:
                continue
            elif state == swsscommon.Select.OBJECT:
                if sel_obj.getFd() == gconfig_sst.getFd():
                    (key, op, fvp) = gconfig_sst.pop()
                    while key != "":
                        if key == "global" and op == "SET":
                            for field, value in dict(fvp).items():
                                value = value.lower()
                                try:
                                    config_enum = PoeConfigDb.__getitem__("GLOBAL_" +\
                                                                          field.replace('-','_').upper()) 
                                except KeyError:
                                    self.log_error("Skipping unknown global config {}={} set "\
                                                   .format(field, value))
                                    continue

                                config_value = poed_gconfig_dict.get(config_enum, None)
                                if value != config_value:
                                    if config_enum.is_mcu():
                                        set_system_config_status = poed_drv_ctl.set_system_config(config_enum,value)
                                        if set_system_config_status == False:
                                            self.log_error("Global config {}={} set failed!"\
                                                             .format(field, value))
                                            poed_errno = PoedErrno.CONFIG_ERR
                                            raise PoeConfigTaskError("Global config {}={} set failed!"\
                                                             .format(field, value))
                                    poed_gconfig_dict[config_enum] = value

                        if self.task_stop_event.isSet():
                            return
                        (key, op, fvp) = gconfig_sst.pop()
                elif sel_obj.getFd() == pconfig_sst.getFd():
                    (key, op, fvp) = pconfig_sst.pop()
                    while key != "":
                        if op == "SET":
                            for field, value in dict(fvp).items():
                                value = value.lower()
                                try:
                                    config_enum = PoeConfigDb.__getitem__("PORT_" +\
                                                                          field.replace('-','_').upper()) 
                                except KeyError:
                                    self.log_error("Skipping unknown {} config {}={} set "\
                                                   .format(key, field, value))
                                    continue

                                config_value = poed_pconfig_dict[key].get(config_enum, None)
                                if value != config_value:
                                    if config_enum.is_mcu() and\
                                        not poed_drv_ctl.set_port_config(config_enum, key, value):
                                        self.log_error("{} config {}={} set failed!"\
                                                             .format(key, field, value))
                                        poed_errno = PoedErrno.CONFIG_ERR
                                        raise PoeConfigTaskError("{} config {}={} set failed!"\
                                                             .format(key, field, value))
                                    poed_pconfig_dict[key][config_enum] = value
                                    self.log_info("Poed_pconfig_dictionary {}".format(poed_pconfig_dict[key]))
                                # Check if the port is already present auto reset dictionary. If so purge it
                                if key in error_status_dict.keys() and field == "reset-mode":
                                    del error_status_dict[key]
                                    self.log_info("Deleted the port {} entry from auto reset dictionary".format(key))
                        if self.task_stop_event.isSet():
                            return
                        (key, op, fvp) = pconfig_sst.pop()
                elif sel_obj.getFd() == counter_nc.getFd():
                    (op, data, values) = counter_nc.pop()
                    if op == "PORT":
                        status = poed_drv_ctl.reset_port_counter(data)
                        if not status:
                            self.log_error("Failed to reset port poe counter for port {}".format(data))
                    if self.task_stop_event.isSet():
                        return
                elif sel_obj.getFd() == error_status_nc.getFd():
                    (op, data, values) = error_status_nc.pop()
                    if op == "PORT":
                        # First check whether port is in error_state
                        status = poed_drv_ctl.set_port_reset(data)
                        if not status:
                            self.log_error("Failed to reset error status for port {}".format(data))
                        else:
                            self.log_info("Cleared Error status for port {}".format(data))
                            if data in error_status_dict.keys():
                                del error_status_dict[data]
                                self.log_info("Deleted auto reset entry for the port {} as it was manually cleared by the user".format(data))
                    if self.task_stop_event.isSet():
                        return
            else:
                poed_errno = PoedErrno.CONFIG_ERR
                raise PoeConfigTaskError("Select wait error!")

    def run(self):
        try:
            self.taskworker()
        except Exception as e:
            self.log_error("Exception occured at {} thread due to {}".format("ConfigUpdateTask", repr(e)))
            exc_type, exc_value, exc_traceback = sys.exc_info()
            msg = traceback.format_exception(exc_type, exc_value, exc_traceback)
            for tb_line in msg:
                for tb_line_split in tb_line.splitlines():
                    self.log_error(tb_line_split)
            self.svc_stop_event.set()

# This thread will update both state db and counters db
class PoedStateUpdateTask(Thread, PoedThreadLogger):
    def __init__(self, svc_stop_event, stage_sync_event):
        Thread.__init__(self)
        self.setName("PoedStateUpdateTask")
        PoedThreadLogger.__init__(self, self.getName())
        self.stage_sync_event = stage_sync_event
        self.svc_stop_event = svc_stop_event
        self.task_stop_event = Event()
        self.monitored_ports = {}
        counters_db = swsscommon.DBConnector("COUNTERS_DB", 0, False)
        self.port_counters_table = swsscommon.Table(counters_db, "POE_PORT")
        state_db = swsscommon.DBConnector("STATE_DB", 0, False)
        appl_db = swsscommon.DBConnector("APPL_DB", 0, False)
        self.gstate_table = swsscommon.Table(state_db, "POE_GLOBAL")
        self.estate_table = swsscommon.Table(state_db, "POE_PSE")
        self.pstate_table = swsscommon.Table(state_db, "POE_PORT")
        self.lldp_appl_table = swsscommon.Table(appl_db, "LLDP_MDI_POWER")
        # Removed the mapping between PORT_MAX_POWER_THRESHOLD and USER_POWER_THRESHOLD
        self.db_state_to_db_config = {\
            PoeStateDb.PORT_PRIORITY: PoeConfigDb.PORT_PRIORITY,\
            PoeStateDb.PORT_DETECTION_TYPE: PoeConfigDb.PORT_DETECTION_TYPE,\
            PoeStateDb.PORT_POWER_THRESHOLD_TYPE: PoeConfigDb.PORT_POWER_THRESHOLD_TYPE,\
            PoeStateDb.PORT_POWER_UP_MODE: PoeConfigDb.PORT_POWER_UP_MODE\
        }

        self.port_pair_states = [\
            PoeStateDb.PORT_PRIMARY_STATE,\
            PoeStateDb.PORT_SECONDARY_STATE,\
            PoeStateDb.PORT_PRIMARY_CLASS,\
            PoeStateDb.PORT_SECONDARY_CLASS,\
            PoeStateDb.PORT_PRIMARY_CATEGORY,\
            PoeStateDb.PORT_SECONDARY_CATEGORY,\
            PoeStateDb.PORT_PRIMARY_CHANNEL_STATUS,\
            PoeStateDb.PORT_SECONDARY_CHANNEL_STATUS\
        ]

        self.port_pair_power_states = [\
            PoeStateDb.PORT_PRIMARY_POWER_CONSUMED,\
            PoeStateDb.PORT_SECONDARY_POWER_CONSUMED\
        ]

        self.port_lldp_states = [\
            PoeStateDb.PORT_LLDP_PD_STATE,\
            PoeStateDb.PORT_LLDP_PD_CLASS,\
            PoeStateDb.PORT_LLDP_PD_PRIMARY_CLASS,\
            PoeStateDb.PORT_LLDP_PD_SECONDARY_CLASS,\
            PoeStateDb.PORT_LLDP_PD_REQUESTED_POWER,\
            PoeStateDb.PORT_LLDP_PD_PRIMARY_REQUESTED_POWER,\
            PoeStateDb.PORT_LLDP_PD_SECONDARY_REQUESTED_POWER,\
            PoeStateDb.PORT_LLDP_PSE_STATE,\
            PoeStateDb.PORT_LLDP_PSE_ALLOCATED_POWER,\
            PoeStateDb.PORT_LLDP_PSE_PRIMARY_ALLOCATED_POWER,\
            PoeStateDb.PORT_LLDP_PSE_SECONDARY_ALLOCATED_POWER\
        ]


    def join(self):
        self.log_info("Stop State Update Task")
        self.task_stop_event.set()
        super(PoedStateUpdateTask, self).join()

    def get_port_lldp_state(self, port):
        global poed_pd_lldp_dict
        global poed_pse_lldp_dict
        global poed_pconfig_dict
        lldp_state_dict = {}

        # Initialize none. None implies the field must be removed from DB
        for state in self.port_lldp_states:
            lldp_state_dict[state] = None

        if poed_pconfig_dict[port].get(PoeConfigDb.PORT_LLDP_STATE, "disabled") == "enabled":
            lldp_state_dict[PoeStateDb.PORT_LLDP_PSE_STATE] = "Enabled"
        else:
            lldp_state_dict[PoeStateDb.PORT_LLDP_PSE_STATE] = "Disabled"
            return lldp_state_dict
        if poed_pconfig_dict[port].get(PoeConfigDb.PORT_ENABLE, "false") == "false":
            return lldp_state_dict

        if len(poed_pd_lldp_dict) != 0:
            lldp_state_dict[PoeStateDb.PORT_LLDP_PD_STATE] = "Available"
            pd_at_class = poed_pd_lldp_dict[port].get(PoeStateDb.LLDP_POWER_CLASS.field, "Class0")
            pd_bt_class =  poed_pd_lldp_dict[port].get(PoeStateDb.LLDP_POWER_CLASS_EXTENSION.field, "Ignore")
            pd_bt_primary_class = poed_pd_lldp_dict[port].get(PoeStateDb.LLDP_POWER_CLASS_EXTENSION_PRIMARY.field, "Ignore")
            pd_bt_secondary_class = poed_pd_lldp_dict[port].get(PoeStateDb.LLDP_POWER_CLASS_EXTENSION_SECONDARY.field, "Ignore")
            if pd_bt_primary_class.startswith("Class") and\
                pd_bt_secondary_class.startswith("Class"):
                lldp_state_dict[PoeStateDb.PORT_LLDP_PD_PRIMARY_CLASS] = pd_bt_primary_class
                lldp_state_dict[PoeStateDb.PORT_LLDP_PD_SECONDARY_CLASS] = pd_bt_secondary_class

                pd_pri_req = poed_pd_lldp_dict[port][PoeStateDb.LLDP_PD_REQUESTED_POWER_PRIMARY.field]
                pd_sec_req = poed_pd_lldp_dict[port][PoeStateDb.LLDP_PD_REQUESTED_POWER_SECONDARY.field]
                lldp_state_dict[PoeStateDb.PORT_LLDP_PD_PRIMARY_REQUESTED_POWER] = pd_pri_req
                lldp_state_dict[PoeStateDb.PORT_LLDP_PD_SECONDARY_REQUESTED_POWER] = pd_sec_req
            else:
                if pd_bt_class.startswith("Class"):
                    lldp_state_dict[PoeStateDb.PORT_LLDP_PD_CLASS] = pd_bt_class
                else:
                    lldp_state_dict[PoeStateDb.PORT_LLDP_PD_CLASS] = pd_at_class
            if PoeStateDb.LLDP_PD_REQUESTED_POWER.field in poed_pd_lldp_dict[port]:
                pd_req = float(poed_pd_lldp_dict[port][PoeStateDb.LLDP_PD_REQUESTED_POWER.field]) * 0.001
                #self.log_info("Updating request from PD as {} {}".format(pd_req,port))
                lldp_state_dict[PoeStateDb.PORT_LLDP_PD_REQUESTED_POWER] = str(pd_req) 
        else:
            lldp_state_dict[PoeStateDb.PORT_LLDP_PD_STATE] = "Unavailable"
        if len(poed_pse_lldp_dict) != 0 and\
            lldp_state_dict[PoeStateDb.PORT_LLDP_PSE_STATE] == "Enabled":
            pse_at_class = poed_pse_lldp_dict[port].get(PoeApplDb.LLDP_POWER_CLASS.field, "Class0")
            pse_bt_class =  poed_pse_lldp_dict[port].get(PoeApplDb.LLDP_POWER_CLASS_EXTENSION.field, "Ignore")
            pse_bt_primary_class = poed_pse_lldp_dict[port].get(PoeApplDb.LLDP_POWER_CLASS_EXTENSION_PRIMARY.field, "Ignore")
            pse_bt_secondary_class = poed_pse_lldp_dict[port].get(PoeApplDb.LLDP_POWER_CLASS_EXTENSION_SECONDARY.field, "Ignore")
            if pse_bt_primary_class.startswith("Class") and\
                pse_bt_secondary_class.startswith("Class"):
                pse_pri_alloc = poed_pse_lldp_dict[port][PoeApplDb.LLDP_PSE_ALLOCATED_POWER_PRIMARY.field]
                pse_sec_alloc = poed_pse_lldp_dict[port][PoeApplDb.LLDP_PSE_ALLOCATED_POWER_SECONDARY.field]
                lldp_state_dict[PoeStateDb.PORT_LLDP_PSE_PRIMARY_ALLOCATED_POWER] = pse_pri_alloc
                lldp_state_dict[PoeStateDb.PORT_LLDP_PSE_SECONDARY_ALLOCATED_POWER] = pse_sec_alloc
            if PoeApplDb.LLDP_PSE_ALLOCATED_POWER.field in poed_pse_lldp_dict[port]:
                pse_alloc = poed_pse_lldp_dict[port][PoeApplDb.LLDP_PSE_ALLOCATED_POWER.field]
                lldp_state_dict[PoeStateDb.PORT_LLDP_PSE_ALLOCATED_POWER] = pse_alloc
            
        return lldp_state_dict

    def power_mode_val(self, power_up_mode):
        str_to_val = {\
            "dot3af": 0,\
            "high-inrush": 1,\
            "pre-dot3at": 2,\
            "dot3at": 3,\
            "pre-dot3bt": 4,\
            "dot3bt-type3": 5,\
            "dot3bt-type4": 6\
        }

        return str_to_val.get(power_up_mode, 0)

    def publish_pse_info_on_lldp(self,port):
        global poed_pd_lldp_dict
        global poed_pse_lldp_dict
        global poed_pstate_dict
        global poed_pconfig_dict
        if poed_pconfig_dict[port].get(PoeConfigDb.PORT_LLDP_STATE, "disabled") == "disabled":
            self.lldp_appl_table.delete(port)
            return
        if poed_pconfig_dict[port].get(PoeConfigDb.PORT_ENABLE, "false") == "false":
            self.lldp_appl_table.delete(port)
            return
        new_pse_lldp_state = {}
        unsupported_power_up_mode = ["dot3af","high-inrush","pre-dot3at"]
        pse_powerup_mode = poed_pstate_dict[port].get(PoeStateDb.PORT_POWER_UP_MODE, "Unknown")
        pse_channel_status = poed_pstate_dict[port].get(PoeStateDb.PORT_CHANNEL_STATUS, "P2CH")
        max_threshold_str = poed_pstate_dict[port].get(PoeStateDb.PORT_MAX_POWER_THRESHOLD, "0.0")
        pse_power_value = float(max_threshold_str)
        if pse_powerup_mode == "Unknown" or power_up_mode in unsupported_power_up_mode:
            return
        else:
            if pse_powerup_mode == "dot3at" or pse_powerup_mode == "pre-dot3bt":
                standard = "at"
            elif pse_powerup_mode == "dot3bt-type3" or pse_powerup_mode == "dot3bt-type4":
                standard = "bt"
            else:
                return
            new_pse_lldp_state[PoeApplDb.LLDP_STANDARD] = standard
            new_pse_lldp_state[PoeApplDb.LLDP_POWER_SOURCE] = "Primary"
            new_pse_lldp_state[PoeApplDb.LLDP_POWER_PRIORITY] = poed_pstate_dict[port].get(PoeStateDb.PORT_PRIORITY, "Unknown")
            if self.power_mode_val(pse_powerup_mode) < self.power_mode_val("dot3at"):
                new_pse_lldp_state[PoeApplDb.LLDP_POWER_TYPE] = "Type-1-PSE"
            else:
                new_pse_lldp_state[PoeApplDb.LLDP_POWER_TYPE] = "Type-2-PSE"
            new_pse_lldp_state[PoeApplDb.LLDP_MDI_POWER_SUPPORTED] = "True"
            # LLDP pkts are sent only when power is enabled
            new_pse_lldp_state[PoeApplDb.LLDP_MDI_POWER_SUPPORT_STATE] = "True" 
            new_pse_lldp_state[PoeApplDb.LLDP_PAIR_CONTROL] = "True"

            # Get power pair info
            if pse_channel_status.startswith("PS4CH"):
                new_pse_lldp_state[PoeApplDb.LLDP_POWER_PAIR] = "Both"
            elif pse_channel_status.startswith("S2CH"):
                new_pse_lldp_state[PoeApplDb.LLDP_POWER_PAIR] = "Secondary"
            else:
                new_pse_lldp_state[PoeApplDb.LLDP_POWER_PAIR] = "Primary"

            # Get power class info
            pd_class = poed_pstate_dict[port].get(PoeStateDb.PORT_CLASS, "Class0")
            if pd_class.startswith("Class"):
                class_num = ord(pd_class[5]) - 48 #ascii to int
                if class_num >= 4:
                    pd_at_class_echo = "Class4"
                    new_pse_lldp_state[PoeApplDb.LLDP_POWER_CLASS] = "Class4"
                else:
                    pd_at_class_echo = pd_class
                    new_pse_lldp_state[PoeApplDb.LLDP_POWER_CLASS] = pd_class
            else:
                # Class unknown is Class0
                pd_at_class_echo = "Class0"
                new_pse_lldp_state[PoeApplDb.LLDP_POWER_CLASS] = "Class0"
            if standard == "at":
                new_pse_lldp_state[PoeApplDb.LLDP_PSE_ALLOCATED_POWER] = str(int(pse_power_value * 1000))
                new_pse_lldp_state[PoeApplDb.LLDP_PD_REQUESTED_POWER] = str(int(pse_power_value * 1000))
                if len(new_pse_lldp_state) != 0:
                    fvp_list = []
                    for state, value in new_state.items():
                        fvp_list.append((state.field, value))
                    timestamp = str(datetime.datetime.now())
                    fvp_list.append(("timestamped",timestamp))
                    fvp = swsscommon.FieldValuePairs(fvp_list)
                    self.lldp_appl_table.set(port, fvp)
                    self.log_info("Published PSE request to PD for the port {} as we are yet to receive the PD's first acknowledgement".format(port))
            elif standard == "bt":
                self.log_info("Processing to be added soon")

    @staticmethod
    def enum_val_to_fvp(old_state, new_state):
        fvp_list = []
        for state, value in new_state.items():
            if old_state.get(state, None) != value:
                fvp_list.append((state.field, value))
        return swsscommon.FieldValuePairs(fvp_list)

    def update_system_db_and_cache_state(self, cached_state, new_state):
        self.gstate_table.set("Global", self.enum_val_to_fvp(cached_state, new_state))
        cached_state.update(new_state)

    def update_pse_db_and_cache_state(self, cached_state, new_state):
        for key, state_dict in new_state.items():
            self.estate_table.set(key, self.enum_val_to_fvp(cached_state[key], state_dict))
            cached_state[key].update(state_dict)

    def update_counters_db_for_port(self, port,new_counters):
        fvp_list = []
        for counter, value in new_counters.items():
            fvp_list.append((counter, value))
        fvp = swsscommon.FieldValuePairs(fvp_list)
        self.port_counters_table.set(port, fvp)

    def disable_port_db_and_cache_state(self, port, cached_state):
        port_state_enum = PoeStateDb.PORT_STATE
        port_state_val = "Disabled"

        self.pstate_table.set(port, self.enum_val_to_fvp({}, {port_state_enum:port_state_val}))
        dynamic_power_limit_enum = PoeStateDb.PORT_DYNAMIC_POWER_LIMIT
        dynamic_power_limit_val  = "N/A"
        self.pstate_table.set(port, self.enum_val_to_fvp({}, {dynamic_power_limit_enum:dynamic_power_limit_val}))
        for state in list(cached_state.keys()):
            if state == port_state_enum:
                cached_state[state] = port_state_val
            else:
                self.pstate_table.hdel(port, state.field)
                cached_state.pop(state)

    def remove_counters_db_for_port(self, port):
        self.port_counters_table.delete(port)

    def update_port_db_and_cache_state(self, port, cached_state, new_state, change_event):
        if change_event:
            cached_pri_state_val = cached_state.get(PoeStateDb.PORT_PRIMARY_STATE, None)
            new_pri_state_val = new_state.get(PoeStateDb.PORT_PRIMARY_STATE, None)
            if cached_pri_state_val != None and new_pri_state_val == None:
                #Remove all primary and secondary channel state fields
                for state in self.port_pair_states:
                    self.pstate_table.hdel(port, state.field)
                    cached_state.pop(state)

            cached_channel_status = cached_state.get(PoeStateDb.PORT_CHANNEL_STATUS, None)
            new_channel_status = new_state.get(PoeStateDb.PORT_CHANNEL_STATUS, None)
            if cached_channel_status != None and cached_channel_status.startswith("PS4CH-") and\
                new_channel_status != cached_channel_status:
                for state in self.port_pair_power_states:
                    self.pstate_table.hdel(port, state.field)
                    if state in cached_state:
                        cached_state.pop(state)

        # None implies the field must be removed from DB
        for state in self.port_lldp_states:
            if state in new_state and\
                new_state[state] == None:
                self.pstate_table.hdel(port, state.field)
                if state in cached_state:
                    cached_state.pop(state)
                if state in new_state:
                    new_state.pop(state)

        self.pstate_table.set(port, self.enum_val_to_fvp(cached_state, new_state))
        cached_state.update(new_state)

    def taskworker(self):
        global poed_drv_ctl
        global poed_gstate_dict
        global poed_estate_dict
        global poed_pstate_dict
        global poed_gconfig_dict
        global poed_pconfig_dict
        global error_status_dict
        global poed_pd_lldp_dict
        error_states = ['MPS absent','Short','Overload','Power Denied','Thermal Shutdown','Startup Failure','UVLO','OVLO']
        # Should always check self.task_stop_event.isSet at least for every second
        self.log_info("Start State Update Task")

        #Wait until PoE Daemon get to PoedStage.READY
        while True:
            if self.stage_sync_event.wait(DEFAULT_WAIT_PERIOD):
                if poed_daemon_stage_get() == PoedStage.READY:
                    break
                else:
                    time.sleep(DEFAULT_WAIT_PERIOD)

            if self.task_stop_event.isSet():
                return

        self.log_info("State Update Task Ready")
        measure_freq = 3
        while True:
            if self.task_stop_event.isSet():
                return

            (status, mcu_state_change) = poed_drv_ctl.get_all_port_state_change()
            if not status:
                self.log_error("Get port event summary failed!")
                poed_errno = PoedErrno.STATE_ERR
                raise PoeStateTaskError("Get port event summary failed!")
            ports_measured = False

            for port, cached_state in poed_pstate_dict.items():
                new_state = {}
                new_counters = {}
                change_event = False

                # Do not fetch state when Port PoE is disabled
                if poed_gconfig_dict.get(PoeConfigDb.GLOBAL_ENABLE, "false") == "false" or\
                    poed_pconfig_dict[port].get(PoeConfigDb.PORT_ENABLE, "false") == "false":
                    if len(cached_state) > 1:
                        self.disable_port_db_and_cache_state(port, cached_state)
                    # Remove entry from counters db
                    self.remove_counters_db_for_port(port)
                    continue
                # Construct dictionary for pconfig_dict
                port_pconfig_dict = {}
                for key,value in poed_pconfig_dict.get(port).items():
                    port_pconfig_dict[key.name] = value
                for state, config in self.db_state_to_db_config.items():
                    config_value = port_pconfig_dict.get(config.name, "Unknown")
                    state_value = cached_state.get(state, "Unknown")
                    if state_value != config_value:
                        new_state.update({state: config_value})
                mcu_state = mcu_state_change.get(port, {})
                if not mcu_state:
                    # Force read port state for the first time even without any event
                    (status, mcu_state) = poed_drv_ctl.get_port_state(port)
                    if not status:
                        self.log_error("Get port state failed!")
                        poed_errno = PoedErrno.STATE_ERR
                        raise PoeStateTaskError("Get port state failed!")

                mcu_power_state = {}
                mcu_port_state = mcu_state.get(PoeStateDb.PORT_STATE, "Unknown")
                cached_port_state = cached_state.get(PoeStateDb.PORT_STATE, "Unknown")
                self.log_info("PoE state {} is read from MCU for port {}".format(mcu_port_state,port))
                if mcu_port_state in error_states:
                    if port not in error_status_dict.keys():
                        # to get latest port reset values always rely poed_pconfig_dictionary as thread switching between config and state 
                        port_reset_value = 'manual'
                        for key,value in poed_pconfig_dict.get(port).items():
                            if key.name == "PORT_RESET_MODE":
                                port_reset_value = value
                        #self.log_info("Port reset value is {}".format(port_reset_value))
                        #port_reset_value = port_pconfig_dict.get("PORT_RESET_MODE","Manual")
                        if port_reset_value != "manual":
                            timer_value = port_pconfig_dict.get("PORT_AUTO_RESET_TIMER","Unknown")
                            self.log_info("timer value is {}".format(timer_value))
                            if timer_value != "Unknown":
                                self.log_info("Including {} port in error status timer list".format(port))
                                error_status_dict[port] = int(timer_value)
                if mcu_port_state != "Delivering Power":
                    poed_pd_lldp_dict[port] = {}
                    for state in self.port_lldp_states:
                        new_state[state] = None
                    if poed_pconfig_dict[port].get(PoeConfigDb.PORT_LLDP_STATE, "disabled") == "enabled":
                        new_state[PoeStateDb.PORT_LLDP_PSE_STATE] = "Enabled"
                    else:
                        new_state[PoeStateDb.PORT_LLDP_PSE_STATE] = "Disabled"
                    new_state[PoeStateDb.PORT_DYNAMIC_POWER_LIMIT] = "N/A"
                if measure_freq == PORT_MEASUREMENT_FREQ or\
                    (mcu_state and\
                     (mcu_port_state == "Delivering Power" or\
                      cached_port_state == "Delivering Power") and\
                     mcu_port_state != cached_port_state):

                    # Also force measurements strictly after power state change
                    (status, mcu_power_state) = poed_drv_ctl.get_port_measurements(port)
                    if not status:
                        self.log_error("Get port power measurements failed!")
                        poed_errno = PoedErrno.STATE_ERR
                        raise PoeStateTaskError("Get port power measurements failed!")
                    new_state.update(mcu_power_state)
                    if mcu_port_state == "Delivering Power":
                        lldp_state = self.get_port_lldp_state(port)
                        if lldp_state:
                            new_state.update(lldp_state)

                    ports_measured = True
                if mcu_port_state == "Delivering Power":
                    self.log_info("Setting Amber LED ON for the port {}".format(port))
                    poed_drv_ctl.set_port_led(port,PoeLedState.PORT_LED_ON)
                else:
                    self.log_info("Setting Amber LED OFF for the port {}".format(port))
                    poed_drv_ctl.set_port_led(port,PoeLedState.PORT_LED_OFF)
                if mcu_state:
                    change_event = True
                    new_state.update(mcu_state)
                self.update_port_db_and_cache_state(port, cached_state, new_state, change_event)
                status, new_counters = poed_drv_ctl.get_mcu_port_all_counters(port)
                if status is True:
                    self.update_counters_db_for_port(port,new_counters)
                # Do not update counters for disabled ports
                # When port is disabled, if such port has entry in counters db (do counters db get) then purge it
                if poed_gconfig_dict.get(PoeConfigDb.GLOBAL_ENABLE, "false") == "false" or\
                    poed_pconfig_dict[port].get(PoeConfigDb.PORT_ENABLE, "false") == "false":
                    if len(cached_state) > 1:
                        self.disable_port_db_and_cache_state(port, cached_state)
                        self.remove_counters_db_for_port(port)
                    continue

            if measure_freq == PORT_MEASUREMENT_FREQ:
                # Update system status for power allocation changes, whenever the ports are measured
                # measure global state even when ports are not measured
                cached_state = poed_gstate_dict
                (status, system_state) = poed_drv_ctl.get_all_system_state()
                if not status:
                    self.log_error("Get system state failed!")
                    poed_errno = PoedErrno.STATE_ERR
                    raise PoeStateTaskError("Get system state failed!")
                self.update_system_db_and_cache_state(cached_state, system_state)

            if measure_freq == PORT_MEASUREMENT_FREQ:
                # Update PSE states
                cached_state = poed_estate_dict
                (status, pse_state) = poed_drv_ctl.get_all_pse_state()
                if not status:
                    self.log_error("Get PSE state failed!")
                    poed_errno = PoedErrno.STATE_ERR
                    raise PoeStateTaskError("Get PSE state failed!")

                self.update_pse_db_and_cache_state(cached_state, pse_state)
            measure_freq = (measure_freq + 1) if measure_freq < PORT_MEASUREMENT_FREQ else 1
            # Sleep for 5 seconds
            for port in error_status_dict.copy():
                error_status_dict[port] = error_status_dict[port] - 5
                if error_status_dict[port] <= 0:
                    self.log_info("Auto clearing error status for port {}".format(port))
                    status = poed_drv_ctl.set_port_reset(port)
                    if not status:
                        self.log_error("Failed to auto reset error status for port {}".format(port))
                    del error_status_dict[port]
            self.log_info("Port auto reset dictionary {}".format(error_status_dict))
            time.sleep(5)

    def run(self):
        try:
            self.taskworker()
        except Exception as e:
            self.log_error("Exception occured at {} thread due to {}".format("StateUpdateTask", repr(e)))
            exc_type, exc_value, exc_traceback = sys.exc_info()
            msg = traceback.format_exception(exc_type, exc_value, exc_traceback)
            for tb_line in msg:
                for tb_line_split in tb_line.splitlines():
                    self.log_error(tb_line_split)
            self.svc_stop_event.set()


class DaemonPoed(daemon_base.DaemonBase):
    def __init__(self, log_id):
        super(DaemonPoed, self).__init__(log_id)

        self.svc_stop_event = Event()
        self.stage_sync_event = Event()
        self.platform_config = None
        self.thread_list = []
 
    # Signal handler
    def signal_handler(self, sig, frame):
        if sig == signal.SIGHUP:
            self.log_info("Caught SIGHUP - ignoring...")
        elif sig == signal.SIGINT:
            self.log_info("Caught SIGINT - exiting...")
            self.svc_stop_event.set()
        elif sig == signal.SIGTERM:
            self.log_info("Caught SIGTERM - exiting...")
            self.svc_stop_event.set()
        else:
            self.log_warning("Caught unhandled signal '" + sig + "'")

    def run(self):
        global poed_platform_config
        global poed_drv_ctl
        global poed_pconfig_dict
        global poed_pstate_dict
        global log_helper

        if not os.geteuid() == 0:
            self.log_error("Must be root to run this daemon({})".format(POED_SERVICE_NAME))
            sys.exit(PoedErrno.INIT_ERR)

        self.log_info("Starting up daemon")

        poed_daemon_stage_set(PoedStage.INIT)
        self.log_debug("PoE stage INIT")


        # Load the platform specific PoE JSON
        (platform_name, hwsku) = device_info.get_platform_and_hwsku()
        cfg_path = POED_PLATFORM_CONFIG_PATH.format(platform_name)
        self.log_info("Loading PoE config from {}".format(cfg_path))
        with open(cfg_path, 'r') as fd:
            poed_platform_config = json.load(fd)

        if poed_platform_config.get("firmware-path", None) == None:
            poed_platform_config["firmware-path"] = POED_FIRMWARE_DEFAULT_PATH.format(platform_name)

        for port_num in range(poed_platform_config["num-poe-ports"]):
            port = "Ethernet{}".format(port_num)
            poed_pconfig_dict[port] = {}
            poed_pstate_dict[port] = {}
            poed_pse_lldp_dict[port] = {}
            poed_pd_lldp_dict[port] = {}
            poed_counters_dict[port] = {}

        for device in range(poed_platform_config["num-pse-devices"]):
            poed_estate_dict[str(device)] = {}

        poed_drv_ctl = PoeDrvUtilHigh(poed_platform_config, log_helper)
        if not poed_drv_ctl.init():
            self.log_error("PoE driver initialization failed! Aborting...")
            sys.exit(PoedErrno.INIT_ERR)

        if not poed_drv_ctl.is_controller_ready():
            self.log_info("PoE controller failed to get to ready state. Aborting...")
            sys.exit(PoedErrno.INIT_ERR)

        lldp_update_task = PoedLldpUpdateTask(self.svc_stop_event, self.stage_sync_event)
        config_update_task = PoedConfigUpdateTask(self.svc_stop_event, self.stage_sync_event)
        state_update_task = PoedStateUpdateTask(self.svc_stop_event, self.stage_sync_event)
        self.log_debug("PoE starting threads")


        config_update_task.start()
        self.thread_list.append(config_update_task)

        state_update_task.start()
        self.thread_list.append(state_update_task)

        # lldp THREAD IS START AT LAST AS it is dependent on state updation first for it to process
        lldp_update_task.start()
        self.thread_list.append(lldp_update_task)

        poed_daemon_stage_set(PoedStage.INIT_DONE)
        self.log_debug("PoE stage INIT_DONE")
        self.stage_sync_event.set()

        #Wait until PoE Daemon get to PoedStage.INIT_DONE
        while True:
            if self.stage_sync_event.wait(DEFAULT_WAIT_PERIOD):
                if poed_daemon_stage_get() == PoedStage.CONFIG_DONE:
                    self.stage_sync_event.clear()
                    break
                else:
                    time.sleep(DEFAULT_WAIT_PERIOD)

            if self.svc_stop_event.isSet():
                break

        if not self.svc_stop_event.isSet():
            poed_daemon_stage_set(PoedStage.READY)
            self.log_debug("PoE stage READY")
            self.stage_sync_event.set()
            self.log_info("Daemon Ready!")

        # Waiting for any stop event
        self.svc_stop_event.wait()
        self.log_info("Shutting down daemon")

        for thread in self.thread_list:
            if thread.is_alive():
                thread.join()

        poed_drv_ctl.deinit()

        sys.exit(poed_errno) 


def main():
    global log_helper
    log_helper = Logger(POED_SERVICE_NAME)
    poed = DaemonPoed(POED_SERVICE_NAME)
    # Set minimum syslog level
    poed.set_min_log_priority_debug()
    log_helper.set_min_log_priority_debug()
    poed.run()


if __name__ == "__main__":
    main()
