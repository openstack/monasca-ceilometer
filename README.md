monasca-ceilometer
========

Python plugin and storage driver for Ceilometer to send samples to monasca-api

### Installation Instructions for setting up Ceilosca manually

*To set up ceilosca automatically, read the instructions in deployer/README.md or use the included Vagrantfile*

Assumes that an active monasca-api server is running.

1.  Run devstack to get openstack installed.

2.  Install python-monascaclient

      pip install python-monascaclient

3.  Clone monasca-ceilometer from github.com.

      Copy the following files from *ceilosca/ceilometer* to devstack's ceilometer location typically at /opt/stack/ceilometer

        monasca_client.py
        storage/impl_monasca.py
        tests/api/v2/test_api_with_monasca_driver.py
        tests/storage/test_impl_monasca.py
        tests/test_monascaclient.py
        tests/publisher/test_monasca_publisher.py
        tests/publisher/test_monasca_data_filter.py
        publisher/monasca_data_filter.py
        publisher/monclient.py

4.  Edit entry_points.txt

      Under [ceilometer.publisher] section add the following line:

        monasca = ceilometer.publisher.monclient:MonascaPublisher

      Under [ceilometer.metering.storage] section add the following line:

        monasca = ceilometer.storage.impl_monasca:Connection

5.  Edit setup.cfg (used at the time of installation)

      Under 'ceilometer.publisher =' section add the following line:

      monasca = ceilometer.publisher.monclient:MonascaPublisher

      Under 'ceilometer.metering.storage =' section add the following line

      monasca = ceilometer.storage.impl_monasca:Connection

6.  Configure /etc/ceilometer/pipeline.yaml to send the metrics to the monasca publisher.  Use the included pipeline.yaml file as an example.

7.  Configure /etc/ceilometer/ceilometer.conf for setting up storage driver for ceilometer API. Use the included ceilometer.conf file as an example.

8.  Copy the included monasca_field_definitions.yml file to /etc/ceilometer.

    This file contains configuration how to treat each field in ceilometer sample object on per meter basis.
    The monasca_data_filter.py uses this file and only stores the fields that are specified in this config file.

9.  Make sure the user specified under service_credentials in ceilometer.conf has *monasca_user role* added.

### Other info

Since we don't have full repo of ceilometer, we setup the ceilometer repo in venv and copy monasca integration files in there,
and run the unit tests over that code. At present this is tested against ceilometer stable/liberty branch, if you need to test
against different branch you can change it in test-requirements.txt

Relevant files are:
monasca_test_setup.py - determines the ceilometer venv path and copies the relevant files over
tox.ini - calls the commands for setup and runs the tests
test-requirements.txt - contains the dependencies required for testing

# License

Copyright (c) 2015 Hewlett-Packard Development Company, L.P.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
implied.
See the License for the specific language governing permissions and
limitations under the License.

