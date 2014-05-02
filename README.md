ceil2mon
========

Python plugin code for Ceilometer to send samples to Jahmon

Run devstack to get openstack installed.

Checkout monclient from git.hpcloud.net.
Copy monclient to the following path:

  /opt/stack/ceilometer/ceilometer/monclient

Copy monclient.py to the following path:
  
  /opt/stack/ceilometer/ceilometer/publisher/monclient.py


edit entry_points.txt

Under [ceilometer.publisher] section add the following line:

  monclient = ceilometer.publisher.monclient:monclient



edit setup.cf

Under 'ceilometer.publisher =' section add the following line:

  monclient = ceilometer.publisher.monclient:monclient


Setup debugging.

  Create a pycharm run configuration.
  
    Script: /usr/local/bin/ceilometer-api
    Script parameters:  -d -v --log-dir=/var/log/ceilometer-api --config-file /etc/ceilometer/ceilometer.conf
    
  Comment out any logging messages that cause the debugger to lose the debugging session.
  Make sure that 'Attach to subprocess automatically while debugging' is checked in Pycharm's Python Debugger settings.
  Make sure that 'Gevent compatible debugging' is checked in Pycharm's Debugger settings.
  
  
  
