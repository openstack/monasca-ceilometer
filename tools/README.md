ceilosca message simulator
========

This is a message generator simulator cloned from oslo.messaging

### Installation Instructions

1.  Create a virtual environment where to run the simulator.

     virtualenv simulator

2.  Activate the virtual environment.

     source simulator/bin/activate

3.  Install oslo.message

     pip install oslo.messaging

4.  Run the simulator

    python ceilosca-message-simulator.py --url rabbit://stackrabbit:password@localhost notify-client -m 1 -s nova -a create

Note: The simulator has three main parameters:

-m number of message to be published

-s service. Currently nova, cinder and glance are supported.

-a action. Currently create and delete are supported.