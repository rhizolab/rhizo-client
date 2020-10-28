import os
from pathlib import Path

from rhizo.config import load_config


def check_config(config):
    assert config.output_path == '/foo/bar'
    assert config.sub_config.a == 'test'
    assert config.sub_config.b == 2
    assert round(config.sub_config.c - 3.14, 4) == 0


def _load_test_config(filename, use_environ=False):
    """Load a config file from the test_data subdirectory."""
    path = Path(__file__).parent / 'test_data' / filename
    return load_config(str(path), use_environ)


def test_environment_config():
    os.environ['RHIZO_SUB_CONFIG'] = 'a: override\nb: 3'
    os.environ['RHIZO_OTHER_SETTING'] = 'from_env'
    config = _load_test_config('sample_config.json', True)

    # Not overridden in environment
    assert config.output_path == '/foo/bar'
    # Overridden in environment; dict value in environment
    assert config.sub_config == { "a": "override", "b": 3 }
    # Only specified in environment
    assert config.other_setting == 'from_env'


def test_json_config():
    # Make sure environment override only happens if requested
    os.environ['RHIZO_OUTPUT_PATH'] = 'overridden'
    config = _load_test_config('sample_config.json')
    check_config(config)


def test_yaml_config():
    config = _load_test_config('sample_config.yaml')
    check_config(config)


def test_get_with_default():
    config = _load_test_config('sample_config.yaml')
    assert config.get('nonexistent') is None
    assert config.get('nonexistent', 'value') == 'value'
    assert config.get('nonexistent', []) == []


def test_config_update():
    config = _load_test_config('sample_config.yaml')
    config.update(_load_test_config('update.yaml'))
    assert config.output_path == '/foo/test'
    assert config.sub_config.a == 'test'
    assert config.sub_config.b == 3
