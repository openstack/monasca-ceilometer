#!/bin/bash -xe

export MONASCA_VAGRANT_REPO=https://github.com/stackforge/monasca-vagrant
export DEVSTACK_REPO=https://github.com/openstack-dev/devstack.git

export BASE_DIR=~
export WORK_DIR=$BASE_DIR/monasca-vagrant
export PREFERRED_BRANCH=stable/kilo
export DEVSTACK_DIR=$BASE_DIR/devstack
export DEVSTACK_IP=192.168.10.5
export MINIMON_IP=192.168.10.4
export NETWORK_IF=eth0
export CEILOSCA_USER=$USER

#The following variables are used by, modified devstack ceilometer (deployer/devstack/ceilometer) script
export TARGET_IP=127.0.0.1
export MONASCA_API_URL=http://$TARGET_IP:8070/v2.0
export CEILOSCA_DIR=${PWD}
export CEILOSCA_FILES='ceilometer/monasca_client.py ceilometer/publisher/monasca_data_filter.py ceilometer/publisher/monclient.py ceilometer/storage/impl_monasca.py setup.cfg'
export CEILOSCA_CONF_FILES='pipeline.yaml monasca_field_definitions.yaml';


setup_devstack()
{
        git clone -b $PREFERRED_BRANCH $DEVSTACK_REPO $DEVSTACK_DIR || true
        cp deployer/devstack/local.conf $DEVSTACK_DIR
        cp deployer/devstack/ceilometer $DEVSTACK_DIR/lib
        pushd $DEVSTACK_DIR
        ./unstack.sh || true
        ./stack.sh
        popd
}

install_ansible()
{
	      sudo apt-get install software-properties-common
	      sudo apt-add-repository -y ppa:ansible/ansible
	      sudo apt-get update
	      sudo apt-get -y install ansible
}

get_monasca_files()
{
	      git clone $MONASCA_VAGRANT_REPO $WORK_DIR || true
        pushd $WORK_DIR
        ansible-galaxy install -r requirements.yml -p ./roles --ignore-errors
        popd
}

disable_monasca_ui_role()
{
        if [ -f $WORK_DIR/roles/monasca-ui/tasks/main.yml ]; then
            rm $WORK_DIR/roles/monasca-ui/tasks/main.yml
            file_list=$(find $WORK_DIR/roles -type f -exec grep -l get_url: {} +)
            for filename in $file_list; do
                sed -i.bak '/get_url:/s/$/ timeout=600/' $filename
            done
        fi

}

disable_monasca_events_installation()
{
        sed -i "s/- include: events.yml/#- include: events.yml/" $WORK_DIR/mini-mon.yml
}

add_to_etc_hosts()
{
        if ! grep -q "$TARGET_IP devstack mini-mon" /etc/hosts; then
            sudo bash -c "echo $TARGET_IP devstack mini-mon >> /etc/hosts"
        fi
}

add_monasca_ips_to_local_net_if()
{
        sudo ip addr add $DEVSTACK_IP/24 dev $NETWORK_IF || true
        sudo ip addr add $MINIMON_IP/24 dev $NETWORK_IF || true
}

run_ceilosca()
{
        cd $WORK_DIR
        ansible-playbook -u $CEILOSCA_USER -c local -k -i "devstack,"  devstack.yml
        ansible-playbook -u $CEILOSCA_USER -c local -k -i "mini-mon,"  mini-mon.yml -e 'database_type=influxdb'
}


setup_devstack
install_ansible
get_monasca_files
disable_monasca_ui_role
disable_monasca_events_installation
add_to_etc_hosts
add_monasca_ips_to_local_net_if
run_ceilosca
