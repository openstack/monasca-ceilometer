import ceilometer
import os
import shutil


ceilo_dir = os.path.dirname(ceilometer.__file__)

ceilosca_files = {
    'ceilosca/ceilometer/' + file: '%s/%s' % (ceilo_dir, file)
    for file in
    [
        'monasca_client.py',
        'publisher/monasca_data_filter.py',
        'publisher/monclient.py',
        'storage/impl_monasca.py'
    ]
}

# Copy the files to ceilometer venv dir. without this step
# python cannot load our files for unit testing
for src, dest in ceilosca_files.items():
    shutil.copyfile(src, dest)
