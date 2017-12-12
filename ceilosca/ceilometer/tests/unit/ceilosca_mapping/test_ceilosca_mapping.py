#
# Copyright 2016 Hewlett Packard
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
import os

import fixtures
import mock
from oslo_utils import fileutils
from oslo_utils import timeutils
from oslotest import base
import six
import yaml

from ceilometer.ceilosca_mapping import ceilosca_mapping
from ceilometer.ceilosca_mapping.ceilosca_mapping import (
    CeiloscaMappingDefinition)
from ceilometer.ceilosca_mapping.ceilosca_mapping import (
    CeiloscaMappingDefinitionException)
from ceilometer.ceilosca_mapping.ceilosca_mapping import PipelineReader
from ceilometer import monasca_ceilometer_opts
from ceilometer import service
from ceilometer import storage
from ceilometer.storage import impl_monasca
from ceilometer.storage import models as storage_models

MONASCA_MEASUREMENT = {
    "id": "fef26f9d27f8027ea44b940cf3626fc398f7edfb",
    "name": "fake_metric",
    "dimensions": {
        "resource_id": "2fe6e3a9-9bdf-4c98-882c-a826cf0107a1",
        "cloud_name": "helion-poc-hlm-003",
        "component": "vm",
        "control_plane": "control-plane-1",
        "service": "compute",
        "device": "tap3356676e-a5",
        "tenant_id": "50ce24dd577c43879cede72b77224e2f",
        "hostname": "hlm003-cp1-comp0003-mgmt",
        "cluster": "compute",
        "zone": "nova"
    },
    "columns": ["timestamp", "value", "value_meta"],
    "measurements": [["2016-05-23T22:22:42.000Z", 54.0, {
        "audit_period_ending": "None",
        "audit_period_beginning": "None",
        "host": "network.hlm003-cp1-c1-m2-mgmt",
        "availability_zone": "None",
        "event_type": "subnet.create.end",
        "enable_dhcp": "true",
        "gateway_ip": "10.43.0.1",
        "ip_version": "4",
        "cidr": "10.43.0.0/28"}]]
}

MONASCA_VALUE_META = {
    'audit_period_beginning': 'None',
    'audit_period_ending': 'None',
    'availability_zone': 'None',
    'cidr': '10.43.0.0/28',
    'enable_dhcp': 'true',
    'event_type': 'subnet.create.end',
    'gateway_ip': '10.43.0.1',
    'host': 'network.hlm003-cp1-c1-m2-mgmt',
    'ip_version': '4'
}


class TestCeiloscaMapping(base.BaseTestCase):
    pipeline_data = yaml.dump({
        'sources': [{
            'name': 'test_pipeline',
            'interval': 1,
            'meters': ['testbatch', 'testbatch2'],
            'resources': ['alpha', 'beta', 'gamma', 'delta'],
            'sinks': ['test_sink']}],
        'sinks': [{
            'name': 'test_sink',
            'transformers': [],
            'publishers': ["test"]}]
    })

    cfg = yaml.dump({
                    'meter_metric_map': [{
                        'user_id': '$.dimensions.user_id',
                        'name': 'fake_meter',
                        'resource_id': '$.dimensions.resource_id',
                        'region': 'NA',
                        'monasca_metric_name': 'fake_metric',
                        'source': 'NA',
                        'project_id': '$.dimensions.tenant_id',
                        'type': 'gauge',
                        'resource_metadata': '$.measurements[0][2]',
                        'unit': 'B/s'
                    }, {
                        'user_id': '$.dimensions.user_id',
                        'name': 'fake_meter2',
                        'resource_id': '$.dimensions.resource_id',
                        'region': 'NA',
                        'monasca_metric_name': 'fake_metric2',
                        'source': 'NA',
                        'project_id': '$.dimensions.project_id',
                        'type': 'delta',
                        'resource_metadata': '$.measurements[0][2]',
                        'unit': 'B/s'
                    }, {
                        'user_id': '$.dimensions.user_id',
                        'name': 'fake_meter3',
                        'resource_id': '$.dimensions.hostname',
                        'region': 'NA',
                        'monasca_metric_name': 'fake_metric3',
                        'source': 'NA',
                        'project_id': '$.dimensions.project_id',
                        'type': 'delta',
                        'resource_metadata': '$.measurements[0][2]',
                        'unit': 'B/s'
                        }
                    ]
                    })

    def setup_pipeline_file(self, pipeline_data):
        if six.PY3:
            pipeline_data = pipeline_data.encode('utf-8')
        pipeline_cfg_file = fileutils.write_to_tempfile(content=pipeline_data,
                                                        prefix="pipeline",
                                                        suffix="yaml")
        self.addCleanup(os.remove, pipeline_cfg_file)
        return pipeline_cfg_file

    def setup_ceilosca_mapping_def_file(self, cfg):
        if six.PY3:
            cfg = cfg.encode('utf-8')
        ceilosca_mapping_file = fileutils.write_to_tempfile(
            content=cfg, prefix='ceilosca_mapping', suffix='yaml')
        self.addCleanup(os.remove, ceilosca_mapping_file)
        return ceilosca_mapping_file


