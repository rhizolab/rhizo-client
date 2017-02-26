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
