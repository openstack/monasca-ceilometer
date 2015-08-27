**The scripts setup a devstack, monasca and ceilosca setup on the local machine**

Few gotchas:

- Monasca-ui doesn't get setup with this since it has some compatibilty issues with stable/kilo
- One of the monasca smoke test fails, but it is at the end and shouldn't affect the operation of ceilosca

Running:

1. git clone https://github.com/stackforge/monasca-ceilometer
2. cd monasca-ceilometer
4. deployer/ceilosca.sh
