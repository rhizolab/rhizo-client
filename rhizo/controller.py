# standard python imports
import os
import sys
import imp
import time
import json
import base64
import socket
import logging
import logging.handlers
import datetime
import traceback
import importlib
from optparse import OptionParser


# external imports
import gevent
from ws4py.client.geventclient import WebSocketClient


# our own imports
import config
import util
from extensions.resources import Resources  # fix(soon): remove this and require add as extension?


# A Controller object contains and manages various communication and control threads.
class Controller(object):

    # ======== initialization ========

    # prepare internal data
    def __init__(self):

        # initialize member variables
        self.config = None  # publicly accessible
        self.VERSION = '0.0.4'
        self.BUILD = 'unknown'
        self._web_socket = None
        self._local_seq_files = {}
        self._extensions = []
        self._outgoing_messages = []
        self._message_handler = None  # user-defined message handler
        self._error_handlers = []
        self._greenlets = []
        self._path_on_server = None
        self.resources = None

        # process command arguments
        parser = OptionParser()
        parser.add_option('-c', '--config-file-name', dest='config_file_name', default='config.hjson')
        parser.add_option('-v', '--verbose', dest='verbose', action='store_true', default=False)
        (options, args) = parser.parse_args()

        # load config file
        self._config_relative_file_name = options.config_file_name
        self.load_config()
        if not self.config:
            sys.exit(1)

        # initialize other controller attributes
        if self.config.get('enable_keyboard_monitor', False):
            import kbhit
            self._kb = kbhit.KBHit()
        self.find_build_ref()
        self.prep_logger(options.verbose or self.config.get('verbose', False))  # make verbose if in config or command-line options
        self.show_config()

        # if connect to server, but no key, request a key using a PIN
        if self.config.get('enable_server', True) and not self.config.get('secret_key'):
            self.request_key()

        # enable logging to server
        if self.config.get('enable_server', True):
            server_handler = ServerHandler(self)
            server_handler.set_level_name(self.config.get('server_log_level', 'info'))
            logging.getLogger().addHandler(server_handler)

        # initialize extensions modules
        if 'extensions' in self.config:
            extension_names = self.config.item_as_list('extensions', [])
            for extension_name in extension_names:
                class_name = underscores_to_camel(extension_name)
                class_name = class_name[0].upper() + class_name[1:]
                module_name = extension_name
                if extension_name == 'serial':  # avoid conflict with pyserial
                    module_name = 'serial_'
                paths = [''] + self.config.get('extension_paths', [])
                success = False
                for path in paths:  # fix(later): better to just to add extension paths to sys.path?
                    try:
                        if path:
                            ext_mod = imp.load_source(module_name, path + '/' + module_name + '.py')
                        else:
                            ext_mod = importlib.import_module('rhizo.extensions.' + module_name)
                        ext_cls = ext_mod.__dict__[class_name]
                        extension = ext_cls(self)
                        self.__dict__[extension_name] = extension
                        self._extensions.append(extension)
                        logging.debug('loaded extension: %s' % extension_name)
                        success = True
                        break
                    except ImportError:
                        pass
                if not success:
                    logging.warning('unable to load extension: %s' % extension_name)
            self.start_greenlets()
            for extension in self._extensions:
                if hasattr(extension, 'init'):
                    extension.init()
        else:
            self.start_greenlets()

        # wait until ready before running user scripts
        while not self.ready():
            gevent.sleep(0.1)

    # add an extension directly (rather than through config)
    def add_extension(self, name, extension):
        self.__dict__[name] = extension
        self._extensions.append(extension)
        if hasattr(extension, 'greenlets'):
            self._greenlets += extension.greenlets()
        if hasattr(extension, 'init'):
            extension.init()

    # reload the configuration file from disk and inform the add-ons
    def reload_config(self):
        self.load_config()
        self.show_config()
        for extension in self._extensions:
            if hasattr(extension, 'reload_config'):
                extension.reload_config()

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
            file_handler.setLevel(5)  # log serial messages to disk
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

    # load configuration file
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
        local_config_file_name = (config_dir + '/' if config_dir else '') + 'local.hjson'
        if os.access(local_config_file_name, os.F_OK):
            local_config = config.load_config(local_config_file_name)
            self.config.update(local_config)

    # show the current configuration
    def show_config(self):
        logging.info('loaded config: %s' % self._config_relative_file_name)
        for (k, v) in self.config.items():
            if k == 'secret_key' or k == 'secretKey':
                logging.debug('%s: %s...%s' % (k, v[:3], v[-3:]))
            else:
                logging.debug('%s: %s' % (k, v))

    # runs all of the pseudo-threads (greenlets) the comprise the controller
    def start_greenlets(self):
        greenlets = []
        # (fix) don't run the keyboard monitor if the positioning helper is running
        if self.config.get('enable_keyboard_monitor', False) and not hasattr(self, 'posHelper'):
            greenlets.append(gevent.spawn(self.keyboard_monitor))
        if self.config.get('enable_server', True):
            greenlets.append(gevent.spawn(self.web_socket_listener))
            greenlets.append(gevent.spawn(self.web_socket_sender))
            greenlets.append(gevent.spawn(self.ping_web_socket))
        for extension in self._extensions:
            if hasattr(extension, 'greenlets'):
                greenlets += extension.greenlets()
        self._greenlets = greenlets

    # wait for the user to interrupt the program
    def wait_for_termination(self):
        try:
            gevent.joinall(self._greenlets)  # this won't complete since some greenlets never return
        except KeyboardInterrupt:
            logging.info('quitting (keyboard interrupt)')
        except Exception as e:
            logging.warning('controller caught exception')
            self.error(exception=e)

    # ======== public API ========

    # sleep for the given number of seconds (e.g. 0.01 -> 10 milliseconds)
    def sleep(self, seconds):
        gevent.sleep(seconds)

    # wait for user input before continuing script
    def wait_for_user(self):
        raw_input('press ENTER to continue')

    # get the path of the controller folder on the server
    def path_on_server(self):
        if not self._path_on_server:
            if not self.resources:  # load resources extension since we'll use REST API
                self.resources = Resources(self)
            file_info = self.resources.file_info('/self')
            self._path_on_server = file_info['path']
        return self._path_on_server

    # send a serial command to the devices via the serial port
    def send_serial_command(self, device_id, command):
        logging.warning('using sendSerialCommand; will be removed')
        self.serial.send_command(device_id, command)

    # send a new sequence value to the server
    def update_sequence(self, sequence_name, value, use_websocket=True):
        if self.config.get('enable_server', True):
            if use_websocket:
                if self._web_socket:
                    self.send_message('update_sequence', {'sequence': sequence_name, 'value': value})
            else:  # note that this case currently requires an absolute path on the server
                if not self.resources:  # create a resource client instance if not already done
                    self.resources = Resources(self)
                value = str(value)  # write_file currently expects string values
                while True:  # repeat until verified that value is written
                    self.resources.write_file(sequence_name, value)
                    server_value = self.resources.read_file(sequence_name)
                    if value == server_value:
                        break
                    gevent.sleep(0.5)
        if self.config.get('enable_local_sequence_storage', False):
            self.store_local_sequence_value(sequence_name, value)

    # update multiple sequences; timestamp must be UTC (or None)
    # values should be a dictionary of sequences
    def update_sequences(self, values, timestamp=None):
        if not timestamp:
            timestamp = datetime.datetime.utcnow()
        if not self.resources:  # create a resource client instance if not already done
            self.resources = Resources(self)
        params = {
            'values': json.dumps({n: str(v) for n, v in values.iteritems()}),  # make sure all values are strings
            'timestamp': timestamp.isoformat() + ' Z',
        }
        self.resources.send_request_to_server('PUT', '/api/v1/resources', params)

    # send an email (to up to five addresses)
    def send_email(self, email_addresses, subject, body):
        self.send_message('send_email', {
            'emailAddresses': email_addresses,
            'subject': subject,
            'body': body,
        })

    # send a text message (to up to five phone numbers)
    def send_text_message(self, phone_numbers, message):
        self.send_message('send_text_message', {
            'phoneNumbers': phone_numbers,
            'message': message,
        })

    # returns if initialization is done and we're ready to start running user scripts
    def ready(self):
        return self._web_socket or not self.config.get('enable_server', True)

    # returns True if websocket is connected to server
    def web_socket_connected(self):
        return self._web_socket is not None

    # add a custom handler for errors
    def add_error_handler(self, error_handler):
        self._error_handlers.append(error_handler)

    # add a custom handler for websocket messages
    # fix(later): allow add multiple
    def add_message_handler(self, message_handler):
        self._message_handler = message_handler

    # trigger the error handler(s)
    def error(self, message=None, exception=None):
        for error_handler in self._error_handlers:
            error_handler(message=message, exception=exception)
        if message:
            logging.error(message)
        if exception:
            logging.error(str(exception))
        error_recipients = self.config.item_as_list('error_recipients', [])
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
                    self.send_email(recipient, subject, body)
                else:
                    self.send_text_message(recipient, subject + ': ' + body)

    # ======== our greenlets ========

    # runs as a greenlet that maintains a websocket connection with the server
    def web_socket_listener(self):
        while True:
            try:
                if self._web_socket:
                    try:
                        message = self._web_socket.receive()
                    except:
                        message = None
                    if message:
                        self.process_web_socket_message(message)
                    else:
                        logging.warning('disconnected (on received); reconnecting...')
                        self._web_socket = None
                        gevent.sleep(10)  # avoid fast reconnects
                gevent.sleep(0.1)
            except Exception as e:
                self.error('error in web socket message listener/handler', exception = e)
                exc_type, exc_value, exc_traceback = sys.exc_info()
                logging.info(traceback.format_exception_only(exc_type, exc_value))
                stack = traceback.extract_tb(exc_traceback)
                for line in stack:
                    logging.info(line)

    # runs as a greenlet that sends queued messages to the server
    def web_socket_sender(self):
        while True:
            if self._web_socket:
                while self._outgoing_messages:
                    try:
                        if self._web_socket:  # check again, in case we closed the socket in another thread
                            (timestamp, message_struct) = self._outgoing_messages[0]
                            if timestamp > datetime.datetime.utcnow() - datetime.timedelta(minutes=5):  # discard (don't send) messages older than 5 minutes
                                self._web_socket.send(json.dumps(message_struct, separators=(',', ':')) + '\n')
                            self._outgoing_messages = self._outgoing_messages[1:]  # remove from queue after send
                    except (AttributeError, socket.error):
                        logging.debug('disconnected (on send); reconnecting...')
                        self._web_socket = None
                        break
                gevent.sleep(0.1)
            else:  # connect if not already connected
                try:
                    self._web_socket = self.connect_web_socket()
                    if self._web_socket:
                        self.send_init_socket_messages()
                    else:
                        gevent.sleep(10)
                except Exception as e:
                    logging.debug(str(e))
                    logging.warning('error connecting; will try again')
                    gevent.sleep(10)  # let's not try to reconnect too often

    # runs as a greenlet that maintains a periodically pings the web server to keep the websocket connection alive
    def ping_web_socket(self):
        while True:
            gevent.sleep(45)
            if self._web_socket:
                self.send_message('ping', {})

    # monitors the keyboard and e-stops the script
    def keyboard_monitor(self):
        is_e_stop = False
        while True:
            if self._kb.kbhit():
                c = self._kb.getch()
                if ord(c) == 27:  # ESC
                    break
                if c == ' ':  # Space bar
                    is_e_stop = True
                    break
                if c == 'c':  # reload configuration
                    logging.info('reloading configuration file from disk')
                    self.reload_config()
            self.sleep(0.01)
        logging.error('ABORTING: Script stopped by user')
        if is_e_stop:
            logging.error('E-STOP: Halting motors')
            self.motors.e_stop()
        self._kb.set_normal_term()  # resets the terminal so we can ctrl-c out
        raise KeyboardInterrupt  # just aborts all running greenlets

    # ======== internal processing functions ========

    # handle an incoming message from the websocket
    def process_web_socket_message(self, message):
        message_struct = json.loads(str(message))

        # process the message
        if 'type' in message_struct and 'parameters' in message_struct:
            type = message_struct['type']
            params = message_struct['parameters']
            channel = message_struct.get('channel')
            response_message = None
            if type == 'get_config' or type == 'getConfig':
                response_message = self.config_message(params['names'].split(','))
            elif type == 'set_config' or type == 'setConfig':
                self.set_config(params)
            elif type == 'shutdown':
                logging.info('shutting down')
                reboot = bool(int(params.get('reboot', True)))
                if reboot:
                    os.system('shutdown -r now')  # reboot (will not work on windows)
                else:
                    os.system('shutdown -h now')  # halt (will not work on windows)
            else:
                message_used = False
                for extension in self._extensions:
                    if hasattr(extension, 'process_message'):
                        (message_used, response_message) = extension.process_message(type, params)
                        if message_used:
                            break
                if not message_used and self._message_handler:
                    if hasattr(self._message_handler, 'handle_message'):
                        self._message_handler.handle_message(type, params)
                    else:
                        self._message_handler(type, params)
            if response_message:
                if channel:
                    response_message['channel'] = channel
                self.send_message_struct_to_server(response_message)

    # stores a sequence value in a local log file (an alternative to sending the value to the server)
    def store_local_sequence_value(self, sequence_name, value):
        if sequence_name not in self._local_seq_files:
            self._local_seq_files[sequence_name] = open('log/%s.csv', sequence_name, 'a')
        self._local_seq_files[sequence_name].write('%.3f,%.3f\n' % (time.time(), value))  # fix(soon): better timestamps, decimal places

    # initiate a websocket connection with the server
    def connect_web_socket(self):
        if 'secure_server' in self.config:
            secure_server = self.config.secure_server
        else:
            host_name = self.config.server_name.split(':')[0]
            secure_server = host_name != 'localhost' and host_name != '127.0.0.1'
        protocol = 'wss' if secure_server else 'ws'
        if self.config.get('old_auth', False):
            headers = None
        else:
            user_name = self.VERSION + '.' + self.BUILD  # send client version as user name
            password = self.config.secret_key  # send secret key as password
            headers = [('Authorization', 'Basic %s' % base64.b64encode('%s:%s' % (user_name, password)))]
        ws = WebSocketClient(protocol + '://' + self.config.server_name + '/api/v1/websocket', protocols=['http-only'], headers=headers)
        try:
            ws.connect()
            logging.debug('opened websocket connection to server')
        except Exception as e:
            logging.debug(str(e))
            logging.warning('error connecting to server')
            ws = None
        return ws

    # send a websocket message to the server subscribing to messages intended for this controller
    # note: these messages are prepended to the queue, so that we're authenticated for everything else in the queue
    def send_init_socket_messages(self):
        params = {
            'authCode': util.build_auth_code(self.config.secret_key),
            'version': self.VERSION + ':' + self.BUILD
        }
        if 'name' in self.config:
            params['name'] = self.config.name
        self.send_message('subscribe', {
            'subscriptions': [  # note: this subscription listens to all message types
                {
                    'folder': 'self',
                    'include_children': self.config.get('subscribe_children', False),
                }
            ]
        }, prepend=True)
        if self.config.get('old_auth', False):
            self.send_message('connect', params, prepend=True)  # add to queue after subscribe so send before; fix(soon): revisit this
        logging.info('controller connected/re-connected')

    # send a websocket message to the server
    def send_message(self, type, parameters, channel=None, folder=None, prepend=False):
        message_struct = {
            'type': type,
            'parameters': parameters
        }
        if folder:
            message_struct['folder'] = folder
        if channel:
            message_struct['channel'] = channel
        self.send_message_struct_to_server(message_struct, prepend)

    # send a websocket message to the server
    def send_message_struct_to_server(self, message_struct, prepend=False, timestamp=None):
        timestamp = datetime.datetime.utcnow()
        if prepend:
            self._outgoing_messages = [(timestamp, message_struct)] + self._outgoing_messages
        else:
            self._outgoing_messages.append((timestamp, message_struct))

    # get a configuration setting as a message
    def config_message(self, names):
        return {
            'type': 'config',
            'parameters': {name: self.config.get(name, '') for name in names},
        }

    # update the config file using a dictionary of config entries
    def set_config(self, params):
        output_lines = []
        input_file = open(self._config_relative_file_name)
        for line in input_file:
            parts = line.split()
            if parts and parts[0] in params:
                line = '%s %s\n' % (parts[0], params[parts[0]])
                output_lines.append(line)
            else:
                output_lines.append(line)
        input_file.close()
        output_file = open(self._config_relative_file_name, 'w')
        for line in output_lines:
            output_file.write(line)
        output_file.close()
        self.reload_config()

    # request a PIN and key from the server;
    # this should run before any other greenlets are running
    def request_key(self):

        # initialize resource client so we can use its request function
        if not self.resources:
            self.config.secret_key = 'x'  # set a temp secret key since resource client expects one
            self.config.secret_key = 'x'
            self.resources = Resources(self)

        # request PIN
        response = json.loads(self.resources.send_request_to_server('POST', '/api/v1/pins'))
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
            response = json.loads(self.resources.send_request_to_server('GET', '/api/v1/pins/%d' % pin, params))
            if 'secret_key' in response:
                break
            if time.time() - start_time > 5 * 60:
                logging.info('timeout waiting for key')
                sys.exit(1)

        # display name, key prefix, key suffix
        secret_key = response['secret_key']
        logging.info('received key for controller: %s' % response['controller_path'])
        logging.debug('key prefix: %s, key suffix: %s' % (secret_key[:3], secret_key[-3:]))

        # save key in local.hjson
        # fix(later): handle case that someone is storing secret_key in a file other than local.hjson?
        config_dir = os.path.dirname(self._config_relative_file_name)
        local_config_file_name = (config_dir + '/' if config_dir else '') + 'local.hjson'
        new_entry = 'secret_key: %s\n' % secret_key
        if os.path.exists(local_config_file_name):
            with open(local_config_file_name) as input_file:
                lines = input_file.readlines()
            output_file = open(local_config_file_name, 'w')
            found = False
            for line in lines:
                if line.strip().startswith('secret_key'):  # if file already has secret key, overwrite it
                    line = new_entry
                    found = True
                output_file.write(line)
            if not found:
                output_file.write(new_entry)  # if not, append it
        else:
            open(local_config_file_name, 'w').write(new_entry)

        # update in-memory config
        self.config.secret_key = secret_key
        self.config.secret_key = secret_key
        self.resources._secret_key = secret_key


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
            self.controller.update_sequence('log', message)
        except (KeyboardInterrupt, SystemExit):
            raise
        except:
            self.handle_error(record)
        self.inside_handler = False


# convert a name with underscores to camel case
def underscores_to_camel(name):
    result = ''
    last_c = ''
    for c in name:
        if c != '_':
            if last_c == '_':
                c = c.upper()
            result += c
        last_c = c
    return result
