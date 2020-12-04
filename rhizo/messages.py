import sys
import json
import socket
import base64
import logging
import datetime
import traceback
import gevent
import paho.mqtt.client as mqtt
from . import util
from ws4py.client.geventclient import WebSocketClient


# provides an interface to the rhizo-server message server
class MessageClient(object):

    def __init__(self, controller):
        self._controller = controller
        self._web_socket = None
        self._outgoing_messages = []
        self._message_handlers = []  # user-defined message handlers
        self._client = None
        self._client_connected = False

    def connect(self):

        # old websocket connection
        if self._controller.config.get('enable_ws', True):
            gevent.spawn(self.web_socket_listener)
            gevent.spawn(self.web_socket_sender)
            gevent.spawn(self.ping_web_socket)

        # MQTT connection
        if 'mqtt_host' in self._controller.config:
            mqtt_host = self._controller.config.mqtt_host
            mqtt_port = self._controller.config.get('mqtt_port', 443)
            mqtt_tls = self._controller.config.get('mqtt_tls', True)

            # run this on connect/reconnect to MQTT server/broker
            def on_connect(client, userdata, flags, rc):
                if rc:
                    logging.warning('unable to connect to MQTT broker/server at %s:%d' % (mqtt_host, mqtt_port))
                else:
                    logging.info('connected to MQTT broker/server at %s:%d' % (mqtt_host, mqtt_port))
                    self._client_connected = True
                topic = self._controller.path_on_server().lstrip('/')  # don't use leading slash for MQTT topics
                self._client.subscribe(topic)
                logging.info('subscribed to %s' % topic)

            # run this on disconnect from MQTT server/broker
            def on_disconnect(client, userdata, rc):
                self._client_connected = False

            # run this on incoming MQTT message
            def on_message(client, userdata, msg):
                # print('MQTT recv: %s, %s' % (msg.topic, msg.payload.decode()))
                self.process_incoming_message(msg.payload.decode())

            self._client = mqtt.Client(transport='websockets')
            self._client.on_connect = on_connect
            self._client.on_disconnect = on_disconnect
            self._client.on_message = on_message
            self._client.username_pw_set('key', self._controller.config.secret_key)
            if mqtt_tls:
                self._client.tls_set()  # enable SSL
            self._client.connect(mqtt_host, mqtt_port)
            self._client.loop_start()

    # returns True if connected to MQTT or websocket server
    def connected(self):
        return (self._web_socket is not None) or (self._client and self._client_connected)

    # send a generic message to the server
    def send(self, message_type, parameters, channel=None, folder=None, prepend=False):
        if self._client:  # MQTT messages
            if folder:
                path = folder
            else:
                path = self._controller.path_on_server()
            topic = path.lstrip('/')  # rhizo paths start with slash (to distinguish absolute vs relative paths) while MQTT topics don't
            message = json.dumps({message_type: parameters})
            self._client.publish(topic, message)
            # print('MQTT send: %s, %s' % (topic, message))
        else:  # old-style websocket messages
            message_struct = {
                'type': message_type,
                'parameters': parameters
            }
            if folder:
                message_struct['folder'] = folder
            if channel:
                message_struct['channel'] = channel
            self.send_message_struct_to_server(message_struct, prepend)

    def send_simple(self, path, message):
        if self._client:
            topic = path.lstrip('/')  # rhizo paths start with slash (to distinguish absolute vs relative paths) while MQTT topics don't
            self._client.publish(topic, message)
            # print('MQTT send: %s, %s' % (topic, message))

    # send an email (to up to five addresses)
    def send_email(self, email_addresses, subject, body):
        self.send('send_email', {
            'emailAddresses': email_addresses,
            'subject': subject,
            'body': body,
        })

    # send a text message (to up to five phone numbers)
    def send_sms(self, phone_numbers, message):
        self.send('send_text_message', {
            'phoneNumbers': phone_numbers,
            'message': message,
        })

    # add a custom handler for messages from server
    def add_handler(self, message_handler):
        self._message_handlers.append(message_handler)

    # ======== internal functions ========

    # initiate a websocket connection with the server
    def connect_web_socket(self):
        config = self._controller.config
        if 'secure_server' in config:
            secure_server = config.secure_server
        else:
            host_name = config.server_name.split(':')[0]
            secure_server = host_name != 'localhost' and host_name != '127.0.0.1'
        protocol = 'wss' if secure_server else 'ws'
        if config.get('old_auth', False):
            headers = None
        else:
            user_name = self._controller.VERSION + '.' + self._controller.BUILD  # send client version as user name
            password = config.secret_key  # send secret key as password
            headers = [('Authorization', 'Basic %s' % base64.b64encode(('%s:%s' % (user_name, password)).encode()).decode())]
        ws = WebSocketClient(protocol + '://' + config.server_name + '/api/v1/websocket', protocols=['http-only'], headers=headers)
        try:
            ws.connect()
            logging.debug('opened websocket connection to server')
        except Exception as e:
            logging.debug(str(e))
            logging.warning('error connecting to websocket server')
            ws = None
        return ws

    # handle an incoming message from the websocket
    def process_incoming_message(self, message):
        message_type = None
        parameters = None
        if str(message)[0] == '{':
            message_struct = json.loads(str(message))
            if 'type' in message_struct:
                message_type = message_struct['type']
                parameters = message_struct['parameters']
            else:
                for k, v in message_struct.items():
                    message_type = k
                    parameters = v
                    break
        else:
            message_type, parameters = message.split(',', 1)  # note: in this case, parameters is a string not dictionary
        if message_type:
            response_message = None
            if message_type == 'get_config' or message_type == 'getConfig':
                response_message = self.config_message(parameters['names'].split(','))
            elif message_type == 'set_config' or message_type == 'setConfig':
                self.set_config(parameters)
            else:
                message_used = False
                if not message_used and self._message_handlers:
                    for handler in self._message_handlers:
                        if hasattr(handler, 'handle_message'):
                            handler.handle_message(message_type, parameters)
                        else:
                            handler(message_type, parameters)
            if response_message:
                self.send_message_struct_to_server(response_message)

    # send a websocket message to the server
    def send_message_struct_to_server(self, message_struct, prepend=False, timestamp=None):
        timestamp = datetime.datetime.utcnow()
        if prepend:
            self._outgoing_messages = [(timestamp, message_struct)] + self._outgoing_messages
        else:
            self._outgoing_messages.append((timestamp, message_struct))

    # send a websocket message to the server subscribing to messages intended for this controller
    # note: these messages are prepended to the queue, so that we're authenticated for everything else in the queue
    def send_init_socket_messages(self):
        config = self._controller.config
        params = {
            'authCode': util.build_auth_code(config.secret_key),
            'version': self._controller.VERSION + ':' + self._controller.BUILD
        }
        if 'name' in config:
            params['name'] = config.name
        self.send('subscribe', {
            'subscriptions': [  # note: this subscription listens to all message types
                {
                    'folder': 'self',
                    'include_children': config.get('subscribe_children', False),
                }
            ]
        }, prepend=True)
        if config.get('old_auth', False):
            self.send('connect', params, prepend=True)  # add to queue after subscribe so send before; fix(soon): revisit this
        logging.info('controller connected/re-connected')

    # get a configuration setting as a message
    def config_message(self, names):
        return {
            'type': 'config',
            'parameters': {name: self._controller.config.get(name, '') for name in names},
        }

    # update the config file using a dictionary of config entries
    # fix(soon): this is out of date (doesn't fit current config file format); rework it or remove it
    def set_config(self, params):
        output_lines = []
        input_file = open(self._controller._config_relative_file_name)
        for line in input_file:
            parts = line.split()
            if parts and parts[0] in params:
                line = '%s %s\n' % (parts[0], params[parts[0]])
                output_lines.append(line)
            else:
                output_lines.append(line)
        input_file.close()
        output_file = open(self._controller._config_relative_file_name, 'w')
        for line in output_lines:
            output_file.write(line)
        output_file.close()
        self._controller.load_config()
        self._controller.show_config()

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
                        self.process_incoming_message(message)
                    else:
                        logging.warning('disconnected (on received); reconnecting...')
                        self._web_socket = None
                        gevent.sleep(10)  # avoid fast reconnects
                gevent.sleep(0.1)
            except Exception as e:
                self._controller.error('error in web socket message listener/handler', exception = e)
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
                self.send('ping', {})
