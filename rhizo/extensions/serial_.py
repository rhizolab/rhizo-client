import gevent
import logging
import collections
import serial as pyserial
from rhizo import util
from device import Device


# The Port object manages a connection a single serial port.
class Port(object):

    # store a serial connection
    def __init__(self, serial_connection):
        self._connection = serial_connection
        self.busy = False
        self.check_sum_error = False

    # read a message from the serial port
    def read_message(self):
        message = None
        try:
            message = self._connection.readline()
        except pyserial.serialutil.SerialException:
            # logging.info('serial exception')  # fix(soon): revisit this
            pass  # for now we'll ignore serial errors, since retrying is probably best approach
        return message.strip() if message else None

    # write a command to the serial port; adds a checksum
    def write_command(self, command):
        crc = util.crc16_ccitt(command)
        try:
            self._connection.write('%s|%d\n' % (command, crc))
        except pyserial.serialutil.SerialException:
            logging.info('serial exception')
            pass  # for now we'll ignore serial errors, since retrying is probably best approach


# The Serial extension manages connections to one or more serial ports.
class Serial(object):

    # initialize this extension object
    def __init__(self, controller):
        self._controller = controller
        self._devices = {}
        self._ports = collections.OrderedDict()
        self._serial_error_count = 0
        self._send_serial_to_server = False
        self._serial_handlers = []  # user-defined serial handlers
        self._fast_polling = None  # fix(soon): remove this

    # run by controller during startup
    def init(self):
        config = self._controller.config

        # check for old serial-related config entries
        assert not 'enableSerial' in config  # -> serial.enable
        assert not 'bbb' in config  # -> serial.bbb
        assert not 'serialPort' in config  # -> serial.port
        assert not 'devices' in config  # no longer supported (add devices from code)
        assert not 'serialSleepSeconds' in config  # -> serial.sleep_seconds
        assert not 'serialPolling' in config  # -> serial.polling
        assert not 'quietPolling' in config  # -> serial.quiet_polling
        assert not 'enablePollingResends' in config  # -> serial.enable_polling_resends

        # open serial port
        if config.get('serial') and config.serial.get('enable', True) and 'port' in config.serial:
            if config.serial.get('baud_rate'):
                self.open_port(config.serial.port, config.serial.baud_rate)
            else:
                self.open_port(config.serial.port)

            # sleep for a moment to make sure Arduino is done resetting before sending first commands (get checksum errors if send messages too soon)
            if self._ports:
                serial_sleep_seconds = config.serial.get('sleep_seconds', 3.0)
                if serial_sleep_seconds:
                    logging.debug('sleeping for %.2f seconds after opening serial port' % serial_sleep_seconds)
                    self._controller.sleep(serial_sleep_seconds)

    # ======== public API ========

    # add a serial device and enables checksums on it;
    # the device object is expected to an instance of a subclass of Device
    def add_device(self, device):

        # temp handle device without port
        if not device.port_name():
            if self._ports:
                device._port_name = self._ports.keys()[0]
            else:
                device._port_name = 'sim'
        if (device.port_name(), device.device_id()) in self._devices:
            logging.warning("device '%s' on port '%s' is already defined" % (device.device_id(), device.port_name()))
        else:
            self._devices[(device.port_name(), device.device_id())] = device

        # enable checksums
        device.enable_checksum(True)

    # temp helper function to get device by ID
    def device(self, device_id):
        if self._ports:
            port_name = self._ports.keys()[0]
        else:
            port_name = 'sim'
        return self._devices[(port_name, device_id)]

    # get a list of devices
    def devices(self):
        return self._devices.values()

    # returns true if connected to at least one serial port
    def is_connected(self):
        return True if self._ports else False

    # send a serial command to the devices via a serial port
    # fix(soon): only works with single serial port
    def send_command(self, device_id, command):
        if device_id == '*':
            message = '%s:%s' % (device_id, command)
            logging.debug('sending broadcast command %s' % command)
            for port in self._ports:
                self._ports[port].write_command(message)
        if self._ports:
            port_name = self._ports.keys()[0]  # note: only works with single serial port
        else:
            port_name = 'sim'
        device_key = (port_name, device_id)
        if device_key in self._devices:
            self._devices[device_key].send_command(command)
        elif device_id != '*':
            logging.warning('send_command to unrecognized device (%s)' % device_id)

    # sets a custom handler for serial messages (can be multiple)
    def add_handler(self, serial_handler):
        self._serial_handlers.append(serial_handler)

    # set special polling to only selected devices, to improve latency. deviceList must be a list
    # fix(soon): remove this
    def fast_polling(self, device_list):
        if device_list:
            assert type(device_list) is list, 'deviceList %r is not a list' % device_list
            if len(device_list) == 0:
                self._fast_polling = None
            else:
                self._fast_polling = device_list
        else:
            self._fast_polling = None

    # ======== our greenlets ========

    # runs as a greenlet that reads incoming data from serial connection(s) with device(s)
    # fix(soon): create a separate greenlet for each serial port
    def serial_listener(self):
        while True:
            received_message = False
            for port_name, port in self._ports.iteritems():
                message = port.read_message()
                if message:
                    gevent.spawn(self.process_serial_message, port_name, message)
                    received_message = True
            if not received_message:
                gevent.sleep(0.01)

    # runs as a greenlet that polls devices over the serial connection
    def poll_serial_devices(self):
        counter = 0
        while True:

            if self._fast_polling:
                if self._ports:
                    port_name = self._ports.keys()[0]  # fix(soon): only works with one serial port
                else:
                    port_name = 'sim'
                poll_devices = {id: self._devices[(port_name, id)] for id in self._fast_polling}
            else:
                poll_devices = {d.device_id(): d for d in self._devices.itervalues() if d._enable_polling}

            dev_count = len(poll_devices)

            # if no device to poll, sleep a bit (need to allow other greenlets to run)
            if dev_count == 0:
                gevent.sleep(0.1)

            config_poll_sleep = self._controller.config.get('serial', {}).get('poll_sleep')
            if config_poll_sleep:
                poll_sleep = config_poll_sleep
            elif self._fast_polling:
                poll_sleep = 0.1
            else:
                if dev_count == 1:
                    poll_sleep = 0.4
                elif dev_count == 2:
                    poll_sleep = 0.3
                else:
                    poll_sleep = 0.2

            for (id, device) in poll_devices.iteritems():
                if device._enable_polling:
                    self.send_command(id, 'q')
                    counter += 1
                    if counter == dev_count or counter == 3:
                        gevent.sleep(poll_sleep)  # poll up to three devices every one-half second
                        counter = 0

    # runs as a greenlet that periodically sends diagnostic information to the server
    # fix(soon): decide what to do with this
    def diagnostic_monitor(self):
        while True:
            gevent.sleep(60)
            if self._controller.config.get('enable_server', True) and self._controller.config.get('enable_diagnostic_sequences', False):
                self._controller.update_sequence('serial_errors', self._serial_error_count)
            self._serial_error_count = 0

    # ======== other methods ========

    # get a serial port object; if port_name is not specified, will return first port;
    # if port not found, will raise exception
    def port(self, port_name = None):
        if port_name:
            return self._ports[port_name]
        else:
            return self._ports.itervalues().next()  # first serial port

    # open a new serial port
    def open_port(self, port_name, baud_rate=9600):

        # handle beaglebone device initialization
        if self._controller.config.get('serial', {}).get('bbb', False):
            import Adafruit_BBIO.UART as UART
            port_number = int(port_name[-1])
            if port_number in range(0, 6):
                uart_name = 'UART%d' % port_number
                logging.info('setting up %s' % uart_name)
                UART.setup(uart_name)
            else:
                logging.warning('invalid BBB serial port')

        # open the serial port
        try:
            serial_connection = pyserial.Serial(port_name, baudrate = baud_rate, timeout = 0.05)
            self._ports[port_name] = Port(serial_connection)
            logging.info('connected to %s' % port_name)
            success = True
        except pyserial.serialutil.SerialException:
            logging.warning('unable to connect to %s' % port_name)
            success = False
        return success

    # close a serial port and remove all devices associated with the port
    def close_port(self, port_name):
        self._ports[port_name]._connection.close()
        del self._ports[port_name]
        self._devices = {dk: d for dk, d in self._devices.iteritems() if d._port_name != port_name}

    # reload settings after a change to the config file
    def reload_config(self):
        pass

    # the collections of greenlets used by this extension
    def greenlets(self):
        glets = [gevent.spawn(self.diagnostic_monitor)]
        glets.append(gevent.spawn(self.serial_listener))
        if self._controller.config.get('serial', {}).get('polling', False):
            glets.append(gevent.spawn(self.poll_serial_devices))
        return glets

    # process a message from the server
    def process_message(self, type, params):
        response_message = None
        message_used = True
        if type == 'serial_command' or type == 'serialCommand':
            command = str(params['command'])
            # fix(later): allow specify port name
            if self._ports:
                logging.info('sending command from server: %s' % command)
                self.port().write_command(command)
            else:
                logging.info('no serial connect for command from server: %s' % command)
        elif type == 'send_serial' or type == 'sendSerial':  # fix(soon): change to use set_config
            self._send_serial_to_server = bool(int(params['enable']))
        else:
            message_used = False
        return (message_used, response_message)

    # process an incoming message from the serial port (from device(s))
    def process_serial_message(self, port_name, message):

        # a helper function for making sure serial messages are safe for JSON
        def remove_bad_chars(message):
            return ''.join([c if ord(c) < 128 else 'X' for c in message])

        # check checksum
        if not '|' in message:
            logging.warning('missing checksum: [%s]' % remove_bad_chars(message))
            self._serial_error_count += 1
            self._ports[port_name].check_sum_error = True
            return
        pipe_pos = message.rfind('|')
        try:
            check_sum = int(message[(pipe_pos+1):])
        except:
            check_sum = 0
        message = message[:pipe_pos]
        calc_check_sum = util.crc16_ccitt(message)
        if calc_check_sum != check_sum:
            logging.warning('checksum mismatch: [%s], calc: %d, remote: %d' % (remove_bad_chars(message), calc_check_sum, check_sum))
            self._serial_error_count += 1
            self._ports[port_name].check_sum_error = True
            return

        # display the message
        if not message.endswith('ack q') or not self._controller.config.get('serial', {}).get('quiet_polling', True):
            logging.debug('    %s' % message)

        # if requested, send to server
        if self._send_serial_to_server and self._web_socket:
            self.send_message('serialMessage', {'message': message})

        # get device ID
        colon_pos = message.find(':')
        if colon_pos >= 0:
            device_id = message[:colon_pos].strip()
            message = message[(colon_pos+1):].strip()

        # if no device ID specified and there's only one device on this serial port, assume it's from that device
        # fix(soon): remove this case? could require that all messages have device IDs
        else:
            found_device_id = False
            for device in self._devices.itervalues():
                if device._port_name == port_name:
                    if found_device_id:
                        logging.warning('serial message (%s) without device ID on port with multiple devices' % message)
                        self._serial_error_count += 1
                        return
                    found_device_id = device.device_id()
            if found_device_id:
                device_id = found_device_id
            else:
                logging.warning('serial message (%s) without device ID' % message)
                self._serial_error_count += 1
                return

        # send to device object
        parts = message.split()
        command = parts[0]
        args = [p.strip() for p in parts[1:]]
        if (port_name, device_id) in self._devices:
            used = self._devices[(port_name, device_id)].process_serial_message(command, args, message)
        else:
            used = False
            logging.warning('device not found: [%s, %s, %s]' % (port_name, device_id, message))

        # send to user callbacks (if any)
        for handler in self._serial_handlers:
            used = used or handler(device_id, command, args)

        # display message for unused serial message
        if not used:
            logging.debug('unrecognized message received from serial')
