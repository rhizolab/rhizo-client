# this will initialize the controller and start the greenlets
from rhizo.main import c

# this will wait for the user to terminate the program
c.wait_for_termination()
