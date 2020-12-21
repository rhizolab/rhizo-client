import json
import logging
import datetime
import gevent
from collections import defaultdict
from itertools import groupby


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

    def create(self, seq_path, data_type, decimal_places=None, units=None, min_storage_interval=None, max_history=None):
        c = self._controller
        if not seq_path.startswith('/'):
            seq_path = c.path_on_server() + '/' + seq_path
        if not self._exists_on_server[seq_path]:
            if not c.files.file_exists(seq_path):
                data_type_num = data_types[data_type]
                parts = seq_path.rsplit('/', 1)
                path = parts[0]
                name = parts[1]
                if min_storage_interval is None:
                    min_storage_interval = 20
                sequence_info = {
                    'path': path,
                    'name': name,
                    'type': 21,  # sequence
                    'data_type': data_type_num,
                    'min_storage_interval': min_storage_interval,
                }
                if not decimal_places is None:
                    sequence_info['decimal_places'] = decimal_places
                if not max_history is None:
                    sequence_info['max_history'] = max_history
                if units:
                    sequence_info['units'] = units
                c.files.send_request_to_server('POST', '/api/v1/resources', sequence_info)
            self._exists_on_server[seq_path] = True

    def value(self, relative_sequence_path):
        return self._values.get(relative_sequence_path)

    # send a new sequence value to the server
    def update(self, sequence_name, value, use_websocket=True):
        if self._controller.config.get('enable_server', True):
            if sequence_name.startswith('/'):
                full_path = sequence_name
            else:
                full_path = self._controller.path_on_server() + '/' + sequence_name
            if use_websocket:
                if self._controller.config.get('mqtt_host'):
                    timestamp = datetime.datetime.utcnow()
                    (path, rel_name) = full_path.rsplit('/', 1)
                    message = 's,%s,%s Z,%s' % (rel_name, timestamp.isoformat(), value)
                    self._controller.messages.send_simple(path, message)  # expects absolute path
                else:
                    self._controller.messages.send('update_sequence', {'sequence': sequence_name, 'value': value})
            else:  # note that this case currently requires an absolute path on the server
                value = str(value)  # write_file currently expects string values
                i = 0
                while True:  # repeat until verified that value is written; note: this isn't really needed since lower level code will retry if error
                    self._controller.files.write_file(full_path, value)
                    server_value = self._controller.files.read_file(full_path).decode()
                    if value == server_value:
                        break
                    i += 1
                    if i == 10:
                        logging.warning('unable to verify sequence update; retrying...')
                    gevent.sleep(0.5)
        if self._controller.config.get('enable_local_sequence_storage', False):
            self.store_local_sequence_value(sequence_name, value)

    # update multiple sequences; timestamp must be UTC (or None)
    # values should be a dictionary of sequence values by path (relative or absolute)
    def update_multiple(self, values, timestamp=None, use_message=True):
        if not timestamp:
            timestamp = datetime.datetime.utcnow()

        # make sure all paths are absolute and all values are strings
        controller_path = self._controller.path_on_server()
        send_values = {}
        for name, value in values.items():
            if not name.startswith('/'):
                name = controller_path + '/' + name
            send_values[name] = str(value)

        # send a new-style multi-sequence update message, one message per folder
        if use_message:
            all_paths = sorted(list(send_values.keys()))
            for folder, paths in groupby(all_paths, lambda path: path.rsplit('/', 1)[0]):
                params = {'$t': timestamp.isoformat() + ' Z'}
                for path in paths:
                    rel_path = path.rsplit('/', 1)[1]
                    params[rel_path] = send_values[path]
                self._controller.messages.send('update', params, folder=folder)

        # update via REST API
        else:
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
