# Installing Ceilosca using automated methods

There are a few options for configuring Ceilosca on top of a Ceilometer and Monasca deployment.

Choose one:
- DevStack can be instructed through the local.conf to "enable ceilosca".  Reference the included
  devstack/sample-local.conf for one example configuration.

- Use the included Vagrantfile to create and provision a VM.  This will provision a new Ubuntu 16.04 VM and run the
  ceilosca.sh.

- Under certain conditions the monasca_test_setup.py may be used to set up Ceilosca for testing.  This .py may also be
  useful reference if you choose to write your own integration scripts.

- The devstack/ceilosca.sh script will copy Ceilosca components on top of Ceilometer.
  - ceilosca.sh has been updated to the Newton release.
  - ceilosca.sh is also used by the Vagrant deployment option.
  - The script should be tweaked before execution, particularly the lines.
    - export SERVICE_HOST=192.168.10.6
    - export HOST_IP_IFACE=eth0
  - The script should be run by a sudoers user with no password required.  Such as is described in
    https://docs.openstack.org/devstack/latest/
  - And note ceilosca.sh does not configure Horizon

# Testing notes

Once Ceilosca is installed the gathered metrics will appear in Monasca.  The `monasca` cli can be used to verify
functionality.

- Source a valid rc file to set the OS_ environment variables needed for the cli.  For example:
```
export OS_PROJECT_NAME=mini-mon
export OS_IDENTITY_API_VERSION=3
export OS_PASSWORD=<the password>
export OS_AUTH_URL=http://<Your Keystone IP>/identity/v3/
export OS_USERNAME=mini-mon
```
- Run `monasca metric-list`
  - Devstack includes a cirros 3.5 image by default.  This will be represented in an `image.size` metric in monasca
    with a datasource of `ceilometer`.
- Cause further metrics to be created by doing more OpenStack operations.
  - Create another image
    - wget -c http://download.cirros-cloud.net/0.4.0/cirros-0.4.0-x86_64-disk.img -o cirros-0.4.0-x86_64-disk.img
    - openstack image create --disk-format qcow2 --container-format bare cirros-0.4.0 < cirros-0.4.0-x86_64-disk.img
  - Create a simple vm
    - openstack image list
    - Choose one of the images listed, note its id
    - openstack flavor list
    - Choose one of the flavors, note its id
    - openstack project list
    - openstack security group list
    - Pick the group that matches the `admin` project, note its id
    - openstack security group rule create --proto tcp --dst-port 22 <security group id>
    - openstack server create --flavor <flavor id> --image <image id> --security-group <security group id> mytest
    - Check the progress with `openstack server list`
  - Look for additional metrics with `datasource: ceilometer` in `monasca metric-list`
- Explore the samples (aka. measurements) in `monasca measurement-list image.size -120` and similar commands.
