#
# Copyright 2015 Hewlett Packard
# (c) Copyright 2018 SUSE LLC
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

import collections
import datetime
import os

import dateutil.parser
import mock
from oslo_utils import fileutils
from oslo_utils import timeutils
from oslotest import base
import six
import yaml

import ceilometer
from ceilometer.api.controllers.v2.meters import Aggregate
from ceilometer.ceilosca_mapping import ceilometer_static_info_mapping
from ceilometer.ceilosca_mapping import ceilosca_mapping
from ceilometer import monasca_ceilometer_opts
from ceilometer import service
from ceilometer import storage
from ceilometer.storage import impl_monasca
from ceilometer.storage import models as storage_models


class _BaseTestCase(base.BaseTestCase):

    def setUp(self):
        super(_BaseTestCase, self).setUp()
        self.CONF = service.prepare_service([], [])
        self.CONF.register_opts(list(monasca_ceilometer_opts.OPTS),
                                'monasca')
        self.CONF.set_override('service_username', 'ceilometer', 'monasca')
        self.CONF.set_override('service_password', 'admin', 'monasca')
        self.CONF.set_override('service_auth_url',
                               'http://localhost:5000/v2.0',
                               'monasca')
        mdf = mock.patch.object(impl_monasca, 'MonascaDataFilter')
        mdf.start()
        self.addCleanup(mdf.stop)
        spl = mock.patch('ceilometer.pipeline.setup_pipeline')
        spl.start()
        self.addCleanup(spl.stop)
        self.static_info_mapper = ceilometer_static_info_mapping\
            .ProcessMappedCeilometerStaticInfo(self.CONF)
        self.static_info_mapper.reinitialize(self.CONF)

    def assertRaisesWithMessage(self, msg, exc_class, func, *args, **kwargs):
        try:
            func(*args, **kwargs)
            self.fail('Expecting %s exception, none raised' %
                      exc_class.__name__)
        except AssertionError:
            raise
        # Only catch specific exception so we can get stack trace when fail
        except exc_class as e:
            self.assertEqual(msg, e.message)

    def assert_raise_within_message(self, msg, e_cls, func, *args, **kwargs):
        try:
            func(*args, **kwargs)
            self.fail('Expecting %s exception, none raised' %
                      e_cls.__name__)
        except AssertionError:
            raise
        # Only catch specific exception so we can get stack trace when fail
        except e_cls as e:
            self.assertIn(msg, '%s' % e)


