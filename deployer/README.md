**The scripts setup a devstack, monasca and ceilosca setup on the local machine**

#Few gotchas:

- Monasca-ui doesn't get setup with this since it has some compatibilty issues with stable/kilo
- Monasca-events doesn't get installed either, as it is attempting to install oslo at system level causing issues with devstack
- One of the monasca smoke test fails, but it is at the end and shouldn't affect the operation of ceilosca

#Pre-Requisites:

- Please make sure that the hostname does not contains hyphens (-) otherwise the creation of root under Percona cluster will fail.

#Running:

- By default uses the current user for setting devstack and monasca, make sure the user has sudo privileges
- If you are running this script behind a proxy, make sure current host-ip is added to no_proxy

1. `git clone https://git.openstack.org/openstack/monasca-ceilometer`
2. `cd monasca-ceilometer`
3. `deployer/ceilosca.sh`

#Re-Running:

If for any reason you need to re-run the ceilosca script please make sure that:

1. MySql and Percona are removed using this command:

`sudo apt-get purge mysql* percona*`


#Using the Clients

##Ceilometer Client

To run the Ceilometer client make sure to have the right OS_ environment variable set.
You can do this running the following command from the devstack folder:

`source openrc admin`

##Monasca Client

To run the Monasca client make sure to have the right OS_ environment variable set.
You can do this running the following command from the monasca-vagrant folder:

`source env.sh`

