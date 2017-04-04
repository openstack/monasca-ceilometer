# Installing Ceilosca using automated methods

There are a few options for configuring Ceilosca on top of a Ceilometer and Monasca deployment.

Choose one:
- DevStack can be instructed through the local.conf to "enable ceilosca".  Reference the included devstack/sample-local.conf for one configuration.

- Use the included Vagrantfile to create and provision a VM.

- Under certain conditions the monasca_test_setup.py may be used to set up Ceilosca for testing.  This .py may also be useful reference if you choose to write your own integration scripts.

- (Deprecated) the devstack/ceilosca.sh script will copy Ceilosca components on top of Ceilometer.
  - ceilosca.sh is left as reference, but has not been updated for the Newton release.
  - The script should be tweaked before execution, particularly the lines.
    - export SERVICE_HOST=192.168.10.6
    - export HOST_IP_IFACE=eth0
  - The script was run by a sudoers user with no password.
  - And did not configure Horizon
