## Stress Testing Notes

This code takes two approaches:

1. one controller, many connections (`one_controller.py`); simple because it uses one config and one secret key

2. many controllers, each with one connection (`many_controllers.py`); a better match for real usage; complex because it uses separate configs and keys

### Many Controllers

In the many controllers case, each controller gets its own local folder containing its own local config.

The controller launcher script has it's own local config that is used to provision the other controllers on the server. This local config 
needs to have a user-associated key (rather than a controller associated key) so that it can create keys for each controller. (Currently
only users are allowed to create new keys, not controllers.)
