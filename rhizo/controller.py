# update standard libraries to use gevent
import gevent
from gevent import monkey
monkey.patch_all()


# standard python imports
import os
import sys
import time
import json
import logging
import logging.handlers
import datetime
from optparse import OptionParser


# external imports
import psutil


# our own imports
from . import config
from .resources import FileClient
from .sequences import SequenceClient
from .messages import MessageClient


# A Controller object contains and manages various communication and control threads.
class Controller(object):

    # ======== initialization ========

    # prepare internal data
    def __init__(self, configuration=None):

        # initialize member variables
        self.config = None  # publicly accessible
        self.VERSION = '0.0.6'
        self.BUILD = 'unknown'
        self._error_handlers = []
        self._path_on_server = None

        # process command arguments
        parser = OptionParser()
        parser.add_option('-c', '--config-file-name', dest='config_file_name', default='config.yaml')
        parser.add_option('-v', '--verbose', dest='verbose', action='store_true', default=False)
        (options, args) = parser.parse_args()

        # prep configuration object
        if configuration:
            self.config = config.Config(configuration)
            self._config_relative_file_name = '(passed by caller)'
        else:
            self._config_relative_file_name = options.config_file_name
            self.load_config()
            if not self.config:
                sys.exit(1)

        # start logging
        self.find_build_ref()
        self.prep_logger(options.verbose or self.config.get('verbose', False))  # make verbose if in config or command-line options
        self.show_config()

        # initialize client API modules
        self.files = FileClient(self.config, self)
        self.resources = self.files  # temp alias for compatibility
        self.sequences = SequenceClient(self)
        self.sequence = self.sequences  # temp alias for compatibility
        self.messages = MessageClient(self)

        # if server connection is enabled in config
        if self.config.get('enable_server', True):

            # if no secret key in our config, request one
            if not self.config.get('secret_key'):
                self.request_key()

            # enable logging to server
            server_handler = ServerHandler(self)
            server_handler.set_level_name(self.config.get('server_log_level', 'info'))
            logging.getLogger().addHandler(server_handler)

            # monitor system status
            gevent.spawn(self.system_monitor)

            # connect to message server
            self.messages.connect()
            last_message_time = time.time()
            while not self.messages.connected():
                gevent.sleep(0.1)
                if time.time() > last_message_time + 5:
                    logging.info('waiting for connection to message server')
                    last_message_time = time.time()

    # prepare file and console logging for the controller (using the standard python logging library)
    # default log level is INFO unless verbose (then it is DEBUG)
    def prep_logger(self, verbose):
        log_path = 'logs'
        if not os.path.isdir(log_path):
            os.makedirs(log_path)
            if not os.path.isdir(log_path):
                print('unable to create log directory: %s' % log_path)
                sys.exit(1)
        formatter = logging.Formatter('%(asctime)s: %(levelname)s: %(message)s')
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG if verbose else logging.INFO)
        console_handler.setFormatter(formatter)
        if self.config.get('log_file_per_run', False):
            time_str = datetime.datetime.now().strftime('%Y-%m-%d-%H%M%S')
            file_handler = logging.FileHandler(log_path + '/' + time_str + '.txt')
            file_handler.setLevel(5)  # used to log serial/etc. messages to disk
            file_handler.setFormatter(formatter)
        else:
            max_log_file_size = self.config.get('max_log_file_size', 10000000)
            file_handler = logging.handlers.RotatingFileHandler(log_path + '/client-log.txt', maxBytes=max_log_file_size, backupCount=10)
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(formatter)
        root = logging.getLogger()
        root.addHandler(console_handler)
        root.addHandler(file_handler)
        root.setLevel(logging.DEBUG)
        version_build = self.VERSION
        if self.BUILD != 'unknown':
            version_build += ':' + self.BUILD
        logging.info('--------------' + '-' * len(version_build))
        logging.info('Rhizo Client v' + version_build)
        logging.info('--------------' + '-' * len(version_build))

    # get build number from git refs
    # fix(soon): rework this to use the path of this file
    def find_build_ref(self):
        rhizo_path = '../rhizo/'
        for i in range(5):  # search for the rhizo directory up to 5 levels above start directory
            try:
                git_build_ref_path = rhizo_path + '.git/refs/heads/master'
                with open(git_build_ref_path) as build_ref_file:
                    self.BUILD = build_ref_file.readline()[:7]  # first 7 chars of the build ref
                break
            except IOError:
                rhizo_path = '../' + rhizo_path

    # load configuration files
    def load_config(self):

        # make sure the config file exists
        config_file_name = self._config_relative_file_name
        if not os.access(config_file_name, os.F_OK):
            logging.error('unable to load config file: %s' % config_file_name)  # note: this won't be logged on startup, since the config is used to configure logger
            return

        # load configuration
        self.config = config.load_config(config_file_name)

        # check for local config
        config_dir = os.path.dirname(config_file_name)
        local_config_file_name = (config_dir + '/' if config_dir else '') + 'local.yaml'
        if os.access(local_config_file_name, os.F_OK):
            local_config = config.load_config(local_config_file_name)
            self.config.update(local_config)

    # show the current configuration
    def show_config(self):
        logging.info('loaded config: %s' % self._config_relative_file_name)
        for (k, v) in self.config.items():
            if 'secret_key' in k:
                logging.debug('%s: %s...%s' % (k, v[:3], v[-3:]))
            else:
                logging.debug('%s: %s' % (k, v))

    # ======== public API ========

    # get the path of the controller folder on the server
    def path_on_server(self):
        if not self._path_on_server:
            file_info = self.files.file_info('/self')
            self._path_on_server = file_info['path']
        return self._path_on_server

    # add a custom handler for errors
    def add_error_handler(self, error_handler):
        self._error_handlers.append(error_handler)

    # trigger the error handler(s)
    def error(self, message=None, exception=None):
        for error_handler in self._error_handlers:
            error_handler(message=message, exception=exception)
        if message:
            logging.error(message)
        if exception:
            logging.error(str(exception))
        error_recipients = self.config.get('error_recipients', [])
        if error_recipients:
            subject = self.config.get('error_subject', 'system error')
            body = self.config.get('error_body', '').strip()
            if body:
                body += ' '
            if message:
                body += message
            if exception:
                body += '\n' + str(exception)
            for recipient in error_recipients:
                recipient = str(recipient)  # in case someone enters a phone number without quotes and it comes in as an integer
                if '@' in recipient:
                    self.messages.send_email(recipient, subject, body)
                else:
                    self.messages.send_sms(recipient, subject + ': ' + body)

    # ======== deprecated public API ========

    # sleep for the requested number of seconds
    def sleep(self, seconds):
        print('controller.sleep is deprecated; use gevent.sleep')
        gevent.sleep(seconds)

    # send a new sequence value to the server
    def update_sequence(self, sequence_name, value, use_websocket=True):
        print('controller.update_sequence is deprecated; use controller.sequences.update')
        self.sequences.update(sequence_name, value, use_websocket)

    # update multiple sequences; timestamp must be UTC (or None)
    # values should be a dictionary of sequence values by path (for now assuming absolute sequence paths)
    def update_sequences(self, values, timestamp=None):
        print('controller.update_sequences is deprecated; use controller.sequences.update_multiple')
        self.sequences.update_multiple(values, timestamp)

    # send a websocket message to the server
    def send_message(self, type, parameters, channel=None, folder=None, prepend=False):
        print('controller.send_message is deprecated; use controller.messages.send')
        self.messages.send(type, parameters, channel, folder, prepend)

    # send an email (to up to five addresses)
    def send_email(self, email_addresses, subject, body):
        print('controller.send_email is deprecated; use controller.messages.send_email')
        self.messages.send_email(email_addresses, subject, body)

    # send a text message (to up to five phone numbers)
    def send_text_message(self, phone_numbers, message):
        print('controller.send_text_message is deprecated; use controller.messages.send_sms')
        self.messages.send_sms(phone_numbers, message)

    # add a custom handler for messages from server
    def add_message_handler(self, message_handler):
        print('controller.add_message_handler is deprecated; use controller.messages.add_handler')
        self.messages.add_handler(message_handler)

    # ======== misc. internal functions ========

    # a greenlet that monitors system status (disk and CPU usage)
    def system_monitor(self):
        gevent.sleep(15)  # do a short sleep on startup
        while True:
            processor_usage = psutil.cpu_percent()
            disk_usage = psutil.disk_usage('/').percent
            status_folder = self.path_on_server() + '/status'
            seq_values = {status_folder + '/processor_usage': processor_usage, status_folder + '/disk_usage': disk_usage}
            self.sequences.update_multiple(seq_values)
            if processor_usage > 80 or disk_usage > 80:
                logging.info('processor usage: %.1f%%, disk usage: %.1f%%' % (processor_usage, disk_usage))
            gevent.sleep(30 * 60)  # sleep for 30 minutes

    # request a PIN and key from the server;
    # this should run before any other greenlets are running
    def request_key(self):

        # request PIN
        response = json.loads(self.files.send_request_to_server('POST', '/api/v1/pins'))
        pin = response['pin']
        pin_code = response['pin_code']

        # display PIN
        logging.info('your PIN is: %d' % pin)
        logging.info('waiting for PIN to be entered on server')

        # check on PIN
        start_time = time.time()
        while True:
            gevent.sleep(5)  # check every ~5 seconds
            params = {'pin_code': pin_code}
            response = json.loads(self.files.send_request_to_server('GET', '/api/v1/pins/%d' % pin, params))
            if 'secret_key' in response:
                break
            if time.time() - start_time > 5 * 60:
                logging.info('timeout waiting for key')
                sys.exit(1)

        # display name, key prefix, key suffix
        secret_key = response['secret_key']
        logging.info('received key for controller: %s' % response['controller_path'])
        logging.debug('key prefix: %s, key suffix: %s' % (secret_key[:3], secret_key[-3:]))

        # save key in local.yaml
        # fix(later): handle case that someone is storing secret_key in a file other than local.yaml?
        config_dir = os.path.dirname(self._config_relative_file_name)
        local_config_file_name = (config_dir + '/' if config_dir else '') + 'local.yaml'
        new_entry = 'secret_key: %s\n' % secret_key
        if os.path.exists(local_config_file_name):
            with open(local_config_file_name) as input_file:
                lines = input_file.readlines()
            with open(local_config_file_name, 'w') as output_file:
                found = False
                for line in lines:
                    if line.strip().startswith('secret_key'):  # if file already has secret key, overwrite it
                        line = new_entry
                        found = True
                    output_file.write(line)
                if not found:
                    output_file.write('\n' + new_entry)  # if not, append it
        else:
            open(local_config_file_name, 'w').write(new_entry)

        # update in-memory config
        self.config.secret_key = secret_key
        self.files._secret_key = secret_key


# a custom log handler for sending logged messages to server (in a log sequence)
class ServerHandler(logging.Handler):

    # initialize the object
    def __init__(self, controller):
        super(ServerHandler, self).__init__()
        self.controller = controller
        self.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
        self.inside_handler = False

    # set logging level by name
    def set_level_name(self, name):
        name = name.lower()
        if name == 'debug':
            self.setLevel(logging.DEBUG)
        elif name == 'info':
            self.setLevel(logging.INFO)
        elif name == 'warn' or name == 'warning':
            self.setLevel(logging.WARNING)
        elif name == 'error':
            self.setLevel(logging.ERROR)

    # handle a log message; send it to server as a log sequence value
    def emit(self, record):
        if self.inside_handler:  # if update_sequence does any logging, let's skip it
            return
        self.inside_handler = True
        try:
            message = self.format(record)
            self.controller.sequences.update('log', message)
        except (KeyboardInterrupt, SystemExit):
            raise
        except:
            self.handle_error(record)
        self.inside_handler = False
