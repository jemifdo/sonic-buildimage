/*
 * $Id: custom_led.c$
 * $Copyright: (c) 2020 Broadcom.
 * Broadcom Proprietary and Confidential. All rights reserved.$
 *
 * File:        custom_led.c
 * Purpose:     Customer CMICx LED bit pattern composer.
 * Requires:
 */

/******************************************************************************
 *
 * The CMICx LED interface has two RAM Banks as shown below, Bank0
 * (Accumulation RAM) for accumulation of status from ports and Bank1
 * (Pattern RAM) for writing LED pattern. Both Bank0 and Bank1 are of
 * 1024x16-bit, each row representing one port.
 *
 *           Accumulation RAM (Bank 0)        Pattern RAM (Bank1)
 *          15                       0     15                          0
 *         ----------------------------   ------------------------------
 * Row 0   |  led_uc_port 0 status    |   | led_uc_port 0 LED Pattern   |
 *         ----------------------------   ------------------------------
 * Row 1   |  led_uc_port 1 status    |   | led_uc_port 1 LED Pattern   |
 *         ----------------------------   ------------------------------
 *         |                          |   |                             |
 *         ----------------------------   ------------------------------
 *         |                          |   |                             |
 *         ----------------------------   ------------------------------
 *         |                          |   |                             |
 *         ----------------------------   ------------------------------
 *         |                          |   |                             |
 *         ----------------------------   ------------------------------
 *         |                          |   |                             |
 *         ----------------------------   ------------------------------
 * Row 127 |  led_uc_port 128 status  |   | led_uc_port 128 LED Pattern |
 *         ----------------------------   ------------------------------
 * Row 128 |                          |   |                             |
 *         ----------------------------   ------------------------------
 *         |                          |   |                             |
 *         ----------------------------   ------------------------------
 *         |                          |   |                             |
 *         ----------------------------   ------------------------------
 * Row x   |  led_uc_port (x+1) status|   | led_uc_port(x+1) LED Pattern|
 *         ----------------------------   ------------------------------
 *         |                          |   |                             |
 *         ----------------------------   ------------------------------
 *         |                          |   |                             |
 *         ----------------------------   ------------------------------
 * Row 1022|  led_uc_port 1022 status |   | led_uc_port 1022 LED Pattern|
 *         ----------------------------   ------------------------------
 * Row 1023|  led_uc_port 1023 status |   | led_uc_port 1023 LED Pattern|
 *         ----------------------------   ------------------------------
 *
 * Format of Accumulation RAM:
 *
 * Bits   15:9       8        7         6        5      4:3     2    1    0
 *    ------------------------------------------------------------------------
 *    | Reserved | Link  | Link-up |  Flow  | Duplex | Speed | Col | Tx | Rx |
 *    |          | Enable| Status  | Control|        |       |     |    |    |
 *    ------------------------------------------------------------------------
 *
 * Where Speed 00 - 10 Mbps
 *             01 - 100 Mbps
 *             10 - 1 Gbps
 *             11 - Above 1 Gbps
 *
 * The customer handler in this file should read the port status from
 * the HW Accumulation RAM or "led_control_data" array, then form the required
 * LED bit pattern in the Pattern RAM at the corrsponding location.
 *
 * The "led_control_data" is a 1024 bytes array, application user can use BCM LED API
 * to exchange port infomation with LED FW.
 *
 * Note that, for Firelight led_uc_port = physical port number - 2.
 * For ESW chip, led_uc_port = physical port number - 1.
 * For DNX/DNXF chip, led_uc_port = physical port number.
 *
 * There are five LED interfaces in CMICx-based devices, and although
 * a single interface can be used to output LED patterns for all
 * ports, it is possible to use more than one interface, e.g. the LEDs
 * for some ports are connected to LED interface-0, while the rest of
 * the ports are connected to LED interface-1. Accordingly, the custom
 * handler MUST fill in start-port, end-port and pattern-width in the
 * soc_led_custom_handler_ctrl_t structure passsed to the custom
 * handler.
 *
 * The example custom handler provided in this file has reference code
 * for forming two different LED patterns. Please refer to these
 * patterns before writing your own custom handler code.
 *
 * The led_customer_t structure definition is available in
 * include/shared/cmicfw/cmicx_led_public.h.
 *
 ******************************************************************************/

