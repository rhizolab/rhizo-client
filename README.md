rhizo
=====

## Installation

Install dependencies:

    pip install -r requirements.txt

Note: some extensions may have additional dependencies (e.g., pyserial, pillow). To install the dependencies for the built-in extensions, run

    pip install -r rhizo/extensions/requirements.txt

Add the `rhizo` folder to your `PYTHONPATH`.

## Controller

The controller handles core functionality: server communication, logging, and running scripts.

## Extensions

Extension objects are used to implement additional functionality. These objects are stored inside the controller 
(and maintain their own reference to the controller).

## Configuration

The rhizo controller reads a `config.yaml` file and optionally `local.yaml` file in the current directory.
Typically the `config.yaml` file can be stored in version control while `local.yaml` contains system-specific
settings and items such as secret keys that should not be in version control. Entries in the `local.yaml` file
override settings in `config.yaml`.

Alternately, config values can be set in environment variables. The variables should be upper-case forms of the config keys with a prefix of `RHIZO_`. For example, `RHIZO_SERVER_NAME` for the `server_name` setting.

The values are parsed as YAML to allow structured values to be specified in the environment. (JSON is valid YAML, so you can use JSON format too.) One specific gotcha to be cautious of is that strings containing colons will need to be enclosed in quotation marks or they'll be interpreted as a key/value pair.

    export RHIZO_SERVER_NAME='"localhost:5000"'

## Tests

There are two test directories. `tests` contains standalone tests and `tests_with_server` has tests that require a running rhizo-server instance.

To run the standalone tests, first install the test dependencies (you only need to do this once):

    pip install -r tests/requirements.txt

Then run `pytest tests`.

To run the server-based tests, create `tests_with_server/local.yaml` with your server settings and execute the test files directly (that is, don't run them under pytest). Make sure your `PYTHONPATH` is set correctly to find the library!
