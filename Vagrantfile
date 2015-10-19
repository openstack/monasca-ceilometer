# -*- mode: ruby -*-
# vi: set ft=ruby :

$script = <<SCRIPT
sudo apt-get update
sudo apt-get install -y git
git clone https://git.openstack.org/openstack/monasca-ceilometer
cd monasca-ceilometer
deployer/ceilosca.sh
SCRIPT

Vagrant.configure(2) do |config|
  config.vm.box = "ubuntu/trusty64"
  config.vm.provider "virtualbox" do |vb|
      vb.memory = 7168
      vb.cpus = 4
  end

  config.vm.provision "shell" do |s|
      s.inline = $script
      s.privileged = false
  end
end
