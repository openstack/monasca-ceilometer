Team and repository tags
========================


.. image:: https://governance.openstack.org/tc/badges/monasca-ceilometer.svg
    :target: https://governance.openstack.org/tc/reference/tags/index.html

.. Change things from this point on

monasca-ceilometer
==================

Python plugin and storage driver for Ceilometer to send samples to
monasca-api. Also known as `Ceilosca`_.

.. important::

    Ceilosca is **DEPRECATED** as of the Ussuri OpenStack release.
    The functionality of Ceilosca is `now found in Ceilometer`_ as the Monasca
    Publisher option.  This closer integration will make it easier to deploy and
    connect Ceilometer to Monasca.  To support older versions and follow OpenStack
    deprecation policies, this repository will continue to be maintained, but new
    deployments are encouraged to determine if the metrics required are available
    directly in Monasca, or use `the Monasca Publisher`_.


Installation
------------

Installation instructions for setting up Ceilosca automatically
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

See `devstack/README.md`_.

Installation Instructions for setting up Ceilosca manually
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

*To set up Ceilosca automatically, read the instructions in
devstack/README.md or use the included Vagrantfile*

Assumes that an active monasca-api server is running after installing
DevStack.

1. Run devstack to get openstack installed, including Monasca and
   Ceilometer plugins.

  a. Not all Ceilometer components are required. The following may be
     disabled in ``local.conf`` if using an older Ceilometer release.
     ::

       disable_service ceilometer-alarm-notifier
       disable_service ceilometer-alarm-evaluator
       disable_service ceilometer-collector

  b. Panko and Aodh from the Telemetry project are not required,
     as Monasca will be providing these types of services.

  c. Gnocchi is also not required, as Monasca uses a configured
     Time-Series Database for measurement storage.

     Gnocchi installation in DevStack may be skipped by setting the
     following in ``local.conf``.
     ::

       CEILOMETER_BACKEND=none

2. Install python-monascaclient.

   ::

      pip install python-monascaclient

3. Clone monasca-ceilometer from github.com.

