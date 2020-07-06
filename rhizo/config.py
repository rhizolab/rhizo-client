import json
import logging  # fix(clean): remove this after remove item_as_list
import hjson
from . import util


## The Config class represents the contents of a configuration file.
class Config(dict):

    # create a config object with the given entries (stored in a dictionary)
    def __init__(self, entries = None):  # can't default entries to {} since that would be shared between multiple configs
        dict.__init__(self)
        if entries:
            for (key, value) in entries.items():
                if True:
                    if isinstance(value, dict) and not isinstance(value, Config):
                        self[key] = Config(value)
                    else:
                        self[key] = value
                else:  # auto config conversion
                    if '_' in key:
                        alt_key = underscores_to_camel(key)  # temp for migration
                    else:
                        alt_key = camel_to_underscores(key)  # temp for migration
                    if isinstance(value, dict) and not isinstance(value, Config):
                        self[key] = Config(value)
                        if alt_key != key:  # temp for migration
                            self[alt_key] = Config(value)
                    else:
                        self[key] = value
                        if alt_key != key:  # temp for migration
                            self[alt_key] = value

    # for . operator; returns the given config entry using config.name syntax
    def __getattr__(self, name):
        if name not in self:
            raise ConfigEntryNotFound(name)
        return self[name]

    # retrieve an item as a list
    def item_as_list(self, name, default = '[noDefault]'):
        if default == '[noDefault]':
            return as_list(self[name])
        else:
            if name in self:
                return as_list(self[name])
            else:
                return default

    # add/overwrite entries with entries from another config
    def update(self, config):
        for (key, new_value) in config.items():
            if key in self and isinstance(new_value, Config) and isinstance(self[key], Config):
                self[key].update(new_value)
            else:
                self[key] = new_value

    # set the value of a config entry
    def set(self, name, value):
        self[name] = value


# load a configuration file (either space-delimited simple text format or .json file)
def load_config(config_file_name):
    config_dict = {}
    if config_file_name.endswith('.json'):
        input_file = open(config_file_name)
        config_dict = json.loads(input_file.read())
    elif config_file_name.endswith('.hjson'):
        input_file = open(config_file_name)
        config_dict = hjson.loads(input_file.read())
    else:
        input_file = open(config_file_name)
        for line in input_file:
            hash_pos = line.find('  #')
            if hash_pos >= 0:
                line = line[:hash_pos].strip()
            parts = line.split(None, 1)
            if parts:

                # get the name and value
                name = parts[0]
                value = parts[1].strip() if len(parts) >= 2 else ''

                # convert value from string to basic python type
                value = util.convert_value(value)

                # add to sub-config
                # fix(later): support sub-sub-configs by moving this code into config.set() and making it recursive
                dot_pos = name.find('.')
                if dot_pos > 0:
                    prefix = name[:dot_pos].strip()
                    if prefix in config_dict:
                        sub_config = config_dict[prefix]  # fix(soon): verify that this is a dict
                    else:
                        sub_config = Config()
                        config_dict[prefix] = sub_config
                    sub_config.set(name[dot_pos + 1:], value)
                    config_dict[name] = value  # for now, let's also add to top-level config so that existing code continues to work

                # or add to main config
                else:
                    config_dict[name] = value
    return Config(config_dict)


# convert a string value into a list of basic python objects (strings or numbers)
def as_list(value):
    if hasattr(value, 'split'):
        values = value.split(',')
        return [util.convert_value(v.strip()) for v in values]
    else:
        return value


# temp function to help with config migration to underscores
def camel_to_underscores(name):
    result = ''
    for c in name:
        if c.isupper():
            result += '_'
            c = c.lower()
        result += c
    return result


# temp function to help with config migration to underscores
def underscores_to_camel(name):
    parts = name.split('_')
    return parts[0] + ''.join([p.title() for p in parts[1:]])


# an exception that is raised when attempting to access an undefined configuration entry
class ConfigEntryNotFound(AttributeError):

    def __init__(self, name):
        self.name = name

    def __str__(self):
        return 'Config entry (%s) not found' % self.name
