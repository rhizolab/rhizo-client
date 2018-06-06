import time
import logging
import gevent
from rhizo import util


# The Device class handles communcation with hardware devices connected via a serial port.
class Device(object):

    # initialize the device object given a device ID (a short string) and controller used to communicate with the device;
    # device IDs should be unique within one serial port connection, but need not be unique across serial ports
    def __init__(self, device_id, controller, port_name = None):
        self._device_id = device_id
        self._controller = controller
        self._port_name = port_name
        self._last_ack = ''
        self._enable_polling = False
        self._polling_interval = 0.2  # default polling interval in seconds
        self._last_poll_time = None  # last poll time (from time.time())

    # device creation method
    @classmethod
    def create(cls, device_id, controller, port_name = None):
        device = cls(device_id, controller, port_name)
        controller.serial.add_device(device)
        return device

    # get the device's serial port name
    def port_name(self):
        return self._port_name

    # get the device's ID
    def device_id(self):
        return self._device_id

    # set whether this device should be polled in the main polling loop
    def enable_polling(self, enabled):
        self._enable_polling = enabled

    # turn on/off checksum verification on the device
    def enable_checksum(self, enable):
        if enable:
            self.send_command('checksum 1')
        else:
            self.send_command('checksum 0')

    # process a serial message received from the device
    # fix(clean): remove message?
    def process_serial_message(self, command, args, message):
        used = True
        if (command == 'ack' or command == 'ack:'):
            self._last_ack = message[4:].strip()
        elif (command == 'log' or command == 'log:') and len(args) > 0:
            self._controller.update_sequence('log', self._device_id + ': ' + message[4:].strip())
        elif command == 'updateSequence' and len(args) > 1:
            sequence_name = args[0]
            value = ' '.join(args[1:])
            value = util.convert_value(value)
            self._controller.update_sequence(sequence_name, value)
        else:
            used = False
        return used

    # send a command to the device; waits for acknowledgement of the command
    def send_command(self, command, timeout=120):
        serial = self._controller.serial
        if serial.is_connected():
            port = serial.port(self._port_name) if self._port_name else serial.port()
            while port.busy:  # we don't want to interleave serial messages
                gevent.sleep(0.1)
            try:
                port.busy = True
                self._last_ack = ''
                ack_match = False
                count = 0
                send_q_r = False
                start_time = None
                while not ack_match:
                    port.check_sum_error = False  # reset this at the top of the command
                    send_time = time.time()
                    if not start_time:
                        start_time = send_time
                    if send_q_r:
                        message = '%s:%s' % (self._device_id, 'qr')
                        port.write_command(message)
                        logging.debug('requesting resend %s:%s' % (self._device_id, command))
                        logging.debug('sending %s:%s' % (self._device_id, 'qr'))
                    else:
                        message = '%s:%s' % (self._device_id, command)
                        if (command != 'q' or not self._controller.config.serial.get('quiet_polling', True)) and self._controller.config.serial.get('log_messages', True):
                            logging.debug('sending %s:%s' % (self._device_id, command))
                        port.write_command(message)
                        if count > 0:
                            logging.debug('resend %d: %s:%s' % (count, self._device_id, command))
                        count += 1

                    # if broadcast message then we won't get an ack, we can break here
                    if self._device_id == '*':
                        ack_match = True
                        break

                    # wait until ack or timeout
                    while time.time() - send_time < 2:
                        gevent.sleep(0.05)
                        if send_q_r:
                            if self._last_ack == 'qr':
                                ack_match = True
                                break
                        else:
                            if self._last_ack == command:
                                ack_match = True
                                break

                    # see if we need to request a resend of messages
                    if port.check_sum_error and ack_match and self._controller.config.serial.get('enable_polling_resends', False):
                        send_q_r = True
                        ack_match = False

                    # eventually give up
                    if not ack_match and time.time() - start_time > timeout:
                        raise Exception('timeout waiting for ack (%s:%s)' % (self._device_id, command))
            finally:
                port.busy = False
        else:
            logging.debug('[sim] %s: %s' % (self._device_id, command))
