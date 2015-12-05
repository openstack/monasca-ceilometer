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
import ceilometer.storage as storage
from ceilometer.storage import impl_monasca


class TestGetResources(base.BaseTestCase):
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
            self.assertEqual(dict(dimensions=dict(project_id='proj1')),
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
            list(conn.get_resources(**kwargs))

            ml_mock = mock_client().measurements_list
            self.assertEqual(2, ml_mock.call_count)
            self.assertEqual(dict(dimensions={},
                                  name='metric1',
                                  limit=1,
                                  start_time='1970-01-01T00:00:00Z'),
                             ml_mock.call_args_list[0][1])

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
            list(conn.get_resources(**kwargs))
            ml_mock = mock_client().measurements_list
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
        self.CONF.set_override('query_concurrency_limit', 3, group='monasca')

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

    def get_concurrent_task_args(self, conn, start_time, end_time,
                                 sample_filter, dimensions=None, limit=None):

        delta = ((end_time - start_time) /
                 self.CONF.monasca.query_concurrency_limit)
        expected_args_list = []
        for start, end in impl_monasca.Connection.get_next_time_delta(
                conn, start_time, end_time, delta):
            if limit:
                expected_args_list.append(dict(
                    dimensions=dimensions if dimensions else {},
                    start_time=timeutils.isotime(start),
                    start_timestamp_op=sample_filter.start_timestamp_op,
                    merge_metrics=False, name='specific meter',
                    limit=limit,
                    end_time=timeutils.isotime(end)))
            else:
                expected_args_list.append(dict(
                    dimensions=dimensions if dimensions else {},
                    start_time=timeutils.isotime(start),
                    start_timestamp_op=sample_filter.start_timestamp_op,
                    merge_metrics=False, name='specific meter',
                    end_time=timeutils.isotime(end)))

        return expected_args_list

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

            start_time = datetime.datetime(1970, 1, 1)
            end_time = datetime.datetime(2015, 4, 20)

            sample_filter = storage.SampleFilter(
                meter='specific meter',
                end_timestamp=timeutils.isotime(end_time))

            list(conn.get_samples(sample_filter))
            self.assertEqual(True, ml_mock.called)

            expected_args_list = self.get_concurrent_task_args(
                conn, start_time, end_time, sample_filter)
            self.assertEqual(3, ml_mock.call_count)
            (self.assertIn(call_arg[1], expected_args_list)
             for call_arg in ml_mock.call_args_list)

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
            end_time = datetime.datetime.utcnow()

            sample_filter = storage.SampleFilter(
                meter='specific meter',
                start_timestamp=timeutils.isotime(start_time),
                start_timestamp_op='ge')
            list(conn.get_samples(sample_filter))
            self.assertEqual(True, ml_mock.called)

            expected_args_list = self.get_concurrent_task_args(conn,
                                                               start_time,
                                                               end_time,
                                                               sample_filter)
            self.assertEqual(3, ml_mock.call_count)
            (self.assertIn(call_arg[1], expected_args_list)
             for call_arg in ml_mock.call_args_list)

    @mock.patch("ceilometer.storage.impl_monasca.MonascaDataFilter")
    def test_get_samples_limit(self, mdf_mock):
        with mock.patch("ceilometer.monasca_client.Client") as mock_client:
            conn = impl_monasca.Connection("127.0.0.1:8080")

            metrics_list_mock = mock_client().metrics_list
            metrics_list_mock.return_value = (
                TestGetSamples.dummy_metrics_mocked_return_value
            )
            ml_mock = mock_client().measurements_list
            ml_mock.return_value = (
                TestGetSamples.dummy_get_samples_mocked_return_value)

            start_time = datetime.datetime(1970, 1, 1)
            end_time = datetime.datetime(2015, 4, 20)

            sample_filter = storage.SampleFilter(
                meter='specific meter', end_timestamp='2015-04-20T00:00:00Z')
            list(conn.get_samples(sample_filter, limit=50))
            self.assertEqual(True, ml_mock.called)

            expected_args_list = self.get_concurrent_task_args(conn,
                                                               start_time,
                                                               end_time,
                                                               sample_filter,
                                                               limit=50)

            self.assertEqual(3, ml_mock.call_count)
            (self.assertIn(call_arg[1], expected_args_list)
             for call_arg in ml_mock.call_args_list)

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

            start_time = datetime.datetime(1970, 1, 1)
            end_time = datetime.datetime.utcnow()
            sample_filter = storage.SampleFilter(meter='specific meter',
                                                 project='specific project')
            list(conn.get_samples(sample_filter))
            self.assertEqual(True, ml_mock.called)

            expected_args_list = self.get_concurrent_task_args(
                conn, start_time, end_time, sample_filter,
                dimensions=dict(project_id=sample_filter.project))

            self.assertEqual(3, ml_mock.call_count)
            (self.assertIn(call_arg[1], expected_args_list)
             for call_arg in ml_mock.call_args_list)

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

            start_time = datetime.datetime(1970, 1, 1)
            end_time = datetime.datetime.utcnow()
            sample_filter = storage.SampleFilter(meter='specific meter',
                                                 resource='specific resource')
            list(conn.get_samples(sample_filter))
            self.assertEqual(True, ml_mock.called)

            expected_args_list = self.get_concurrent_task_args(
                conn, start_time, end_time, sample_filter,
                dimensions=dict(resource_id=sample_filter.resource))

            self.assertEqual(3, ml_mock.call_count)
            (self.assertIn(call_arg[1], expected_args_list)
             for call_arg in ml_mock.call_args_list)

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

            start_time = datetime.datetime(1970, 1, 1)
            end_time = datetime.datetime.utcnow()
            sample_filter = storage.SampleFilter(meter='specific meter',
                                                 source='specific source')
            list(conn.get_samples(sample_filter))
            self.assertEqual(True, ml_mock.called)

            expected_args_list = self.get_concurrent_task_args(
                conn, start_time, end_time, sample_filter,
                dimensions=dict(source=sample_filter.source))

            self.assertEqual(3, ml_mock.call_count)
            (self.assertIn(call_arg[1], expected_args_list)
             for call_arg in ml_mock.call_args_list)

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

            start_time = datetime.datetime(1970, 1, 1)
            end_time = datetime.datetime.utcnow()
            sample_filter = storage.SampleFilter(
                meter='specific meter',
                metaquery={'metadata.key': u'value'})
            list(conn.get_samples(sample_filter))
            self.assertEqual(True, ml_mock.called)

            expected_args_list = self.get_concurrent_task_args(
                conn, start_time, end_time, sample_filter)

            self.assertEqual(3, ml_mock.call_count)
            (self.assertIn(call_arg[1], expected_args_list)
             for call_arg in ml_mock.call_args_list)

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

            self.assertEqual(3, ml_mock.call_count)


class MeterStatisticsTest(base.BaseTestCase):

    Aggregate = collections.namedtuple("Aggregate", ['func', 'param'])

    def assertRaisesWithMessage(self, msg, exc_class, func, *args, **kwargs):
        try:
            func(*args, **kwargs)
            self.fail('Expecting %s exception, none raised' %
                      exc_class.__name__)
        except AssertionError:
            raise
        except Exception as e:
            self.assertIsInstance(e, exc_class)
            self.assertEqual(e.message, msg)

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
            self.assertRaisesWithMessage("Groupby not implemented",
                                         ceilometer.NotImplementedError,
                                         lambda: list(
                                             conn.get_meter_statistics(
                                                 sf,
                                                 groupby="resource_id")))

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
            sf.start_timestamp = timeutils.parse_isotime(
                '2014-10-24T12:12:42').replace(tzinfo=None)
            stats = list(conn.get_meter_statistics(sf, period=30))

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
                            'complex': False,
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
