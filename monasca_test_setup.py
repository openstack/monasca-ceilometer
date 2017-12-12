#
#  Licensed under the Apache License, Version 2.0 (the "License"); you may
#  not use this file except in compliance with the License. You may obtain
#  a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#  WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#  License for the specific language governing permissions and limitations
#  under the License.
#
import ceilometer
import os
import shutil


ceilo_dir = os.path.dirname(ceilometer.__file__)

ceilosca_files = {
    'ceilosca/ceilometer/' + file: '%s/%s' % (ceilo_dir, file)
    for file in
    [
        'monasca_client.py',
        'monasca_ceilometer_opts.py',
        'publisher/monasca_data_filter.py',
        'publisher/monclient.py',
        'storage/impl_monasca.py'
    ]
}

# Copy the files to ceilometer venv dir. without this step
# python cannot load our files for unit testing
for src, dest in ceilosca_files.items():
    shutil.copyfile(src, dest)

# Include new module
shutil.rmtree(ceilo_dir + "/ceilosca_mapping/", True)
shutil.copytree('ceilosca/ceilometer/ceilosca_mapping',
                ceilo_dir + "/ceilosca_mapping/")

ceilo_parent_dir = os.path.dirname(os.path.abspath(
    os.path.dirname(ceilometer.__file__)))

ceilosca_conf_files = {
    file: '%s/%s' % (ceilo_parent_dir, file)
    for file in
    [
        'etc/ceilometer/monasca_field_definitions.yaml',
        'etc/ceilometer/pipeline.yaml',
        'etc/ceilometer/monasca_pipeline.yaml',
        'etc/ceilometer/ceilometer.conf',
        'etc/ceilometer/policy.json'
    ]
}

dest_conf_dir = ceilo_parent_dir + '/etc/ceilometer'

if not os.path.exists(dest_conf_dir):
    os.makedirs(dest_conf_dir)

for src, dest in ceilosca_conf_files.items():
    shutil.copyfile(src, dest)