class TestGetPipelineReader(TestCeiloscaMapping):

    def setUp(self):
        super(TestGetPipelineReader, self).setUp()
        self.CONF = service.prepare_service([], [])
        self.CONF.register_opts(list(monasca_ceilometer_opts.OPTS),
                                'monasca')

    def test_pipeline_reader(self):
        pipeline_cfg_file = self.setup_pipeline_file(
            self.pipeline_data)
        self.CONF.set_override("pipeline_cfg_file", pipeline_cfg_file)

        test_pipeline_reader = PipelineReader(self.CONF)

        self.assertEqual(set(['testbatch', 'testbatch2']),
                         test_pipeline_reader.get_pipeline_meters()
                         )


class TestMappingDefinition(base.BaseTestCase):

    def test_mapping_definition(self):
        cfg = dict(name="network.outgoing.rate",
                   monasca_metric_name="vm.net.out_bytes_sec",
                   resource_id="$.dimensions.resource_id",
                   project_id="$.dimensions.tenant_id",
                   user_id="$.dimensions.user_id",
                   region="NA",
                   type="gauge",
                   unit="B/s",
                   source="NA",
                   resource_metadata="$.measurements[0][2]")
        handler = CeiloscaMappingDefinition(cfg)
        self.assertIsNone(handler.parse_fields("user_id", MONASCA_MEASUREMENT))
        self.assertEqual("2fe6e3a9-9bdf-4c98-882c-a826cf0107a1",
                         handler.parse_fields("resource_id",
                                              MONASCA_MEASUREMENT))
        self.assertEqual("50ce24dd577c43879cede72b77224e2f",
                         handler.parse_fields("project_id",
                                              MONASCA_MEASUREMENT))
        self.assertEqual(MONASCA_VALUE_META,
                         handler.parse_fields("resource_metadata",
                                              MONASCA_MEASUREMENT))
        self.assertEqual("$.dimensions.tenant_id", handler.cfg["project_id"])

    def test_config_required_missing_fields(self):
        cfg = dict()
        try:
            CeiloscaMappingDefinition(cfg)
        except CeiloscaMappingDefinitionException as e:
            self.assertEqual("Required fields ["
                             "'name', 'monasca_metric_name', 'type', 'unit', "
                             "'source', 'resource_metadata', 'resource_id', "
                             "'project_id', 'user_id', 'region'] "
                             "not specified", e.message)

    def test_bad_type_cfg_definition(self):
        cfg = dict(name="fake_meter",
                   monasca_metric_name="fake_metric",
                   resource_id="$.dimensions.resource_id",
                   project_id="$.dimensions.tenant_id",
                   user_id="$.dimensions.user_id",
                   region="NA",
                   type="foo",
                   unit="B/s",
                   source="NA",
                   resource_metadata="$.measurements[0][2]")
        try:
            CeiloscaMappingDefinition(cfg)
        except CeiloscaMappingDefinitionException as e:
            self.assertEqual("Invalid type foo specified", e.message)


