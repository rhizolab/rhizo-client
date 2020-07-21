class SequenceManager(object):

    def __init__(self, controller):
        self._controller = controller
        self._values = {}

    def update(self, relative_sequence_path, value):
        self._values[relative_sequence_path] = value

    def value(self, relative_sequence_path):
        return self._values.get(relative_sequence_path)
