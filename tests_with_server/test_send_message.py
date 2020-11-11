import logging
import gevent
from rhizo.main import c


# test sending a message
def test_send_message():
    if False:
        c.send_message('send_email',
            {
                'emailAddresses': 'peter@modularscience.com',
                'subject': 'test message',
                'body': 'This is a test.',
            }
        )
    if False:
        c.send_message('send_text_message',
            {
                'phoneNumbers': '415-857-5658',
                'message': 'This is a test.',
            }
        )
    gevent.sleep(2)


def message_handler(type, params):
    logging.debug('message: %s, %s' % (type, params))


def test_send_message_with_folder():
    c.messages.add_handler(message_handler)
    c.messages.send('test_message', {'foo': 'bar'}, folder = c.path_on_server() + '/folder')
    gevent.sleep(5)


# if run as a top-level script
if __name__ == '__main__':
    test_send_message_with_folder()
