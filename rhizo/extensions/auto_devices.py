import os
import gevent
from device import Device


# The AutoDevice class represents a device that operates as a self-identifying stand-alone USB device (sensor or actuator).
class AutoDevice(Device):

    # initialize a sensor or actuator device
    def __init__(self, device_id, controller, port_name):
        super(AutoDevice, self).__init__(device_id, controller, port_name)
        self.name = None  # the device ID will stay fixed, but the name may be changed by the user
        self.dir = 'in'  # fix(soon): default to None
        self.type = None
        self.model = None
        self.version = None
        self.units = None
        self.sent_info = False
        self.store_sequence = False  # indicates whether the sensor values will be stored in a sequence on the server

    # process a serial message from the sensor/actuator
    def process_serial_message(self, command, args, message):
        used = super(AutoDevice, self).process_serial_message(command, args, message)
        if not used:
            used = True

            # handle sensor value(s)
            if command == 'v':
                if self.name:  # we only send values to server if we have a name
                    values = [float(v) for v in args]

                    # send device info to server if not done already
                    # fix(soon): remove this once hardware is migrated to send 'ready'
                    if not self.sent_info:
                        self.sent_info = True
                        self._controller.send_message('device_added', self.as_dict())

                    # send a message to the server
                    self._controller.send_message('sensor_update', {'name': self.name, 'values': values})

                    # call handlers
                    self._controller.auto_devices.run_input_handlers(self, values)

                    # update sequence (if sensor is associated with a sequence)
                    if self.store_sequence:
                        self._controller.update_sequence(self.name, values[0])  # fix(soon): figure out how to handle multi-value sensors

            # handle button press; used to help identify sensors/actuators when multiple of same type plugged in at once
            elif command == 'button':
                if self.name:  # we only send values to server if we have a name
                    self._controller.send_message('device_button', {'name': self.name})

            # handle sensor/actuator information
            elif command == 'dir' and len(args) >= 1:
                self.dir = args[0]
            elif command == 'type' and len(args) >= 1:
                self.type = ' '.join(args)
                if not self.name:  # assign a name based on the type
                    self.name = self._controller.auto_devices.assign_name(self.type)
            elif command == 'model' and len(args) >= 1:
                self.model = ' '.join(args)
            elif command == 'ver' and len(args) >= 1:
                self.version = ' '.join(args)
            elif command == 'units' and len(args) >= 1:
                self.units = ' '.join(args)
            elif command == 'ready':
                self.sent_info = True
                self._controller.send_message('device_added', self.as_dict())
                if self.dir == 'in':
                    self.send_command('interval 1')  # inform sensors to send their values once per second

            # command not used here
            else:
                used = False
        return used

    # return information about the sensor/actuator as a dictionary
    def as_dict(self):
        return {
            'name': self.name,
            'dir': self.dir,
            'type': self.type,
            'model': self.model,
            'version': self.version,
            'units': self.units,
            'store_sequence': self.store_sequence,
        }


class MetaDevice(Device):

    # process a serial message from the sensor/actuator
    def process_serial_message(self, command, args, message):
        used = super(MetaDevice, self).process_serial_message(command, args, message)
        if not used:
            if command == 'devices':
                for device_id in args:
                    device = AutoDevice(device_id, self._controller, self._port_name)
                    self._controller.serial.add_device(device)
                    self._controller.auto_devices.add_device(device)
                    device.send_command('info')  # request information about the sensor
                used = True
        return used


