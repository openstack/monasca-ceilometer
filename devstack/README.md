# Installing Ceilosca using automated methods

There are a few options for configuring Ceilosca on top of a Ceilometer and Monasca deployment.

Choose one:
- DevStack can be instructed through the local.conf to "enable ceilosca".  Reference the included devstack/sample-local.conf for one configuration.

- Use the included Vagrantfile to create and provision a VM.  This will provision a new Ubuntu 16.04 VM and run the ceilosca.sh.

- Under certain conditions the monasca_test_setup.py may be used to set up Ceilosca for testing.  This .py may also be useful reference if you choose to write your own integration scripts.

- The devstack/ceilosca.sh script will copy Ceilosca components on top of Ceilometer.
  - ceilosca.sh has been updated to the Newton release.
  - ceilosca.sh is also used by the Vagrant deployment option.
  - The script should be tweaked before execution, particularly the lines.
    - export SERVICE_HOST=192.168.10.6
    - export HOST_IP_IFACE=eth0
  - The script should be run by a sudoers user with no password required.  Such as is described in https://docs.openstack.org/devstack/latest/
  - And did not configure Horizon