class TestGetResources(_BaseTestCase):

    dummy_get_resources_mocked_return_value = (
        [{u'dimensions': {},
          u'measurements': [[u'2015-04-14T17:52:31Z', 1.0, {}]],
          u'id': u'2015-04-14T18:42:31Z',
          u'columns': [u'timestamp', u'value', u'value_meta'],
          u'name': u'image'}])

    cfg = yaml.dump({
                    'meter_metric_map': [{
                        'user_id': '$.dimensions.user_id',
                        'name': 'network.incoming.rate',
                        'resource_id': '$.dimensions.resource_id',
                        'region': 'NA',
                        'monasca_metric_name': 'vm.net.in_rate',
                        'source': 'NA',
                        'project_id': '$.dimensions.tenant_id',
                        'type': 'gauge',
                        'resource_metadata': '$.measurements[0][2]',
                        'unit': 'B/s'
                    }, {
                        'user_id': '$.dimensions.user_id',
                        'name': 'network.outgoing.rate',
                        'resource_id': '$.dimensions.resource_id',
                        'region': 'NA',
                        'monasca_metric_name': 'vm.net.out_rate',
                        'source': 'NA',
                        'project_id': '$.dimensions.project_id',
                        'type': 'delta',
                        'resource_metadata': '$.measurements[0][2]',
                        'unit': 'B/s'
                    }]
                    })

    def setup_ceilosca_mapping_def_file(self, cfg):
        if six.PY3:
            cfg = cfg.encode('utf-8')
        ceilosca_mapping_file = fileutils.write_to_tempfile(
            content=cfg, prefix='ceilosca_mapping', suffix='yaml')
        self.addCleanup(os.remove, ceilosca_mapping_file)
        return ceilosca_mapping_file

    def setUp(self):
        super(TestGetResources, self).setUp()
        ceilosca_mapping_file = self.setup_ceilosca_mapping_def_file(
            TestGetResources.cfg)
        self.CONF.set_override('ceilometer_monasca_metrics_mapping',
                               ceilosca_mapping_file, group='monasca')
        ceilosca_mapper = ceilosca_mapping\
            .ProcessMappedCeiloscaMetric(self.CONF)
        ceilosca_mapper.reinitialize(self.CONF)

    def test_not_implemented_params(self):
        with mock.patch("ceilometer.monasca_client.Client"):
            conn = impl_monasca.Connection(self.CONF, "127.0.0.1:8080")

            kwargs = dict(start_timestamp_op='le')
            self.assertRaises(ceilometer.NotImplementedError,
                              lambda: list(conn.get_resources(**kwargs)))
            kwargs = dict(end_timestamp_op='ge')
            self.assertRaises(ceilometer.NotImplementedError,
                              lambda: list(conn.get_resources(**kwargs)))

    def test_dims_filter(self):
        with mock.patch("ceilometer.monasca_client.Client") as mock_client:
            conn = impl_monasca.Connection(self.CONF, "127.0.0.1:8080")
            mnl_mock = mock_client().metric_names_list
            mnl_mock.return_value = [
                {
                    "id": "335b5d569ad29dc61b3dc24609fad3619e947944",
                    "name": "some"
                }
            ]
            end_time = datetime.datetime(2015, 4, 1, 12, 00, 00)
            kwargs = dict(project='proj1',
                          end_timestamp=end_time)
            list(conn.get_resources(**kwargs))
            self.assertEqual(True, mnl_mock.called)

            expected = [
                mock.call(
                    dimensions={
                        'project_id': 'proj1'}),
                mock.call(
                    dimensions={
                        'tenant_id': 'proj1'})
            ]
            self.assertTrue(expected == mnl_mock.call_args_list)
            self.assertEqual(2, mnl_mock.call_count)

    @mock.patch('oslo_utils.timeutils.utcnow')
    def test_get_resources(self, mock_utcnow):
        mock_utcnow.return_value = datetime.datetime(2016, 4, 7, 18, 20)
        with mock.patch("ceilometer.monasca_client.Client") as mock_client:
            conn = impl_monasca.Connection(self.CONF, "127.0.0.1:8080")
            mnl_mock = mock_client().metric_names_list
            mnl_mock.return_value = [
                {
                    "id": "335b5d569ad29dc61b3dc24609fad3619e947944",
                    "name": "storage.objects.size"
                },
                {
                    "id": "335b5d569ad29dc61b3dc24609fad3619e947944",
                    "name": "vm.net.in_rate"
                }
            ]

            kwargs = dict(source='openstack')
            ml_mock = mock_client().measurements_list
            data1 = (
                [{u'dimensions': {u'resource_id': u'abcd',
                                  u'datasource': u'ceilometer'},
                  u'measurements': [[u'2015-04-14T17:52:31Z', 1.0, {}],
                                    [u'2015-04-15T17:52:31Z', 2.0, {}],
                                    [u'2015-04-16T17:52:31Z', 3.0, {}]],
                  u'id': u'2015-04-14T18:42:31Z',
                  u'columns': [u'timestamp', u'value', u'value_meta'],
                  u'name': u'storage.objects.size'}])

            data2 = (
                [{u'dimensions': {u'resource_id': u'abcd',
                                  u'datasource': u'ceilometer'},
                  u'measurements': [[u'2015-04-14T17:52:31Z', 1.0, {}],
                                    [u'2015-04-15T17:52:31Z', 2.0, {}],
                                    [u'2015-04-16T17:52:31Z', 3.0, {}]],
                  u'id': u'2015-04-14T18:42:31Z',
                  u'columns': [u'timestamp', u'value', u'value_meta'],
                  u'name': u'vm.net.in_rate'}])
            ml_mock.side_effect = [data1, data2]
            list(conn.get_resources(**kwargs))
            self.assertEqual(2, ml_mock.call_count)
            self.assertEqual(dict(dimensions=dict(datasource='ceilometer',
                                                  source='openstack'),
                                  name='storage.objects.size',
                                  start_time='1970-01-01T00:00:00.000000Z',
                                  group_by='*',
                                  end_time='2016-04-07T18:20:00.000000Z'),
                             ml_mock.call_args_list[0][1])

    def test_get_resources_limit(self):
        with mock.patch("ceilometer.monasca_client.Client") as mock_client:
            conn = impl_monasca.Connection(self.CONF, "127.0.0.1:8080")

            mnl_mock = mock_client().metric_names_list
            mnl_mock.return_value = [
                {
                    "id": "335b5d569ad29dc61b3dc24609fad3619e947944",
                    "name": "storage.objects.size"
                },
                {
                    "id": "335b5d569ad29dc61b3dc24609fad3619e947944",
                    "name": "vm.net.in_rate"
                }
            ]
            dummy_get_resources_mocked_return_value = (
                [{u'dimensions': {u'resource_id': u'abcd',
                                  u'datasource': u'ceilometer'},
                  u'measurements': [[u'2015-04-14T17:52:31Z', 1.0, {}],
                                    [u'2015-04-15T17:52:31Z', 2.0, {}],
                                    [u'2015-04-16T17:52:31Z', 3.0, {}]],
                  u'id': u'2015-04-14T18:42:31Z',
                  u'columns': [u'timestamp', u'value', u'value_meta'],
                  u'name': u'image'}])

            ml_mock = mock_client().measurements_list
            ml_mock.return_value = (
                dummy_get_resources_mocked_return_value)

            sample_filter = storage.SampleFilter(
                meter='specific meter', end_timestamp='2015-04-20T00:00:00Z')
            resources = list(conn.get_resources(sample_filter, limit=2))
            self.assertEqual(2, len(resources))
            self.assertEqual(True, ml_mock.called)
            self.assertEqual(1, ml_mock.call_count)

    @mock.patch('oslo_utils.timeutils.utcnow')
    def test_get_resources_simple_metaquery(self, mock_utcnow):
        mock_utcnow.return_value = datetime.datetime(2016, 4, 7, 18, 28)
        with mock.patch("ceilometer.monasca_client.Client") as mock_client:
            conn = impl_monasca.Connection(self.CONF, "127.0.0.1:8080")
            mnl_mock = mock_client().metric_names_list
            mnl_mock.return_value = [
                {
                    "id": "335b5d569ad29dc61b3dc24609fad3619e947944",
                    "name": "storage.objects.size"
                },
                {
                    "id": "335b5d569ad29dc61b3dc24609fad3619e947944",
                    "name": "vm.net.in_rate"
                }
            ]
            kwargs = dict(metaquery={'metadata.key': 'value1'})

            ml_mock = mock_client().measurements_list
            data1 = (
                [{u'dimensions': {u'resource_id': u'abcd',
                                  u'datasource': u'ceilometer'},
                  u'measurements': [[u'2015-04-14T17:52:31Z', 1.0, {}],
                                    [u'2015-04-15T17:52:31Z', 2.0, {}],
                                    [u'2015-04-16T17:52:31Z', 3.0, {}]],
                  u'id': u'2015-04-14T18:42:31Z',
                  u'columns': [u'timestamp', u'value', u'value_meta'],
                  u'name': u'storage.objects.size'}])

            data2 = (
                [{u'dimensions': {u'resource_id': u'abcd',
                                  u'datasource': u'ceilometer'},
                  u'measurements': [[u'2015-04-14T17:52:31Z', 1.0, {}],
                                    [u'2015-04-15T17:52:31Z', 2.0, {}],
                                    [u'2015-04-16T17:52:31Z', 3.0, {}]],
                  u'id': u'2015-04-14T18:42:31Z',
                  u'columns': [u'timestamp', u'value', u'value_meta'],
                  u'name': u'vm.net.in_rate'}])

            ml_mock.side_effect = [data1, data2]
            list(conn.get_resources(**kwargs))

            self.assertEqual(2, ml_mock.call_count)
            self.assertEqual(dict(dimensions=dict(datasource='ceilometer'),
                                  name="storage.objects.size",
                                  start_time='1970-01-01T00:00:00.000000Z',
                                  group_by='*',
                                  end_time='2016-04-07T18:28:00.000000Z'),
                             ml_mock.call_args_list[0][1])


