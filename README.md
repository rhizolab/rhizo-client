rhizo-client
============

This is a client library for communicating with [rhizo-server](https://github.com/rhizolab/rhizo-server).

## Installation

For ordinary usage, the library may be installed using pip (`pip install rhizo-client`).

To work on the library itself, install it in editable mode (`pip install -e .`) which will install the required dependencies.

To use a local copy of the library in a different project, install it in editable mode.

    cd /path/to/other/project
    pip install -e /path/to/rhizo-client

## Configuration

The rhizo controller reads a `config.yaml` file and optionally `local.yaml` file in the current directory.
Typically the `config.yaml` file can be stored in version control while `local.yaml` contains system-specific
settings and items such as secret keys that should not be in version control. Entries in the `local.yaml` file
override settings in `config.yaml`.

A minimal sample configuration file (`sample_config.yaml`) is included in the distribution.

Alternately, config values can be set in environment variables. The variables should be upper-case forms of the config keys with a prefix of `RHIZO_`. For example, `RHIZO_SERVER_NAME` for the `server_name` setting.

The values are parsed as YAML to allow structured values to be specified in the environment. (JSON is valid YAML, so you can use JSON format too.) One specific gotcha to be cautious of is that strings containing colons will need to be enclosed in quotation marks or they'll be interpreted as a key/value pair.

    export RHIZO_SERVER_NAME='"localhost:5000"'

## Tests

There are two test directories: `tests` contains standalone tests and `tests_with_server` has tests that require a running rhizo-server instance.

To run the standalone tests, first install the test dependencies (you only need to do this once):

    pip install -r tests/requirements.txt

Then run `pytest tests`.

To run the server-based tests, create `tests_with_server/local.yaml` with your server settings and run `pytest` from the `tests_with_server` directory.
(Note: currently this requires some steps to be completed on the server; we'll work on streamlining/documenting this.)

## Packaging

To build a package for public release, follow [the usual procedure](https://packaging.python.org/guides/distributing-packages-using-setuptools/#packaging-your-project):

    pip install wheel
    python setup.py bdist_wheel

The project is configured to build as a universal wheel since it supports both Python 2 and Python 3 and does not include compiled extensions.

To upload new releases to PyPI, see [the Python packaging documentation](https://packaging.python.org/guides/distributing-packages-using-setuptools/#uploading-your-project-to-pypi).
