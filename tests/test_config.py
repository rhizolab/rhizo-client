import py.test
from rhizo.config import load_config


def check_config(config):
    assert config.output_path == '/foo/bar'
    assert config.sub_config.a == 'test'
    assert config.sub_config.b == 2
    assert round(config.sub_config.c - 3.14, 4) == 0


def test_text_config():
    config = load_config('test_data/sample_config.txt')
    check_config(config)


def test_json_config():
    config = load_config('test_data/sample_config.json')
    check_config(config)


def test_hjson_config():
    config = load_config('test_data/sample_config.hjson')
    check_config(config)


def test_config_update():
    config = load_config('test_data/sample_config.hjson')
    config.update(load_config('test_data/update.hjson'))
    assert config.output_path == '/foo/test'
    assert config.sub_config.a == 'test'
    assert config.sub_config.b == 3


if __name__ == '__main__':
    test_test()
