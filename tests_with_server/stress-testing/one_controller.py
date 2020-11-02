# update standard libraries to use gevent
import gevent
from gevent import monkey
monkey.patch_all()


from rhizo.controller import Controller


# this object holds a controller instances, allowing multiple mostly-independent server connections
class TestConnection(object):

    # create a controller
    def __init__(self, name):
        self.name = name
        self.c = Controller()
        self.message_index = 0
        self.c.messages.add_handler(self)
        gevent.spawn(self.main_loop)

    # loop forever sending messages
    def main_loop(self):
        while True:
            message = 'msg-%s-%d' % (self.name, self.message_index)
            print('%s: send: %s' % (self.name, message))
            self.c.send_message(message, {})
            gevent.sleep(self.c.config.update_interval)
            self.message_index += 1

    # display any received messages
    def handle_message(self, type, params):
        print('%s: recv %s %s' % (self.name, type, params))


if __name__ == '__main__':

    # create a set of connections
    test_conns = []
    for i in range(5):
        name = chr(ord('a') + i)
        test_conns.append(TestConnection(name))

    # run forever
    while True:
        gevent.sleep(1)
