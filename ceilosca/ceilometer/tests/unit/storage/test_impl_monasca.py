#
# Copyright 2015 Hewlett Packard
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
import dateutil.parser
import mock
from oslo_config import fixture as fixture_config
from oslo_utils import timeutils
from oslotest import base

import ceilometer
from ceilometer.api.controllers.v2.meters import Aggregate
from ceilometer import storage
from ceilometer.storage import impl_monasca
from ceilometer.storage import models as storage_models


class TestGetResources(base.BaseTestCase):

    dummy_get_resources_mocked_return_value = (
        [{u'dimensions': {},
          u'measurements': [[u'2015-04-14T17:52:31Z', 1.0, {}]],
          u'id': u'2015-04-14T18:42:31Z',
          u'columns': [u'timestamp', u'value', u'value_meta'],
          u'name': u'image'}])

    def setUp(self):
        super(TestGetResources, self).setUp()
        self.CONF = self.useFixture(fixture_config.Config()).conf
        self.CONF([], project='ceilometer', validate_default_values=True)

    @mock.patch("ceilometer.storage.impl_monasca.MonascaDataFilter")
    def test_not_implemented_params(self, mock_mdf):
        with mock.patch("ceilometer.monasca_client.Client"):
            conn = impl_monasca.Connection("127.0.0.1:8080")

            kwargs = dict(start_timestamp_op='le')
            self.assertRaises(ceilometer.NotImplementedError,
                              lambda: list(conn.get_resources(**kwargs)))
            kwargs = dict(end_timestamp_op='ge')
            self.assertRaises(ceilometer.NotImplementedError,
                              lambda: list(conn.get_resources(**kwargs)))

    @mock.patch("ceilometer.storage.impl_monasca.MonascaDataFilter")
    def test_dims_filter(self, mdf_patch):
        with mock.patch("ceilometer.monasca_client.Client") as mock_client:
            conn = impl_monasca.Connection("127.0.0.1:8080")
            start_timestamp = timeutils.isotime(datetime.datetime(1970, 1, 1))
            mnl_mock = mock_client().metrics_list
            mnl_mock.return_value = [
                {
                    'name': 'some',
                    'dimensions': {}
                }
            ]
            kwargs = dict(project='proj1')
            list(conn.get_resources(**kwargs))
            self.assertEqual(True, mnl_mock.called)
            self.assertEqual(dict(dimensions=dict(
                             project_id='proj1'), start_time=start_timestamp),
                             mnl_mock.call_args[1])
            self.assertEqual(1, mnl_mock.call_count)

    @mock.patch("ceilometer.storage.impl_monasca.MonascaDataFilter")
    def test_get_resources(self, mock_mdf):
        with mock.patch("ceilometer.monasca_client.Client") as mock_client:
            conn = impl_monasca.Connection("127.0.0.1:8080")
            mnl_mock = mock_client().metrics_list
            mnl_mock.return_value = [{'name': 'metric1',
                                      'dimensions': {}},
                                     {'name': 'metric2',
                                      'dimensions': {}}
                                     ]
            kwargs = dict(source='openstack')
            ml_mock = mock_client().measurements_list
            ml_mock.return_value = (
                TestGetResources.dummy_get_resources_mocked_return_value)
            list(conn.get_resources(**kwargs))
            self.assertEqual(2, ml_mock.call_count)
            self.assertEqual(dict(dimensions={},
                                  name='metric1',
                                  limit=1,
                                  start_time='1970-01-01T00:00:00Z'),
                             ml_mock.call_args_list[0][1])

    @mock.patch("ceilometer.storage.impl_monasca.MonascaDataFilter")
    def test_get_resources_limit(self, mdf_mock):
        with mock.patch("ceilometer.monasca_client.Client") as mock_client:
            conn = impl_monasca.Connection("127.0.0.1:8080")

            mnl_mock = mock_client().metrics_list
            mnl_mock.return_value = [{'name': 'metric1',
                                      'dimensions': {'resource_id': 'abcd'}},
                                     {'name': 'metric2',
                                      'dimensions': {'resource_id': 'abcd'}}
                                     ]

            dummy_get_resources_mocked_return_value = (
                [{u'dimensions': {u'resource_id': u'abcd'},
                  u'measurements': [[u'2015-04-14T17:52:31Z', 1.0, {}],
                                    [u'2015-04-15T17:52:31Z', 2.0, {}],
                                    [u'2015-04-16T17:52:31Z', 3.0, {}]],
                  u'id': u'2015-04-14T18:42:31Z',
                  u'columns': [u'timestamp', u'value', u'value_meta'],
                  u'name': u'image'}])

            ml_mock = mock_client().measurements_list
            ml_mock.return_value = (
                TestGetSamples.dummy_metrics_mocked_return_value
            )
            ml_mock = mock_client().measurements_list
            ml_mock.return_value = (
                dummy_get_resources_mocked_return_value)

            sample_filter = storage.SampleFilter(
                meter='specific meter', end_timestamp='2015-04-20T00:00:00Z')
            resources = list(conn.get_resources(sample_filter, limit=2))
            self.assertEqual(2, len(resources))
            self.assertEqual(True, ml_mock.called)
            self.assertEqual(2, ml_mock.call_count)

    @mock.patch("ceilometer.storage.impl_monasca.MonascaDataFilter")
    def test_get_resources_simple_metaquery(self, mock_mdf):
        with mock.patch("ceilometer.monasca_client.Client") as mock_client:
            conn = impl_monasca.Connection("127.0.0.1:8080")
            mnl_mock = mock_client().metrics_list
            mnl_mock.return_value = [{'name': 'metric1',
                                      'dimensions': {},
                                      'value_meta': {'key': 'value1'}},
                                     {'name': 'metric2',
                                      'dimensions': {},
                                      'value_meta': {'key': 'value2'}},
                                     ]
            kwargs = dict(metaquery={'metadata.key': 'value1'})

            ml_mock = mock_client().measurements_list
            ml_mock.return_value = (
                TestGetResources.dummy_get_resources_mocked_return_value)
            list(conn.get_resources(**kwargs))

            self.assertEqual(2, ml_mock.call_count)
            self.assertEqual(dict(dimensions={},
                                  name='metric2',
                                  limit=1,
                                  start_time='1970-01-01T00:00:00Z'),
                             ml_mock.call_args_list[1][1])


