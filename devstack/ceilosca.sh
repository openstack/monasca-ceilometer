#!/bin/bash -xe

echo "going to copy /monasca-ceilometer-source to /home/vagrant ..."
rsync -a --exclude='tools/vagrant/.vagrant' /monasca-ceilometer-source /home/vagrant/

echo "going to move /home/vagrant/monasca-ceilometer-source /home/vagrant/monasca-ceilometer..."
mv /home/vagrant/monasca-ceilometer-source /home/vagrant/monasca-ceilometer

#Change to Home directory
cd $HOME

#Essentials
# Note - Vagrant bento box chokes on update/upgrade, so just use a current build instead
# sudo apt-get update
# sudo apt-get -y upgrade
sudo apt-get -y install git

wget https://bootstrap.pypa.io/get-pip.py
sudo python get-pip.py
sudo apt-get -y install python-dev
sudo pip install numpy
sudo pip install python-monascaclient

#Handle if http_proxy is set
if [ $http_proxy ]; then
  git config --global url.https://git.openstack.org/.insteadOf https://git.openstack.org/
  sudo git config --global url.https://git.openstack.org/.insteadOf https://git.openstack.org/
  protocol=`echo $http_proxy | awk -F: '{print $1}'`
  host=`echo $http_proxy | awk -F/ '{print $3}' | awk -F: '{print $1}'`
  port=`echo $http_proxy | awk -F/ '{print $3}' | awk -F: '{print $2}'`
  echo "<settings>
          <proxies>
              <proxy>
                  <id>$host</id>
                  <active>true</active>
                  <protocol>$protocol</protocol>
                  <host>$host</host>
                  <port>$port</port>
              </proxy>
          </proxies>
         </settings>" > ./maven_proxy_settings.xml
  mkdir -p ~/.m2
  cp ./maven_proxy_settings.xml ~/.m2/settings.xml
  sudo mkdir -p /root/.m2
  sudo cp ./maven_proxy_settings.xml /root/.m2/settings.xml
fi

#Clone devstack and switch to newton
git clone https://git.openstack.org/openstack-dev/devstack | true
cd devstack
git checkout stable/newton

#Add hard coded IP to the default interface
##NOTE: Change the interface if your system is different net_if
export SERVICE_HOST=192.168.10.6
export HOST_IP_IFACE=eth0
sudo ip addr add $SERVICE_HOST/24 dev $HOST_IP_IFACE || true

#local.conf for devstack
#NOTE: setting other services to versions compatible with newton and later Ceilosca
echo '[[local|localrc]]
SERVICE_HOST=$SERVICE_HOST
HOST_IP=$SERVICE_HOST
HOST_IP_IFACE=$HOST_IP_IFACE
MYSQL_HOST=$SERVICE_HOST
MYSQL_PASSWORD=secretmysql
DATABASE_PASSWORD=secretdatabase
RABBIT_PASSWORD=secretrabbit
ADMIN_PASSWORD=secretadmin
SERVICE_PASSWORD=secretservice
SERVICE_TOKEN=111222333444
LOGFILE=$DEST/logs/stack.sh.log
LOGDIR=$DEST/logs
LOG_COLOR=False
disable_service ceilometer-alarm-notifier ceilometer-alarm-evaluator
disable_service ceilometer-collector
disable_service monasca-thresh
# The following must be disabled as the test does not work at this point
# See https://bugs.launchpad.net/monasca/+bug/1636508
disable_service monasca-smoke-test
enable_service rabbit mysql key tempest
# The following two variables allow switching between Java and Python for the implementations
# of the Monasca API and the Monasca Persister. If these variables are not set, then the
# default is to install the Java implementations of both the Monasca API and the Monasca Persister.
# Uncomment one of the following two lines to choose Java or Python for the Monasca API.
#MONASCA_API_IMPLEMENTATION_LANG=${MONASCA_API_IMPLEMENTATION_LANG:-java}
MONASCA_API_IMPLEMENTATION_LANG=${MONASCA_API_IMPLEMENTATION_LANG:-python}
# Uncomment one of the following two lines to choose Java or Python for the Monasca Pesister.
#MONASCA_PERSISTER_IMPLEMENTATION_LANG=${MONASCA_PERSISTER_IMPLEMENTATION_LANG:-java}
MONASCA_PERSISTER_IMPLEMENTATION_LANG=${MONASCA_PERSISTER_IMPLEMENTATION_LANG:-python}
# This line will enable all of Monasca.
enable_plugin monasca-api https://git.openstack.org/openstack/monasca-api stable/newton
enable_plugin ceilometer https://git.openstack.org/openstack/ceilometer stable/newton
# Optional
#enable_plugin monasca-transform https://git.openstack.org/openstack/monasca-transform master
' > local.conf


pushd /home/vagrant/monasca-ceilometer

echo "creating a local commit..."
git config --global user.email "local.devstack.committer@hpe.com"
git config --global user.name "Local devstack committer"
git add --all
git commit -m "Local commit"
echo "creating a local commit done."

CURRENT_BRANCH=`git status | grep 'On branch' | sed 's/On branch //'`
if [ ${CURRENT_BRANCH} != 'master' ]
then
    echo "Maintaining current branch ${CURRENT_BRANCH}"
    # set the branch to what we're using in local.conf
    if [[ -z `grep ${CURRENT_BRANCH} /home/vagrant/devstack/local.conf` ]]; then
        sed -i "s/enable_plugin ceilosca \/home\/vagrant\/monasca-ceilometer//g" /home/vagrant/devstack/local.conf
        sed -i "s/# END DEVSTACK LOCAL.CONF CONTENTS//g" /home/vagrant/devstack/local.conf
        printf "enable_plugin ceilosca /home/vagrant/monasca-ceilometer ${CURRENT_BRANCH}\n" >> /home/vagrant/devstack/local.conf
        printf "# END DEVSTACK LOCAL.CONF CONTENTS" >> /home/vagrant/devstack/local.conf
    fi
fi
popd

#Run the stack.sh
./unstack.sh | true
./stack.sh