4. Copy the following files from ``ceilosca/ceilometer`` to devstack’s
   ceilometer location, typically at ``/opt/stack/ceilometer``.

   ::

      monasca_client.py
      monasca_opts.py
      opts.py
      publisher/monasca_data_filter.py
      publisher/monasca.py
      tests/* (skipping the init.py files)


5. Edit ``setup.cfg`` (used at the time of installation)

   Under ‘ceilometer.sample.publisher =’ section add the following line:

   ::

      monasca = ceilometer.publisher.monasca:MonascaPublisher

6. Configure ``/etc/ceilometer/pipeline.yaml`` to send the metrics to
   the monasca publisher. Use the included
   ``monasca-ceilometer/etc/ceilometer/pipeline.yaml`` file as an example.

7. Configure ``/etc/ceilometer/ceilometer.conf`` for setting up storage
   driver for Ceilometer. Use the included
   ``monasca-ceilometer/etc/ceilometer/ceilometer.conf`` file as an
   example.

8. Copy the included ``monasca_field_definitions.yml`` file from
   ``monasca-ceilometer/etc/ceilometer`` to ``/etc/ceilometer``.

   This ``monasca_field_definitions.yaml`` file contains configuration how
   to treat each field in Ceilometer sample object on per meter basis.
   The ``monasca_data_filter.py`` uses this file and only stores the fields
   that are specified in this config file.

9. Make sure the user specified under ``[service_credentials]`` in
   ``ceilometer.conf`` has *monasca_user* role added.

Other install info
~~~~~~~~~~~~~~~~~~

Since we don’t have a full repo of ceilometer, we setup the ceilometer
repo in venv and copy monasca integration files in there, and run the
unit tests over that code. At present this is tested against ceilometer
stable/pike branch, if you need to test against different branch you can
change it in test-requirements.txt

Relevant files are:

-  monasca_test_setup.py - determines the ceilometer venv path and
   copies the relevant files over

-  tox.ini - calls the commands for setup and runs the tests

-  test-requirements.txt - contains the dependencies required for
   testing

Using Ceilosca
--------------

Defining or changing existing meters
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

From time to time, Ceilometer introduces new meters. The list of
currently supported measurements can be found at
https://docs.openstack.org/ceilometer/pike/admin/telemetry-measurements.html
(which is generated from
https://github.com/openstack/ceilometer/doc/source/admin/telemetry-measurements.rst).

Some meters require additional configuration in Ceilometer. For example,
the SDN pollster meters need specialized drivers. For more information
about how Ceilometer collects meters through polling or collecting,
please reference the `Telemetry documentation`_ and `measurements`_.

Defining which meters are published from Ceilometer to Monasca API
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

As with Ceilometer, the list of meters to be published is specified in
``/etc/ceilometer/pipeline.yaml``.

As metering data accumulates over time, it is recommended that
Ceilometer be configured to only publish meters where the customer has a
need for the data. Additionally, it is recommended to check the
measurements captured by Monasca agents to avoid any duplication of
data.

To enable or disable meters,

1. Identify the current list of meters being collected, specified in
   ``/etc/ceilometer/pipeline.yaml``. *Hint: You can see which meters
   are currently being reported through ``monasca metric-list`` (or
   ``ceilometer meter-list`` in Pike and earlier).*

2. Edit the ``/etc/ceilometer/pipeline.yaml`` file to add or remove
   entries from the meters list.

3. Repeat changes for all control plane nodes.

4. Restart all Ceilometer notification agents, polling agents, and central
   services to pick up the changes.

To create new meters (or clean out removed meters),

1. Identify which meters are available for this OpenStack Ceilometer release
   on `measurements`_ page.

   - Idenfity which parameters should be transfered to Monasca.
   - Identify the Origin of the meter. Be aware that Pollster meters may
     require additional configuration.

2. Modify ``monasca_field_definitions.yml`` with the new meters.

3. Restart Ceilometer services on all control nodes.

Also note that HPE published documentation describing how to configure
the metering service (using Ceilosca in Helion OpenStack 3.0 and later),
which may be helpful for historical context. `link 1`_ `link 2`_ `link 3`_

Using Monasca API meters collected by Ceilosca
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Here are a few examples of how a meter gathered by Ceilometer and passed
through Ceilosca can be found and used in the Monasca API.

In Ceilometer pipeline YAML file

.. csv-table::
   :header: "Ceilometer meter", "Monasca API metric"
   :widths: 50, 50

   "vcpus", "vcpus"
   "image.size", "image.size"
   "disk.root.size", "disk.root.size"
   "memory", "memory"
   "storage.objects", "storage.objects"

Note: Monasca Agent can gather many similar metrics directly, such as
cpu time for a VM. For simplicity, it is recommended that the Monasca
Agent be favored when choosing which metrics to use.

License
=======

Copyright (c) 2015-2017 Hewlett-Packard Development Company, L.P.

Copyright (c) 2018 SUSE LLC

Licensed under the Apache License, Version 2.0 (the “License”); you may
not use this file except in compliance with the License. You may obtain
a copy of the License at

::

   http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an “AS IS” BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

.. _Telemetry documentation: https://docs.openstack.org/ceilometer/pike/admin/index.html
.. _measurements: https://docs.openstack.org/ceilometer/pike/admin/telemetry-measurements.html
.. _telemetry-measurements.html: https://docs.openstack.org/ceilometer/pike/admin/telemetry-measurements.html
.. _link 1: https://docs.hpcloud.com/hos-3.x/helion/metering/metering_reconfig.html
.. _link 2: https://docs.hpcloud.com/hos-3.x/helion/metering/metering_notifications.html#notifications__list
.. _link 3: https://docs.hpcloud.com/hos-5.x/helion/metering/metering_notifications.html#notifications__list
.. _Ceilosca: https://wiki.openstack.org/wiki/Ceilosca
.. _devstack/README.md: devstack/README.md
.. _now found in Ceilometer: https://opendev.org/openstack/ceilometer/commit/126350c0ae609c5d35d54556883da2476e81e30e
.. _the Monasca Publisher: https://docs.openstack.org/ceilometer/latest/admin/telemetry-data-pipelines.html#pipeline-configuration
