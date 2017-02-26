import os
import sys
import logging
import traceback
import gevent
import util


# The ScriptExec class manages the execution of a single script.
class ScriptExec(object):

    # initialize the script execution object; does not run the script (until start() is called)
    def __init__(self, controller, rel_file_name, channel):
        self._controller = controller
        self._rel_file_name = rel_file_name
        self._greenlet = None
        self._running = False
        self._channel = channel

    # start the script running (spawn a greenlet for it) if not already running
    def start(self):
        if self._running:
            logging.warning('script already running: %s' % self._rel_file_name)
            return
        full_file_name = util.safe_join('.', self._rel_file_name)
        if os.path.isfile(full_file_name):
            # fix(later): do we need to add this to the joinall set? probably not strictly necessary
            self._greenlet = gevent.spawn(self.run)
        else:
            logging.warning('script not found: %s' % self._rel_file_name)

    # runs as a greenlet that executes an external script
    def run(self):
        while not self._controller.ready():
            gevent.sleep(0.5)
        try:
            full_file_name = util.safe_join('.', self._rel_file_name)
            logging.info('starting script: %s' % self._rel_file_name)
            context = {}  # create a dictionary to use for locals and globals
            self._running = True
            execfile(full_file_name, context, context)
            self.send_status('done')
        except gevent.GreenletExit:
            self.send_status('stopped')
            self._running = False
        except Exception as exception:
            self._controller.error('exception from %s: %s' % (self._rel_file_name, exception))
            self.send_status('error', exception)
            self._running = False  # fix(later): should also kill/stop greenlet?
            raise

    # stop the script (stop the script's greenlet)
    def stop(self):
        if self._running:
            self._greenlet.kill()
            self._running = False
            self._greenlet = None

    # send a script status message to the server
    def send_status(self, status_name, exception = None):
        if self._controller.web_socket_connected():
            message_struct = {
                'type': 'scriptStatus',
                'parameters': {
                    'scriptName': self._rel_file_name,
                    'status': status_name,
                }
            }
            if exception:
                exc_type, exc_value, exc_traceback = sys.exc_info()
                message_struct['parameters']['exception'] = traceback.format_exception_only(exc_type, exc_value)
                message_struct['parameters']['stack'] = traceback.extract_tb(exc_traceback)[1:]  # fix(later): make this more robust; we're discarding the first stack item since it's part of this class
            if self._channel:
                message_struct['channel'] = self._channel
            self._controller.send_message_struct_to_server(message_struct)
