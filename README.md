rhizo
=====

## Installation

Install dependencies:

    pip install gevent
    pip install ws4py
    pip install hjson

Note: some extensions may have additional dependencies (e.g., pyserial, pillow).

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