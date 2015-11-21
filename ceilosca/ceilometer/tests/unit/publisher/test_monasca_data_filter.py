#
# Copyright 2015 Hewlett-Packard Company
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import datetime
import mock
from oslo_utils import timeutils
from oslotest import base

from ceilometer.publisher import monasca_data_filter as mdf
from ceilometer import sample


class TestMonUtils(base.BaseTestCase):
    def setUp(self):
        super(TestMonUtils, self).setUp()
        self._field_mappings = {
            'dimensions': ['resource_id',
                           'project_id',
                           'user_id',
                           'geolocation',
                           'region',
                           'availability_zone'],

            'metadata': {
                'common': ['event_type',
                           'audit_period_beginning',
                           'audit_period_ending'],
                'image': ['size', 'status'],
                'image.delete': ['size', 'status'],
                'image.size': ['size', 'status'],
                'image.update': ['size', 'status'],
                'image.upload': ['size', 'status'],
                'instance': ['state', 'state_description'],
                'snapshot': ['status'],
                'snapshot.size': ['status'],
                'volume': ['status'],
                'volume.size': ['status'],
            }
        }

    def test_process_sample(self):
        s = sample.Sample(
            name='test',
            type=sample.TYPE_CUMULATIVE,
            unit='',
            volume=1,
            user_id='test',
            project_id='test',
            resource_id='test_run_tasks',
            timestamp=datetime.datetime.utcnow().isoformat(),
            resource_metadata={'name': 'TestPublish'},
        )

        to_patch = ("ceilometer.publisher.monasca_data_filter."
                    "MonascaDataFilter._get_mapping")
        with mock.patch(to_patch, side_effect=[self._field_mappings]):
            data_filter = mdf.MonascaDataFilter()
            r = data_filter.process_sample_for_monasca(s)

            self.assertEqual(s.name, r['name'])
            self.assertIsNotNone(r.get('dimensions'))
            self.assertIsNotNone(r.get('value_meta'))
            self.assertIsNotNone(r.get('value'))
            self.assertEqual(s.user_id, r['dimensions'].get('user_id'))
            self.assertEqual(s.project_id, r['dimensions'].get('project_id'))
            self.assertEqual(s.resource_id, r['dimensions'].get('resource_id'))
            # 2015-04-07T20:07:06.156986 compare upto millisec
            monasca_ts = \
                timeutils.iso8601_from_timestamp(r['timestamp'] / 1000.0,
                                                 microsecond=True)[:23]
            self.assertEqual(s.timestamp[:23], monasca_ts)

    def test_process_sample_field_mappings(self):
        s = sample.Sample(
            name='test',
            type=sample.TYPE_CUMULATIVE,
            unit='',
            volume=1,
            user_id='test',
            project_id='test',
            resource_id='test_run_tasks',
            timestamp=datetime.datetime.utcnow().isoformat(),
            resource_metadata={'name': 'TestPublish'},
        )

        field_map = self._field_mappings
        field_map['dimensions'].remove('project_id')
        field_map['dimensions'].remove('user_id')

        to_patch = ("ceilometer.publisher.monasca_data_filter."
                    "MonascaDataFilter._get_mapping")
        with mock.patch(to_patch, side_effect=[field_map]):
            data_filter = mdf.MonascaDataFilter()
            r = data_filter.process_sample_for_monasca(s)

            self.assertIsNone(r['dimensions'].get('project_id'))
            self.assertIsNone(r['dimensions'].get('user_id'))

    def test_process_sample_metadata(self):
        s = sample.Sample(
            name='image',
            type=sample.TYPE_CUMULATIVE,
            unit='',
            volume=1,
            user_id='test',
            project_id='test',
            resource_id='test_run_tasks',
            timestamp=datetime.datetime.utcnow().isoformat(),
            resource_metadata={'event_type': 'notification',
                               'status': 'active',
                               'size': '1500'},
        )

        to_patch = ("ceilometer.publisher.monasca_data_filter."
                    "MonascaDataFilter._get_mapping")
        with mock.patch(to_patch, side_effect=[self._field_mappings]):
            data_filter = mdf.MonascaDataFilter()
            r = data_filter.process_sample_for_monasca(s)

            self.assertEqual(s.name, r['name'])
            self.assertIsNotNone(r.get('value_meta'))

            self.assertEqual(s.resource_metadata.items(),
                             r['value_meta'].items())
