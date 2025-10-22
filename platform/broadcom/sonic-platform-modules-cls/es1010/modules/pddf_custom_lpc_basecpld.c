/*
 * baseboard_cpld.c - driver for DS3000 Base Board CPLD
 * This driver implement sysfs for CPLD register access using LPC bus.
 * Copyright (C) 2019 Celestica Corp.
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 */

#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/stddef.h>
#include <linux/io.h>
#include <linux/init.h>
#include <linux/slab.h>
#include <linux/platform_device.h>
#include <linux/types.h>
#include <linux/string.h>

#define DRIVER_NAME "sys_cpld"
/**
 * CPLD register address for read and write.
 */
#define VERSION_ADDR 0xA100
#define COME_CPLD_VER_ADDR 0xA1E0
#define SYS_LED_ADDR 0xA143
#define CPLD_REGISTER_SIZE 0x77

struct baseboard_cpld_data {
    struct mutex       cpld_lock;
    uint16_t           read_addr;
};

struct baseboard_cpld_data *cpld_data;

/**
 * Read the value from scratch register as hex string.
 * @param  dev     kernel device
 * @param  devattr kernel device attribute
 * @param  buf     buffer for get value
 * @return         Hex string read from scratch register.
 */

/* COME CPLD version attributes */
static ssize_t come_cpld_version_show(struct device *dev, struct device_attribute *attr, char *buf)
{
    u8 val;
    // COME CPLD register is one byte
    val = sprintf(buf, "0x%2.2x\n",inb(COME_CPLD_VER_ADDR));
    return val;
}
static DEVICE_ATTR_RO(come_cpld_version);

/**
 * Show system led
 * @param  dev     kernel device
 * @param  devattr kernel device attribute
 * @param  buf     buffer for get value
 * @return         system led color (string).
 */
static ssize_t sys_led_show(struct device *dev, struct device_attribute *devattr,
                char *buf)
{
    char *led_color = "unknown";
    unsigned char data = 0;
    mutex_lock(&cpld_data->cpld_lock);
    data = (inb(SYS_LED_ADDR)) & 0x33;
    mutex_unlock(&cpld_data->cpld_lock);

    if (data == 0x33) {
        led_color = "off";
    } else if (data == 0x10) {
        led_color = "amber";
    } else if (data == 0x20) {
        led_color = "green";
    } else if (data == 0x01) {
        led_color = "alternate_blink_1hz";
    } else if (data == 0x02) {
        led_color = "alternate_blink_4hz";
    } else if (data == 0x11) {
        led_color = "amber_blink_1hz";
    } else if (data == 0x12) {
        led_color = "amber_blink_4hz";
    } else if (data == 0x21) {
        led_color = "green_blink_1hz";
    } else if (data == 0x22) {
        led_color = "green_blink_4hz";
    }

    return sprintf(buf, "%s\n", led_color);
}

/**
 * Set the system led
 * @param  dev     kernel device
 * @param  devattr kernel device attribute
 * @param  buf     buffer of set value
 * @param  count   number of bytes in buffer
 * @return         number of bytes written, or error code < 0.
 */
static ssize_t sys_led_store(struct device *dev, struct device_attribute *devattr,
                const char *buf, size_t count)
{
    unsigned char led_status,data;
    if (sysfs_streq(buf, "off")) {
        led_status = 0x33;
    } else if (sysfs_streq(buf, "amber")) {
        led_status = 0x10;
    } else if (sysfs_streq(buf, "green")) {
        led_status = 0x20;
    } else if (sysfs_streq(buf, "alternate_blink_1hz")) {
        led_status = 0x01;
    } else if (sysfs_streq(buf, "alternate_blink_4hz")) {
        led_status = 0x02;
    } else if (sysfs_streq(buf, "amber_blink_1hz")) {
        led_status = 0x11;
    } else if (sysfs_streq(buf, "amber_blink_4hz")) {
        led_status = 0x12;
    } else if (sysfs_streq(buf, "green_blink_1hz")) {
        led_status = 0x21;
    } else if (sysfs_streq(buf, "green_blink_4hz")) {
        led_status = 0x22;
    } else {
        count = -EINVAL;
        return count;
    }

    mutex_lock(&cpld_data->cpld_lock);
    data = (inb(SYS_LED_ADDR)) & 0x33;
    if (data != led_status) {
        outb(led_status, SYS_LED_ADDR);
    }

    mutex_unlock(&cpld_data->cpld_lock);
    return count;
}
static DEVICE_ATTR_RW(sys_led);

static struct attribute *baseboard_cpld_attrs[] = {
    &dev_attr_come_cpld_version.attr,
    &dev_attr_sys_led.attr,
    NULL,
};

static struct attribute_group baseboard_cpld_attrs_grp = {
    .attrs = baseboard_cpld_attrs,
};

static struct resource baseboard_cpld_resources[] = {
    {
        .start  = 0xA100,
        .end    = 0xA1FF,
        .flags  = IORESOURCE_IO,
    },
};

static void baseboard_cpld_dev_release( struct device * dev)
{
    return;
}

static struct platform_device baseboard_cpld_dev = {
    .name           = DRIVER_NAME,
    .id             = -1,
    .num_resources  = ARRAY_SIZE(baseboard_cpld_resources),
    .resource       = baseboard_cpld_resources,
    .dev = {
        .release = baseboard_cpld_dev_release,
    }
};

static int baseboard_cpld_drv_probe(struct platform_device *pdev)
{
    struct resource *res;
    int ret =0;

    cpld_data = devm_kzalloc(&pdev->dev, sizeof(struct baseboard_cpld_data),
        GFP_KERNEL);
    if (!cpld_data)
        return -ENOMEM;

    mutex_init(&cpld_data->cpld_lock);

    cpld_data->read_addr = VERSION_ADDR;

    res = platform_get_resource(pdev, IORESOURCE_IO, 0);
    if (unlikely(!res)) {
        printk(KERN_ERR "Specified Resource Not Available...\n");
        return -1;
    }

    ret = sysfs_create_group(&pdev->dev.kobj, &baseboard_cpld_attrs_grp);
    if (ret) {
        printk(KERN_ERR "Cannot create sysfs for baseboard CPLD\n");
    }
    return 0;
}

static int baseboard_cpld_drv_remove(struct platform_device *pdev)
{
    sysfs_remove_group(&pdev->dev.kobj, &baseboard_cpld_attrs_grp);
    return 0;
}

static struct platform_driver baseboard_cpld_drv = {
    .probe  = baseboard_cpld_drv_probe,
    .remove = __exit_p(baseboard_cpld_drv_remove),
    .driver = {
        .name   = DRIVER_NAME,
    },
};

int baseboard_cpld_init(void)
{
    // Register platform device and platform driver
    platform_device_register(&baseboard_cpld_dev);
    platform_driver_register(&baseboard_cpld_drv);
    return 0;
}

void baseboard_cpld_exit(void)
{
    // Unregister platform device and platform driver
    platform_driver_unregister(&baseboard_cpld_drv);
    platform_device_unregister(&baseboard_cpld_dev);
}

module_init(baseboard_cpld_init);
module_exit(baseboard_cpld_exit);

MODULE_AUTHOR("Pradchaya Phucharoen  <pphuchar@celestica.com>");
MODULE_DESCRIPTION("Celestica ES1000 Baseboard CPLD Driver");
MODULE_LICENSE("GPL");