class TestMappedCeiloscaMetricProcessing(TestCeiloscaMapping):

    def setUp(self):
        super(TestMappedCeiloscaMetricProcessing, self).setUp()

        self.CONF = service.prepare_service([], [])
        self.CONF.register_opts(list(monasca_ceilometer_opts.OPTS),
                                'monasca')

    def test_fallback_mapping_file_path(self):
        self.useFixture(fixtures.MockPatchObject(self.CONF,
                                                 'find_file',
                                                 return_value=None))
        fall_bak_path = ceilosca_mapping.get_config_file(self.CONF)
        self.assertIn("ceilosca_mapping/data/ceilosca_mapping.yaml",
                      fall_bak_path)

    @mock.patch('ceilometer.ceilosca_mapping.ceilosca_mapping.LOG')
    def test_bad_meter_definition_skip(self, LOG):
        cfg = yaml.dump({
                        'meter_metric_map': [{
                            'user_id': '$.dimensions.user_id',
                            'name': 'fake_meter',
                            'resource_id': '$.dimensions.resource_id',
                            'region': 'NA',
                            'monasca_metric_name': 'fake_metric',
                            'source': 'NA',
                            'project_id': '$.dimensions.tenant_id',
                            'type': 'gauge',
                            'resource_metadata': '$.measurements[0][2]',
                            'unit': 'B/s'
                        }, {
                            'user_id': '$.dimensions.user_id',
                            'name': 'fake_meter',
                            'resource_id': '$.dimensions.resource_id',
                            'region': 'NA',
                            'monasca_metric_name': 'fake_metric',
                            'source': 'NA',
                            'project_id': '$.dimensions.tenant_id',
                            'type': 'foo',
                            'resource_metadata': '$.measurements[0][2]',
                            'unit': 'B/s'
                        }]
                        })
        ceilosca_mapping_file = self.setup_ceilosca_mapping_def_file(cfg)
        self.CONF.set_override('ceilometer_monasca_metrics_mapping',
                               ceilosca_mapping_file, group='monasca')
        data = ceilosca_mapping.setup_ceilosca_mapping_config(self.CONF)
        meter_loaded = ceilosca_mapping.load_definitions(data)
        self.assertEqual(1, len(meter_loaded))
        LOG.error.assert_called_with(
            "Error loading Ceilometer Monasca Mapping Definition : "
            "Invalid type foo specified")

    def test_list_of_meters_returned(self):
        ceilosca_mapping_file = self.setup_ceilosca_mapping_def_file(self.cfg)
        self.CONF.set_override('ceilometer_monasca_metrics_mapping',
                               ceilosca_mapping_file, group='monasca')
        ceilosca_mapper = ceilosca_mapping\
            .ProcessMappedCeiloscaMetric(self.CONF)
        ceilosca_mapper.reinitialize(self.CONF)
        self.assertItemsEqual(['fake_metric', 'fake_metric2', 'fake_metric3'],
                              ceilosca_mapper.get_list_monasca_metrics().keys()
                              )

    def test_monasca_metric_name_map_ceilometer_meter(self):
        cfg = yaml.dump({
                        'meter_metric_map': [{
                            'user_id': '$.dimensions.user_id',
                            'name': 'fake_meter',
                            'resource_id': '$.dimensions.resource_id',
                            'region': 'NA',
                            'monasca_metric_name': 'fake_metric',
                            'source': 'NA',
                            'project_id': '$.dimensions.tenant_id',
                            'type': 'gauge',
                            'resource_metadata': '$.measurements[0][2]',
                            'unit': 'B/s'
                            }]
                        })
        ceilosca_mapping_file = self.setup_ceilosca_mapping_def_file(cfg)
        self.CONF.set_override('ceilometer_monasca_metrics_mapping',
                               ceilosca_mapping_file, group='monasca')
        ceilosca_mapper = ceilosca_mapping\
            .ProcessMappedCeiloscaMetric(self.CONF)
        ceilosca_mapper.reinitialize(self.CONF)
        self.assertEqual('fake_metric',
                         ceilosca_mapper.get_monasca_metric_name('fake_meter')
                         )
        self.assertEqual('$.dimensions.tenant_id',
                         ceilosca_mapper.
                         get_ceilosca_mapped_definition_key_val('fake_metric',
                                                                'project_id'))