class MeterTest(base.BaseTestCase):

    @mock.patch("ceilometer.storage.impl_monasca.MonascaDataFilter")
    def test_not_implemented_params(self, mock_mdf):
        with mock.patch('ceilometer.monasca_client.Client'):
            conn = impl_monasca.Connection('127.0.0.1:8080')

            kwargs = dict(metaquery=True)
            self.assertRaises(ceilometer.NotImplementedError,
                              lambda: list(conn.get_meters(**kwargs)))

    @mock.patch("ceilometer.storage.impl_monasca.MonascaDataFilter")
    def test_metrics_list_call(self, mock_mdf):
        with mock.patch('ceilometer.monasca_client.Client') as mock_client:
            conn = impl_monasca.Connection('127.0.0.1:8080')
            metrics_list_mock = mock_client().metrics_list

            kwargs = dict(user='user-1',
                          project='project-1',
                          resource='resource-1',
                          source='openstack',
                          limit=100)

            list(conn.get_meters(**kwargs))

            self.assertEqual(True, metrics_list_mock.called)
            self.assertEqual(1, metrics_list_mock.call_count)
            self.assertEqual(dict(dimensions=dict(user_id='user-1',
                                                  project_id='project-1',
                                                  resource_id='resource-1',
                                                  source='openstack'),
                                  limit=100),
                             metrics_list_mock.call_args[1])