# The AutoDevices extension manages one or more sensor or actuator devices, each plugged into a separate USB port.
# It checks for new USB connections and instantiates a new AutoDevice instance for each one.
class AutoDevices(object):

    def __init__(self, controller):
        self._controller = controller
        self._auto_devices = []  # fix(soon): remove this
        self._next_id = 1
        self._input_handlers = []

    # a greenlet that checks for new USB serial connections
    def check_usb(self):
        prev_usb_devs = []
        while True:

            # get list of usb devices
            if os.path.exists('/dev/'):
                all_devs = os.listdir('/dev')  # fix(faster): use glob?
            else:
                all_devs = []
            usb_devs = [port_name for port_name in all_devs if (port_name.startswith('ttyUSB') or port_name.startswith('ttyACM'))]

            # look for USB devices added
            for short_port_name in usb_devs:
                if not short_port_name in prev_usb_devs:

                    # open serial port
                    # fix(soon): handle case that fails to open; don't want to keep retrying once per second
                    gevent.sleep(0.1)  # sleep a moment to make sure USB port is ready to be opened
                    port_name = '/dev/' + short_port_name
                    self._controller.serial.open_port(port_name)  # fix(soon): retry on failure?

                    # create a meta device
                    device = MetaDevice('meta', self._controller, port_name = port_name)
                    self._controller.serial.add_device(device)

                    # request device list
                    device.send_command('devices')

            # look for USB devices removed
            # fix(soon): handle write failed
            for short_port_name in prev_usb_devs:
                if not short_port_name in usb_devs:
                    port_name = '/dev/' + short_port_name

                    # close the serial port and remove devices on the port
                    self._controller.serial.close_port(port_name)

                    # remove from devices that are using this port
                    self.remove_devices(port_name)

            # save list for next pass around
            prev_usb_devs = usb_devs

            # fix(soon): can we avoid constantly checking this, perhaps using libusb?
            gevent.sleep(1)

    # a greenlet that checks on device states
    def check_devices(self):
        while True:
            for device in self._auto_devices:  # fix(later): avoid sending another request_type if we just added device (and haven't had a chance to get type back from it)
                if not device.type:
                    device.send_command('info')
            gevent.sleep(10)

    # return greenlets used by this extension
    def greenlets(self):
        return [gevent.spawn(self.check_usb), gevent.spawn(self.check_devices)]

    # process incoming websocket message
    def process_message(self, type, params):
        message_used = True
        response_message = None

        # get a list devices
#        if type == 'list_devices':
#            response_message = json.dumps([s.as_dict() for s in self._auto_devices])

        # rename a device
        if type == 'rename_device':
            old_name = params['old_name']
            new_name = params['new_name']
            device = self.find_device(old_name)
            if device:
                device.name = new_name
            else:
                response_message = 'error'  # fix(soon): provide error response

        # set a sensor as one to be stored in a sequence on the server
        # fix(soon): remove this? make all sensors into sequences?
        elif type == 'store_sensor':
            name = params['name']
            device = self.find_device(name)
            if device:
                device.store_sequence = True
            else:
                response_message = 'error'  # fix(soon): provide error response

        # control actuators
        elif type == 'update_actuator':
            name = params['name']
            value = params['value']
            device = self.find_device(name)
            if device:
                device.send_command('set %s' % value)

        # message not used here
        else:
            message_used = False
        return (message_used, response_message)

    # run functions when we receive data from a sensor
    def run_input_handlers(self, device, values):
        for handler in self._input_handlers:
            handler(device.name, values)

    # add a function that will get called when we receive data from a sensor
    def add_input_handler(self, handler):
        self._input_handlers.append(handler)

    # assign device name based on type
    def assign_name(self, type):
        i = 2
        name = type
        while self.find_device(name):
            name = '%s %d' % (type, i)
            i += 1
        return name

    # add a device and notify server
    def add_device(self, device):
        self._auto_devices.append(device)

    # remove devices associated with given serial port and notify server
    # fix(soon): also remove from serial._devices
    def remove_devices(self, port_name):
        new_devices = []
        for device in self._auto_devices:
            if device.port_name() == port_name:
                self._controller.send_message('device_removed', device.as_dict())
            else:
                new_devices.append(device)
        self._auto_devices = new_devices

    # find a device by name; each device should have a unique name
    def find_device(self, name):
        for device in self._auto_devices:
            if device.name == name:
                return device
        return None
