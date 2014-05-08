ceil2mon
========

Python plugin code for Ceilometer to send samples to Jahmon

### Installation Instructions

Assumes that mini-mon is running with an active mon-api server.

1. Run devstack to get openstack installed.  ceil2mon was developed on a Ubuntu 12.04 host.

2.  Checkout monclient from git.hpcloud.net.
    
      Copy monclient to the following path:

        /opt/stack/ceilometer/ceilometer/monclient

3.  Checkout ceil2mon  from git.hpcloud.net.

      Copy monclient.py to the following path:
  
        /opt/stack/ceilometer/ceilometer/publisher/monclient.py

4.  Edit entry_points.txt

      Under [ceilometer.publisher] section add the following line:

        monclient = ceilometer.publisher.monclient:monclient


5.  Edit setup.cfg

      Under 'ceilometer.publisher =' section add the following line:

        monclient = ceilometer.publisher.monclient:monclient

6.  Configure /etc/ceilometer/pipeline.yaml to send the metrics to the monclient publisher.  Use the included pipeline.yaml file as an example.

7.  Setup debugging.

    * Create a pycharm run configuration.
  
        - Script: /usr/local/bin/ceilometer-api
        - Script parameters:  -d -v --log-dir=/var/log/ceilometer-api --config-file /etc/ceilometer/ceilometer.conf
    
    * Comment out any logging messages that cause the debugger to lose the debugging session.
    * Make sure that 'Attach to subprocess automatically while debugging' is checked in Pycharm's Python Debugger settings.
    * Make sure that 'Gevent compatible debugging' is checked in Pycharm's Debugger settings.
  
  
### Todo

1. Modify monclient.py to not hard-code kwargs sent to client.Client.
 
# License

Copyright (c) 2014 Hewlett-Packard Development Company, L.P.

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
 




