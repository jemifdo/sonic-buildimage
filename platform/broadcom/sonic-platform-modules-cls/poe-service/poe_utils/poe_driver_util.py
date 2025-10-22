import time
import math
import subprocess
from enum import IntEnum, Enum, auto
try:
    from .poe_constants import PoeConfigDb, PoeStateDb, PoeLedState
    from .poe_driver import PoeDrv
except ImportError as e:
    raise ImportError(str(e) + "- required module not found")
 
BSC_SEQ_NUM = 0
MAX_UPGRADE_ATTEMPT = 3
MAX_PORT_MAP_ATTEMPT = 3
MAX_BSC_RETRY = 1
MAX_MCU_WAIT_TIME = 3 # 3000ms max of all wait times

MCU_BOOT_ROM = 0xAF
RSP_ACK = 0
RSP_NACK = 1

def get_bsc_seq_num():
    global BSC_SEQ_NUM

    seq = BSC_SEQ_NUM
    if BSC_SEQ_NUM == 255:
        BSC_SEQ_NUM = 0
    else:
        BSC_SEQ_NUM = BSC_SEQ_NUM + 1

    return seq

def get_bsc_cmd(bsc_cmd):
    # Add padding byte 0xFF upto BSC command size of 11 bytes
    for x in range(11 - len(bsc_cmd)):
        bsc_cmd.append(0xFF)

    return bytearray(bsc_cmd)

def mcu_retry_transaction(operation):
    def mcu_retry_transaction_set(function):
        def wrapper(*args, **kwargs):
            attempt = 0
            while attempt < MAX_BSC_RETRY:
                status = function(*args, **kwargs)
                if status:
                    break
                attempt = attempt + 1
                time.sleep(0.03) # 30ms

            return status

        return wrapper

    def mcu_retry_transaction_get(function):
        def wrapper(*args, **kwargs):
            attempt = 0
            while attempt < MAX_BSC_RETRY:
                (status, status_dict) = function(*args, **kwargs)
                if status:
                    break
                attempt = attempt + 1
                time.sleep(0.03) # 30ms

            return (status, status_dict)

        return wrapper

    if operation == "SET":
        return mcu_retry_transaction_set
    elif operation == "GET":
        return mcu_retry_transaction_get


class MCUCommand(IntEnum):
    # Global Configs
    GLOBAL_ENABLE = 0x101
    GLOBAL_CONTROLLER_MODE = 0x102
    #GLOBAL_UVLO = 0x0A
    #GLOBAL_OVLO = 0x0A
    #GLOBAL_DOUBLE_DETECTION = 0x0A
    GLOBAL_PORT_EVENT_MASK = 0x0D
    #GLOBAL_PRE_ALLOC = 0x0B
    #GLOBAL_EXT_POWER_MGMT = 0x0B
    GLOBAL_PSE_RESET = 0x09
    GLOBAL_POWER_MANAGEMENT = 0x17
    GLOBAL_POWER_SOURCE = 0x18
    #GLOBAL_LED_BEHAVIOR
    #GLOBAL_4BIT_MPSS
    #GLOBAL_BOOT_DELAY_RESET_LOW
    GLOBAL_STATUS = 0x20
    PORT_STATUS_QUERY = 0x21
    PORT_COUNTER_QUERY = 0x22
    PORT_COUNTER_RESET = 0x05
    GLOBAL_TOTAL_POWER_QUERY = 0x23
    PORT_CONFIG_QUERY = 0x25
    PORT_EXT_CONFIG_QUERY = 0x26
    GLOBAL_POWER_MGMT_QUERY = 0x27
    GLOBAL_V48_VOLTAGE_STATUS = 0x2D
    # Port configs
    PORT_PSE_ENABLE = 0x00
    #PORT_POWER_UP
    PORT_LOGICAL_MAP = 0x02
    PORT_HIGH_POWER_MODE = 0x08
    PORT_PAIR_MAPPING = 0x0E
    PORT_DETECTION_TYPE = 0x10
    #PORT_CLASSIF_TYPE
    #PORT_AUTO_POWER_UP
    #PORT_DISCONNECT_TYPE
    PORT_POWER_THRESHOLD_TYPE = 0x15
    PORT_USER_POWER_THRESHOLD = 0x16
    PORT_POWER_PAIR = 0x19
    PORT_PRIORITY = 0x1A
    PORT_POWER_UP_MODE = 0x1C
    #PORT_DISCONNECT_MASK
    #PORT_LED_BEHAVIOR
    #PORT_4BIT_DISCONNECT_MASK
    #PORT_LED_REMAP
    GLOBAL_PORT_EVENT_STATUS = 0x2C
    PORT_MEASUREMENT = 0x30
    PORT_PAIR_POWER_AUTO_CLASS = 0x3C
    PORT_PAIR_STATUS_QUERY = 0x3D
    GLOBAL_PSE_DEVICE_ADDRESS = 0x40
    PORT_DYNAMIC_THRESHOLD = 0x4A
    GLOBAL_RESET_CAUSE = 0x4D
    #PORT_POWER_UP_ALTERNATE
    PORT_RESET = 0x03
    GLOBAL_MISC_CMD = 0xE0


class MiscSubCommand(IntEnum):
    FORCE_CRC_AND_SWITCH = 0x40
    DOWNLOAD_IMAGE = 0x80
    CLEAR_IMAGE = 0xC0
    CLEAR_CONFIG = 0xE0
    SAVE_CONFIG = 0xF0


class MCUState(IntEnum):
    # Global
    GLOBAL_IN_BOOT_MODE = auto()
    GLOBAL_CONTROLLER_MODE = auto()
    GLOBAL_MAX_PORTS = auto()
    GLOBAL_PORT_MAP = auto()
    GLOBAL_DEVICE_ID = auto()
    GLOBAL_FW_VERSION = auto()
    GLOBAL_CONTROLLER_TYPE = auto()
    GLOBAL_CONFIG_DIRTY = auto()
    GLOBAL_IS_SYSTEM_RESET = auto()
    GLOBAL_ENABLE = auto()
    GLOBAL_SLAP_MAP = auto()
    GLOBAL_CONTROLLER_STATUS = auto()
    GLOBAL_EXT_FW_VERSION = auto()
    GLOBAL_POWER_MANAGEMENT = auto()
    GLOBAL_GUARD_BAND = auto()
    GLOBAL_AVAILABLE_POWER = auto()
    GLOBAL_ALLOCATED_POWER = auto()
    GLOBAL_MPSS_STATE = auto()
    GLOBAL_RESET_CAUSE = auto()
    GLOBAL_EVENT_PORTS = auto()
    # PSE
    PSE_VOLTAGE = auto()
    PSE_OTP_VERSION = auto()
    PSE_HW_ADDRESS = auto()
    PSE_TYPE = auto()
    # Port
    PORT_STATE = auto()
    PORT_CLASS = auto()
    PORT_CATEGORY = auto()
    PORT_MPSS_MASK = auto()
    PORT_POWER_UP_MODE = auto()
    PORT_POWERED_CHANNEL = auto()
    PORT_CONNECTION_TYPE = auto()
    PORT_PRIMARY_STATE = auto()
    PORT_PRIMARY_CLASS = auto()
    PORT_PRIMARY_CATEGORY = auto()
    PORT_PRIMARY_POWER_UP_MODE = auto()
    PORT_PRIMARY_POWER_APPLIED = auto()
    PORT_SECONDARY_STATE = auto()
    PORT_SECONDARY_CLASS = auto()
    PORT_SECONDARY_CATEGORY = auto()
    PORT_SECONDARY_POWER_UP_MODE = auto()
    PORT_SECONDARY_POWER_APPLIED = auto()
    PORT_POWER_CONSUMED = auto()
    PORT_PRIMARY_POWER_CONSUMED = auto()
    PORT_SECONDARY_POWER_CONSUMED = auto()
    PORT_VOLTAGE = auto()
    PORT_CURRENT = auto()
    PORT_TEMPERATURE = auto()
    PORT_AUTO_CLASS_STATE = auto()
    PORT_AUTO_CLASS_POWER = auto()
    PORT_DYNAMIC_POWER_LIMIT = auto()

    def is_global(self):
        if self.name.startswith('GLOBAL_'):
            return True

        return False

    def is_port(self):
        if self.name.startswith('PORT_'):
            return True

        return False


class PoeDrvLogger():
    def __init__(self, logger, log_prefix="PoeDriver"):
        self.log = logger
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


