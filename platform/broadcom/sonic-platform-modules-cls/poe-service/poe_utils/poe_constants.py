"""Module to provide common enumerations for accessing PoE config_db and state_db"""

from enum import Enum

class PoeDbBase(Enum):
    """Enumeration base class for PoE DB field type evaluation"""
    # g* - System specific param
    # p* - Port specific param
    # e* - PSE specific param
    # *m - Handled in MCU
    # *d - Handled in Daemon

    def is_global(self):
        if self.value[0] == 'g':
            return True

        return False

    def is_port(self):
        if self.value[0] == 'p':
            return True

        return False

    def is_pse(self):
        if self.value[0] == 'e':
            return True

        return False

    def is_mcu(self):
        if self.value[1] == 'm':
            return True

        return False

    def is_daemon(self):
        if self.value[1] == 'd':
            return True

        return False

    @property
    def field(self):
        return self.value[3:]


class PoeConfigDb(PoeDbBase):
    """Enumeration class for PoE Config DB fields"""
    # Global conifig fields
    GLOBAL_ENABLE = "gm-enable"
    GLOBAL_CONTROLLER_MODE = "gm-controller-mode"
    GLOBAL_POWER_MANAGEMENT = "gm-power-management"
    GLOBAL_GUARD_BAND = "gm-guard-band"
    # Port config fields
    PORT_ENABLE = "pm-enable"
    PORT_RESET_MODE = "pd-reset-mode"
    PORT_AUTO_RESET_TIMER = "pd-auto-reset-timer"
    PORT_DETECTION_TYPE = "pm-detection-type"
    PORT_POWER_UP_MODE = "pm-power-up-mode"
    PORT_POWER_PAIR = "pm-power-pair"
    PORT_PRIORITY = "pm-priority"
    PORT_POWER_THRESHOLD_TYPE = "pm-power-threshold-type"
    PORT_USER_POWER_THRESHOLD = "pm-user-power-threshold"
    PORT_LLDP_STATE = "pd-lldp-state"


class PoeStateDb(PoeDbBase):
    """Enumeration class for PoE Config DB fields"""
    # Global state fields
    GLOBAL_ENABLE = "gm-enable"
    GLOBAL_CONTROLLER_MODE = "gm-controller-mode"
    GLOBAL_POWER_MANAGEMENT = "gm-power-management"
    GLOBAL_GUARD_BAND = "gm-guard-band"
    GLOBAL_AVAILABLE_POWER = "gm-available-power"
    GLOBAL_ALLOCATED_POWER = "gm-allocated-power"
    GLOBAL_RESET_CAUSE = "gm-reset-cause"
    GLOBAL_CONTROLLER_TYPE = "gm-controller-type"
    GLOBAL_CONTROLLER_STATUS = "gm-controller-status"
    GLOBAL_FW_VERSION = "gm-fw-version"
    GLOBAL_EXT_FW_VERSION = "gm-ext-fw-version"
    # Port state fields
    PORT_DEVICE_ID = "pm-device-id"
    PORT_PRIMARY_CHANNEL = "pm-primary-channel"
    PORT_SECONDARY_CHANNEL = "pm-secondary-channel"
    PORT_LLDP_PD_STATE = "pd-port-lldp-pd-state"
    PORT_LLDP_PD_CLASS = "pd-port-lldp-pd-class"
    PORT_LLDP_PD_PRIMARY_CLASS = "pd-port-lldp-pd-primary-class"
    PORT_LLDP_PD_SECONDARY_CLASS = "pd-port-lldp-pd-secondary-class"
    PORT_LLDP_PD_REQUESTED_POWER = "pd-port-lldp-pd-requested-power"
    PORT_LLDP_PD_PRIMARY_REQUESTED_POWER = "pd-port-lldp-pd-primary-requested-power"
    PORT_LLDP_PD_SECONDARY_REQUESTED_POWER = "pd-port-lldp-pd-secondary-requested-power"
    PORT_LLDP_PSE_STATE = "pd-port-lldp-pse-state"
    PORT_LLDP_PSE_ALLOCATED_POWER = "pd-port-lldp-pse-allocated-power"
    PORT_LLDP_PSE_PRIMARY_ALLOCATED_POWER = "pd-port-lldp-pse-primary-allocated-power"
    PORT_LLDP_PSE_SECONDARY_ALLOCATED_POWER = "pd-port-lldp-pse-secondary-allocated-power"
    PORT_PRIORITY = "pd-priority"
    PORT_MAX_POWER_THRESHOLD = "pd-max-power-threshold"
    PORT_DETECTION_TYPE = "pd-detection-type"
    PORT_POWER_THRESHOLD_TYPE = "pd-power-threshold-type"
    PORT_POWER_UP_MODE = "pd-power-up-mode"
    PORT_PD_SIGNATURE = "pm-pd-signature"
    PORT_STATE = "pm-state"
    PORT_PRIMARY_STATE = "pm-primary-state"
    PORT_SECONDARY_STATE = "pm-secondary-state"
    PORT_CLASS = "pm-class"
    PORT_PRIMARY_CLASS = "pm-primary-class"
    PORT_SECONDARY_CLASS = "pm-secondary-class"
    PORT_CATEGORY = "pm-category"
    PORT_PRIMARY_CATEGORY = "pm-primary-category"
    PORT_SECONDARY_CATEGORY = "pm-secondary-category"
    PORT_POWERED_CHANNEL = "pm-powered-channel"
    PORT_CHANNEL_STATUS = "pm-channel-status"
    PORT_PRIMARY_CHANNEL_STATUS = "pm-primary-channel-status"
    PORT_SECONDARY_CHANNEL_STATUS = "pm-secondary-channel-status"
    PORT_POWER_CONSUMED = "pm-power-consumed"
    PORT_PRIMARY_POWER_CONSUMED = "pm-primary-power-consumed"
    PORT_SECONDARY_POWER_CONSUMED = "pm-secondary-power-consumed"
    PORT_VOLTAGE = "pm-voltage"
    PORT_CURRENT = "pm-current"
    PORT_TEMPERATURE = "pm-temperature"
    PORT_AUTO_CLASS_STATE = "pm-auto-class-state"
    PORT_AUTO_CLASS_POWER = "pm-auto-class-power"
    PORT_DYNAMIC_POWER_LIMIT = "pm-dynamic-power-limit"
    # PSE state fields
    PSE_TYPE = "em-type"
    PSE_VOLTAGE = "em-voltage"
    PSE_OTP_VERSION = "em-otp-version"
    PSE_HW_ADDRESS = "em-hw-address"
    # Port LLDP state fields
    LLDP_STANDARD = "standard"
    LLDP_POWER_TYPE = "power-type"
    LLDP_POWER_SOURCE = "pd-power-source"
    LLDP_POWER_PRIORITY = "pd-power-priority"
    LLDP_POWER_VALUE = "pd-power-value"
    LLDP_MDI_POWER_SUPPORTED = "pd-mdi-power-supported"
    LLDP_MDI_POWER_SUPPORT_STATE = "pd-mdi-power-support-state"
    LLDP_PAIR_CONTROL = "pd-pair-control"
    LLDP_POWER_PAIR = "pd-power-pair"
    LLDP_POWER_CLASS = "pd-power-class"
    LLDP_PD_REQUESTED_POWER = "pd-pd-requested-power"
    LLDP_PSE_ALLOCATED_POWER = "pd-pse-allocated-power"
    LLDP_PD_REQUESTED_POWER_PRIMARY = "pd-pd-requested-power-primary"
    LLDP_PD_REQUESTED_POWER_SECONDARY = "pd-pd-requested-power-secondary"
    LLDP_PSE_ALLOCATED_POWER_PRIMARY = "pd-pse-allocated-power-primary"
    LLDP_PSE_ALLOCATED_POWER_SECONDARY = "pd-pse-allocated-power-secondary"
    LLDP_POWER_TYPE_EXTENSION = "pd-power-type-extension"
    LLDP_PD_LOAD = "pd-pd-load"
    LLDP_POWER_CLASS_EXTENSION = "pd-power-class-extension"
    LLDP_POWER_CLASS_EXTENSION_PRIMARY = "pd-power-class-extension-primary"
    LLDP_POWER_CLASS_EXTENSION_SECONDARY = "pd-power-class-extension-secondary"
    LLDP_PD_POWERED_STATUS = "pd-pd-powered-status"
    LLDP_PSE_POWER_STATUS = "pd-pse-power-status"
    LLDP_PSE_MAX_POWER = "pd-pse-max-power"
    
