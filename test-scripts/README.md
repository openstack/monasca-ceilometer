**Instructions to install, setup and use Rally**

1. Download rally: git clone https://git.openstack.org/openstack/rally
  (Ensure install libffi-dev libssl-dev libxml2 are installed)

2. Run ./install_rally.sh with the -v option to install Rally in its
   own virtual env. This should create a install dir - rally

3. Under the rally install dir, go to samples/deployments, edit the
   existing.json to update auth_url, admin username, password and tenant_name.

4. Activate the rally venv and create the rally deployment environment using
   rally deployment create --filename=existing.json --name=existing

5. Create rally.conf under /etc/rally and use the following contents:
   '''
   [DEFAULT]
   # Path to CA server cetrificate for SSL
   https_cacert=/usr/local/share/ca-certificates/ephemeralca-cacert.crt
   [database]
   connection = sqlite:///<your path of rally install dir>/database/rally.sqlite
   '''
6. Ensure Rally can talk to the environment using:
   rally --config-file=/etc/rally/rally.conf  deployment check

7. Run Rally tests: (assuming you run this from the rally install folder)
   rally --config-file=/etc/rally/rally.conf -v task start samples/tasks/scenarios/ceilometer/list-meters.json

   Under samples/tasks/scenarios/ceilometer, are different test scenarion configurations to test
   different ceilometer apis, these can all be tested using the above command.


8. Other - Rally Deployment commands

    check Check keystone authentication and list all available services.
    config Display configuration of the deployment.
    create Create new deployment.
    destroy Destroy existing deployment.
    list List existing deployments.
    recreate Destroy and create an existing deployment.
    show Show the endpoints of the deployment.
    use Set active deployment. Alias for "rally use deployment".


**Rally scenario yaml file example**

This feature can be easily tested in real life by running one of the most important and plain benchmark scenario called
“KeystoneBasic.authenticate”. This scenario just tries to authenticate from users that were pre-created by Rally. Rally
input task looks as follows (auth.yaml):


---
Authenticate.keystone:
-
runner:
type: "rps"
times: 6000
rps: 50
context:
users:
tenants: 5
users_per_tenant: 10
sla:
max_avg_duration: 5


In human-readable form this input task means: Create 5 tenants with 10 users in each, after that try to authenticate
to Keystone 6000 times performing 50 authentications per second (running new authentication request every 20ms).
Each time we are performing authentication from one of the Rally pre-created user. This task passes only if max
average duration of authentication takes less than 5 seconds.