class TestGetSamples(base.BaseTestCase):

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

    def setUp(self):
        super(TestGetSamples, self).setUp()
        self.CONF = self.useFixture(fixture_config.Config()).conf
        self.CONF([], project='ceilometer', validate_default_values=True)

    @mock.patch("ceilometer.storage.impl_monasca.MonascaDataFilter")
    def test_get_samples_not_implemented_params(self, mdf_mock):
        with mock.patch("ceilometer.monasca_client.Client"):
            conn = impl_monasca.Connection("127.0.0.1:8080")

            sample_filter = storage.SampleFilter(meter='specific meter',
                                                 start_timestamp_op='<')
            self.assertRaises(ceilometer.NotImplementedError,
                              lambda: list(conn.get_samples(sample_filter)))

            sample_filter = storage.SampleFilter(meter='specific meter',
                                                 end_timestamp_op='>')
            self.assertRaises(ceilometer.NotImplementedError,
                              lambda: list(conn.get_samples(sample_filter)))

            sample_filter = storage.SampleFilter(meter='specific meter',
                                                 message_id='specific message')
            self.assertRaises(ceilometer.NotImplementedError,
                              lambda: list(conn.get_samples(sample_filter)))

    @mock.patch("ceilometer.storage.impl_monasca.MonascaDataFilter")
    def test_get_samples_name(self, mdf_mock):
        with mock.patch("ceilometer.monasca_client.Client") as mock_client:
            conn = impl_monasca.Connection("127.0.0.1:8080")
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
                dimensions={},
                start_time='1970-01-01T00:00:00Z',
                merge_metrics=False, name='specific meter',
                end_time='2015-04-20T00:00:00Z'),
                ml_mock.call_args[1])
            self.assertEqual(1, ml_mock.call_count)

    @mock.patch("ceilometer.storage.impl_monasca.MonascaDataFilter")
    def test_get_samples_start_timestamp_filter(self, mdf_mock):
        with mock.patch("ceilometer.monasca_client.Client") as mock_client:
            conn = impl_monasca.Connection("127.0.0.1:8080")

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

    @mock.patch("ceilometer.storage.impl_monasca.MonascaDataFilter")
    def test_get_samples_limit(self, mdf_mock):
        with mock.patch("ceilometer.monasca_client.Client") as mock_client:
            conn = impl_monasca.Connection("127.0.0.1:8080")

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

    @mock.patch("ceilometer.storage.impl_monasca.MonascaDataFilter")
    def test_get_samples_project_filter(self, mock_mdf):
        with mock.patch("ceilometer.monasca_client.Client") as mock_client:
            conn = impl_monasca.Connection("127.0.0.1:8080")
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

    @mock.patch("ceilometer.storage.impl_monasca.MonascaDataFilter")
    def test_get_samples_resource_filter(self, mock_mdf):
        with mock.patch("ceilometer.monasca_client.Client") as mock_client:
            conn = impl_monasca.Connection("127.0.0.1:8080")
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

    @mock.patch("ceilometer.storage.impl_monasca.MonascaDataFilter")
    def test_get_samples_source_filter(self, mdf_mock):
        with mock.patch("ceilometer.monasca_client.Client") as mock_client:
            conn = impl_monasca.Connection("127.0.0.1:8080")
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

    @mock.patch("ceilometer.storage.impl_monasca.MonascaDataFilter")
    def test_get_samples_simple_metaquery(self, mdf_mock):
        with mock.patch("ceilometer.monasca_client.Client") as mock_client:
            conn = impl_monasca.Connection("127.0.0.1:8080")
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

    @mock.patch("ceilometer.storage.impl_monasca.MonascaDataFilter")
    def test_get_samples_results(self, mdf_mock):
        with mock.patch("ceilometer.monasca_client.Client") as mock_client:
            conn = impl_monasca.Connection("127.0.0.1:8080")
            metrics_list_mock = mock_client().metrics_list
            metrics_list_mock.return_value = (
                [{u'dimensions': {
                    'source': 'some source',
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
                meter='specific meter',
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


class _BaseTestCase(base.BaseTestCase):
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


class MeterStatisticsTest(_BaseTestCase):

    Aggregate = collections.namedtuple("Aggregate", ['func', 'param'])

    @mock.patch("ceilometer.storage.impl_monasca.MonascaDataFilter")
    def test_not_implemented_params(self, mock_mdf):
        with mock.patch("ceilometer.monasca_client.Client"):
            conn = impl_monasca.Connection("127.0.0.1:8080")

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

    @mock.patch("ceilometer.storage.impl_monasca.MonascaDataFilter")
    def test_stats_list_called_with(self, mock_mdf):
        with mock.patch("ceilometer.monasca_client.Client") as mock_client:
            conn = impl_monasca.Connection("127.0.0.1:8080")
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
                                'resource_id': 'resource_id'
                                },
                 'start_time': '1970-01-01T00:00:00Z',
                 'period': 10,
                 'statistics': 'min',
                 'name': 'image'
                 },
                sl_mock.call_args[1]
            )

    @mock.patch("ceilometer.storage.impl_monasca.MonascaDataFilter")
    def test_stats_list(self, mock_mdf):
        with mock.patch("ceilometer.monasca_client.Client") as mock_client:
            conn = impl_monasca.Connection("127.0.0.1:8080")
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

    @mock.patch("ceilometer.storage.impl_monasca.MonascaDataFilter")
    def test_stats_list_with_groupby(self, mock_mdf):
        with mock.patch("ceilometer.monasca_client.Client") as mock_client:
            conn = impl_monasca.Connection("127.0.0.1:8080")
            ml_mock = mock_client().metrics_list
            ml_mock.return_value = [
                {
                    'name': 'image',
                    'dimensions': {'project_id': '1234'}
                },
                {
                    'name': 'image',
                    'dimensions': {'project_id': '5678'}
                }
            ]

            sl_mock = mock_client().statistics_list
            sl_mock.side_effect = [[
                {
                    'statistics':
                        [
                            ['2014-10-24T12:12:12Z', 0.008, 1.3, 3, 0.34],
                            ['2014-10-24T12:20:12Z', 0.078, 1.25, 2, 0.21],
                            ['2014-10-24T12:52:12Z', 0.018, 0.9, 4, 0.14]
                        ],
                    'dimensions': {'project_id': '1234', 'unit': 'gb'},
                    'columns': ['timestamp', 'min', 'max', 'count', 'avg']
                }],
                [{
                    'statistics':
                        [
                            ['2014-10-24T12:14:12Z', 0.45, 2.5, 2, 2.1],
                            ['2014-10-24T12:20:12Z', 0.58, 3.2, 3, 3.4],
                            ['2014-10-24T13:52:42Z', 1.67, 3.5, 1, 5.3]
                        ],
                    'dimensions': {'project_id': '5678', 'unit': 'gb'},
                    'columns': ['timestamp', 'min', 'max', 'count', 'avg']
                }]]

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
    def setUp(self):
        super(TestQuerySamples, self).setUp()
        self.CONF = self.useFixture(fixture_config.Config()).conf
        self.CONF([], project='ceilometer', validate_default_values=True)

    @mock.patch("ceilometer.storage.impl_monasca.MonascaDataFilter")
    def test_query_samples_not_implemented_params(self, mdf_mock):
        with mock.patch("ceilometer.monasca_client.Client"):
            conn = impl_monasca.Connection("127.0.0.1:8080")
            query = {'or': [{'=': {"project_id": "123"}},
                            {'=': {"user_id": "456"}}]}

            self.assertRaisesWithMessage(
                'fitler must be specified',
                ceilometer.NotImplementedError,
                lambda: list(conn.query_samples()))
            self.assertRaisesWithMessage(
                'limit must be specified',
                ceilometer.NotImplementedError,
                lambda: list(conn.query_samples(query)))
            order_by = [{"timestamp": "desc"}]
            self.assertRaisesWithMessage(
                'orderby is not supported',
                ceilometer.NotImplementedError,
                lambda: list(conn.query_samples(query, order_by)))
            self.assertRaisesWithMessage(
                'Supply meter name at the least',
                ceilometer.NotImplementedError,
                lambda: list(conn.query_samples(query, None, 1)))

    @mock.patch("ceilometer.storage.impl_monasca.MonascaDataFilter")
    def test_query_samples(self, mdf_mock):
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
            conn = impl_monasca.Connection("127.0.0.1:8080")
            with mock.patch.object(conn, 'get_samples') as gsm:
                gsm.side_effect = _get_samples

                query = {'or': [{'=': {"project_id": "123"}},
                                {'=': {"user_id": "456"}}]}
                samples = conn.query_samples(query, None, 100)
                self.assertEqual(2, len(samples))
                self.assertEqual(2, gsm.call_count)

                samples = SAMPLES[:]
                query = {'and': [{'=': {"project_id": "123"}},
                                 {'>': {"counter_volume": 2}}]}
                samples = conn.query_samples(query, None, 100)
                self.assertEqual(0, len(samples))
                self.assertEqual(3, gsm.call_count)


class CapabilitiesTest(base.BaseTestCase):

    def test_capabilities(self):
        expected_capabilities = {
            'meters':
                {
                    'query':
                        {
                            'complex': False,
                            'metadata': False,
                            'simple': True
                        }
                },
            'resources':
                {
                    'query':
                        {
                            'complex': False, 'metadata': True, 'simple': True
                        }
                },
            'samples':
                {
                    'groupby': False,
                    'pagination': False,
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
                            'complex': False,
                            'metadata': False,
                            'simple': True
                        }
                }
        }

        actual_capabilities = impl_monasca.Connection.get_capabilities()
        self.assertEqual(expected_capabilities, actual_capabilities)
