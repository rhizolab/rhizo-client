import logging
from rhizo.main import c
from rhizo.util import crc16_ccitt
from rhizo.extensions.serial_ import Port
from rhizo.extensions.device import Device


# a mock serial connection for testing the serial extension
class MockSerialConnection(object):

    def __init__(self):
        self.replies = []
        self.polled = False

    # handle a message sent to the serial port
    def write(self, text):

        # simplistic parsing of command message
        text = text.strip()
        parts = text.split('|')
        message = parts[0]
        crc = int(parts[1])
        parts = message.split(':')
        device_id = parts[0]
        command = parts[1]
        if crc16_ccitt(message) != crc:
            print('crc error')

        # note if received polling message
        if command == 'q':
            self.polled = True

        # acknowledge the command
        ack = '%s:ack %s' % (device_id, command)
        self.replies.append(ack)

    # send responses back from serial port
    def readline(self):
        message = None
        if self.replies:
            message = self.replies.pop()
            message += '|%d' % crc16_ccitt(message)
        return message


# basic test of serial using mock serial port
def test_serial():

    # open a mock serial port
    mock_conn = MockSerialConnection()
    c.serial._ports['mock'] = Port(mock_conn)

    # create a test device
    device = Device('x', c)
    device.enable_polling(True)
    c.serial.add_device(device)
    c.serial.send_command('x', 'hello')

    # wait until polled
    while not mock_conn.polled:
        c.sleep(0.1)


# if run as a top-level script
if __name__ == '__main__':
    test_serial()
