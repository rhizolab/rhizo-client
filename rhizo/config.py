import os
import yaml

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


def load_config(config_file_name, use_environ=True):
    """Load a YAML or JSON configuration file.

    If use_environ is True, values from the config file will be overridden by values from
    environment variables whose names start with RHIZO_, e.g., RHIZO_SERVER_NAME will set
    the server_name config value. Environment variable values are always parsed as YAML.
    """
    with open(config_file_name) as input_file:
        config_dict = yaml.load(input_file, yaml.Loader)

    # allow settings to be supplied or overridden with environment variables
    if use_environ:
        prefix = 'RHIZO_'
        for (name, value) in os.environ.items():
            if name[:len(prefix)] == prefix:
                config_dict[name[len(prefix):].lower()] = yaml.load(value, yaml.Loader)

    return Config(config_dict)


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