class MeterTest(_BaseTestCase):

    dummy_metrics_mocked_return_value = (
        [{u'dimensions': {u'datasource': u'ceilometer'},
          u'id': u'2015-04-14T18:42:31Z',
          u'name': u'meter-1'},
         {u'dimensions': {u'datasource': u'ceilometer'},
          u'id': u'2015-04-15T18:42:31Z',
          u'name': u'meter-1'},
         {u'dimensions': {u'datasource': u'ceilometer'},
          u'id': u'2015-04-16T18:42:31Z',
          u'name': u'meter-2'}])

    def test_not_implemented_params(self):
        with mock.patch('ceilometer.monasca_client.Client'):
            conn = impl_monasca.Connection(self.CONF, '127.0.0.1:8080')

            kwargs = dict(metaquery=True)
            self.assertRaises(ceilometer.NotImplementedError,
                              lambda: list(conn.get_meters(**kwargs)))

    def test_metrics_list_call(self):
        with mock.patch('ceilometer.monasca_client.Client') as mock_client:
            conn = impl_monasca.Connection(self.CONF, '127.0.0.1:8080')
            metrics_list_mock = mock_client().metrics_list

            kwargs = dict(user='user-1',
                          project='project-1',
                          resource='resource-1',
                          source='openstack',
                          limit=100)
            list(conn.get_meters(**kwargs))

            self.assertEqual(True, metrics_list_mock.called)
            self.assertEqual(4, metrics_list_mock.call_count)
            expected = [
                mock.call(
                    dimensions={
                        'source': 'openstack',
                        'project_id': 'project-1',
                        'user_id': 'user-1',
                        'datasource': 'ceilometer',
                        'resource_id': 'resource-1'}),
                mock.call(
                    dimensions={
                        'source': 'openstack',
                        'project_id': 'project-1',
                        'user_id': 'user-1',
                        'resource_id': 'resource-1'}),
                mock.call(
                    dimensions={
                        'source': 'openstack',
                        'tenant_id': 'project-1',
                        'user_id': 'user-1',
                        'resource_id': 'resource-1'}),
                mock.call(
                    dimensions={
                        'source': 'openstack',
                        'project_id': 'project-1',
                        'user_id': 'user-1',
                        'hostname': 'resource-1'})
            ]
            self.assertTrue(expected == metrics_list_mock.call_args_list)

    def test_unique_metrics_list_call(self):
        dummy_metric_names_mocked_return_value = (
            [{"id": "015c995b1a770147f4ef18f5841ef566ab33521d",
              "name": "network.delete"},
             {"id": "335b5d569ad29dc61b3dc24609fad3619e947944",
              "name": "subnet.update"}])
        with mock.patch('ceilometer.monasca_client.Client') as mock_client:
            conn = impl_monasca.Connection(self.CONF, '127.0.0.1:8080')
            metric_names_list_mock = mock_client().metric_names_list
            metric_names_list_mock.return_value = (
                dummy_metric_names_mocked_return_value
            )
            kwargs = dict(user='user-1',
                          project='project-1',
                          resource='resource-1',
                          source='openstack',
                          limit=2,
                          unique=True)

            self.assertEqual(2, len(list(conn.get_meters(**kwargs))))

            self.assertEqual(True, metric_names_list_mock.called)
            self.assertEqual(1, metric_names_list_mock.call_count)
            self.assertEqual(dict(dimensions=dict(user_id='user-1',
                                                  project_id='project-1',
                                                  resource_id='resource-1',
                                                  source='openstack')),
                             metric_names_list_mock.call_args[1])


