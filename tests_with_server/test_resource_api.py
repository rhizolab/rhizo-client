import json
from rhizo.config import load_config
from rhizo.extensions.resources import ResourceClient


# test create, update, read, delete folder resource
def test_folder():
    config = load_config('local.yaml')
    resource_client = ResourceClient(config)


# test create, update, read, delete node resource
def test_node():
    pass


# test create, update, read, delete sequence resource
def test_sequence():
    pass


# test create, update, read, delete app link resource
def test_app_link():
    pass


# test create, update, read, delete remote folder resource
def test_remote_folder():
    pass