#include <shared/cmicfw/cmicx_led_public.h>

/*! The time window of activity LED diplaying on. */
#define ACT_TICKS 2

/*! Customer defined software flag. */
/*Format for led_control_data format definition
 * left LED indicate link status
 * right LED indicate active status
 * Bits                 3:1               0
 *    -------------------------------------------
 *    |         Lane Speed       | Link Status  |
 *    -------------------------------------------
 *             001: 10M            0: Link down
 *             010: 100M           1: Linkeup
 *             011: 1000M
 *             100: 2500M
 *             101: 10G
 *             110: 25G
 */

#define LED_SW_LINK_UP       0x1

#define ETH_2500M_PORT_MAX   16
#define ETH_PORT_MAX         48
#define SFP_PORT_MAX         4
#define FRONT_PORT_MAX       ETH_PORT_MAX+SFP_PORT_MAX

#define PATTERN_RIGHT_LED_YELLOW_OFF(pattern)   (pattern |= 1)
#define PATTERN_RIGHT_LED_GREEN_OFF(pattern)    (pattern |= (1 << 1))
#define PATTERN_LEFT_LED_YELLOW_OFF(pattern)    (pattern |= (1 << 2))
#define PATTERN_LEFT_LED_GREEN_OFF(pattern)     (pattern |= (1 << 3))

#define PATTERN_RIGHT_LED_YELLOW_ON(pattern)    (pattern &= ~(0x1))
#define PATTERN_RIGHT_LED_GREEN_ON(pattern)     (pattern &= ~(0x2))
#define PATTERN_LEFT_LED_YELLOW_ON(pattern)     (pattern &= ~(0x4))
#define PATTERN_LEFT_LED_GREEN_ON(pattern)      (pattern &= ~(0x8))


unsigned short phyPortMap[] = {
     26,  25,  28,  27,  30,  29,  32,  31,
     34,  33,  36,  35,  38,  37,  40,  39,
     42,  41,  44,  43,  50,  49,  52,  51,
     2,   1,   4,   3,   6,   5,   8,   7,
     10,  9,   12,  11,  14,  13,  16,  15,
     18,  17,  20,  19,  22,  21,  24,  23,
     60,  58,  59,  57
};

#define LED_CONTROL_DATA_LANE_SPEED_GET(led_control_data)  ((led_control_data >> 1) & 0x7)

/*!
 * \brief Function for LED bit pattern generator.
 *
 * Customer can compose the LED bit pattern to control serial LED
 * according to link/traffic information.
 *
 * \param [in,out] ctrl Data structure indicating the locations of the
 *                      port status and serial LED bit pattern RAM.
 * \param [in] cnt 30Hz counter.
 *
 */