class TestGetSamples(_BaseTestCase):

    dummy_get_samples_mocked_return_value = (
        [{u'dimensions': {},
          u'measurements': [[u'2015-04-14T17:52:31Z', 1.0, {}]],
          u'id': u'2015-04-14T18:42:31Z',
          u'columns': [u'timestamp', u'value', u'value_meta'],
          u'name': u'image'}])

    dummy_metrics_mocked_return_value = (
        [{u'dimensions': {},
          u'id': u'2015-04-14T18:42:31Z',
          u'name': u'specific meter'}])

    dummy_get_samples_mocked_return_extendedkey_value = (
        [{u'dimensions': {},
          u'measurements': [[u'2015-04-14T17:52:31Z',
                             1.0,
                             {'image_meta.base_url': 'base_url'}]],
          u'id': u'2015-04-14T18:42:31Z',
          u'columns': [u'timestamp', u'value', u'value_meta'],
          u'name': u'image'}])

    def test_get_samples_not_implemented_params(self):
        with mock.patch("ceilometer.monasca_client.Client"):
            conn = impl_monasca.Connection(self.CONF, "127.0.0.1:8080")

            sample_filter = storage.SampleFilter(meter='specific meter',
                                                 message_id='specific message')
            self.assertRaises(ceilometer.NotImplementedError,
                              lambda: list(conn.get_samples(sample_filter)))

    def test_get_samples_name(self):
        with mock.patch("ceilometer.monasca_client.Client") as mock_client:
            conn = impl_monasca.Connection(self.CONF, "127.0.0.1:8080")
            metrics_list_mock = mock_client().metrics_list
            metrics_list_mock.return_value = (
                TestGetSamples.dummy_metrics_mocked_return_value
            )
            ml_mock = mock_client().measurements_list
            ml_mock.return_value = (
                TestGetSamples.dummy_get_samples_mocked_return_value)
            sample_filter = storage.SampleFilter(
                meter='specific meter', end_timestamp='2015-04-20T00:00:00Z')
            list(conn.get_samples(sample_filter))
            self.assertEqual(True, ml_mock.called)
            self.assertEqual(dict(
                dimensions=dict(datasource='ceilometer'),
                start_time='1970-01-01T00:00:00.000000Z',
                group_by='*', name='specific meter',
                end_time='2015-04-20T00:00:00.000000Z'),
                ml_mock.call_args[1])
            self.assertEqual(1, ml_mock.call_count)

    def test_get_samples_start_timestamp_filter(self):
        with mock.patch("ceilometer.monasca_client.Client") as mock_client:
            conn = impl_monasca.Connection(self.CONF, "127.0.0.1:8080")

            metrics_list_mock = mock_client().metrics_list
            metrics_list_mock.return_value = (
                TestGetSamples.dummy_metrics_mocked_return_value
            )
            ml_mock = mock_client().measurements_list
            ml_mock.return_value = (
                TestGetSamples.dummy_get_samples_mocked_return_value)

            start_time = datetime.datetime(2015, 3, 20)

            sample_filter = storage.SampleFilter(
                meter='specific meter',
                start_timestamp=timeutils.isotime(start_time),
                start_timestamp_op='ge')
            list(conn.get_samples(sample_filter))
            self.assertEqual(True, ml_mock.called)
            self.assertEqual(1, ml_mock.call_count)

    def test_get_samples_timestamp_filter_exclusive_range(self):
        with mock.patch("ceilometer.monasca_client.Client") as mock_client:
            conn = impl_monasca.Connection(self.CONF, "127.0.0.1:8080")

            metrics_list_mock = mock_client().metrics_list
            metrics_list_mock.return_value = (
                TestGetSamples.dummy_metrics_mocked_return_value
            )
            ml_mock = mock_client().measurements_list
            ml_mock.return_value = (
                TestGetSamples.dummy_get_samples_mocked_return_value)

            start_time = datetime.datetime(2015, 3, 20)
            end_time = datetime.datetime(2015, 4, 1, 12, 00, 00)

            sample_filter = storage.SampleFilter(
                meter='specific meter',
                start_timestamp=timeutils.isotime(start_time),
                start_timestamp_op='gt',
                end_timestamp=timeutils.isotime(end_time),
                end_timestamp_op='lt')
            list(conn.get_samples(sample_filter))
            self.assertEqual(True, ml_mock.called)
            self.assertEqual(1, ml_mock.call_count)
            self.assertEqual(dict(dimensions=dict(datasource='ceilometer'),
                                  name='specific meter',
                                  start_time='2015-03-20T00:00:00.001000Z',
                                  end_time='2015-04-01T11:59:59.999000Z',
                                  start_timestamp_op='ge',
                                  end_timestamp_op='le',
                                  group_by='*'),
                             ml_mock.call_args_list[0][1])

    def test_get_samples_limit(self):
        with mock.patch("ceilometer.monasca_client.Client") as mock_client:
            conn = impl_monasca.Connection(self.CONF, "127.0.0.1:8080")

            metrics_list_mock = mock_client().metrics_list

            dummy_get_samples_mocked_return_value = (
                [{u'dimensions': {},
                  u'measurements': [[u'2015-04-14T17:52:31Z', 1.0, {}],
                                    [u'2015-04-15T17:52:31Z', 2.0, {}],
                                    [u'2015-04-16T17:52:31Z', 3.0, {}]],
                  u'id': u'2015-04-14T18:42:31Z',
                  u'columns': [u'timestamp', u'value', u'value_meta'],
                  u'name': u'image'}])

            metrics_list_mock.return_value = (
                TestGetSamples.dummy_metrics_mocked_return_value
            )
            ml_mock = mock_client().measurements_list
            ml_mock.return_value = (
                dummy_get_samples_mocked_return_value)

            sample_filter = storage.SampleFilter(
                meter='specific meter', end_timestamp='2015-04-20T00:00:00Z')
            samples = list(conn.get_samples(sample_filter, limit=2))
            self.assertEqual(2, len(samples))
            self.assertEqual(True, ml_mock.called)
            self.assertEqual(1, ml_mock.call_count)

    def test_get_samples_project_filter(self):
        with mock.patch("ceilometer.monasca_client.Client") as mock_client:
            conn = impl_monasca.Connection(self.CONF, "127.0.0.1:8080")
            metrics_list_mock = mock_client().metrics_list
            metrics_list_mock.return_value = (
                [{u'dimensions': dict(project_id='specific project'),
                  u'id': u'2015-04-14T18:42:31Z',
                  u'name': u'specific meter'}]
            )

            ml_mock = mock_client().measurements_list
            ml_mock.return_value = (
                TestGetSamples.dummy_get_samples_mocked_return_value)

            sample_filter = storage.SampleFilter(meter='specific meter',
                                                 project='specific project')
            list(conn.get_samples(sample_filter))
            self.assertEqual(True, ml_mock.called)
            self.assertEqual(1, ml_mock.call_count)

    def test_get_samples_resource_filter(self):
        with mock.patch("ceilometer.monasca_client.Client") as mock_client:
            conn = impl_monasca.Connection(self.CONF, "127.0.0.1:8080")
            metrics_list_mock = mock_client().metrics_list
            metrics_list_mock.return_value = (
                [{u'dimensions': dict(resource_id='specific resource'),
                  u'id': u'2015-04-14T18:42:31Z',
                  u'name': u'specific meter'}]
            )
            ml_mock = mock_client().measurements_list
            ml_mock.return_value = (
                TestGetSamples.dummy_get_samples_mocked_return_value)

            sample_filter = storage.SampleFilter(meter='specific meter',
                                                 resource='specific resource')
            list(conn.get_samples(sample_filter))
            self.assertEqual(True, ml_mock.called)
            self.assertEqual(1, ml_mock.call_count)

    def test_get_samples_source_filter(self):
        with mock.patch("ceilometer.monasca_client.Client") as mock_client:
            conn = impl_monasca.Connection(self.CONF, "127.0.0.1:8080")
            metrics_list_mock = mock_client().metrics_list
            metrics_list_mock.return_value = (
                [{u'dimensions': dict(source='specific source'),
                  u'id': u'2015-04-14T18:42:31Z',
                  u'name': u'specific meter'}]
            )
            ml_mock = mock_client().measurements_list
            ml_mock.return_value = (
                TestGetSamples.dummy_get_samples_mocked_return_value)

            sample_filter = storage.SampleFilter(meter='specific meter',
                                                 source='specific source')
            list(conn.get_samples(sample_filter))
            self.assertEqual(True, ml_mock.called)
            self.assertEqual(1, ml_mock.call_count)

    def test_get_samples_simple_metaquery(self):
        with mock.patch("ceilometer.monasca_client.Client") as mock_client:
            conn = impl_monasca.Connection(self.CONF, "127.0.0.1:8080")
            metrics_list_mock = mock_client().metrics_list
            metrics_list_mock.return_value = (
                TestGetSamples.dummy_metrics_mocked_return_value
            )
            ml_mock = mock_client().measurements_list
            ml_mock.return_value = (
                TestGetSamples.dummy_get_samples_mocked_return_value)

            sample_filter = storage.SampleFilter(
                meter='specific meter',
                metaquery={'metadata.key': u'value'})
            list(conn.get_samples(sample_filter))
            self.assertEqual(True, ml_mock.called)
            self.assertEqual(1, ml_mock.call_count)

    def test_get_samples_simple_metaquery_with_extended_key(self):
        with mock.patch("ceilometer.monasca_client.Client") as mock_client:
            conn = impl_monasca.Connection(self.CONF, "127.0.0.1:8080")
            metrics_list_mock = mock_client().metrics_list
            metrics_list_mock.return_value = (
                TestGetSamples.dummy_metrics_mocked_return_value
            )
            ml_mock = mock_client().measurements_list
            ml_mock.return_value = (
                TestGetSamples.
                dummy_get_samples_mocked_return_extendedkey_value
            )
            sample_filter = storage.SampleFilter(
                meter='specific meter',
                metaquery={'metadata.image_meta.base_url': u'base_url'})
            self.assertTrue(len(list(conn.get_samples(sample_filter))) > 0)
            self.assertEqual(True, ml_mock.called)
            self.assertEqual(1, ml_mock.call_count)

    def test_get_samples_results(self):
        with mock.patch("ceilometer.monasca_client.Client") as mock_client:
            conn = impl_monasca.Connection(self.CONF, "127.0.0.1:8080")
            metrics_list_mock = mock_client().metrics_list
            metrics_list_mock.return_value = (
                [{u'dimensions': {
                    'source': 'some source',
                    'datasource': 'ceilometer',
                    'project_id': 'some project ID',
                    'resource_id': 'some resource ID',
                    'type': 'some type',
                    'unit': 'some unit'},
                  u'id': u'2015-04-14T18:42:31Z',
                  u'name': u'image'}]
            )
            ml_mock = mock_client().measurements_list
            # TODO(this test case needs more work)
            ml_mock.return_value = (
                [{u'dimensions': {
                    'source': 'some source',
                    'datasource': 'ceilometer',
                    'project_id': 'some project ID',
                    'resource_id': 'some resource ID',
                    'type': 'some type',
                    'unit': 'some unit'},
                  u'measurements':
                    [[u'2015-04-01T02:03:04Z', 1.0, {}],
                     [u'2015-04-11T22:33:44Z', 2.0, {}]],
                  u'id': u'2015-04-14T18:42:31Z',
                  u'columns': [u'timestamp', u'value', u'value_meta'],
                  u'name': u'image'}])

            sample_filter = storage.SampleFilter(
                meter='image',
                start_timestamp='2015-03-20T00:00:00Z')
            results = list(conn.get_samples(sample_filter))
            self.assertEqual(True, ml_mock.called)

            self.assertEqual(results[0].counter_name,
                             ml_mock.return_value[0].get('name'))
            self.assertEqual(results[0].counter_type,
                             ml_mock.return_value[0].get('dimensions').
                             get('type'))
            self.assertEqual(results[0].counter_unit,
                             ml_mock.return_value[0].get('dimensions').
                             get('unit'))
            self.assertEqual(results[0].counter_volume,
                             ml_mock.return_value[0].
                             get('measurements')[0][1])
            self.assertEqual(results[0].message_id,
                             ml_mock.return_value[0].get('id'))
            self.assertEqual(results[0].message_signature, '')
            self.assertEqual(results[0].project_id,
                             ml_mock.return_value[0].get('dimensions').
                             get('project_id'))
            self.assertEqual(results[0].recorded_at,
                             dateutil.parser.parse(
                                 ml_mock.return_value[0].
                                 get('measurements')[0][0]))
            self.assertEqual(results[0].resource_id,
                             ml_mock.return_value[0].get('dimensions').
                             get('resource_id'))
            self.assertEqual(results[0].resource_metadata, {})
            self.assertEqual(results[0].source,
                             ml_mock.return_value[0].get('dimensions').
                             get('source'))
            self.assertEqual(results[0].timestamp,
                             dateutil.parser.parse(
                                 ml_mock.return_value[0].
                                 get('measurements')[0][0]))
            self.assertEqual(results[0].user_id, None)

            self.assertEqual(1, ml_mock.call_count)