# This Class will only test the driver for the mapped meteric
# Impl_Monasca Tests will be doing exhaustive tests for non mapped metrics
@mock.patch("ceilometer.storage.impl_monasca.MonascaDataFilter")
class TestMoanscaDriverForMappedMetrics(TestCeiloscaMapping):
    Aggregate = collections.namedtuple("Aggregate", ['func', 'param'])

    def setUp(self):

        super(TestMoanscaDriverForMappedMetrics, self).setUp()

        self.CONF = service.prepare_service([], [])
        self.CONF.register_opts(list(monasca_ceilometer_opts.OPTS),
                                'monasca')

        pipeline_cfg_file = self.setup_pipeline_file(self.pipeline_data)
        self.CONF.set_override("pipeline_cfg_file", pipeline_cfg_file)

        ceilosca_mapping_file = self.setup_ceilosca_mapping_def_file(self.cfg)
        self.CONF.set_override('ceilometer_monasca_metrics_mapping',
                               ceilosca_mapping_file, group='monasca')

        ceilosca_mapper = ceilosca_mapping\
            .ProcessMappedCeiloscaMetric(self.CONF)
        ceilosca_mapper.reinitialize(self.CONF)

    def test_get_samples_for_mapped_meters(self, mdf_mock):
        with mock.patch("ceilometer.monasca_client.Client") as mock_client:
            conn = impl_monasca.Connection(self.CONF, "127.0.0.1:8080")
            ml_mock = mock_client().measurements_list
            # TODO(this test case needs more work)
            ml_mock.return_value = ([MONASCA_MEASUREMENT])

            sample_filter = storage.SampleFilter(
                meter='fake_meter',
                start_timestamp='2015-03-20T00:00:00Z')
            results = list(conn.get_samples(sample_filter))
            self.assertEqual(True, ml_mock.called)
            self.assertEqual('fake_meter', results[0].counter_name)
            self.assertEqual(54.0, results[0].counter_volume)
            self.assertEqual('gauge', results[0].counter_type)
            self.assertEqual('2fe6e3a9-9bdf-4c98-882c-a826cf0107a1',
                             results[0].resource_id
                             )
            self.assertEqual(MONASCA_VALUE_META, results[0].resource_metadata)
            self.assertEqual('50ce24dd577c43879cede72b77224e2f',
                             results[0].project_id,
                             )
            self.assertEqual('B/s', results[0].counter_unit)
            self.assertIsNone(results[0].user_id)

    def test_get_meter_for_mapped_meters_non_uniq(self, mdf_mock):
        data1 = (
            [{u'dimensions': {u'datasource': u'ceilometer'},
              u'id': u'2015-04-14T18:42:31Z',
              u'name': u'meter-1'},
             {u'dimensions': {u'datasource': u'ceilometer'},
              u'id': u'2015-04-15T18:42:31Z',
              u'name': u'meter-1'}])
        data2 = (
            [{u'dimensions': {u'datasource': u'ceilometer'},
              u'id': u'2015-04-14T18:42:31Z',
              u'name': u'meter-1'},
             {u'dimensions': {u'datasource': u'ceilometer'},
              u'id': u'2015-04-15T18:42:31Z',
              u'name': u'meter-1'},
             {u'id': u'fef26f9d27f8027ea44b940cf3626fc398f7edfb',
              u'name': u'fake_metric',
              u'dimensions': {
                  u'resource_id': u'2fe6e3a9-9bdf-4c98-882c-a826cf0107a1',
                  u'cloud_name': u'helion-poc-hlm-003',
                  u'component': u'vm',
                  u'control_plane': u'control-plane-1',
                  u'service': u'compute',
                  u'device': u'tap3356676e-a5',
                  u'tenant_id': u'50ce24dd577c43879cede72b77224e2f',
                  u'hostname': u'hlm003-cp1-comp0003-mgmt',
                  u'cluster': u'compute',
                  u'zone': u'nova'}
              },
             {u'dimensions': {},
              u'id': u'2015-04-16T18:42:31Z',
              u'name': u'testbatch'}])
        with mock.patch("ceilometer.monasca_client.Client") as mock_client:
            conn = impl_monasca.Connection(self.CONF, "127.0.0.1:8080")
            metrics_list_mock = mock_client().metrics_list
            metrics_list_mock.side_effect = [data1, data2]
            kwargs = dict(limit=4)

            results = list(conn.get_meters(**kwargs))
            # result contains 2 records from data 1 since datasource
            # = ceilometer, 2 records from data 2, 1 for pipeline
            # meter but no datasource set to ceilometer  and one for
            # mapped meter
            self.assertEqual(4, len(results))
            self.assertEqual(True, metrics_list_mock.called)
            self.assertEqual(2, metrics_list_mock.call_count)

    def test_get_meter_for_mapped_meters_uniq(self, mdf_mock):
        dummy_metric_names_mocked_return_value = (
            [{"id": "015c995b1a770147f4ef18f5841ef566ab33521d",
              "name": "network.delete"},
             {"id": "335b5d569ad29dc61b3dc24609fad3619e947944",
              "name": "subnet.update"}])
        with mock.patch("ceilometer.monasca_client.Client") as mock_client:
            conn = impl_monasca.Connection(self.CONF, "127.0.0.1:8080")
            metric_names_list_mock = mock_client().metric_names_list
            metric_names_list_mock.return_value = (
                dummy_metric_names_mocked_return_value)
            kwargs = dict(limit=4, unique=True)
            results = list(conn.get_meters(**kwargs))
            self.assertEqual(2, len(results))
            self.assertEqual(True, metric_names_list_mock.called)
            self.assertEqual(1, metric_names_list_mock.call_count)

    def test_stats_list_mapped_meters(self, mock_mdf):
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
            sf.meter = "fake_meter"
            aggregate = self.Aggregate(func="min", param=None)
            sf.start_timestamp = timeutils.parse_isotime(
                '2014-10-24T12:12:42').replace(tzinfo=None)
            stats = list(conn.get_meter_statistics(sf, aggregate=[aggregate],
                                                   period=30))
            self.assertEqual(2, len(stats))
            self.assertEqual('B/s', stats[0].unit)
            self.assertEqual('B/s', stats[1].unit)
            self.assertEqual(0.008, stats[0].min)
            self.assertEqual(0.018, stats[1].min)
            self.assertEqual(30, stats[0].period)
            self.assertEqual('2014-10-24T12:12:42',
                             stats[0].period_end.isoformat())
            self.assertEqual('2014-10-24T12:52:42',
                             stats[1].period_end.isoformat())
            self.assertIsNotNone(stats[0].as_dict().get('aggregate'))
            self.assertEqual({u'min': 0.008}, stats[0].as_dict()['aggregate'])

    def test_get_resources_for_mapped_meters(self, mock_mdf):
        with mock.patch("ceilometer.monasca_client.Client") as mock_client:
            conn = impl_monasca.Connection(self.CONF, "127.0.0.1:8080")
            dummy_metric_names_mocked_return_value = (
                [{"id": "015c995b1a770147f4ef18f5841ef566ab33521d",
                  "name": "fake_metric"},
                 {"id": "335b5d569ad29dc61b3dc24609fad3619e947944",
                  "name": "metric1"}])
            mnl_mock = mock_client().metric_names_list
            mnl_mock.return_value = (
                dummy_metric_names_mocked_return_value)

            dummy_get_resources_mocked_return_value = (
                [{u'dimensions': {u'resource_id': u'abcd'},
                  u'measurements': [[u'2015-04-14T17:52:31Z', 1.0, {}],
                                    [u'2015-04-15T17:52:31Z', 2.0, {}],
                                    [u'2015-04-16T17:52:31Z', 3.0, {}]],
                  u'id': u'2015-04-14T18:42:31Z',
                  u'columns': [u'timestamp', u'value', u'value_meta'],
                  u'name': u'fake_metric'}])

            ml_mock = mock_client().measurements_list
            ml_mock.return_value = (
                dummy_get_resources_mocked_return_value)

            sample_filter = storage.SampleFilter(
                meter='fake_meter', end_timestamp='2015-04-20T00:00:00Z')
            resources = list(conn.get_resources(sample_filter, limit=2))
            self.assertEqual(2, len(resources))
            self.assertEqual(True, ml_mock.called)
            self.assertEqual(1, ml_mock.call_count)
            resources_without_limit = list(conn.get_resources(sample_filter))
            self.assertEqual(3, len(resources_without_limit))

    def test_stats_list_with_groupby_for_mapped_meters(self, mock_mdf):
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
                    'dimensions': {'hostname': '1234', 'unit': 'gb'},
                    'columns': ['timestamp', 'min', 'max', 'count', 'avg']
                },
                {
                    'statistics':
                        [
                            ['2014-10-24T12:14:12Z', 0.45, 2.5, 2, 2.1],
                            ['2014-10-24T12:20:12Z', 0.58, 3.2, 3, 3.4],
                            ['2014-10-24T13:52:42Z', 1.67, 3.5, 1, 5.3]
                        ],
                    'dimensions': {'hostname': '5678', 'unit': 'gb'},
                    'columns': ['timestamp', 'min', 'max', 'count', 'avg']
                }]

            sf = storage.SampleFilter()
            sf.meter = "fake_meter3"
            sf.start_timestamp = timeutils.parse_isotime(
                '2014-10-24T12:12:42').replace(tzinfo=None)
            groupby = ['resource_id']
            stats = list(conn.get_meter_statistics(sf, period=30,
                                                   groupby=groupby))

            self.assertEqual(2, len(stats))

            for stat in stats:
                self.assertIsNotNone(stat.groupby)
                resource_id = stat.groupby.get('resource_id')
                self.assertIn(resource_id, ['1234', '5678'])
                if resource_id == '1234':
                    self.assertEqual(0.008, stat.min)
                    self.assertEqual(1.3, stat.max)
                    self.assertEqual(0.23, stat.avg)
                    self.assertEqual(9, stat.count)
                    self.assertEqual(30, stat.period)
                    self.assertEqual('2014-10-24T12:12:12',
                                     stat.period_start.isoformat())
                if resource_id == '5678':
                    self.assertEqual(0.45, stat.min)
                    self.assertEqual(3.5, stat.max)
                    self.assertEqual(3.6, stat.avg)
                    self.assertEqual(6, stat.count)
                    self.assertEqual(30, stat.period)
                    self.assertEqual('2014-10-24T13:52:42',
                                     stat.period_end.isoformat())

    def test_query_samples_for_mapped_meter(self, mock_mdf):
        SAMPLES = [[
            storage_models.Sample(
                counter_name="fake_meter",
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
                message_signature='', )
        ]] * 2
        samples = SAMPLES[:]

        def _get_samples(*args, **kwargs):
            return samples.pop()

        with mock.patch("ceilometer.monasca_client.Client"):
            conn = impl_monasca.Connection(self.CONF, "127.0.0.1:8080")
            with mock.patch.object(conn, 'get_samples') as gsm:
                gsm.side_effect = _get_samples

                query = {'and': [{'=': {'counter_name': 'fake_meter'}},
                                 {'or': [{'=': {"project_id": "123"}},
                                         {'=': {"user_id": "456"}}]}]}
                samples = conn.query_samples(query, None, 100)
                self.assertEqual(2, len(samples))
                self.assertEqual(2, gsm.call_count)

                samples = SAMPLES[:]
                query = {'and': [{'=': {'counter_name': 'fake_meter'}},
                                 {'or': [{'=': {"project_id": "123"}},
                                         {'>': {"counter_volume": 2}}]}]}
                samples = conn.query_samples(query, None, 100)
                self.assertEqual(1, len(samples))
                self.assertEqual(4, gsm.call_count)
