from collections import defaultdict


data_types = {'numeric': 1, 'text': 2, 'image': 3}


class SequenceManager(object):

    def __init__(self, controller):
        self._controller = controller
        self._values = {}
        self._timestamps = {}
        self._exists_on_server = defaultdict(bool)

    def update(self, relative_sequence_path, value, timestamp=None):
        self._values[relative_sequence_path] = value
        self._timestamps[relative_sequence_path] = timestamp

    def create(self, relative_sequence_path, data_type, decimal_places=None, units=None):
        if self._exists_on_server[relative_sequence_path] == False:
            c = self._controller
            full_seq_path = c.path_on_server() + '/' + relative_sequence_path
            if not c.resources.file_exists(full_seq_path):
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
                c.resources.send_request_to_server('POST', '/api/v1/resources', sequence_info)
            self._exists_on_server[relative_sequence_path] = True

    def value(self, relative_sequence_path):
        return self._values.get(relative_sequence_path)