void
custom_led_handler(soc_led_custom_handler_ctrl_t *ctrl, uint32 cnt)
{
    uint16 led_uc_port = 0, next_led_uc_port = 0, front_port = 0;
    uint16 tmp_port;
    uint16 accu_val = 0, next_accu_val = 0, pattern = 0;
    uint8 idx;
    uint8 led_control_data = 0, next_led_control_data = 0;
    /*
     * Assume that board configuration is as follows.
     *  - Front-panel ports are 48x1G+4x25G or 16x2.5G+24x1G+4x25G.
     *  - led_uc_port 0-51 are connected to LED interface 0.
     *  - Each port has two LEDs to display link status and activity.
     *  - LED1 pattern: b[1-0] - Link status: Grern - Up, Off - Down
     *    LED2 pattern: b[3-2] - Tx/Tx Activity: Green/Orange.
     */

    /* Process all fornt ports. */
    /* for ETH port, one port two led */
    for (front_port = 1; front_port <= ETH_PORT_MAX ; front_port++) {
        pattern = 0;
        led_uc_port = phyPortMap[front_port-1] - 1;

        led_control_data = ctrl->led_control_data[(led_uc_port)];

        //if (led_control_data & LED_SW_LINK_UP) {// link up
        if (led_control_data) {// link up
	        /* Read value from accumulation RAM */
            accu_val = LED_HW_RAM_READ16(ctrl->accu_ram_base, led_uc_port);
            // Set LED to GREEN
            PATTERN_LEFT_LED_YELLOW_OFF(pattern);
            PATTERN_LEFT_LED_GREEN_ON(pattern);

            // activity is always green
            if ((accu_val & LED_HW_RX) || (accu_val & LED_HW_TX)) {
                PATTERN_RIGHT_LED_YELLOW_OFF(pattern);
                PATTERN_RIGHT_LED_GREEN_ON(pattern);
                if (cnt & ACT_TICKS) {
                    PATTERN_RIGHT_LED_YELLOW_OFF(pattern);
                    PATTERN_RIGHT_LED_GREEN_OFF(pattern);
                }
            }
        } else {
            PATTERN_LEFT_LED_YELLOW_OFF(pattern);
            PATTERN_LEFT_LED_GREEN_OFF(pattern);
            PATTERN_RIGHT_LED_YELLOW_OFF(pattern);
            PATTERN_RIGHT_LED_GREEN_OFF(pattern);
        }

        /* Write value to pattern RAM */
        LED_HW_RAM_WRITE16(ctrl->pat_ram_base, front_port, pattern);
    }

    /* for SFP port, one port one led*/
    for (tmp_port = 0; tmp_port < SFP_PORT_MAX/2 ; tmp_port++) {
        pattern = 0;
        front_port = (ETH_PORT_MAX + 1) + tmp_port;
        led_uc_port = phyPortMap[(ETH_PORT_MAX + 1) + 2*tmp_port - 1] - 1;
        next_led_uc_port = phyPortMap[(ETH_PORT_MAX + 1) + 2*tmp_port] - 1;

        led_control_data = ctrl->led_control_data[(led_uc_port)];
        next_led_control_data = ctrl->led_control_data[(next_led_uc_port)];

        //if (led_control_data & LED_SW_LINK_UP) {// link up
        if (led_control_data) {// link up
	        /* Read value from accumulation RAM */
            accu_val = LED_HW_RAM_READ16(ctrl->accu_ram_base, led_uc_port);
            // Set LED to GREEN
            PATTERN_RIGHT_LED_YELLOW_ON(pattern);
            PATTERN_RIGHT_LED_GREEN_OFF(pattern);

            // for activity
            if (((accu_val & LED_HW_RX) || (accu_val & LED_HW_TX)) &&
                            (cnt & ACT_TICKS)) {
                PATTERN_RIGHT_LED_YELLOW_OFF(pattern);
                PATTERN_RIGHT_LED_GREEN_OFF(pattern);
            }
        } else {
            PATTERN_RIGHT_LED_YELLOW_OFF(pattern);
            PATTERN_RIGHT_LED_GREEN_OFF(pattern);
        }

        //if (next_led_control_data & LED_SW_LINK_UP) {// link up
        if (next_led_control_data) {// link up
	        /* Read value from accumulation RAM */
            accu_val = LED_HW_RAM_READ16(ctrl->accu_ram_base, next_led_uc_port);
            // Set LED to GREEN
            PATTERN_LEFT_LED_YELLOW_ON(pattern);
            PATTERN_LEFT_LED_GREEN_OFF(pattern);

            // for activity
            if (((accu_val & LED_HW_RX) || (accu_val & LED_HW_TX)) &&
                            (cnt & ACT_TICKS)) {
                PATTERN_LEFT_LED_YELLOW_OFF(pattern);
                PATTERN_LEFT_LED_GREEN_OFF(pattern);
            }
        } else {
            PATTERN_LEFT_LED_YELLOW_OFF(pattern);
            PATTERN_LEFT_LED_GREEN_OFF(pattern);
        }

        /* Write value to pattern RAM */
        LED_HW_RAM_WRITE16(ctrl->pat_ram_base, front_port, pattern);
    }

    /* Configure LED HW interfaces based on board configuration */
    for (idx = 0; idx < LED_HW_INTF_MAX_NUM; idx++) {
        soc_led_intf_ctrl_t *lic = &ctrl->intf_ctrl[idx];
        switch (idx) {
        case 0:
            lic->valid = 1;
            lic->start_row = 0;
            lic->end_row = 50; //50*4=200bit
            lic->pat_width = 4;
            break;
        default:
            /* Invalidate rest of the interfaces */
            lic->valid = 0;
            break;
        }
    }

    return;
}
