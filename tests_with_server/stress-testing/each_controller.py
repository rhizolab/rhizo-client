import os
import gevent
from rhizo.main import c


path_on_server = c.path_on_server()
name = path_on_server.rsplit('/', 1)[1]
print name, os.getcwd(), path_on_server


# loop forever sending messages
message_index = 0
while True:
    message = 'msg-%s-%d' % (name, message_index)
    print('%s: send: %s' % (name, message))
    c.send_message(message, {})
    gevent.sleep(1)
    message_index += 1
