# create a single global instance of the controller; this instance can be imported into user scripts
from rhizo.controller import Controller
c = Controller()

print('**** this module is deprecated; create a Controller instance directly ****')