class MeterStatisticsTest(_BaseTestCase):

    Aggregate = collections.namedtuple("Aggregate", ['func', 'param'])

    def test_not_implemented_params(self):
        with mock.patch("ceilometer.monasca_client.Client"):
            conn = impl_monasca.Connection(self.CONF, "127.0.0.1:8080")

            self.assertRaisesWithMessage("Query without filter "
                                         "not implemented",
                                         ceilometer.NotImplementedError,
                                         lambda: list(
                                             conn.get_meter_statistics(None)))

            sf = storage.SampleFilter()
            self.assertRaisesWithMessage("Query without meter "
                                         "not implemented",
                                         ceilometer.NotImplementedError,
                                         lambda: list(
                                             conn.get_meter_statistics(sf)))

            sf.meter = "image"
            self.assertRaisesWithMessage("Groupby message_id not implemented",
                                         ceilometer.NotImplementedError,
                                         lambda: list(
                                             conn.get_meter_statistics(
                                                 sf,
                                                 groupby=['message_id'])))

            sf.metaquery = "metaquery"
            self.assertRaisesWithMessage("Metaquery not implemented",
                                         ceilometer.NotImplementedError,
                                         lambda: list(
                                             conn.get_meter_statistics(sf)))

            sf.metaquery = None
            sf.start_timestamp_op = 'le'
            self.assertRaisesWithMessage("Start time op le not implemented",
                                         ceilometer.NotImplementedError,
                                         lambda: list(
                                             conn.get_meter_statistics(sf)))

            sf.start_timestamp_op = None
            sf.end_timestamp_op = 'ge'
            self.assertRaisesWithMessage("End time op ge not implemented",
                                         ceilometer.NotImplementedError,
                                         lambda: list(
                                             conn.get_meter_statistics(sf)))

            sf.end_timestamp_op = None
            sf.message_id = "message_id"
            self.assertRaisesWithMessage("Message_id query not implemented",
                                         ceilometer.NotImplementedError,
                                         lambda: list(
                                             conn.get_meter_statistics(sf)))

            sf.message_id = None
            aggregate = [self.Aggregate(func='stddev', param='test')]
            self.assertRaisesWithMessage("Aggregate function(s) ['stddev']"
                                         " not implemented",
                                         ceilometer.NotImplementedError,
                                         lambda: list(
                                             conn.get_meter_statistics(
                                                 sf, aggregate=aggregate)))

    @mock.patch('oslo_utils.timeutils.utcnow')
    def test_stats_list_called_with(self, mock_utcnow):
        mock_utcnow.return_value = datetime.datetime(2016, 4, 7, 18, 31)
        with mock.patch("ceilometer.monasca_client.Client") as mock_client:
            conn = impl_monasca.Connection(self.CONF, "127.0.0.1:8080")
            sl_mock = mock_client().statistics_list

            sf = storage.SampleFilter()
            sf.meter = "image"
            sf.project = "project_id"
            sf.user = "user_id"
            sf.resource = "resource_id"
            sf.source = "source_id"
            aggregate = [self.Aggregate(func="min", param="some")]
            list(conn.get_meter_statistics(sf, period=10, aggregate=aggregate))

            self.assertEqual(True, sl_mock.called)
            self.assertEqual(
                {'merge_metrics': True,
                 'dimensions': {'source': 'source_id',
                                'project_id': 'project_id',
                                'user_id': 'user_id',
                                'resource_id': 'resource_id',
                                'datasource': 'ceilometer'
                                },
                 'end_time': '2016-04-07T18:31:00.000000Z',
                 'start_time': '1970-01-01T00:00:00.000000Z',
                 'period': 10,
                 'statistics': 'min',
                 'name': 'image'
                 },
                sl_mock.call_args[1]
            )

    def test_stats_list(self):
        with mock.patch("ceilometer.monasca_client.Client") as mock_client:
            conn = impl_monasca.Connection(self.CONF, "127.0.0.1:8080")
            sl_mock = mock_client().statistics_list
            sl_mock.return_value = [
                {
                    'statistics':
                        [
                            ['2014-10-24T12:12:12Z', 0.008],
                            ['2014-10-24T12:52:12Z', 0.018]
                        ],
                    'dimensions': {'unit': 'gb'},
                    'columns': ['timestamp', 'min']
                }
            ]

            sf = storage.SampleFilter()
            sf.meter = "image"
            aggregate = Aggregate()
            aggregate.func = 'min'
            sf.start_timestamp = timeutils.parse_isotime(
                '2014-10-24T12:12:42').replace(tzinfo=None)
            stats = list(conn.get_meter_statistics(sf, aggregate=[aggregate],
                                                   period=30))

            self.assertEqual(2, len(stats))
            self.assertEqual('gb', stats[0].unit)
            self.assertEqual('gb', stats[1].unit)
            self.assertEqual(0.008, stats[0].min)
            self.assertEqual(0.018, stats[1].min)
            self.assertEqual(30, stats[0].period)
            self.assertEqual('2014-10-24T12:12:42',
                             stats[0].period_end.isoformat())
            self.assertEqual('2014-10-24T12:52:42',
                             stats[1].period_end.isoformat())
            self.assertIsNotNone(stats[0].as_dict().get('aggregate'))
            self.assertEqual({u'min': 0.008}, stats[0].as_dict()['aggregate'])

    def test_stats_list_with_groupby(self):
        with mock.patch("ceilometer.monasca_client.Client") as mock_client:
            conn = impl_monasca.Connection(self.CONF, "127.0.0.1:8080")
            sl_mock = mock_client().statistics_list
            sl_mock.return_value = [
                {
                    'statistics':
                        [
                            ['2014-10-24T12:12:12Z', 0.008, 1.3, 3, 0.34],
                            ['2014-10-24T12:20:12Z', 0.078, 1.25, 2, 0.21],
                            ['2014-10-24T12:52:12Z', 0.018, 0.9, 4, 0.14]
                        ],
                    'dimensions': {'project_id': '1234', 'unit': 'gb'},
                    'columns': ['timestamp', 'min', 'max', 'count', 'avg']
                },
                {
                    'statistics':
                        [
                            ['2014-10-24T12:14:12Z', 0.45, 2.5, 2, 2.1],
                            ['2014-10-24T12:20:12Z', 0.58, 3.2, 3, 3.4],
                            ['2014-10-24T13:52:42Z', 1.67, 3.5, 1, 5.3]
                        ],
                    'dimensions': {'project_id': '5678', 'unit': 'gb'},
                    'columns': ['timestamp', 'min', 'max', 'count', 'avg']
                }]

            sf = storage.SampleFilter()
            sf.meter = "image"
            sf.start_timestamp = timeutils.parse_isotime(
                '2014-10-24T12:12:42').replace(tzinfo=None)
            groupby = ['project_id']
            stats = list(conn.get_meter_statistics(sf, period=30,
                                                   groupby=groupby))

            self.assertEqual(2, len(stats))

            for stat in stats:
                self.assertIsNotNone(stat.groupby)
                project_id = stat.groupby.get('project_id')
                self.assertIn(project_id, ['1234', '5678'])
                if project_id == '1234':
                    self.assertEqual(0.008, stat.min)
                    self.assertEqual(1.3, stat.max)
                    self.assertEqual(0.23, stat.avg)
                    self.assertEqual(9, stat.count)
                    self.assertEqual(30, stat.period)
                    self.assertEqual('2014-10-24T12:12:12',
                                     stat.period_start.isoformat())
                if project_id == '5678':
                    self.assertEqual(0.45, stat.min)
                    self.assertEqual(3.5, stat.max)
                    self.assertEqual(3.6, stat.avg)
                    self.assertEqual(6, stat.count)
                    self.assertEqual(30, stat.period)
                    self.assertEqual('2014-10-24T13:52:42',
                                     stat.period_end.isoformat())