class PoeApplDb(PoeDbBase):
    """Enumeration class for PoE Application DB fields"""
    # Port LLDP appl fields
    LLDP_PORT = "pd-port"
    LLDP_STANDARD = "pd-standard"
    LLDP_POWER_TYPE = "pd-power-type"
    LLDP_POWER_SOURCE = "pd-power-source"
    LLDP_POWER_PRIORITY = "pd-power-priority"
    LLDP_POWER_VALUE = "pd-power-value"
    LLDP_MDI_POWER_SUPPORTED = "pd-mdi-power-supported"
    LLDP_MDI_POWER_SUPPORT_STATE = "pd-mdi-power-support-state"
    LLDP_PAIR_CONTROL = "pd-pair-control"
    LLDP_POWER_PAIR = "pd-power-pair"
    LLDP_POWER_CLASS = "pd-power-class"
    LLDP_PD_REQUESTED_POWER = "pd-pd-requested-power"
    LLDP_PSE_ALLOCATED_POWER = "pd-pse-allocated-power"
    LLDP_PD_REQUESTED_POWER_PRIMARY = "pd-pd-requested-power-primary"
    LLDP_PD_REQUESTED_POWER_SECONDARY = "pd-pd-requested-power-secondary"
    LLDP_PSE_ALLOCATED_POWER_PRIMARY = "pd-pse-allocated-power-primary"
    LLDP_PSE_ALLOCATED_POWER_SECONDARY = "pd-pse-allocated-power-secondary"
    LLDP_POWER_TYPE_EXTENSION = "pd-power-type-extension"
    LLDP_POWER_CLASS_EXTENSION = "pd-power-class-extension"
    LLDP_POWER_CLASS_EXTENSION_PRIMARY = "pd-power-class-extension-primary"
    LLDP_POWER_CLASS_EXTENSION_SECONDARY = "pd-power-class-extension-secondary"
    LLDP_PSE_POWER_STATUS = "pd-pse-power-status"
    LLDP_PSE_MAX_POWER = "pd-pse-max-power"

class PoeLedState(Enum):
    PORT_LED_OFF = "led_off"
    PORT_LED_ON = "led_on"
    PORT_LED_ERROR = "led_err"