class PoeDrvUtilHigh(PoeDrvLogger):
    def __init__(self, poe_platform_config, logger):
        self.poe_platform_config = poe_platform_config
        PoeDrvLogger.__init__(self, logger)
        self.mcu_drv = PoeDrv(self.poe_platform_config["drv-intf"]["id"],\
                              self.poe_platform_config["drv-intf"]["type"],\
                              logger)
        self.mcu_value_cache = {}
        self.global_system_is_reset = "False"
        self.global_pse_enable_cmd = None
        self.global_controller_mode_cmd = None
        self.port_led_set_cmd = None
        self.port_led_state_dict = {\
            PoeLedState.PORT_LED_OFF: None,\
            PoeLedState.PORT_LED_ON: None,\
            PoeLedState.PORT_LED_ERROR: None\
        }

        self.db_config_to_mcu_config_cmd = {\
            PoeConfigDb.GLOBAL_ENABLE: MCUCommand.GLOBAL_ENABLE,\
            PoeConfigDb.GLOBAL_CONTROLLER_MODE: MCUCommand.GLOBAL_CONTROLLER_MODE,\
            PoeConfigDb.GLOBAL_POWER_MANAGEMENT: MCUCommand.GLOBAL_POWER_MANAGEMENT,\
            PoeConfigDb.GLOBAL_GUARD_BAND: MCUCommand.GLOBAL_POWER_SOURCE,\

            PoeConfigDb.PORT_ENABLE: MCUCommand.PORT_PSE_ENABLE,\
            PoeConfigDb.PORT_DETECTION_TYPE: MCUCommand.PORT_DETECTION_TYPE,\
            PoeConfigDb.PORT_POWER_UP_MODE: MCUCommand.PORT_POWER_UP_MODE,\
            PoeConfigDb.PORT_POWER_PAIR: MCUCommand.PORT_POWER_PAIR,\
            PoeConfigDb.PORT_PRIORITY: MCUCommand.PORT_PRIORITY,\
            PoeConfigDb.PORT_POWER_THRESHOLD_TYPE: MCUCommand.PORT_POWER_THRESHOLD_TYPE,\
            PoeConfigDb.PORT_USER_POWER_THRESHOLD: MCUCommand.PORT_USER_POWER_THRESHOLD\
        }

        self.mcu_state_to_db_state = {\
            MCUState.GLOBAL_ENABLE: PoeStateDb.GLOBAL_ENABLE,\
            MCUState.GLOBAL_CONTROLLER_MODE: PoeStateDb.GLOBAL_CONTROLLER_MODE,\
            MCUState.GLOBAL_POWER_MANAGEMENT: PoeStateDb.GLOBAL_POWER_MANAGEMENT,\
            MCUState.GLOBAL_GUARD_BAND: PoeStateDb.GLOBAL_GUARD_BAND,\
            MCUState.GLOBAL_AVAILABLE_POWER: PoeStateDb.GLOBAL_AVAILABLE_POWER,\
            MCUState.GLOBAL_ALLOCATED_POWER: PoeStateDb.GLOBAL_ALLOCATED_POWER,\
            MCUState.GLOBAL_RESET_CAUSE: PoeStateDb.GLOBAL_RESET_CAUSE,\
            MCUState.GLOBAL_CONTROLLER_TYPE: PoeStateDb.GLOBAL_CONTROLLER_TYPE,\
            MCUState.GLOBAL_CONTROLLER_STATUS: PoeStateDb.GLOBAL_CONTROLLER_STATUS,\
            MCUState.GLOBAL_FW_VERSION: PoeStateDb.GLOBAL_FW_VERSION,\
            MCUState.GLOBAL_EXT_FW_VERSION: PoeStateDb.GLOBAL_EXT_FW_VERSION,\

            MCUState.PORT_STATE: PoeStateDb.PORT_STATE,\
            MCUState.PORT_PRIMARY_STATE: PoeStateDb.PORT_PRIMARY_STATE,\
            MCUState.PORT_SECONDARY_STATE: PoeStateDb.PORT_SECONDARY_STATE,\
            MCUState.PORT_CLASS: PoeStateDb.PORT_CLASS,\
            MCUState.PORT_PRIMARY_CLASS: PoeStateDb.PORT_PRIMARY_CLASS,\
            MCUState.PORT_SECONDARY_CLASS: PoeStateDb.PORT_SECONDARY_CLASS,\
            MCUState.PORT_CATEGORY: PoeStateDb.PORT_CATEGORY,\
            MCUState.PORT_PRIMARY_CATEGORY: PoeStateDb.PORT_PRIMARY_CATEGORY,\
            MCUState.PORT_SECONDARY_CATEGORY: PoeStateDb.PORT_SECONDARY_CATEGORY,\
            MCUState.PORT_POWER_CONSUMED: PoeStateDb.PORT_POWER_CONSUMED,\
            MCUState.PORT_PRIMARY_POWER_CONSUMED: PoeStateDb.PORT_PRIMARY_POWER_CONSUMED,\
            MCUState.PORT_SECONDARY_POWER_CONSUMED: PoeStateDb.PORT_SECONDARY_POWER_CONSUMED,\
            MCUState.PORT_VOLTAGE: PoeStateDb.PORT_VOLTAGE,\
            MCUState.PORT_CURRENT: PoeStateDb.PORT_CURRENT,\
            MCUState.PORT_TEMPERATURE: PoeStateDb.PORT_TEMPERATURE,\
            MCUState.PORT_AUTO_CLASS_STATE: PoeStateDb.PORT_AUTO_CLASS_STATE,\
            MCUState.PORT_AUTO_CLASS_POWER: PoeStateDb.PORT_AUTO_CLASS_POWER,\
            MCUState.PORT_DYNAMIC_POWER_LIMIT: PoeStateDb.PORT_DYNAMIC_POWER_LIMIT,\

            MCUState.PSE_VOLTAGE: PoeStateDb.PSE_VOLTAGE,\
            MCUState.PSE_OTP_VERSION: PoeStateDb.PSE_OTP_VERSION,\
            MCUState.PSE_HW_ADDRESS: PoeStateDb.PSE_HW_ADDRESS,\
            MCUState.PSE_TYPE: PoeStateDb.PSE_TYPE,\
        }

        self.mcu_command_to_set_api = {\
            MCUCommand.GLOBAL_ENABLE: self._sset_cpld_global_pse_enable_config,\
            MCUCommand.GLOBAL_CONTROLLER_MODE: self._sset_cpld_global_controller_mode_config,\
            MCUCommand.GLOBAL_POWER_MANAGEMENT: self._sset_mcu_global_power_mgmt_mode_config,\
            MCUCommand.GLOBAL_POWER_SOURCE: self._sset_mcu_global_guard_band_config,\

            MCUCommand.PORT_PSE_ENABLE: self._sset_mcu_port_pse_enable_config,\
            MCUCommand.PORT_RESET: self._sset_mcu_port_reset_config,\
            MCUCommand.PORT_DETECTION_TYPE: self._sset_mcu_port_detection_type_config,\
            MCUCommand.PORT_POWER_UP_MODE: self._sset_mcu_port_power_up_mode_config,\
            MCUCommand.PORT_POWER_PAIR: self._sset_mcu_port_power_pair_config,\
            MCUCommand.PORT_PRIORITY: self._sset_mcu_port_priority_config,\
            MCUCommand.PORT_POWER_THRESHOLD_TYPE: self._sset_mcu_port_power_threshold_type_config,\
            MCUCommand.PORT_USER_POWER_THRESHOLD: self._sset_mcu_port_user_power_threshold_config,\
        }

        self.mcu_config_to_get_api = {\
            MCUCommand.GLOBAL_ENABLE: self._gget_cpld_global_pse_enable_config,\
            MCUCommand.GLOBAL_CONTROLLER_MODE: self._gget_cpld_global_controller_mode_config,\
            MCUCommand.GLOBAL_POWER_MANAGEMENT: self._gget_mcu_global_power_mgmt_mode_config,\
            MCUCommand.GLOBAL_POWER_SOURCE: self._gget_mcu_global_guard_band_config,\

            MCUCommand.PORT_PSE_ENABLE: self._gget_mcu_port_pse_enable_config,\
            MCUCommand.PORT_DETECTION_TYPE: self._gget_mcu_port_detection_type_config,\
            MCUCommand.PORT_POWER_UP_MODE: self._gget_mcu_port_power_up_mode_config,\
            MCUCommand.PORT_POWER_PAIR: self._gget_mcu_port_power_pair_config,\
            MCUCommand.PORT_PRIORITY: self._gget_mcu_port_priority_config,\
            MCUCommand.PORT_POWER_THRESHOLD_TYPE: self._gget_mcu_port_power_threshold_type_config,\
            MCUCommand.PORT_USER_POWER_THRESHOLD: self._gget_mcu_port_user_power_threshold_config,\
        }

    def init(self):
        status = False
        status_dict = {}

        if not self.mcu_drv.init():
            self.log_error("Controller interface driver init failed!")
            return False

        (status, status_dict) = self._gget_mcu_global_status()
        if not status:
            self.log_error("PoE get global status failed!")
            return False

        # Upgrade image if MCU in boot mode
        if status_dict[MCUState.GLOBAL_IN_BOOT_MODE] == "True":
            self.global_system_is_reset = "True"
            upgrade_attempt = 0
            while upgrade_attempt < MAX_UPGRADE_ATTEMPT and\
                status_dict[MCUState.GLOBAL_IN_BOOT_MODE] == "True":
                upgrade_attempt = upgrade_attempt + 1
                self.log_warning("PoE Controller does not have a valid firmware,"\
                                 " upgrading (attempt:{})".format(upgrade_attempt))
                if not self.__mcu_upgrade_firmware(self.poe_platform_config["firmware-path"], False):
                    continue

                (status, status_dict) = self._gget_mcu_global_status()
                if not status:
                    self.log_error("PoE get global status failed!")
                    return False

                break

            if upgrade_attempt == MAX_UPGRADE_ATTEMPT:
                self.log_error("All {} attempts to upgrade PoE Controller failed!".format(upgrade_attempt))
                return False

            time.sleep(2) # Wait is required for configuring the MCU after upgrade
        else:
            self.global_system_is_reset = status_dict[MCUState.GLOBAL_IS_SYSTEM_RESET] 

        # Check for ready state stage1
        if status_dict[MCUState.GLOBAL_CONTROLLER_STATUS] != "Ready":
            self.log_error("PoE Controller is not ready at stage1 boot")
            return False

        # Check and program port map if not present
        port_map_attempt = 0
        while port_map_attempt < MAX_PORT_MAP_ATTEMPT and\
            (status_dict[MCUState.GLOBAL_MAX_PORTS] != str(self.poe_platform_config["num-poe-ports"]) or\
             status_dict[MCUState.GLOBAL_SLAP_MAP] != "Present"):
            self.global_system_is_reset = "True"

            port_map_attempt = port_map_attempt + 1
            if status_dict[MCUState.GLOBAL_SLAP_MAP] == "Present":
                self.log_warning("PoE Controller does not have a valid port map."\
                                 " Erasing port map (attempt:{})".format(port_map_attempt))
                if not self._sset_mcu_platform_port_map_clear_config():
                    continue

                (status, status_dict) = self._gget_mcu_global_status()
                if not status:
                    self.log_error("PoE get global status failed!")
                    return False

                # Successfully cleared the port map, lets install new port map
                port_map_attempt = port_map_attempt - 1
                continue
            else:
                self.log_warning("PoE Controller does not have any port map."\
                                 " Progarmming port map (attempt:{})".format(port_map_attempt))

            if not self._sset_mcu_platform_port_map_config():
                continue

            (status, status_dict) = self._gget_mcu_global_status()
            if not status:
                self.log_error("PoE get global status failed!")
                return False

            break

        if port_map_attempt == MAX_PORT_MAP_ATTEMPT:
            self.log_error("All {} attempts to program platfrom port map failed!".format(port_map_attempt))
            return False

        # Check for ready state stage2
        if status_dict[MCUState.GLOBAL_CONTROLLER_STATUS] != "Ready":
            self.log_error("PoE Controller is not ready at stage2 boot")
            return False

        # Program MCU default configs
        if not self._sset_global_port_event_mask_config():
            self.log_error("Global port event mask enable failed!")
            return False

        if self.global_system_is_reset == "True" and\
            not self._sset_mcu_global_power_mgmt_mode_config("dynamic-with-priority"):
            self.log_error("Set default power management mode failed!")
            return False

        return True

    def deinit(self):
        self.mcu_drv.deinit()

    def upgrade_firmware(self, image_path):
        return self.__mcu_upgrade_firmware(self.poe_platform_config["firmware-path"], True)

    def is_controller_ready(self):
        state = MCUState.GLOBAL_CONTROLLER_STATUS

        (status, tmp_dict) = self._gget_mcu_global_status()
        if not status:
            return False

        return True if tmp_dict[state] == "Ready" else False

    def is_controller_reset(self):
        return True if self.global_system_is_reset == "True" else False

    def set_system_total_power(self, power):
        status = False

        if len(power) == pow(2, self.poe_platform_config["num-psus"]):
            status = self._sset_mcu_global_total_power_config(power)

        return status

    def set_port_reset(self, port):
        status = False
        mcu_cmd = MCUCommand.PORT_RESET

        mcu_port = int(port[len("Ethernet"):])
        if mcu_port < self.poe_platform_config["num-poe-ports"]:
            mcu_api = self.mcu_command_to_set_api.get(mcu_cmd, None)
            if mcu_api:
                status = mcu_api(port)

        return status

    def set_system_config(self, config, value):
        status = False
        if not config.is_global():
            return False

        mcu_cmd = self.db_config_to_mcu_config_cmd.get(config, None)
        if mcu_cmd != None:
            mcu_api = self.mcu_command_to_set_api.get(mcu_cmd, None)
            if mcu_api != None:
                status = mcu_api(value)
        return status

    def set_port_config(self, config, port, value):
        status = False
        if not config.is_port():
            return False

        try:
            mcu_port = int(port[len("Ethernet"):])
            if mcu_port < self.poe_platform_config["num-poe-ports"]:
                mcu_cmd = self.db_config_to_mcu_config_cmd.get(config, None)
                if mcu_cmd != None:
                    mcu_api = self.mcu_command_to_set_api.get(mcu_cmd, None)
                    if mcu_api != None:
                        status = mcu_api(mcu_port, value)
        except ValueError:
            pass

        return status

    def set_dll_power_limit(self, port, power):
        status = False


        try:
            mcu_port = int(port[len("Ethernet"):])
            if mcu_port < self.poe_platform_config["num-poe-ports"]:
                status = self._sset_high_power_mode(mcu_port)
                if status is False:
                    self.log_info("Failed to set high power mode for the port {}".format(port))
                    return status
                power = power * 5
                self.log_info("Moved to high power mode. Nowwe will set dynamic power limit {} for the port {}".format(power,port))
                status = self._sset_port_dynamic_power_limit(mcu_port, power)
                self.log_info("Status of setting dll power limit is {}".format(status))
                return status
        except Exception as e:
            self.log_info("Exception received {}".format(str(e)))
            pass

        return status

    def set_port_led(self, port, led_mode):
        status = False

        try:
            mcu_port = int(port[len("Ethernet"):])
            cpld_info = self.poe_platform_config["cpld-ctrl"]["port-led"]
            shift = int((mcu_port % (8 / cpld_info["num_bits"])) * 2)
            mask = ~(0x3 << shift)
            reg = cpld_info["reg_base"] + int(mcu_port / (8 / cpld_info["num_bits"]))

            status, value = self._gget_cpld_led_reg(reg)
            if status is False:
                self.log_info("Failed to get LED value for reg:{}".format(hex(reg)))
                return status

            led_value = self.port_led_state_dict[led_mode]
            value = (value & mask) | (led_value << shift)

            status = self._sset_cpld_led_reg(reg, value)
            if status is False:
                self.log_info("Failed to set LED value({}) for reg:{}".format(hex(value), hex(reg)))
                return status

        except Exception as e:
            self.log_info("Exception received {}".format(str(e)))
            pass

        return status

    def get_all_system_config(self):
        status = False
        config_dict = {}

        for config in PoeConfigDb:
            if not config.is_global() or not config.is_mcu():
                continue

            mcu_cmd = self.db_config_to_mcu_config_cmd.get(config, None)
            if mcu_cmd == None:
                return (False, None)

            mcu_api = self.mcu_config_to_get_api.get(mcu_cmd, None)
            if mcu_api == None:
                return (False, None)

            (status, value) = mcu_api()
            if not status:
                return (False, None)

            config_dict[config] = value

        return (status, config_dict)

    def get_all_port_config(self, port):
        status = False
        config_db_dict = {}
        config_dict = {}

        try:
            mcu_port = int(port[len("Ethernet"):])
            if mcu_port >= self.poe_platform_config["num-poe-ports"]:
                return (False, None)

            (status, tmp_dict) = self._gget_mcu_port_all_config(mcu_port)
            if not status:
                return (False, None)
            config_dict.update(tmp_dict)

            (status, tmp_dict) = self._gget_mcu_port_all_ext_config(mcu_port)
            if not status:
                return (False, None)
            config_dict.update(tmp_dict)
            for config in PoeConfigDb:
                if not config.is_port() or not config.is_mcu():
                    continue

                mcu_cmd = self.db_config_to_mcu_config_cmd.get(config, None)
                if mcu_cmd == None:
                    return (False, None)

                config_db_dict[config] = config_dict.get(mcu_cmd, "unknown")
            if "dynamic-power-limit" in config_dict:
                config_db_dict["dynamic-power-limit"] = config_dict["dynamic-power-limit"]
            if "user-power-threshold-limit" in config_dict:
                config_db_dict["user-power-threshold-limit"] = config_dict["user-power-threshold-limit"]
        except ValueError:
            return (False, None)

        return (status, config_db_dict)

    def get_all_system_state(self):
        status = False
        state_db_dict = {}
        status_dict = {}

        (status, tmp_dict) = self._gget_mcu_global_status()
        if not status:
            return (False, None)
        status_dict.update(tmp_dict)

        (status, tmp_dict) = self._gget_mcu_global_power_mgmt_status()
        if not status:
            return (False, None)
        status_dict.update(tmp_dict)

        (status, tmp_dict) = self._gget_mcu_global_power_alloc_status()
        if not status:
            return (False, None)
        status_dict.update(tmp_dict)

        (status, tmp_dict) = self._gget_mcu_global_reset_cause()
        if not status:
            return (False, None)
        status_dict.update(tmp_dict)

        for mcu_state in status_dict:
            db_state = self.mcu_state_to_db_state.get(mcu_state, None)
            if db_state != None:
                state_db_dict[db_state] = status_dict[mcu_state]

        return (status, state_db_dict)

    def get_all_pse_state(self):
        status = False
        pse_db_dict = {}
        pse_dict = {}
        (status, tmp_dict) = self._gget_mcu_pse_voltage_status()
        if not status:
            return (False, None)
        pse_dict.update(tmp_dict)
        (status, tmp_dict) = self._gget_mcu_pse_device_address()
        if not status:
            return (False, None)
        for key in pse_dict.keys():
            pse_dict[key].update(tmp_dict.get(key, {}))

            state_db_dict = {}
            for mcu_state, mcu_value in pse_dict[key].items():
                db_state = self.mcu_state_to_db_state.get(mcu_state, None)
                if db_state != None:
                    state_db_dict[db_state] = mcu_value

            pse_db_dict[key] = state_db_dict

        return (status, pse_db_dict)

    def get_port_measurements(self, port):
        status = False
        state_db_dict = {}

        try:
            mcu_port = int(port[len("Ethernet"):])

            (status, measurement_dict) = self._gget_mcu_port_measurements(mcu_port)
            if not status:
                return (False, None)

            for mcu_state in measurement_dict:
                db_state = self.mcu_state_to_db_state.get(mcu_state, None)
                if db_state != None:
                    state_db_dict[db_state] = measurement_dict[mcu_state]

        except ValueError:
            return (False, None)

        return (status, state_db_dict)

    def get_port_state(self, port):
        status = False
        state_db_dict = {}
        pair_map = self.poe_platform_config["poe-port-map"]

        try:
            mcu_port = int(port[len("Ethernet"):])
            port_status = {}
            port_pair_status = {}
            port_config_dict = {}

            (status, port_state) = self._gget_mcu_port_status(mcu_port)
            if not status:
                return (False, None)

            state_db_dict[PoeStateDb.PORT_DEVICE_ID] = str(pair_map[port]["dev-id"])
            state_db_dict[PoeStateDb.PORT_PRIMARY_CHANNEL] = str(pair_map[port]["ch0"])
            state_db_dict[PoeStateDb.PORT_SECONDARY_CHANNEL] = str(pair_map[port]["ch1"])

            # Calculate the max power threshold
            if port_state[MCUState.PORT_STATE] == "Delivering Power":
                type_mcu_cmd_str = str(MCUCommand.PORT_POWER_THRESHOLD_TYPE.value)
                val_mcu_cmd_str = str(MCUCommand.PORT_USER_POWER_THRESHOLD.value)
                # First check in the mcu_value_cache. If not present then check the config_Dictionary
                threshold_type = self.mcu_value_cache.get(type_mcu_cmd_str + str(port))
                if threshold_type is None:
                    # Now check the port threshold type from hardware
                    status,port_config_dict = self.get_all_port_config(port)
                    threshold_type = port_config_dict.get(PoeConfigDb.PORT_POWER_THRESHOLD_TYPE,'power-up-based')
                threshold_value = self.mcu_value_cache.get(val_mcu_cmd_str + str(port))
                if threshold_value is None:
                    threshold_value = float(port_config_dict.get(PoeConfigDb.PORT_USER_POWER_THRESHOLD,'0.0')) * 2
                else:
                    threshold_value = float(threshold_value) * 2
                if threshold_type == "power-up-based":
                    str_to_val = {\
                        "dot3af": "16.2",\
                        "high-inrush": "15.4",\
                        "pre-dot3at": "30",\
                        "dot3at": "31.2",\
                        "pre-dot3bt": "65",\
                        "dot3bt-type3": "65",\
                        "dot3bt-type4": "97"\
                    }                        
                    mcu_cmd_str = str(MCUCommand.PORT_POWER_UP_MODE.value)
                    power_up_mode = self.mcu_value_cache.get(mcu_cmd_str + str(port))
                    if power_up_mode is None:
                        power_up_mode = port_config_dict.get(PoeConfigDb.PORT_POWER_UP_MODE,'dot3at')
                    max_power_threshold = str_to_val.get(power_up_mode, "15.4")
                elif threshold_type == "class-based":
                    str_to_val = {\
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
                    port_class = port_state[MCUState.PORT_CLASS]
                    port_pri_class = port_state.get(MCUState.PORT_PRIMARY_CLASS, None)
                    port_sec_class = port_state.get(MCUState.PORT_SECONDARY_CLASS, None)
                    if port_pri_class != None and port_sec_class != None:
                        max_power_threshold = str(str_to_val.get(port_pri_class, 15.4) +\
                                                  str_to_val.get(port_sec_class, 15.4)) 
                    else:
                        max_power_threshold = str(str_to_val.get(port_class, 15.4))
                else:
                    if len(port_config_dict) == 0:
                        status,port_config_dict = self.get_all_port_config(port)
                    if 'user-power-threshold-limit' in port_config_dict:
                        max_power_threshold = port_config_dict["user-power-threshold-limit"]
                    else:
                        max_power_threshold = str(threshold_value)
            else:
                max_power_threshold = "0"
            if "dynamic-power-limit" in port_config_dict:
                state_db_dict[PoeStateDb.PORT_DYNAMIC_POWER_LIMIT] = port_config_dict["dynamic-power-limit"]
                self.log_info("Port {} Dynamic power limit is {}".format(port,port_config_dict["dynamic-power-limit"]))
            state_db_dict[PoeStateDb.PORT_MAX_POWER_THRESHOLD] = max_power_threshold

            # Construct abbreviated channel status
            str_to_val = {\
                "Primary" : "P2CH-",\
                "Secondary": "S2CH-",\
                "Both": "PS4CH-"\
            }
            state_db_dict[PoeStateDb.PORT_POWERED_CHANNEL] = port_state[MCUState.PORT_POWERED_CHANNEL]
            channel_state = str_to_val.get(port_state[MCUState.PORT_POWERED_CHANNEL], "")
            if channel_state == "":
                state_db_dict[PoeStateDb.PORT_CHANNEL_STATUS] = "NA"
            else:
                power_up_mode = port_state[MCUState.PORT_POWER_UP_MODE]
                state_db_dict[PoeStateDb.PORT_CHANNEL_STATUS] = channel_state +\
                                                              power_up_mode.split(' ')[1]

            primary_power_up_mode = port_state.get(MCUState.PORT_PRIMARY_POWER_UP_MODE, None)
            secondary_power_up_mode = port_state.get(MCUState.PORT_SECONDARY_POWER_UP_MODE, None)
            if primary_power_up_mode != None and\
                secondary_power_up_mode != None:
                state_db_dict[PoeStateDb.PORT_PRIMARY_CHANNEL_STATUS] = "P2CH-" + primary_power_up_mode
                state_db_dict[PoeStateDb.PORT_SECONDARY_CHANNEL_STATUS] = "S2CH-" + secondary_power_up_mode

            # Construct PD signature
            str_to_val = {\
                "Shared": "Single",\
                "Separate": "Dual",\
                "Unknown": "Unknown",\
            }
            pd_signature = str_to_val.get(port_state[MCUState.PORT_CONNECTION_TYPE], "NA")
            state_db_dict[PoeStateDb.PORT_PD_SIGNATURE] = pd_signature

            for mcu_state in port_state:
                db_state = self.mcu_state_to_db_state.get(mcu_state, None)
                if db_state != None:
                    state_db_dict[db_state] = port_state[mcu_state]

        except ValueError:
            return (False, None)
        return (status, state_db_dict)

    def get_all_port_state_change(self):
        status = False
        state_db_dict = {}
        pair_map = self.poe_platform_config["poe-port-map"]

        (status, event_dict) = self._gget_mcu_all_port_events()
        if not status:
            return (False, None)

        for port in event_dict[MCUState.GLOBAL_EVENT_PORTS]:
            port_str = "Ethernet" + port
            (status, port_state_dict) = self.get_port_state(port_str)
            if not status:
                return (False, None)

            state_db_dict[port_str] = port_state_dict

        return (True, state_db_dict)

    def get_port_led(self, port):
        status = False
        led_mode = None

        try:
            mcu_port = int(port[len("Ethernet"):])
            cpld_info = self.poe_platform_config["cpld-ctrl"]["port-led"]
            shift = int((mcu_port % (8 / cpld_info["num_bits"])) * 2)
            mask = 0x3 << shift
            reg = cpld_info["reg_base"] + int(mcu_port / (8 / cpld_info["num_bits"]))

            status, value = self._gget_cpld_led_reg(reg)
            if status is False:
                self.log_info("Failed to get LED value for reg:{}".format(hex(reg)))
                return (status, led_mode)

            led_value = (value & mask) >> shift
            for key, value in self.port_led_state_dict.items():
                if value == led_value:
                    led_mode = key
                    status = True

        except Exception as e:
            self.log_info("Exception received {}".format(str(e)))
            pass

        return (status, led_mode)

    def __mcu_upgrade_firmware(self, image_path, clear_image):
        mcu_cmd = MCUCommand.GLOBAL_MISC_CMD

        if clear_image:
            bsc_cmd = get_bsc_cmd([mcu_cmd.value, MiscSubCommand.CLEAR_IMAGE])
            (status, rsp) = self.mcu_drv.bsc_transaction(bsc_cmd)
            if rsp[0] != MCU_BOOT_ROM:
                if not status or\
                    (status and\
                     (rsp[0] != bsc_cmd[0] or\
                      rsp[1] != bsc_cmd[1] or\
                      rsp[2] != RSP_ACK)):
                    return False

                # Wait until MCU clears image
                time.sleep(2)

        # Program the image
        try:
            offset = 0
            with open(image_path, 'rb') as fd:
                data = fd.read(32)
                while len(data) > 0:
                    bsc_cmd = bytearray([mcu_cmd.value,\
                                        MiscSubCommand.DOWNLOAD_IMAGE,\
                                        (offset >> 8) & 0xFF, offset & 0xFF] + data)
                    if not self.mcu_drv.bsc_write(bsc_cmd):
                        return False

                    offset = offset + len(data)
                    data = fd.read(32)
                    time.sleep(0.01)
                         
        except (PermissionError, FileNotFoundError):
            return False

        # Force CRC check and boot image
        bsc_cmd = bytearray([mcu_cmd.value, MiscSubCommand.FORCE_CRC_AND_SWITCH])
        if not self.mcu_drv.bsc_write(bsc_cmd):
            return False

        time.sleep(3)
        self.mcu_drv.bsc_flush()

        return True

    def _sset_mcu_platform_port_map_clear_config(self):
        mcu_cmd = MCUCommand.PORT_LOGICAL_MAP

        # Start Pair Mapping
        bsc_cmd = get_bsc_cmd([mcu_cmd.value, get_bsc_seq_num(), 0x2])
        (status, rsp) = self.mcu_drv.bsc_transaction(bsc_cmd)
        if not status or\
            (status and\
             (rsp[0] != bsc_cmd[0] or\
              rsp[1] != bsc_cmd[1] or\
              rsp[2] != RSP_ACK)):
            return False

        time.sleep(0.3)

        # Clear the config
        mcu_clear_cmd = MCUCommand.GLOBAL_MISC_CMD
        bsc_cmd = get_bsc_cmd([mcu_clear_cmd.value, MiscSubCommand.CLEAR_CONFIG])
        (status, rsp) = self.mcu_drv.bsc_transaction(bsc_cmd)
        if not status or\
            (status and\
             (rsp[0] != bsc_cmd[0] or\
              rsp[1] != bsc_cmd[1] or\
              rsp[2] != RSP_ACK)):
            return False

        time.sleep(0.05)

        # Reset the system
        self._sset_mcu_global_pse_reset()

        time.sleep(2)
        return True

    def _sset_mcu_platform_port_map_config(self):
        mcu_cmd = MCUCommand.PORT_LOGICAL_MAP
        pair_map = self.poe_platform_config["poe-port-map"]
        max_ports = self.poe_platform_config["num-poe-ports"]

        # Start Pair Mapping
        bsc_cmd = get_bsc_cmd([mcu_cmd.value, get_bsc_seq_num(), 0x2, max_ports])
        (status, rsp) = self.mcu_drv.bsc_transaction(bsc_cmd)
        if not status or\
            (status and\
             (rsp[0] != bsc_cmd[0] or\
              rsp[1] != bsc_cmd[1] or\
              rsp[2] != RSP_ACK)):
            return False

        time.sleep(0.3)

        # Send individual port pair info
        for port, pair_info in pair_map.items():
            mcu_port = int(port[len("Ethernet"):])
            if mcu_port < max_ports:
                bsc_cmd = get_bsc_cmd([MCUCommand.PORT_PAIR_MAPPING.value, \
                                       get_bsc_seq_num(), mcu_port,\
                                       pair_info["4pair"], pair_info["dev-id"],\
                                       pair_info["ch0"], pair_info["ch1"],\
                                       0x01, 0x01, 0x01])
                (status, rsp) = self.mcu_drv.bsc_transaction(bsc_cmd)
                if not status or\
                    (status and\
                     (rsp[0] != bsc_cmd[0] or\
                      rsp[1] != bsc_cmd[1] or\
                      rsp[2] != RSP_ACK)):
                    return False
            time.sleep(0.02)

        # End Pair Mapping
        bsc_cmd = get_bsc_cmd([mcu_cmd.value, get_bsc_seq_num(), 0x3, max_ports])
        (status, rsp) = self.mcu_drv.bsc_transaction(bsc_cmd)
        if not status or\
            (status and\
             (rsp[0] != bsc_cmd[0] or\
              rsp[1] != bsc_cmd[1] or\
              rsp[2] != RSP_ACK)):
            return False

        time.sleep(2)
        return True

    def _sset_global_port_event_mask_config(self):
        status = False
        mcu_cmd = MCUCommand.GLOBAL_PORT_EVENT_MASK

        bsc_cmd = get_bsc_cmd([mcu_cmd.value, get_bsc_seq_num(), 0x1F])
        (status, rsp) = self.mcu_drv.bsc_transaction(bsc_cmd)
        if status and\
            (rsp[0] != bsc_cmd[0] or\
             rsp[1] != bsc_cmd[1] or\
             rsp[2] != RSP_ACK):
            status = False

        return status

    def _sset_cpld_global_pse_enable_config(self, enable_str):
        status = False

        if self.global_pse_enable_cmd == None:
            if "cpld-ctrl" in self.poe_platform_config and\
                "pse-enable" in self.poe_platform_config["cpld-ctrl"]:
                cpld_info = self.poe_platform_config["cpld-ctrl"]["pse-enable"]
                self.global_pse_enable_cmd = ['-f', '-y',\
                                              str(cpld_info["bus-id"]),\
                                              str(cpld_info["dev-addr"]),\
                                              str(cpld_info["offset"])]
            else:
                # Not supported
                return status

        cpld_info = self.poe_platform_config["cpld-ctrl"]["pse-enable"]
        i2cset = '/usr/sbin/i2cset'
        try:
            cmd = [i2cset] + self.global_pse_enable_cmd + [str(cpld_info["value"][enable_str.lower()])]
            subprocess.run(cmd, check=True)
            status = True
        except (KeyError, subprocess.CalledProcessError):
            pass

        return status

    def _sset_cpld_global_controller_mode_config(self, mode):
        status = False

        if self.global_controller_mode_cmd == None:
            if "cpld-ctrl" in self.poe_platform_config and\
                "controller-mode" in self.poe_platform_config["cpld-ctrl"]:
                cpld_info = self.poe_platform_config["cpld-ctrl"]["controller-mode"]
                self.global_controller_mode_cmd = ['-f', '-y',\
                                                   str(cpld_info["bus-id"]),\
                                                   str(cpld_info["dev-addr"]),\
                                                   str(cpld_info["offset"])]
            else:
                # Not supported
                return status

        cpld_info = self.poe_platform_config["cpld-ctrl"]["controller-mode"]
        i2cset = '/usr/sbin/i2cset'
        try:
            cmd = [i2cset] + self.global_controller_mode_cmd + [str(cpld_info["value"][mode.lower()])]
            subprocess.run(cmd, check=True)
            status = True
        except (KeyError, subprocess.CalledProcessError):
            pass

        return status

    def _sset_cpld_led_reg(self, reg, value):
        status = False

        try:

            if self.port_led_set_cmd == None:
                cpld_info = self.poe_platform_config["cpld-ctrl"]["port-led"]
                self.port_led_set_cmd = ['/usr/sbin/i2cset', '-f', '-y',\
                                         str(cpld_info["bus-id"]),\
                                         str(cpld_info["dev-addr"])]

                for key in self.port_led_state_dict.keys():
                    self.port_led_state_dict[key] = cpld_info[key.value]

            cmd = self.port_led_set_cmd + [str(reg), str(value)]
            subprocess.run(cmd, check=True)
            status = True
        except (KeyError, subprocess.CalledProcessError):
            pass

        return status

    @mcu_retry_transaction("SET")
    def _sset_mcu_global_pse_reset(self):
        status = False
        mcu_cmd = MCUCommand.GLOBAL_PSE_RESET

        bsc_cmd = get_bsc_cmd([mcu_cmd.value, get_bsc_seq_num(), 0x01])
        (status, rsp) = self.mcu_drv.bsc_transaction(bsc_cmd)
        if status and\
            (rsp[0] != bsc_cmd[0] or\
             rsp[1] != bsc_cmd[1] or\
             rsp[2] != RSP_ACK):
            status = False

        return status

    @mcu_retry_transaction("SET")
    def _sset_mcu_global_power_mgmt_mode_config(self, mode_str):
        status = False
        mcu_cmd = MCUCommand.GLOBAL_POWER_MANAGEMENT
        str_to_val = {\
            "static-with-priority": 1,\
            "dynamic-with-priority": 2,\
            "static-without-priority": 3,\
            "dynamic-without-priority": 4\
        }

        value = str_to_val.get(mode_str, None)
        if value == None:
            return False

        bsc_cmd = get_bsc_cmd([mcu_cmd.value, get_bsc_seq_num(), value])
        (status, rsp) = self.mcu_drv.bsc_transaction(bsc_cmd)
        if status and\
            (rsp[0] != bsc_cmd[0] or\
             rsp[1] != bsc_cmd[1] or\
             rsp[2] != RSP_ACK):
            status = False

        return status

    def __convert_mpss_to_psu_power_idx(self, mpss):
        psu_num = 0
        for psu in range(self.poe_platform_config["num-psus"]):
            psu_num = psu_num + ((1 if ((mpss >> self.poe_platform_config["psu-bitpos"]["psu" + str(psu+1)]) & 0x1) else 0) << psu)

        return psu_num

    @mcu_retry_transaction("SET")
    def _sset_mcu_global_total_power_config(self, power):
        status = False
        mcu_cmd = MCUCommand.GLOBAL_POWER_SOURCE
        read_cmd = MCUCommand.GLOBAL_POWER_MGMT_QUERY.value
        read_cmd_str = str(read_cmd)
        self.log_info("Setting the power budget as {}".format(power))
        for mpss in range(0,16):
            old_req = self.mcu_value_cache.get(read_cmd_str + hex(mpss), None)
            if not old_req:
                # Fetch first as it is a multi attribute commmand
                bsc_cmd = get_bsc_cmd([read_cmd, mpss])
                (status, rsp) = self.mcu_drv.bsc_transaction(bsc_cmd)
                if status and\
                    (rsp[0] != bsc_cmd[0] or\
                     rsp[1] != bsc_cmd[1]):
                    return False

                self.mcu_value_cache[read_cmd_str + hex(mpss)] = [rsp[3], rsp[4], rsp[5], rsp[6]]
                self.mcu_value_cache[read_cmd_str + hex(mpss+1)] = [rsp[7], rsp[8], rsp[9], rsp[10]]
                old_req = self.mcu_value_cache[read_cmd_str + hex(mpss)]

            power_value = (int(power[self.__convert_mpss_to_psu_power_idx(mpss)]) * 10) & 0xFFFF
            bsc_cmd = get_bsc_cmd([mcu_cmd.value, get_bsc_seq_num(), mpss,\
                                  (power_value >> 8) & 0xFF, power_value & 0xFF,\
                                  old_req[2], old_req[3]])
            (status, rsp) = self.mcu_drv.bsc_transaction(bsc_cmd)
            if status and\
                (rsp[0] != bsc_cmd[0] or\
                 rsp[1] != bsc_cmd[1] or\
                 rsp[2] != bsc_cmd[2] or\
                 rsp[3] != RSP_ACK):
                return False

            self.mcu_value_cache[read_cmd_str + hex(mpss)][0] = bsc_cmd[3]
            self.mcu_value_cache[read_cmd_str + hex(mpss)][1] = bsc_cmd[4]

        return status

    @mcu_retry_transaction("SET")
    def _sset_mcu_global_guard_band_config(self, power):
        status = False
        mcu_cmd = MCUCommand.GLOBAL_POWER_SOURCE
        band_value = int(float(power) * 10.0) & 0xFFFF
        read_cmd = MCUCommand.GLOBAL_POWER_MGMT_QUERY.value
        read_cmd_str = str(read_cmd)

        for mpss in range(0,16):
            old_req = self.mcu_value_cache.get(read_cmd_str + hex(mpss), None)
            if not old_req:
                # Fetch first as it is a multi attribute commmand
                bsc_cmd = get_bsc_cmd([read_cmd, mpss])
                (status, rsp) = self.mcu_drv.bsc_transaction(bsc_cmd)
                if status and\
                    (rsp[0] != bsc_cmd[0] or\
                     rsp[1] != bsc_cmd[1]):
                    return False

                self.mcu_value_cache[read_cmd_str + hex(mpss)] = [rsp[3], rsp[4], rsp[5], rsp[6]]
                self.mcu_value_cache[read_cmd_str + hex(mpss+1)] = [rsp[7], rsp[8], rsp[9], rsp[10]]
                old_req = self.mcu_value_cache[read_cmd_str + hex(mpss)]

            power_value = band_value if old_req[0] > 0 or old_req[1] > 0 else 0
            bsc_cmd = get_bsc_cmd([mcu_cmd.value, get_bsc_seq_num(), mpss,\
                                  old_req[0], old_req[1],\
                                  (power_value >> 8) & 0xFF, power_value & 0xFF])
            (status, rsp) = self.mcu_drv.bsc_transaction(bsc_cmd)
            if status and\
                (rsp[0] != bsc_cmd[0] or\
                 rsp[1] != bsc_cmd[1] or\
                 rsp[2] != bsc_cmd[2] or\
                 rsp[3] != RSP_ACK):
                return False

            self.mcu_value_cache[read_cmd_str + hex(mpss)][2] = bsc_cmd[5]
            self.mcu_value_cache[read_cmd_str + hex(mpss)][3] = bsc_cmd[6]

        return status

    @mcu_retry_transaction("SET")
    def _sset_high_power_mode(self, port):
        status = False
        mcu_cmd = MCUCommand.PORT_HIGH_POWER_MODE

        bsc_cmd = get_bsc_cmd([mcu_cmd.value, get_bsc_seq_num(), port, 0x02])
        (status, rsp) = self.mcu_drv.bsc_transaction(bsc_cmd)
        if status and\
            (rsp[0] != bsc_cmd[0] or\
             rsp[1] != bsc_cmd[1] or\
             rsp[2] != bsc_cmd[2] or\
             rsp[3] != RSP_ACK):
            status = False

        return status

    @mcu_retry_transaction("SET")
    def _sset_port_dynamic_power_limit(self, port, power):
        status = False
        mcu_cmd = MCUCommand.PORT_DYNAMIC_THRESHOLD
        bsc_cmd = get_bsc_cmd([mcu_cmd.value, get_bsc_seq_num(), port, int(power)])
        (status, rsp) = self.mcu_drv.bsc_transaction(bsc_cmd)
        if status and\
            (rsp[0] != bsc_cmd[0] or\
             rsp[1] != bsc_cmd[1] or\
             rsp[2] != bsc_cmd[2] or\
             rsp[3] != RSP_ACK):
            status = False

        return status

    @mcu_retry_transaction("SET")
    def _sset_mcu_port_pse_enable_config(self, port, enable_str):
        status = False
        mcu_cmd = MCUCommand.PORT_PSE_ENABLE
        enable = True if enable_str.lower() == "true" else False

        bsc_cmd = get_bsc_cmd([mcu_cmd.value, get_bsc_seq_num(), port, int(enable)])
        (status, rsp) = self.mcu_drv.bsc_transaction(bsc_cmd)
        if status and\
            (rsp[0] != bsc_cmd[0] or\
             rsp[1] != bsc_cmd[1] or\
             rsp[2] != bsc_cmd[2] or\
             rsp[3] != RSP_ACK):
            status = False

        return status

    def reset_port_counter(self, port):
        status = False
        mcu_cmd = MCUCommand.PORT_COUNTER_RESET
        port = int(port[len("Ethernet"):])
        clear_flag = 0x1
        bsc_cmd = get_bsc_cmd([mcu_cmd.value, get_bsc_seq_num(), port, clear_flag])
        (status, rsp) = self.mcu_drv.bsc_transaction(bsc_cmd)
        if status and\
            (rsp[0] != bsc_cmd[0] or\
             rsp[1] != bsc_cmd[1] or\
             rsp[2] != bsc_cmd[2] or\
             rsp[3] != RSP_ACK):
            status = False

        return status

    @mcu_retry_transaction("SET")
    def _sset_mcu_port_reset_config(self, port):
        status = False
        mcu_cmd = MCUCommand.PORT_RESET
        port = int(port[len("Ethernet"):])
        bsc_cmd = get_bsc_cmd([mcu_cmd.value, get_bsc_seq_num(), port, 0x01])
        (status, rsp) = self.mcu_drv.bsc_transaction(bsc_cmd)
        if status and\
            (rsp[0] != bsc_cmd[0] or\
             rsp[1] != bsc_cmd[1] or\
             rsp[2] != bsc_cmd[2] or\
             rsp[3] != RSP_ACK):
            status = False

        return status

    @mcu_retry_transaction("SET")
    def _sset_mcu_port_detection_type_config(self, port, detect_type):
        status = False
        mcu_cmd = MCUCommand.PORT_DETECTION_TYPE
        str_to_val = {\
            "legacy-only": 1,\
            "four-point-dot3af": 2,\
            "four-point-dot3af-legacy": 3,\
            "two-point-dot3af": 4,\
            "two-point-dot3af-legacy": 5\
        }

        value = str_to_val.get(detect_type, None)
        if value == None:
            return False

        bsc_cmd = get_bsc_cmd([mcu_cmd.value, get_bsc_seq_num(), port, value])
        (status, rsp) = self.mcu_drv.bsc_transaction(bsc_cmd)
        if status and\
            (rsp[0] != bsc_cmd[0] or\
             rsp[1] != bsc_cmd[1] or\
             rsp[2] != bsc_cmd[2] or\
             rsp[3] != RSP_ACK):
            status = False

        return status

    @mcu_retry_transaction("SET")
    def _sset_mcu_port_power_up_mode_config(self, port, power_up_mode):
        status = False
        mcu_cmd = MCUCommand.PORT_POWER_UP_MODE
        mcu_cmd_str = str(mcu_cmd.value)
        str_to_val = {\
            "dot3af": 0,\
            "high-inrush": 1,\
            "pre-dot3at": 2,\
            "dot3at": 3,\
            "pre-dot3bt": 4,\
            "dot3bt-type3": 5,\
            "dot3bt-type4": 6\
        }

        value = str_to_val.get(power_up_mode, None)
        if value == None:
            return False

        bsc_cmd = get_bsc_cmd([mcu_cmd.value, get_bsc_seq_num(), port, value])
        (status, rsp) = self.mcu_drv.bsc_transaction(bsc_cmd)
        if status and\
            (rsp[0] != bsc_cmd[0] or\
             rsp[1] != bsc_cmd[1] or\
             rsp[2] != bsc_cmd[2] or\
             rsp[3] != RSP_ACK):
            status = False

        self.mcu_value_cache[str(mcu_cmd.value) + str(port)] = [power_up_mode]

        return status

    @mcu_retry_transaction("SET")
    def _sset_mcu_port_power_pair_config(self, port, power_pair):
        status = False
        mcu_cmd = MCUCommand.PORT_POWER_PAIR
        str_to_val = {\
            "primary": 0,\
            "secondary": 1\
        }

        value = str_to_val.get(power_pair, None)
        if value == None:
            return False

        bsc_cmd = get_bsc_cmd([mcu_cmd.value, get_bsc_seq_num(), port, value])
        (status, rsp) = self.mcu_drv.bsc_transaction(bsc_cmd)
        if status and\
            (rsp[0] != bsc_cmd[0] or\
             rsp[1] != bsc_cmd[1] or\
             rsp[2] != bsc_cmd[2] or\
             rsp[3] != RSP_ACK):
            status = False

        return status

    @mcu_retry_transaction("SET")
    def _sset_mcu_port_priority_config(self, port, priority):
        status = False
        mcu_cmd = MCUCommand.PORT_PRIORITY
        str_to_val = {\
            "low": 0,\
            "medium": 1,\
            "high": 2,\
            "critical": 3\
        }

        value = str_to_val.get(priority, None)
        if value == None:
            return False

        bsc_cmd = get_bsc_cmd([mcu_cmd.value, get_bsc_seq_num(), port, value])
        (status, rsp) = self.mcu_drv.bsc_transaction(bsc_cmd)
        if status and\
            (rsp[0] != bsc_cmd[0] or\
             rsp[1] != bsc_cmd[1] or\
             rsp[2] != bsc_cmd[2] or\
             rsp[3] != RSP_ACK):
            status = False
        return status

    @mcu_retry_transaction("SET")
    def _sset_mcu_port_power_threshold_type_config(self, port, threshold_type):
        status = False
        mcu_cmd = MCUCommand.PORT_POWER_THRESHOLD_TYPE
        str_to_val = {\
            "power-up-based": 0,\
            "class-based": 1,\
            "user-defined": 2\
        }

        value = str_to_val.get(threshold_type, None)
        if value == None:
            return False

        bsc_cmd = get_bsc_cmd([mcu_cmd.value, get_bsc_seq_num(), port, value])
        (status, rsp) = self.mcu_drv.bsc_transaction(bsc_cmd)
        if status and\
            (rsp[0] != bsc_cmd[0] or\
             rsp[1] != bsc_cmd[1] or\
             rsp[2] != bsc_cmd[2] or\
             rsp[3] != RSP_ACK):
            status = False

        self.mcu_value_cache[str(mcu_cmd.value) + str(port)] = [threshold_type]
        return status

    @mcu_retry_transaction("SET")
    def _sset_mcu_port_user_power_threshold_config(self, port, threshold):
        status = False
        mcu_cmd = MCUCommand.PORT_USER_POWER_THRESHOLD
        value = int(float(threshold) * 5) & 0xFF

        bsc_cmd = get_bsc_cmd([mcu_cmd.value, get_bsc_seq_num(), port, value])
        (status, rsp) = self.mcu_drv.bsc_transaction(bsc_cmd)
        if status and\
            (rsp[0] != bsc_cmd[0] or\
             rsp[1] != bsc_cmd[1] or\
             rsp[2] != bsc_cmd[2] or\
             rsp[3] != RSP_ACK):
            status = False

        self.mcu_value_cache[str(mcu_cmd.value) + str(port)] = [threshold]

        return status

    def _gget_cpld_global_pse_enable_config(self):
        if self.global_pse_enable_cmd == None:
            if "cpld-ctrl" in self.poe_platform_config and\
                "pse-enable" in self.poe_platform_config["cpld-ctrl"]:
                cpld_info = self.poe_platform_config["cpld-ctrl"]["pse-enable"]
                self.global_pse_enable_cmd = ['-f', '-y',\
                                              str(cpld_info["bus-id"]),\
                                              str(cpld_info["dev-addr"]),\
                                              str(cpld_info["offset"])]
            else:
                # Not supported
                return (False, None)

        cpld_info = self.poe_platform_config["cpld-ctrl"]["pse-enable"]
        i2cget = '/usr/sbin/i2cget'
        cmd = [i2cget] + self.global_pse_enable_cmd
        try:
            p = subprocess.run(cmd, check=True, capture_output=True)
            data = int(p.stdout.strip().decode("utf-8"), 16)
            mask = cpld_info["mask"]
            for key, val in cpld_info["value"].items():
                if data & mask == val:
                   return (True, key)
        except subprocess.CalledProcessError:
            return (False, None)
        
        return (False, None)

    def _gget_cpld_global_controller_mode_config(self):
        if self.global_controller_mode_cmd == None:
            if "cpld-ctrl" in self.poe_platform_config and\
                "controller-mode" in self.poe_platform_config["cpld-ctrl"]:
                cpld_info = self.poe_platform_config["cpld-ctrl"]["controller-mode"]
                self.global_controller_mode_cmd = ['-f', '-y',\
                                                   str(cpld_info["bus-id"]),\
                                                   str(cpld_info["dev-addr"]),\
                                                   str(cpld_info["offset"])]
            else:
                # Not supported
                return (True, self.poe_platform_config["default-controller-mode"])

        cpld_info = self.poe_platform_config["cpld-ctrl"]["controller-mode"]
        i2cget = '/usr/sbin/i2cget'
        cmd = [i2cget] + self.global_controller_mode_cmd
        try:
            p = subprocess.run(cmd, check=True, capture_output=True)
            data = int(p.stdout.strip().decode("utf-8"), 16)
            mask = cpld_info["mask"]
            for key, val in cpld_info["value"].items():
                if data & mask == val:
                   return (True, key)
        except subprocess.CalledProcessError:
            return (False, None)

        return (False, None)

    def _gget_cpld_led_reg(self, reg):
        status = False
        data = None

        try:
            if self.port_led_set_cmd == None:
                cpld_info = self.poe_platform_config["cpld-ctrl"]["port-led"]
                self.port_led_get_cmd = ['/usr/sbin/i2cget', '-f', '-y',\
                                         str(cpld_info["bus-id"]),\
                                         str(cpld_info["dev-addr"])]

                for key in self.port_led_state_dict.keys():
                    self.port_led_state_dict[key] = cpld_info[key.value]

            cmd = self.port_led_get_cmd + [str(reg)]

            p = subprocess.run(cmd, check=True, capture_output=True)
            data = int(p.stdout.strip().decode("utf-8"), 16)
            status = True
        except (KeyError, subprocess.CalledProcessError):
            return (status, data)

        return (status, data)

    @mcu_retry_transaction("GET")
    def _gget_mcu_global_power_mgmt_mode_config(self):
        status = False
        mcu_cmd = MCUCommand.GLOBAL_POWER_MGMT_QUERY.value

        bsc_cmd = get_bsc_cmd([mcu_cmd, 0x0])
        (status, rsp) = self.mcu_drv.bsc_transaction(bsc_cmd)
        if not status or\
            (status and\
             (rsp[0] != bsc_cmd[0] or\
              rsp[1] != bsc_cmd[1])):
            return (False, None)

        val_to_str = {\
            1: "static-with-priority",\
            2: "dynamic-with-priority",\
            3: "static-without-priority",\
            4: "dynamic-without-priority"\
        }

        power_mgmt_mode_str = val_to_str.get(rsp[2], "unknown")

        return (status, power_mgmt_mode_str)

    @mcu_retry_transaction("GET")
    def _gget_mcu_global_guard_band_config(self):
        # Always make the daemon to program the guard band to MCU
        # Hence return zero
        return (True, "0")

    @mcu_retry_transaction("GET")
    def _gget_mcu_port_all_config(self, port):
        status = False
        mcu_cmd = MCUCommand.PORT_CONFIG_QUERY
        config_dict = {}

        bsc_cmd = get_bsc_cmd([mcu_cmd.value, get_bsc_seq_num(), port])
        (status, rsp) = self.mcu_drv.bsc_transaction(bsc_cmd)
        if not status or\
            (status and\
             (rsp[0] != bsc_cmd[0] or\
              rsp[1] != bsc_cmd[1] or\
              rsp[2] != bsc_cmd[2])):
            return (False, None)

        enable_to_str = {\
            0: "false",\
            1: "true",\
            2: "test-mode",\
            3: "reserved" }
        config_dict[MCUCommand.PORT_PSE_ENABLE] = enable_to_str.get(rsp[3],"unknown")

        detect_type_to_str = {\
            1: "legacy-only",\
            2: "four-point-dot3af",\
            3: "four-point-dot3af-legacy",\
            4: "two-point-dot3af",\
            5: "two-point-dot3af-legacy"\
        }
        config_dict[MCUCommand.PORT_DETECTION_TYPE] = detect_type_to_str.get(rsp[5],"unknown")

        power_pair_to_str = {\
            0: "primary",\
            1: "secondary"\
        }
        config_dict[MCUCommand.PORT_POWER_PAIR] = power_pair_to_str.get(rsp[8],"unknown")

        return (status, config_dict)

    @mcu_retry_transaction("GET")
    def _gget_mcu_port_all_ext_config(self, port):
        status = False
        four_pair_modes = ["dot3bt-type3","dot3bt-type4"]
        mcu_cmd = MCUCommand.PORT_EXT_CONFIG_QUERY
        config_dict = {}

        bsc_cmd = get_bsc_cmd([mcu_cmd.value, get_bsc_seq_num(), port])
        (status, rsp) = self.mcu_drv.bsc_transaction(bsc_cmd)
        if not status or\
            (status and\
             (rsp[0] != bsc_cmd[0] or\
              rsp[1] != bsc_cmd[1] or\
              rsp[2] != bsc_cmd[2])):
            return (False, None)

        power_up_mode_to_str = {\
            0: "dot3af",\
            1: "high-inrush",\
            2: "pre-dot3at",\
            3: "dot3at",\
            4: "pre-dot3bt",\
            5: "dot3bt-type3",\
            6: "dot3bt-type4"\
        }
        power_up_mode = power_up_mode_to_str.get(rsp[3],"unknown")
        config_dict[MCUCommand.PORT_POWER_UP_MODE] = power_up_mode

        thresh_type_to_str = {\
            0: "power-up-based",\
            1: "class-based",\
            2: "user-defined"\
        }
        config_dict[MCUCommand.PORT_POWER_THRESHOLD_TYPE] = thresh_type_to_str.get(rsp[4],"unknown")
        if power_up_mode in four_pair_modes:
            threshold = str((rsp[5] / 5.0) * 2.0)
        else:
            threshold = str(rsp[5] / 5.0)
        config_dict[MCUCommand.PORT_USER_POWER_THRESHOLD] = threshold

        priority_to_str = {\
            0: "low",\
            1: "medium",\
            2: "high",\
            3: "critical"\
        }
        config_dict[MCUCommand.PORT_PRIORITY] = priority_to_str.get(rsp[6],"unknown")
        
        dll_read = rsp[9]
        if str(dll_read) == 0:
            dynamic_power_limit = "0.0"
        else:
            if power_up_mode in four_pair_modes:
                dynamic_power_limit = str((dll_read / 5.0) * 2.0)
            else:
                dynamic_power_limit = str(dll_read / 5.0)
        if dynamic_power_limit != "0.0":
            config_dict["dynamic-power-limit"] = dynamic_power_limit
            self.log_info("Port {} dynamic power limit read from MCU is {}".format(port,dynamic_power_limit))
        config_dict["user-power-threshold-limit"] = threshold
        return (status, config_dict)

    def get_mcu_port_all_counters(self, port):
        status = False
        mcu_cmd = MCUCommand.PORT_COUNTER_QUERY
        # Reset flag is set to false
        reset_flag = 0x0
        counters_dict = {}
        port_id = int(port[len("Ethernet"):])
        bsc_cmd = get_bsc_cmd([mcu_cmd.value, get_bsc_seq_num(), port_id,reset_flag])
        (status, rsp) = self.mcu_drv.bsc_transaction(bsc_cmd)
        if not status or\
            (status and\
             (rsp[0] != bsc_cmd[0] or\
              rsp[1] != bsc_cmd[1] or\
              rsp[2] != bsc_cmd[2])):
            return (False, None)

        counters_dict["mpss-absent"] = str(int.from_bytes(rsp[3:4],"big"))
        counters_dict["overload"] = str(int.from_bytes(rsp[4:5],"big"))
        counters_dict["short"] = str(int.from_bytes(rsp[5:6],"big"))
        counters_dict["power-denied"] = str(int.from_bytes(rsp[6:7],"big"))
        counters_dict["invalid-signature"] = str(int.from_bytes(rsp[7:8],"big"))
        return (status, counters_dict)

    def _gget_mcu_port_pse_enable_config(self, port):
        mcu_cmd = MCUCommand.PORT_PSE_ENABLE

        (status, tmp_dict) = self._gget_mcu_port_all_config(port)
        value = tmp_dict.get(mcu_cmd, None)
        if not status or value == None:
            return (False, None)

        return (status, value)

    def _gget_mcu_port_detection_type_config(self, port):
        mcu_cmd = MCUCommand.PORT_DETECTION_TYPE

        (status, tmp_dict) = self._gget_mcu_port_all_config(port)
        value = tmp_dict.get(mcu_cmd, None)
        if not status or value == None:
            return (False, None)

        return (status, value)

    def _gget_mcu_port_power_up_mode_config(self, port):
        mcu_cmd = MCUCommand.PORT_POWER_UP_MODE

        (status, tmp_dict) = self._gget_mcu_port_all_ext_config(port)
        value = tmp_dict.get(mcu_cmd, None)
        if not status or value == None:
            return (False, None)

        return (status, value)

    def _gget_mcu_port_power_pair_config(self, port):
        mcu_cmd = MCUCommand.PORT_POWER_PAIR

        (status, tmp_dict) = self._gget_mcu_port_all_config(port)
        value = tmp_dict.get(mcu_cmd, None)
        if not status or value == None:
            return (False, None)

        return (status, value)

    def _gget_mcu_port_priority_config(self, port):
        mcu_cmd = MCUCommand.PORT_PRIORITY

        (status, tmp_dict) = self._gget_mcu_port_all_ext_config(port)
        value = tmp_dict.get(mcu_cmd, None)
        if not status or value == None:
            return (False, None)

        return (status, value)

    def _gget_mcu_port_power_threshold_type_config(self, port):
        mcu_cmd = MCUCommand.PORT_POWER_THRESHOLD_TYPE

        (status, tmp_dict) = self._gget_mcu_port_all_ext_config(port)
        value = tmp_dict.get(mcu_cmd, None)
        if not status or value == None:
            return (False, None)

        return (status, value)

    def _gget_mcu_port_user_power_threshold_config(self, port):
        mcu_cmd = MCUCommand.PORT_USER_POWER_THRESHOLD

        (status, tmp_dict) = self._gget_mcu_port_all_ext_config(port)
        value = tmp_dict.get(mcu_cmd, None)
        if not status or value == None:
            return (False, None)

        return (status, value)

    @mcu_retry_transaction("GET")
    def _gget_mcu_global_status(self):
        status = False
        mcu_cmd = MCUCommand.GLOBAL_STATUS
        status_dict = None

        mode_to_str = {\
            0: "semi-automatic",\
            1: "automatic"\
        }
        device_to_str = {\
            0xE011: "BCM59011",\
            0xE121: "BCM59121",\
            0xE131: "BCM59131",\
            0xE141: "BCM59141",\
            0xE1FF: "Generic"\
        }
        mcu_type_to_str = {\
            0: "ST Micro STM32F100 Mircontroller",\
            1: "Nuvoton M0516 Mircontroller",\
            2: "ST Micro STF030C8 Mircontroller",\
            3: "Nuvoton M058 Mircontroller",\
            4: "Nuvoton NUC122 Mircontroller",\
            5: "Nuvoton M0518 Mircontroller",\
            6: "Nuvoton NUC029ZPoE Mircontroller",\
            7: "Giga Device GD32F103 Mircontroller"\
        }

        bsc_cmd = get_bsc_cmd([mcu_cmd.value, get_bsc_seq_num()])
        (status, rsp) = self.mcu_drv.bsc_transaction(bsc_cmd)
        if status:
            status_dict = {}
            if rsp[0] == MCU_BOOT_ROM:
                status_dict[MCUState.GLOBAL_IN_BOOT_MODE] = "True"
            elif rsp[0] == bsc_cmd[0] and\
                rsp[1] == bsc_cmd[1]:
                status_dict[MCUState.GLOBAL_IN_BOOT_MODE] = "False"
                status_dict[MCUState.GLOBAL_CONTROLLER_MODE] = mode_to_str.get(((rsp[2] & 0x02) >> 1), "unknown")
                status_dict[MCUState.GLOBAL_MAX_PORTS] = str(rsp[3])
                status_dict[MCUState.GLOBAL_PORT_MAP] = "Enabled" if rsp[4] == 1 else "Disabled"
                status_dict[MCUState.GLOBAL_DEVICE_ID] = device_to_str.get((rsp[5] << 8) + rsp[6], "Unknown")
                status_dict[MCUState.GLOBAL_FW_VERSION] = str(rsp[7] >> 4) + "." + str(rsp[7] & 0x0F)
                status_dict[MCUState.GLOBAL_CONTROLLER_TYPE] = mcu_type_to_str.get(rsp[8], "Unknown")
                status_dict[MCUState.GLOBAL_CONFIG_DIRTY] = "Dirty" if (rsp[9] & 0x01) == 1 else "Saved"
                status_dict[MCUState.GLOBAL_IS_SYSTEM_RESET] = "True" if ((rsp[9] >> 1) & 0x01) == 1 else "False"
                status_dict[MCUState.GLOBAL_ENABLE] = "False" if ((rsp[9] >> 2) & 0x01) != 0 else "True"
                status_dict[MCUState.GLOBAL_SLAP_MAP] = "Present" if ((rsp[9] >> 3) & 0x01) == 1 else "Not Present"
                status_dict[MCUState.GLOBAL_CONTROLLER_STATUS] = "Ready" if ((rsp[9] >> 5) & 0x01) == 1 else "Not Ready"
                status_dict[MCUState.GLOBAL_EXT_FW_VERSION] = str(rsp[10] >> 4) + "." + str(rsp[10] & 0x0F)
                self.mcu_value_cache[str(mcu_cmd.value)] = [status_dict[MCUState.GLOBAL_DEVICE_ID]]
            else:
                status = False
        return (status, status_dict)

    @mcu_retry_transaction("GET")
    def _gget_mcu_global_power_mgmt_status(self):
        status = False
        mcu_cmd = MCUCommand.GLOBAL_POWER_MGMT_QUERY
        status_dict = {}

        bsc_cmd = get_bsc_cmd([mcu_cmd.value, 0x0])
        (status, rsp) = self.mcu_drv.bsc_transaction(bsc_cmd)
        if not status or\
            (status and\
             (rsp[0] != bsc_cmd[0] or\
              rsp[1] != bsc_cmd[1])):
            return (False, None)

        val_to_str = {\
            1: "static-with-priority",\
            2: "dynamic-with-priority",\
            3: "static-without-priority",\
            4: "dynamic-without-priority"\
        }
        status_dict[MCUState.GLOBAL_POWER_MANAGEMENT] = val_to_str.get(rsp[2], "unknown")

        # Value of MPSS 0 is taken as the guard band value
        guard_band = int.from_bytes(rsp[9:11],'big') / 10.0
        status_dict[MCUState.GLOBAL_GUARD_BAND] = str(guard_band)
        return (status, status_dict)

    @mcu_retry_transaction("GET")
    def _gget_mcu_global_power_alloc_status(self):
        status = False
        mcu_cmd = MCUCommand.GLOBAL_TOTAL_POWER_QUERY
        status_dict = {}

        bsc_cmd = get_bsc_cmd([mcu_cmd.value, get_bsc_seq_num()])
        (status, rsp) = self.mcu_drv.bsc_transaction(bsc_cmd)
        if not status or\
            (status and\
             (rsp[0] != bsc_cmd[0] or\
              rsp[1] != bsc_cmd[1])):
            return (False, None)

        total_power = int.from_bytes(rsp[4:6],'big') / 10.0
        status_dict[MCUState.GLOBAL_AVAILABLE_POWER] = str(total_power)

        allocated_power = int.from_bytes(rsp[2:4],'big') / 10.0
        status_dict[MCUState.GLOBAL_ALLOCATED_POWER] = str(allocated_power)

        mpss_state = rsp[6]
        status_dict[MCUState.GLOBAL_MPSS_STATE] = str(mpss_state)

        return (status, status_dict)

    @mcu_retry_transaction("GET")
    def _gget_mcu_global_reset_cause(self):
        status = False
        reset_cause = "Unknown"
        mcu_cmd = MCUCommand.GLOBAL_RESET_CAUSE
        status_dict = {}

        bsc_cmd = get_bsc_cmd([mcu_cmd.value, get_bsc_seq_num()])
        (status, rsp) = self.mcu_drv.bsc_transaction(bsc_cmd)
        if not status or\
            (status and\
             (rsp[0] != bsc_cmd[0] or\
              rsp[1] != bsc_cmd[1])):
            return (False, None)

        val_to_str = {\
            0: "Power ON Reset",\
            1: "NRST Pin",\
            2: "System Reset Command",\
            3: "Watchdog Reset",\
            4: "Brown-out Voltage (2.2V)",\
            5: "I2C Error",\
            6: "PSE Self-reset - I2C Addr:{}",\
            7: "VDD_UVLO_Warm"\
        }

        for i in range(0,8):
            if (rsp[2] >> i) & 0x01:
                if i == 6:
                    reset_cause = val_to_str[6].format(hex(rsp[3]))
                else:
                    reset_cause = val_to_str[i]

                break

        status_dict[MCUState.GLOBAL_RESET_CAUSE] = reset_cause

        return (status, status_dict)

    @mcu_retry_transaction("GET")
    def _gget_mcu_port_pair_power_auto_class(self, port):
        status = False
        mcu_cmd = MCUCommand.PORT_PAIR_POWER_AUTO_CLASS
        read_cmd_str = MCUCommand.PORT_STATUS_QUERY.value
        status_dict = {}

        bsc_cmd = get_bsc_cmd([mcu_cmd.value, get_bsc_seq_num(), port])
        (status, rsp) = self.mcu_drv.bsc_transaction(bsc_cmd)
        if not status or\
            (status and\
             (rsp[0] != bsc_cmd[0] or\
              rsp[1] != bsc_cmd[1] or\
              rsp[2] != bsc_cmd[2])):
            return (False, None)


        pair_status = self.mcu_value_cache.get(str(read_cmd_str) + hex(port), None)
        if pair_status != None and pair_status[0] == 3:
            primary_power_consumed = int.from_bytes(rsp[3:5],'big') / 10.0
            status_dict[MCUState.PORT_PRIMARY_POWER_CONSUMED] = str(round(primary_power_consumed,2))
            secondary_power_consumed = int.from_bytes(rsp[5:7],'big') / 10.0
            status_dict[MCUState.PORT_SECONDARY_POWER_CONSUMED] = str(round(secondary_power_consumed,2))

        str_to_val = {\
            0: "Not supported",\
            1: "Supported"\
        }
        status_dict[MCUState.PORT_AUTO_CLASS_STATE] = str_to_val.get(rsp[7], "Unknown")

        status_dict[MCUState.PORT_AUTO_CLASS_POWER] = "{:2.1f}".format(((rsp[8] << 8 + rsp[9]) * 0.1))

        return (status, status_dict)

    @mcu_retry_transaction("GET")
    def _gget_mcu_port_measurements(self, port):
        status = False
        mcu_cmd = MCUCommand.PORT_MEASUREMENT
        status_dict = {}

        bsc_cmd = get_bsc_cmd([mcu_cmd.value, get_bsc_seq_num(), port])
        (status, rsp) = self.mcu_drv.bsc_transaction(bsc_cmd)
        if not status or\
            (status and\
             (rsp[0] != bsc_cmd[0] or\
              rsp[1] != bsc_cmd[1] or\
              rsp[2] != bsc_cmd[2])):
            return (False, None)
        voltage = int.from_bytes(rsp[3:5],'big') * 0.06445
        status_dict[MCUState.PORT_VOLTAGE] = str(round(voltage))
        current = int.from_bytes(rsp[5:7],'big') * 0.001
        status_dict[MCUState.PORT_CURRENT] = "{}A".format(current)
        temp_value = 1.25 * int.from_bytes(rsp[7:9],'big')
        temp_value = 275 - temp_value
        status_dict[MCUState.PORT_TEMPERATURE] = "{}C".format(temp_value)
        power_consumed = int.from_bytes(rsp[9:11],'big') / 10.0
        status_dict[MCUState.PORT_POWER_CONSUMED] = str(round(power_consumed,2))

        (status, pair_dict) = self._gget_mcu_port_pair_power_auto_class(port)
        if not status:
            return (False, None)

        status_dict.update(pair_dict)

        return (status, status_dict)

    @mcu_retry_transaction("GET")
    def _gget_mcu_all_port_events(self):
        status = False
        mcu_cmd = MCUCommand.GLOBAL_PORT_EVENT_STATUS
        status_dict = {}

        bsc_cmd = get_bsc_cmd([mcu_cmd.value, get_bsc_seq_num(), 0x01])
        (status, rsp) = self.mcu_drv.bsc_transaction(bsc_cmd)
        if not status or\
            (status and\
             (rsp[0] != bsc_cmd[0] or\
              rsp[1] != bsc_cmd[1])):
            return (False, None)

        port_list = []
        for status in range(4,10):
            for bit_pos in range(0,8):
                if (rsp[status] >> bit_pos) & 0x01:
                    port_list.append(str(((status - 4) * 8) + bit_pos))

        status_dict[MCUState.GLOBAL_EVENT_PORTS] = port_list
        return (status, status_dict)

    @mcu_retry_transaction("GET")
    def _gget_mcu_port_pair_status(self, port):
        status = False
        mcu_cmd = MCUCommand.PORT_PAIR_STATUS_QUERY
        status_dict = {}

        bsc_cmd = get_bsc_cmd([mcu_cmd.value, get_bsc_seq_num(), port])
        (status, rsp) = self.mcu_drv.bsc_transaction(bsc_cmd)
        if not status or\
            (status and\
             (rsp[0] != bsc_cmd[0] or\
              rsp[1] != bsc_cmd[1] or\
              rsp[2] != bsc_cmd[2])):
            return (False, None)

        # Primary
        str_to_val = {\
            0: "Unknown",\
            1: "Short Circuit",\
            2: "High Cap",\
            3: "Rlow",\
            4: "Valid PD",\
            5: "Rhigh",\
            6: "Open Circuit",\
        }
        detect_val = str_to_val.get(rsp[3] & 0xF,"Unknown S")

        if detect_val == "Open Circuit":
            status_dict[MCUState.PORT_PRIMARY_CATEGORY] = "PD None"
            status_dict[MCUState.PORT_PRIMARY_CLASS] = "NA"
            status_dict[MCUState.PORT_PRIMARY_POWER_UP_MODE] = "NA"
            status_dict[MCUState.PORT_PRIMARY_POWER_APPLIED] = "false"
            status_dict[MCUState.PORT_PRIMARY_STATE] = detect_val
        else:
            str_to_val = {\
                0: "PD None",\
                1: "IEEE PD",\
                2: "Pre-std PD",\
                3: "Ext range PD"\
            }
            status_dict[MCUState.PORT_PRIMARY_CATEGORY] = str_to_val.get(rsp[3] >> 4, "Unknown")

            str_to_val = {\
                14: "Class Mismatch",\
                15: "Class Over Current"\
            }
            if rsp[4] <= 8:
                status_dict[MCUState.PORT_PRIMARY_CLASS] = "Class" + str(rsp[4])
            else:
                status_dict[MCUState.PORT_PRIMARY_CLASS] = str_to_val.get(rsp[4], "NA")

            str_to_val = {\
                0: "No Error",\
                1: "MPS Absent",\
                2: "Short",\
                3: "Overload",\
                4: "Power Denied",\
                5: "Thermal Shutdown",\
                6: "Startup Failure",\
                7: "UVLO",\
                8: "OVLO"\
            }
            error_val = str_to_val.get(rsp[5], "Unknown E")

            str_to_val = {\
                0: "15W",\
                1: "30W",\
                2: "45W",\
            }
            status_dict[MCUState.PORT_PRIMARY_POWER_UP_MODE] = str_to_val.get(rsp[6] & 0x3, "Unknown")

            status_dict[MCUState.PORT_PRIMARY_POWER_APPLIED] = "true" if (rsp[6] >> 4) & 0x01 else "false"

            if status_dict[MCUState.PORT_PRIMARY_POWER_APPLIED] == "true":
                status_dict[MCUState.PORT_PRIMARY_STATE] = "Delivering Power"
            elif status_dict[MCUState.PORT_PRIMARY_POWER_APPLIED] == "false" and\
                detect_val == "Valid PD":
                status_dict[MCUState.PORT_PRIMARY_STATE] = "Requesting Power"
            elif detect_val != "Unknown":
                status_dict[MCUState.PORT_PRIMARY_STATE] = detect_val
            elif error_val != "No Error":
                status_dict[MCUState.PORT_PRIMARY_STATE] = error_val
            else:
                status_dict[MCUState.PORT_PRIMARY_STATE] = "Unknown"

        # Secondary
        str_to_val = {\
            0: "Unknown",\
            1: "Short Circuit",\
            2: "High Cap",\
            3: "Rlow",\
            4: "Valid PD",\
            5: "Rhigh",\
            6: "Open Circuit",\
        }
        detect_val = str_to_val.get(rsp[7] & 0xF,"Unknown S")

        if detect_val == "Open Circuit":
            status_dict[MCUState.PORT_SECONDARY_CATEGORY] = "PD None"
            status_dict[MCUState.PORT_SECONDARY_CLASS] = "NA"
            status_dict[MCUState.PORT_SECONDARY_POWER_UP_MODE] = "NA"
            status_dict[MCUState.PORT_SECONDARY_POWER_APPLIED] = "false"
            status_dict[MCUState.PORT_SECONDARY_STATE] = detect_val
        else:
            str_to_val = {\
                0: "PD None",\
                1: "IEEE PD",\
                2: "Pre-std PD",\
                3: "Ext range PD"\
            }
            if detect_val != "Open Circuit":
                status_dict[MCUState.PORT_SECONDARY_CATEGORY] = str_to_val.get(rsp[7] >> 4, "Unknown")
            else:
                status_dict[MCUState.PORT_SECONDARY_CATEGORY] = "PD None"

            str_to_val = {\
                14: "Class Mismatch",\
                15: "Class Over Current"\
            }
            if rsp[8] <= 8:
                status_dict[MCUState.PORT_SECONDARY_CLASS] = "Class" + str(rsp[8])
            else:
                status_dict[MCUState.PORT_SECONDARY_CLASS] = str_to_val.get(rsp[8], "NA")

            str_to_val = {\
                0: "No Error",\
                1: "MPS Absent",\
                2: "Short",\
                3: "Overload",\
                4: "Power Denied",\
                5: "Thermal Shutdown",\
                6: "Startup Failure",\
                7: "UVLO",\
                8: "OVLO"\
            }
            error_val = str_to_val.get(rsp[9], "Unknown E")

            str_to_val = {\
                0: "15W",\
                1: "30W",\
                2: "45W",\
            }
            status_dict[MCUState.PORT_SECONDARY_POWER_UP_MODE] = str_to_val.get(rsp[10] & 0x3, "Unknown")

            status_dict[MCUState.PORT_SECONDARY_POWER_APPLIED] = "true" if (rsp[10] >> 4) & 0x01 else "false"

            if status_dict[MCUState.PORT_SECONDARY_POWER_APPLIED] == "true":
                status_dict[MCUState.PORT_SECONDARY_STATE] = "Delivering Power"
            elif status_dict[MCUState.PORT_SECONDARY_POWER_APPLIED] == "false" and\
                detect_val == "Valid PD":
                status_dict[MCUState.PORT_SECONDARY_STATE] = "Requesting Power"
            elif detect_val != "Unknown":
                status_dict[MCUState.PORT_SECONDARY_STATE] = detect_val
            elif error_val != "No Error":
                status_dict[MCUState.PORT_SECONDARY_STATE] = error_val
            else:
                status_dict[MCUState.PORT_SECONDARY_STATE] = "Unknown"

        return (status, status_dict)

    @mcu_retry_transaction("GET")
    def _gget_mcu_port_status(self, port):
        status = False
        mcu_cmd = MCUCommand.PORT_STATUS_QUERY
        status_dict = {}

        bsc_cmd = get_bsc_cmd([mcu_cmd.value, get_bsc_seq_num(), port])
        (status, rsp) = self.mcu_drv.bsc_transaction(bsc_cmd)
        if not status or\
            (status and\
             (rsp[0] != bsc_cmd[0] or\
              rsp[1] != bsc_cmd[1] or\
              rsp[2] != bsc_cmd[2])):
            return (False, None)

        str_to_val = {\
            0: "Disabled",\
            1: "Searching",\
            2: "Delivering Power",\
            3: "Test Mode",\
            4: "Fault",\
            5: "Other Fault",\
            6: "Requesting Power"\
        }
        status_dict[MCUState.PORT_STATE] = str_to_val.get(rsp[3],"Unknown")

        detect_to_val = {\
            0: "Unknown",\
            1: "Short Circuit",\
            2: "High Cap",\
            3: "Rlow",\
            5: "Rhigh",\
            6: "Open Circuit",\
            7: "FET Failure"\
        }
        error_to_val = {\
            0: "No Error",\
            1: "MPS Absent",\
            2: "Short",\
            3: "Overload",\
            4: "Power Denied",\
            5: "Thermal Shutdown",\
            6: "Startup Failure",\
            7: "UVLO",\
            8: "OVLO"\
        }
        if status_dict[MCUState.PORT_STATE] == "Searching":
            status_dict[MCUState.PORT_STATE] = detect_to_val.get(rsp[4],"Unknown S")
        elif status_dict[MCUState.PORT_STATE] == "Fault" or\
            status_dict[MCUState.PORT_STATE] == "Other Fault":
            status_dict[MCUState.PORT_STATE] = error_to_val.get(rsp[4], "Unknown E")

        if status_dict[MCUState.PORT_STATE] == "Open Circuit":
            status_dict[MCUState.PORT_CLASS] = "NA"
            status_dict[MCUState.PORT_CATEGORY] = "PD None"
            status_dict[MCUState.PORT_MPSS_MASK] = str(rsp[7])
            status_dict[MCUState.PORT_POWER_UP_MODE] = "NA"
            status_dict[MCUState.PORT_POWERED_CHANNEL] = "NA"
            status_dict[MCUState.PORT_CONNECTION_TYPE] = "NA"
        else:
            str_to_val = {\
                14: "Class Mismatch",\
                15: "Class Over Current"\
            }
            if rsp[5] <= 8:
                status_dict[MCUState.PORT_CLASS] = "Class" + str(rsp[5])
            else:
                status_dict[MCUState.PORT_CLASS] = str_to_val.get(rsp[5], "NA")

            str_to_val = {\
                0: "PD None",\
                1: "IEEE PD",\
                2: "Pre-std PD",\
                3: "Ext range PD"\
            }
            status_dict[MCUState.PORT_CATEGORY] = str_to_val.get(rsp[6], "Unknown")

            status_dict[MCUState.PORT_MPSS_MASK] = str(rsp[7])

            str_to_val = {\
                0: "2-pair 15W",\
                1: "2-pair 30W",\
                2: "4-pair 30W",\
                3: "4-pair 60W",\
                4: "4-pair 15W",\
                5: "4-pair 90W",\
                6: "2-pair 45W"\
            }
            status_dict[MCUState.PORT_POWER_UP_MODE] = str_to_val.get(rsp[8], "Unknown")

            str_to_val = {\
                0: "NA",\
                1: "Primary",\
                2: "Secondary",\
                3: "Both"\
            }
            status_dict[MCUState.PORT_POWERED_CHANNEL] = str_to_val.get(rsp[9], "Unknown")

            str_to_val = {\
                0: "NA",\
                1: "Shared",\
                2: "Separate",\
                3: "Unknown"\
            }
            status_dict[MCUState.PORT_CONNECTION_TYPE] = str_to_val.get(rsp[10], "Unknown")

            self.mcu_value_cache[str(mcu_cmd.value) + hex(port)] = [rsp[9], rsp[10]]

            if status_dict[MCUState.PORT_POWERED_CHANNEL] == "Both" and\
                status_dict[MCUState.PORT_CONNECTION_TYPE] == "Separate":
                (status, pair_status_dict) = self._gget_mcu_port_pair_status(port)
                if not status:
                    return (False, None)
                status_dict.update(pair_status_dict)

        return (status, status_dict)

    @mcu_retry_transaction("GET")
    def _gget_mcu_pse_voltage_status(self):
        status = False
        mcu_cmd = MCUCommand.GLOBAL_V48_VOLTAGE_STATUS
        status_dict = {}

        for device in range(0, self.poe_platform_config["num-pse-devices"]):
            tmp_dict = {}
            bsc_cmd = get_bsc_cmd([mcu_cmd.value, get_bsc_seq_num(), device])
            (status, rsp) = self.mcu_drv.bsc_transaction(bsc_cmd)
            if not status or\
                (status and\
                 (rsp[0] != bsc_cmd[0] or\
                  rsp[1] != bsc_cmd[1] or\
                  rsp[2] != RSP_ACK or\
                  rsp[3] != bsc_cmd[2])):
                return (False, None)
            voltage = int.from_bytes(rsp[4:6],'big') * 0.06445
            tmp_dict[MCUState.PSE_VOLTAGE] = str(round(voltage,1))
            tmp_dict[MCUState.PSE_OTP_VERSION] = str(rsp[7] >> 4) + "." + str(rsp[7] & 0x0F)

            status_dict[str(device)] = tmp_dict

        return (status, status_dict)

    @mcu_retry_transaction("GET")
    def _gget_mcu_pse_device_address(self):
        status = False
        mcu_cmd = MCUCommand.GLOBAL_PSE_DEVICE_ADDRESS
        read_cmd_str = MCUCommand.GLOBAL_STATUS.value
        status_dict = {}
        dev_blksz = 6

        for dev_offset in range(0, self.poe_platform_config["num-pse-devices"], dev_blksz):
            bsc_cmd = get_bsc_cmd([mcu_cmd.value, get_bsc_seq_num(), dev_offset])
            (status, rsp) = self.mcu_drv.bsc_transaction(bsc_cmd)
            if not status or\
                (status and\
                 (rsp[0] != bsc_cmd[0] or\
                  rsp[1] != bsc_cmd[1] or\
                  rsp[2] != bsc_cmd[2])):
                return (False, None)

            idx = 3
            for device in range(dev_offset, dev_offset + dev_blksz):
                tmp_dict = {}
                tmp_dict[MCUState.PSE_HW_ADDRESS] = hex(rsp[idx])
                tmp_dict[MCUState.PSE_TYPE] = self.mcu_value_cache.get(str(read_cmd_str), "Unknown")[0]
                status_dict[str(device)] = tmp_dict
                idx = idx + 1
        return (status, status_dict)
