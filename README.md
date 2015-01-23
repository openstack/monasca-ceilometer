monasca-ceilometer
========

Python plugin code for Ceilometer to send samples to monasca-api

### Installation Instructions

Assumes that an active monasca-api server is running.

1. Run devstack to get openstack installed.  monasca-ceilometer was developed on a Ubuntu 12.04 host.

2.  Install python-monascaclient
    
      pip install python-monascaclient

3.  Clone monasca-ceilometer from github.com.

      Copy monclient.py to the following path:
  
        /opt/stack/ceilometer/ceilometer/publisher/monclient.py

      Edit monclient.py and set auth_url if using username and password for authentication.
      Either set a token or username and password in monclient.py or configure it in pipeline.yaml below.

4.  Edit entry_points.txt

      Under [ceilometer.publisher] section add the following line:

        monclient = ceilometer.publisher.monclient:monclient

5.  Edit setup.cfg

      Under 'ceilometer.publisher =' section add the following line:

        monclient = ceilometer.publisher.monclient:monclient

6.  Configure /etc/ceilometer/pipeline.yaml to send the metrics to the monclient publisher.  Use the included pipeline.yaml file as an example.

      Set a valid username and password if a token or username and password weren't added to monclient.py

7.  Setup debugging.

    * Create a pycharm run configuration.
  
        - Script: /usr/local/bin/ceilometer-api
        - Script parameters:  -d -v --log-dir=/var/log/ceilometer-api --config-file /etc/ceilometer/ceilometer.conf
    
    * Comment out any logging messages that cause the debugger to lose the debugging session.
    * Make sure that 'Attach to subprocess automatically while debugging' is checked in Pycharm's Python Debugger settings.
    * Make sure that 'Gevent compatible debugging' is checked in Pycharm's Debugger settings.
  
  
### Todo

1. Modify monclient.py to not hard-code kwargs sent to client.Client.
2. Reuse the token until it expires if username and password are used
 
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
 




