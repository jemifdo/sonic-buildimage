#!/usr/bin/python

from sonic_py_common import logger
from sonic_platform import platform

log = logger.Logger()

def get_temperature_sensors(chassis):
    sensor_format = '{0:{1}}{2} degrees C'
    print("Temperature Sensors:")

    all_thermals = []

    # get chassis thermal info
    for temp in chassis.get_all_thermals():
        all_thermals.append(temp)

    # get psu thermal info
    for psu in chassis.get_all_psus():
        for temp in psu.get_all_thermals():
            all_thermals.append(temp)

    # Sort all thermal sensors
    all_thermals.sort(key=lambda temp: temp.get_name())

    # Find max length of sensor name
    width = max(len(temp.get_name()) for temp in all_thermals) + 4

    # Print sorted sensor data
    for temp in all_thermals:
        temp_name = temp.get_name()
        temp_val = round(get_sensor_value(temp.get_temperature, temp_name), 2)
        print(sensor_format.format(temp_name + ':', width, temp_val))

    print()

def get_psu_sensors(chassis):
    width = 26
    output = "PSU Sensors:\n"
    sensor_format = '{0:{1}}{2} {3}\n'

    for psu in chassis.get_all_psus():
        psu_name = psu.get_name()

        # get presence
        sensor_name = psu_name + ' Presence:'
        presence = get_sensor_value(psu.get_presence, sensor_name)
        presence_str = 'Present' if presence else 'Not Present'
        output += sensor_format.format(sensor_name, width, presence_str, '')

        # get status
        status_str = 'NOT OK'
        status = False
        sensor_name = psu_name + ' Status:'
        if presence:
            status = get_sensor_value(psu.get_status, sensor_name)
            status_str = 'OK' if status else 'NOT OK'
        output += sensor_format.format(sensor_name, width, status_str, '')

        # get psu fan speed
        fan_speed = 0
        sensor_name = psu_name + ' Fan Speed:'
        speed_func = psu.get_fan(0).get_speed_rpm
        if status: fan_speed = int(get_sensor_value(speed_func, sensor_name))
        output += sensor_format.format(sensor_name, width, fan_speed, 'RPM')

        # get input voltage
        input_voltage = 0
        sensor_name = psu_name + ' Input Voltage:'
        if status: input_voltage = round(get_sensor_value(psu.get_input_voltage, sensor_name), 2)
        output += sensor_format.format(sensor_name, width, input_voltage, 'Volts')

        # get input current
        input_current = 0
        sensor_name = psu_name + ' Input Current:'
        if status: input_current = round(get_sensor_value(psu.get_input_current, sensor_name), 2)
        output += sensor_format.format(sensor_name, width, input_current, 'Amps')

        # get input power
        input_power = 0
        sensor_name = psu_name + ' Input Power:'
        if status: input_power = round(float(input_voltage) * float(input_current), 2)
        output += sensor_format.format(sensor_name, width, input_power, 'Watts')

        # get output voltage
        output_voltage = 0
        sensor_name = psu_name + ' Output Voltage:'
        if status: output_voltage = round(get_sensor_value(psu.get_voltage, sensor_name), 2)
        output += sensor_format.format(sensor_name, width, output_voltage, 'Volts')

        # get output current
        output_current = 0
        sensor_name = psu_name + ' Output Current:'
        if status: output_current = round(get_sensor_value(psu.get_current, sensor_name), 2)
        output += sensor_format.format(sensor_name, width, output_current, 'Amps')

        # get output Power
        output_power = 0
        sensor_name = psu_name + ' Output Power:'
        if status: output_power = round(get_sensor_value(psu.get_power, sensor_name), 2)
        output += sensor_format.format(sensor_name, width, output_power, 'Watts')

    print(output)

def get_sensor_value(sensor_function, sensor_name):
    invalid_data = ["N/A", "", None]
    try:
        value = sensor_function()
        if value in invalid_data:
            value = 0
        return value
    except Exception as e:
        log.log_error(f"Error getting {sensor_name}: {e}")
        return 0

def get_fan_sensors(chassis):
    width = 24
    sensor_format = '{0:{1}}{2} {3}'
    print("Fan Sensors:")

    for fan in chassis.get_all_fans():
        # get fan presence
        fan_name = fan.get_name()
        sensor_name = fan_name + ' Presence'
        presence = get_sensor_value(fan.get_presence, sensor_name)
        presence_str = 'Present' if presence else 'Not Present'
        print(sensor_format.format(sensor_name+':', width, presence_str, ''))

        # get fan status
        status = 'NOT OK'
        sensor_name = fan_name + ' Status'
        if presence:
            status = 'OK' if get_sensor_value(fan.get_status, sensor_name) else 'NOT OK'
        print(sensor_format.format(sensor_name+':', width, status, ''))

        # get fan speed
        fan_speed = 0
        sensor_name = fan_name + ' Speed:'
        if presence: fan_speed = int(get_sensor_value(fan.get_speed_rpm, sensor_name))
        print(sensor_format.format(sensor_name, width, fan_speed, 'RPM'))

def main():
    try:
        chassis = platform.Platform().get_chassis()
        get_temperature_sensors(chassis)
        get_psu_sensors(chassis)
        get_fan_sensors(chassis)
    except Exception as err:
        log.log_error(f"Failed to process the sensor data: {err}")

if __name__ == '__main__':
    main()
