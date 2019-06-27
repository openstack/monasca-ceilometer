===========================
Example configuration files
===========================

The files contained in this directory are for reference when configuring
Ceilosca [1]_ applied to a Ceilometer installation.

* monasca_field_definitions.yaml.full-example

  - This is an example configuration taken from a production deployment around
    the Pike release.  It shows how inclusive the configuration can be, and is
    kept for historical reference.

    **Note** Many meters in Ceilometer were removed after the Pike release.
    Compare `Pike measurements`_ list to the `Stein measurements`_ list.

    **Note** Having additional fields (including those that have been
    removed from Ceilometer) in a field definitions .yaml will not cause
    failures, as the definitions are used for pattern matching and any
    additional fields will simply not match.

* monasca_field_definitions.yaml.json-example

  - This example shows how JSON Path pattern matching can be used to specify
    how metadata is converted in passing to Monasca API.  For example, the
    cinder samples have metadata stored in lists which the Monasca API needs
    formatted correctly.  The jsonpath specified must resolve to a simple
    leaf node (a string value, not a dict).
    More details can be found in `Storyboard`_.


.. [1] Also known as Monasca Ceilometer, or referred to by the repository
       name of openstack/monasca-ceilometer.

.. _Pike measurements: https://docs.openstack.org/ceilometer/pike/admin/telemetry-measurements.html
.. _Stein measurements: https://docs.openstack.org/ceilometer/stein/admin/telemetry-measurements.html
.. _Storyboard: https://storyboard.openstack.org/#!/story/2000954
