import json
import logging
import datetime
import gevent
from collections import defaultdict


data_types = {'numeric': 1, 'text': 2, 'image': 3}


class SequenceClient(object):

    def __init__(self, controller):
        self._controller = controller
        self._values = {}
        self._timestamps = {}
        self._exists_on_server = defaultdict(bool)
        self._local_seq_files = {}

    # fix(soon): merge with update() function below
    def update_value(self, relative_sequence_path, value, timestamp=None):
        self._values[relative_sequence_path] = value
        self._timestamps[relative_sequence_path] = timestamp

    def create(self, relative_sequence_path, data_type, decimal_places=None, units=None):
        if self._exists_on_server[relative_sequence_path] == False:
            c = self._controller
            full_seq_path = c.path_on_server() + '/' + relative_sequence_path
            if not c.files.file_exists(full_seq_path):
                data_type_num = data_types[data_type]
                parts = full_seq_path.rsplit('/', 1)
                path = parts[0]
                name = parts[1]
                sequence_info = {
                    'path': path,
                    'name': name,
                    'type': 21,  # sequence
                    'data_type': data_type_num,
                    'min_storage_interval': 20,  # fix(soon): make this an argument? or make it a controller/org-level setting?
                }
                if not decimal_places is None:
                    sequence_info['decimal_places'] = decimal_places
                if units:
                    sequence_info['units'] = units
                c.files.send_request_to_server('POST', '/api/v1/resources', sequence_info)
            self._exists_on_server[relative_sequence_path] = True

    def value(self, relative_sequence_path):
        return self._values.get(relative_sequence_path)

    # send a new sequence value to the server
    def update(self, sequence_name, value, use_websocket=True):
        if self._controller.config.get('enable_server', True):
            if use_websocket:
                if self._controller.config.get('mqtt_host'):
                    timestamp = datetime.datetime.utcnow()
                    if sequence_name.startswith('/'):
                        full_path = sequence_name
                    else:
                        full_path = self._controller.path_on_server() + '/' + sequence_name
                    (path, rel_name) = full_path.rsplit('/', 1)
                    message = 's,%s,%s Z,%s' % (rel_name, timestamp.isoformat(), value)
                    self._controller.messages.send_simple(path, message)  # expects absolute path
                else:
                    self._controller.messages.send('update_sequence', {'sequence': sequence_name, 'value': value})
            else:  # note that this case currently requires an absolute path on the server
                value = str(value)  # write_file currently expects string values
                i = 0
                while True:  # repeat until verified that value is written
                    self._controller.files.write_file(sequence_name, value)
                    server_value = self._controller.files.read_file(sequence_name).decode()
                    if value == server_value:
                        break
                    i += 1
                    if i == 10:
                        logging.warning('unable to verify sequence update; retrying...')
                    gevent.sleep(0.5)
        if self._controller.config.get('enable_local_sequence_storage', False):
            self.store_local_sequence_value(sequence_name, value)

    # update multiple sequences; timestamp must be UTC (or None)
    # values should be a dictionary of sequence values by path (for now assuming absolute sequence paths)
    def update_multiple(self, values, timestamp=None, use_message=False):
        if not timestamp:
            timestamp = datetime.datetime.utcnow()
        controller_path = self._controller.path_on_server()
        if use_message:  # send a new-style multi-sequence update message 
            params = {'$t': timestamp.isoformat() + ' Z'}
            path_len = len(controller_path)
            for name, value in values.items():
                if name.startswith('/'):  # make sure all paths are relative
                    assert name.startswith(controller_path)
                    rel_name = name[path_len+1:]
                else:
                    rel_name = name
                params[rel_name] = str(value)  # make sure all values are strings
            self._controller.messages.send('update', params)
        else:  # update via REST API
            send_values = {}
            for name, value in values.items():
                if not name.startswith('/'):  # make sure all paths are absolute
                    name = controller_path + '/' + name
                send_values[name] = str(value)  # make sure all values are strings
            params = {
                'values': json.dumps(send_values),
                'timestamp': timestamp.isoformat() + ' Z',
            }
            self._controller.files.send_request_to_server('PUT', '/api/v1/resources', params)

    # stores a sequence value in a local log file (an alternative to sending the value to the server)
    def store_local_sequence_value(self, sequence_name, value):
        if sequence_name not in self._local_seq_files:
            self._local_seq_files[sequence_name] = open('log/%s.csv', sequence_name, 'a')
        self._local_seq_files[sequence_name].write('%.3f,%.3f\n' % (time.time(), value))  # fix(soon): better timestamps, decimal places
