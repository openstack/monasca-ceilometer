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

import os

import fixtures
import mock
# from oslo_config import fixture as fixture_config
from oslo_utils import fileutils
from oslotest import base
import six
import yaml

from ceilometer.ceilosca_mapping import ceilometer_static_info_mapping
from ceilometer.ceilosca_mapping.ceilometer_static_info_mapping import (
    CeilometerStaticMappingDefinition)
from ceilometer.ceilosca_mapping.ceilometer_static_info_mapping import (
    CeilometerStaticMappingDefinitionException)
from ceilometer import monasca_ceilometer_opts
from ceilometer import service
from ceilometer.storage import impl_monasca


class TestStaticInfoBase(base.BaseTestCase):
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
                    'meter_info_static_map': [{
                        'name': "disk.ephemeral.size",
                        'type': "gauge",
                        'unit': "GB"
                        }, {
                        'name': "image.delete",
                        'type': "delta",
                        'unit': "image"
                        }, {
                        'name': "image",
                        'type': "gauge",
                        'unit': "image"
                        }, {
                        'name': "disk.root.size",
                        'type': "gauge",
                        'unit': "GB"
                        }
                    ]
                    })
    ceilosca_cfg = yaml.dump({
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
            }]
        })

    def setup_static_mapping_def_file(self, cfg):
        if six.PY3:
            cfg = cfg.encode('utf-8')
        ceilometer_static_info_mapping = fileutils.write_to_tempfile(
            content=cfg, prefix='ceilometer_static_info_mapping', suffix='yaml'
        )
        self.addCleanup(os.remove, ceilometer_static_info_mapping)
        return ceilometer_static_info_mapping

    def setup_ceilosca_mapping_def_file(self, ceilosca_cfg):
        if six.PY3:
            ceilosca_cfg = ceilosca_cfg.encode('utf-8')
        ceilosca_mapping_file = fileutils.write_to_tempfile(
            content=ceilosca_cfg, prefix='ceilosca_mapping', suffix='yaml')
        self.addCleanup(os.remove, ceilosca_mapping_file)
        return ceilosca_mapping_file

    def setup_pipeline_file(self, pipeline_data):
        if six.PY3:
            pipeline_data = pipeline_data.encode('utf-8')
        pipeline_cfg_file = fileutils.write_to_tempfile(content=pipeline_data,
                                                        prefix="pipeline",
                                                        suffix="yaml")
        self.addCleanup(os.remove, pipeline_cfg_file)
        return pipeline_cfg_file


class TestStaticInfoDefinition(base.BaseTestCase):

    def test_static_info_definition(self):
        cfg = dict(name="image.delete",
                   type="delta",
                   unit="image")
        handler = CeilometerStaticMappingDefinition(cfg)
        self.assertEqual("delta", handler.cfg['type'])
        self.assertEqual("image.delete", handler.cfg['name'])
        self.assertEqual("image", handler.cfg['unit'])

    def test_config_required_missing_fields(self):
        cfg = dict()
        try:
            CeilometerStaticMappingDefinition(cfg)
        except CeilometerStaticMappingDefinitionException as e:
            self.assertEqual("Required fields ["
                             "'name', 'type', 'unit'] "
                             "not specified", e.message)

    def test_bad_type_cfg_definition(self):
        cfg = dict(name="fake_meter",
                   type="foo",
                   unit="B/s")
        try:
            CeilometerStaticMappingDefinition(cfg)
        except CeilometerStaticMappingDefinitionException as e:
            self.assertEqual("Invalid type foo specified", e.message)


