ceilosca message simulator
========

This is a message generator simulator cloned from oslo.messaging

# Installation Instructions

1.  Create a virtual environment where to run the simulator.

     ```
     virtualenv simulator
     ```

2.  Activate the virtual environment.

     ```
     source simulator/bin/activate
     ```

3.  Install oslo.message

     ```
     pip install oslo.messaging==3.0.0
     ```

4.  Run the simulator

    ```
    python ceilosca-message-simulator.py --url rabbit://stackrabbit:password@localhost notify-client -m 1 -s nova -a create -x tenant_id -r resource_id -d load_date
    ```

Note: The simulator has three main parameters:

-m number of message to be published

-s service. Currently nova, cinder and glance are supported.

-a action. Currently create and delete are supported.

-x tenant. Defines the tenant_id you want to use to assign the load.

-r resource. Defines the resource_id you want to use to assign the load

-d load_date. Defines the load date so then you can create load for a specific date.

# Testing in a DevStack constrained environment with high load

Testing the system in a devstack environment is challenging when you want to go above
millions of messages. For this reason we came up with a set of steps that simplify
and allow stretching the envelope to achieve the required load.

The Public and Private simulation scripts are generating 7.5M. In order to successfully
load the devstack with these amounts these are the recommended steps.

Memory change for monasca-api, monasca-persister, and remove keystone auth for ceilometer-api:

## Increase memory for the monasca-api

```
sudo vim /etc/init/monasca-api.conf
```

Change:

```
exec /usr/bin/java -Dfile.encoding=UTF-8 –Xmx1g -cp /opt/monasca/monasca-api.jar:/opt/monasca/vertica/vertica_jdbc.jar monasca.api.MonApiApplication server /etc/monasca/api-config.yml
```

To:

```
exec /usr/bin/java -Dfile.encoding=UTF-8 -Xmx4g -cp /opt/monasca/monasca-api.jar:/opt/monasca/vertica/vertica_jdbc.jar monasca.api.MonApiApplication server /etc/monasca/api-config.yml
```

Then re-start the Monasca API service

```
sudo service monasca-api restart
```

## Increase memory for the monasca-persister

```
sudo vim /etc/init/monasca-persister.conf
```

Change:

```
exec /usr/bin/java -Dfile.encoding=UTF-8 –Xmx1g -cp /opt/monasca/monasca-persister.jar:/opt/monasca/vertica/vertica_jdbc.jar monasca.persister.PersisterApplication server /etc/monasca/persister-config.yml
```

To:

```
exec /usr/bin/java -Dfile.encoding=UTF-8 -Xmx4g -cp /opt/monasca/monasca-persister.jar:/opt/monasca/vertica/vertica_jdbc.jar monasca.persister.PersisterApplication server /etc/monasca/persister-config.yml
```

Then re-start the Monasca Persister service.

```
sudo service monasca-persister restart
```

## Remove ceilometer-api auth

```
sudo vim /etc/ceilometer/api_paste.ini
```

Change:

```
[pipeline:main]
pipeline = request_id authtoken api-server
```

To:

```
[pipeline:main]
pipeline = request_id api-server
```

Then re-start the Ceilometer API.