class TestQuerySamples(_BaseTestCase):

    def test_query_samples_not_implemented_params(self):
        with mock.patch("ceilometer.monasca_client.Client"):
            conn = impl_monasca.Connection(self.CONF, "127.0.0.1:8080")
            query = {'and': [{'=': {'counter_name': 'instance'}},
                             {'or': [{'=': {"project_id": "123"}},
                                     {'=': {"user_id": "456"}}]}]}

            self.assertRaisesWithMessage(
                'filter must be specified',
                ceilometer.NotImplementedError,
                lambda: list(conn.query_samples()))
            order_by = [{"timestamp": "desc"}]
            self.assertRaisesWithMessage(
                'orderby is not supported',
                ceilometer.NotImplementedError,
                lambda: list(conn.query_samples(query, order_by)))

            query = {'or': [{'=': {"project_id": "123"}},
                            {'=': {"user_id": "456"}}]}
            self.assert_raise_within_message(
                'meter name is not found in',
                impl_monasca.InvalidInputException,
                lambda: list(conn.query_samples(query, None, 1)))

    def test_query_samples(self):
        SAMPLES = [[
            storage_models.Sample(
                counter_name="instance",
                counter_type="gauge",
                counter_unit="instance",
                counter_volume=1,
                project_id="123",
                user_id="456",
                resource_id="789",
                resource_metadata={},
                source="openstack",
                recorded_at=timeutils.utcnow(),
                timestamp=timeutils.utcnow(),
                message_id="0",
                message_signature='',)
        ]] * 2
        samples = SAMPLES[:]

        def _get_samples(*args, **kwargs):
            return samples.pop()

        with mock.patch("ceilometer.monasca_client.Client"):
            conn = impl_monasca.Connection(self.CONF, "127.0.0.1:8080")
            with mock.patch.object(conn, 'get_samples') as gsm:
                gsm.side_effect = _get_samples

                query = {'and': [{'=': {'counter_name': 'instance'}},
                                 {'or': [{'=': {"project_id": "123"}},
                                         {'=': {"user_id": "456"}}]}]}
                samples = conn.query_samples(query, None, 100)
                self.assertEqual(2, len(samples))
                self.assertEqual(2, gsm.call_count)

                samples = SAMPLES[:]
                query = {'and': [{'=': {'counter_name': 'instance'}},
                                 {'or': [{'=': {"project_id": "123"}},
                                         {'>': {"counter_volume": 2}}]}]}
                samples = conn.query_samples(query, None, 100)
                self.assertEqual(1, len(samples))
                self.assertEqual(4, gsm.call_count)

    def test_query_samples_timestamp_gt_lt(self):
        SAMPLES = [[
            storage_models.Sample(
                counter_name="instance",
                counter_type="gauge",
                counter_unit="instance",
                counter_volume=1,
                project_id="123",
                user_id="456",
                resource_id="789",
                resource_metadata={},
                source="openstack",
                recorded_at=timeutils.utcnow(),
                timestamp=timeutils.utcnow(),
                message_id="0",
                message_signature='',)
        ]] * 2
        samples = SAMPLES[:]

        def _get_samples(*args, **kwargs):
            return samples.pop()

        with mock.patch("ceilometer.monasca_client.Client"):
            conn = impl_monasca.Connection(self.CONF, "127.0.0.1:8080")
            with mock.patch.object(conn, 'get_samples') as gsm:
                gsm.side_effect = _get_samples

                start = datetime.datetime(2014, 10, 24, 13, 52, 42)
                end = datetime.datetime(2014, 10, 24, 14, 52, 42)
                ts_query = {
                    'or': [{'>': {"timestamp": start}},
                           {'<': {"timestamp": end}}]
                }
                query = {'and': [{'=': {'counter_name': 'instance'}},
                                 ts_query]}
                samples = conn.query_samples(query, None, 100)
                self.assertEqual(2, len(samples))
                self.assertEqual(2, gsm.call_count)


class CapabilitiesTest(base.BaseTestCase):

    def test_capabilities(self):
        expected_capabilities = {
            'meters':
                {
                    'query':
                        {
                            'metadata': False,
                            'simple': True
                        }
                },
            'resources':
                {
                    'query':
                        {
                            'metadata': True, 'simple': True
                        }
                },
            'samples':
                {
                    'query':
                        {
                            'complex': True,
                            'metadata': True,
                            'simple': True
                        }
                },
            'statistics':
                {
                    'aggregation':
                        {
                            'selectable':
                                {
                                    'avg': True,
                                    'cardinality': False,
                                    'count': True,
                                    'max': True,
                                    'min': True,
                                    'stddev': False,
                                    'sum': True
                                },
                            'standard': True},
                    'groupby': False,
                    'query':
                        {
                            'metadata': False,
                            'simple': True
                        }
                },
            'events':
                {
                    'query':
                        {
                            'simple': False
                        }
                }
        }

        actual_capabilities = impl_monasca.Connection.get_capabilities()
        self.assertEqual(expected_capabilities, actual_capabilities)