class TestMappedCeilometerStaticInfoProcessing(TestStaticInfoBase):

    def setUp(self):
        super(TestMappedCeilometerStaticInfoProcessing, self).setUp()
        # self.CONF = self.useFixture(fixture_config.Config()).conf
        self.CONF = service.prepare_service([], [])
        self.CONF.register_opts(list(monasca_ceilometer_opts.OPTS),
                                'monasca')
        static_info_mapping_file = self.setup_static_mapping_def_file(self.cfg)
        self.CONF.set_override('ceilometer_static_info_mapping',
                               static_info_mapping_file, group='monasca')
        self.static_info_mapper = ceilometer_static_info_mapping\
            .ProcessMappedCeilometerStaticInfo(self.CONF)
        # self.CONF([], project='ceilometer', validate_default_values=True)

    def test_fallback_mapping_file_path(self):
        self.useFixture(fixtures.MockPatchObject(self.CONF,
                                                 'find_file',
                                                 return_value=None))
        self.CONF.set_override('ceilometer_static_info_mapping',
                               ' ', group='monasca')
        self.static_info_mapper.reinitialize(self.CONF)
        fall_bak_path = ceilometer_static_info_mapping.get_config_file(
            self.CONF)
        self.assertIn(
            "ceilosca_mapping/data/ceilometer_static_info_mapping.yaml",
            fall_bak_path)

    @mock.patch(
        'ceilometer.ceilosca_mapping.ceilometer_static_info_mapping.LOG')
    def test_bad_mapping_definition_skip(self, LOG):
        cfg = yaml.dump({
            'meter_info_static_map': [{
                'name': "disk.ephemeral.size",
                'type': "gauge",
                'unit': "GB"
                }, {
                'name': "image.delete",
                'type': "delta",
                'unit': "image"
                }, {
                'name': "image",
                'type': "gauge",
                'unit': "image"
                }, {
                'name': "disk.root.size",
                'type': "foo",
                'unit': "GB"
                }]
        })
        static_info_mapping_file = self.setup_static_mapping_def_file(cfg)
        self.CONF.set_override('ceilometer_static_info_mapping',
                               static_info_mapping_file, group='monasca')
        data = ceilometer_static_info_mapping.\
            setup_ceilometer_static_mapping_config(self.CONF)
        meter_loaded = ceilometer_static_info_mapping.load_definitions(data)
        self.assertEqual(3, len(meter_loaded))
        LOG.error.assert_called_with(
            "Error loading Ceilometer Static Mapping Definition : "
            "Invalid type foo specified")

    def test_list_of_meters_returned(self):
        self.static_info_mapper.reinitialize(self.CONF)
        self.assertItemsEqual(['disk.ephemeral.size', 'disk.root.size',
                               'image', 'image.delete'],
                              self.static_info_mapper.
                              get_list_supported_meters().
                              keys()
                              )

    def test_static_info_of_ceilometer_meter(self):
        cfg = yaml.dump({
            'meter_info_static_map': [{
                'name': "disk.ephemeral.size",
                'type': "gauge",
                'unit': "GB"
                }]
        })
        static_info_mapping_file = self.setup_static_mapping_def_file(cfg)
        self.CONF.set_override('ceilometer_static_info_mapping',
                               static_info_mapping_file, group='monasca')
        self.static_info_mapper.reinitialize(self.CONF)
        self.assertEqual('gauge',
                         self.static_info_mapper.get_meter_static_info_key_val(
                             'disk.ephemeral.size', 'type')
                         )


# This Class will only test the driver for the mapped static info
# Impl_Monasca Tests will be doing exhaustive tests for other test cases
@mock.patch("ceilometer.storage.impl_monasca.MonascaDataFilter")
class TestMoanscaDriverForMappedStaticInfo(TestStaticInfoBase):

    def setUp(self):
        super(TestMoanscaDriverForMappedStaticInfo, self).setUp()
        # self.CONF = self.useFixture(fixture_config.Config()).conf
        # self.CONF([], project='ceilometer', validate_default_values=True)
        self.CONF = service.prepare_service([], [])
        self.CONF.register_opts(list(monasca_ceilometer_opts.OPTS),
                                'monasca')
        pipeline_cfg_file = self.setup_pipeline_file(self.pipeline_data)
        self.CONF.set_override("pipeline_cfg_file", pipeline_cfg_file)
        static_info_mapping_file = self.setup_static_mapping_def_file(self.cfg)
        self.CONF.set_override('ceilometer_static_info_mapping',
                               static_info_mapping_file, group='monasca')
        ceilosca_mapping_file = self.setup_ceilosca_mapping_def_file(
            self.ceilosca_cfg)
        self.CONF.set_override('ceilometer_monasca_metrics_mapping',
                               ceilosca_mapping_file, group='monasca')
        self.static_info_mapper = ceilometer_static_info_mapping\
            .ProcessMappedCeilometerStaticInfo(self.CONF)
        self.static_info_mapper.reinitialize(self.CONF)

    def test_get_statc_info_for_mapped_meters_uniq(self, mdf_mock):
        dummy_metric_names_mocked_return_value = (
            [{"id": "015c995b1a770147f4ef18f5841ef566ab33521d",
              "name": "image"},
             {"id": "335b5d569ad29dc61b3dc24609fad3619e947944",
              "name": "fake_metric"}])

        with mock.patch('ceilometer.monasca_client.Client') as mock_client:
            conn = impl_monasca.Connection(self.CONF, '127.0.0.1:8080')
            metric_names_list_mock = mock_client().metric_names_list
            metric_names_list_mock.return_value = (
                dummy_metric_names_mocked_return_value
            )

            kwargs = dict(limit=4,
                          unique=True)
            results = list(conn.get_meters(**kwargs))
            self.assertEqual(2, len(results))
            self.assertEqual(True, metric_names_list_mock.called)
            self.assertEqual(1, metric_names_list_mock.call_count)
