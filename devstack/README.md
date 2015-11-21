# Setting up ceilosca solution

Setup ceilosca solution with following steps

- wget https://raw.githubusercontent.com/openstack/monasca-ceilometer/master/devstack/ceilosca.sh
- chmod +x ceilosca.sh
  - (Optional) check ceilosca.sh to tweak and modify if you require any changes from default behaviour
- ./ceilosca.sh

# Few things to take note

- The user running the script should be part of sudoers with no password
- Like devstack this setup adds the packages and modifies at system level

# What's missing

Horizon isn't being setup since it is causing issue which require further investigation

# Vagrant approved!

Use the provided Vagrantfile to create and provision a VM.