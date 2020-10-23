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

The rhizo controller reads a `config.hjson` file and optionally `local.hjson` file in the current directory.
Typically the `config.hjson` file can be stored in version control while `local.hjson` contains system-specific
settings and items such as secret keys that should not be in version control. Entries in the `local.hjson` file
override settings in `config.hjson`.

## Tests

There are two test directories. `tests` contains standalone tests and `tests_with_server` has tests that require a running rhizo-server instance.

To run the standalone tests, first install the test dependencies (you only need to do this once):

    pip install -r tests/requirements.txt

Then run `pytest tests`.

To run the server-based tests, create `tests_with_server/local.hjson` with your server settings and execute the test files directly (that is, don't run them under pytest). Make sure your `PYTHONPATH` is set correctly to find the library!
