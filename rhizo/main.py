# update standard libraries to use gevent
import gevent
from gevent import monkey
monkey.patch_all()

# create a single global instance of the controller; this instance can be imported into user scripts
from controller import Controller
c = Controller()
