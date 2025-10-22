#!/usr/bin/env python3
import serial
import time
import multiprocessing


class PoeDrv:
    """Perform the trnasaction to BCM591x1 PoE controller.
       Refer to 591x1-PG101 document.
    """

    def __init__(self, device_id, intf, logger):
        """BCM591x1 constructor

        Args:
            device_id (str): The target device to open.
            intf (str): The BSC interface, now only supprt uart. Defaults to "uart".
            logger (sonic_py_common.logger.Logger): For syslog.
        """
        self.dev = "/dev/ttyS{}".format(device_id)
        self.intf = intf
        self.logger = logger
        self.ser_port = None

    def init(self):
        if self.intf != "uart":
            return False

        self.buadrate = 19200
        self.write_timeout = 0.05
        self.read_timeout = 0.05
        self.error_idle_gap = 0.5
        self.inter_byte_timeout = 0.002
        self.inter_packet_gap = 0.01
        self.max_write_size = 36
        self.bsc_packet_size = 12
        self.bsc_err_dict = {0xff: 'Not Ready to Response',
                             0xfe: 'Checksum Error in Request',
                             0xaf: 'PoE Controller is in BOOTROM, requesting Image.',
                             0xfd: 'Incomplete Request Frame.'}
        self.mutex = multiprocessing.Lock()
        try:
            self.ser_port = serial.Serial(self.dev, baudrate=self.buadrate,
                                          write_timeout=self.write_timeout,
                                          timeout=self.read_timeout,
                                          inter_byte_timeout=self.inter_byte_timeout)
        except serial.SerialException:
            return False

        return True

    def deinit(self):
        if self.ser_port != None:
            self.ser_port.close()

    def bsc_transaction(self, request):
        """Sending the request to the chip and process the reponse in 12 bytes
        BSC formatted.

        Takes 11 bytes of data_list and calculates checksum.
        Writes 12 bytes to UART and reads 12 bytes with timeout.
        Validates the checksum for the read 12 bytes.
        Handle error status from first read byte.

        Args:
            bytearray (bytes): The 11 bytes data to send to device.

        Returns:
            (bool, bytearray): the tuple of status and 12 bytes of data from device.
        """
        data_list = None
        status = False
        read = None

        if len(request) != (self.bsc_packet_size - 1):
            raise ValueError("request data must be 11 bytes.")

        try:
            self.mutex.acquire()
            request.append(sum(request) & 255)

            _ = self.ser_port.write(request)
            read = self.ser_port.read(self.bsc_packet_size)

            '''handle the error cases'''
            if len(read) < self.bsc_packet_size:
                self.logger.log_info("Packet not received in expected seconds")
                raise IOError('packet not receive in {} sec'.format(self.read_timeout))
            """
            if (sum([ord(str(b)) for b in read[:-1]]) & 255) != read[-1]:
                raise ValueError('Response packet with invalid checksum')
            """
            if read[0] in self.bsc_err_dict.keys():
                raise ValueError('device response k:v'.format(read(0), self.bsc_err_dict[read(0)]))

            data_list = bytearray(read)
            status = True
            time.sleep(self.inter_packet_gap)
        except Exception as e:
        #except (serial.SerialException, IOError, ValueError, IndexError):
            self.logger.log_info("Exception at low level driver {}".format(str(e)))
            status = False
            time.sleep(self.error_idle_gap)
        finally:
            self.mutex.release()
        return (status, data_list)

    def bsc_write(self, request, size=1):
        """Write data to the device.

        Takes size bytes of data writes size bytes to UART
        The maximum wtite size is 36 bytes.

        Args:
            bytes (bytes): The data to send to device.
            size (int): size of the data to send to device.

        Returns:
            bool: Write status
        """
        status = False
        written = None

        if size > self.max_write_size or size <= 0:
            raise ValueError("Invalid size {}".format(self.max_write_size))
        try:
            self.mutex.acquire()
            written = self.ser_port.write(request)
            if written == size:
                status = True
        except serial.SerialException:
            pass
        finally:
            self.mutex.release()
        return status

    def bsc_read(self, size=1):
        """Read specific bytes from device with timeout.

        Args:
            size (int): size to read from device.

        Returns:
            (bool, bytes): the tuple of status and 12 bytes of data from device.
        """
        status = False
        read = None
        try:
            self.mutex.acquire()
            read = self.ser_port.read(size)
            if len(read) == size:
                status = True
        except serial.SerialException:
            pass
        finally:
            self.mutex.release()
        return (status, read)

    def bsc_flush(self):
        """Clear all write and read buffer from the wire.
        """
        try:
            self.mutex.acquire()
            self.ser_port.flush()
            self.ser_port.read_all()
        except serial.SerialException:
            pass
        finally:
            self.mutex.release()
