**The scripts setup a devstack, monasca and ceilosca setup on the local machine**

Few gotchas:

- Monasca-ui doesn't get setup with this since it has some compatibilty issues with stable/kilo
- Monasca-events doesn't get installed either, as it is attempting to install oslo at system level causing issues with devstack
- One of the monasca smoke test fails, but it is at the end and shouldn't affect the operation of ceilosca

Running:

- By default uses the current user for setting devstack and monasca, make sure the user has sudo privileges
- If you are running this script behind a proxy, make sure current host-ip is added to no_proxy

1. git clone https://github.com/stackforge/monasca-ceilometer
2. cd monasca-ceilometer
3. deployer/ceilosca.sh
