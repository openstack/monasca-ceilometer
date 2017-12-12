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

"""Monasca metric to Ceilometer Meter Mapper
"""

import functools
import os
import pkg_resources
import six
import yaml

from jsonpath_rw_ext import parser
from oslo_log import log

from ceilometer import pipeline
from ceilometer import sample

LOG = log.getLogger(__name__)


class CeiloscaMappingDefinitionException(Exception):
    def __init__(self, message, definition_cfg):
        super(CeiloscaMappingDefinitionException, self).__init__(message)
        self.message = message
        self.definition_cfg = definition_cfg

    def __str__(self):
        return '%s %s: %s' % (self.__class__.__name__,
                              self.definition_cfg, self.message)


class CeiloscaMappingDefinition(object):
    JSONPATH_RW_PARSER = parser.ExtentedJsonPathParser()

    REQUIRED_FIELDS = ['name', 'monasca_metric_name', 'type', 'unit', 'source',
                       'resource_metadata', 'resource_id', 'project_id',
                       'user_id', 'region']

    def __init__(self, definition_cfg):
        self.cfg = definition_cfg
        missing = [field for field in self.REQUIRED_FIELDS
                   if not self.cfg.get(field)]
        if missing:
            raise CeiloscaMappingDefinitionException(
                "Required fields %s not specified" % missing, self.cfg)

        self._monasca_metric_name = self.cfg.get('monasca_metric_name')
        if isinstance(self._monasca_metric_name, six.string_types):
            self._monasca_metric_name = [self._monasca_metric_name]

        if ('type' not in self.cfg.get('lookup', []) and
                self.cfg['type'] not in sample.TYPES):
            raise CeiloscaMappingDefinitionException(
                "Invalid type %s specified" % self.cfg['type'], self.cfg)

        self._field_getter = {}
        for name, field in self.cfg.items():
            if name in ["monasca_metric_name", "lookup"] or not field:
                continue
            elif isinstance(field, six.integer_types):
                self._field_getter[name] = field
            elif isinstance(field, six.string_types) and not \
                    field.startswith('$'):
                self._field_getter[name] = field
            elif isinstance(field, dict) and name == 'resource_metadata':
                meta = {}
                for key, val in field.items():
                    parts = self.parse_jsonpath(val)
                    meta[key] = functools.partial(self._parse_jsonpath_field,
                                                  parts)
                self._field_getter['resource_metadata'] = meta
            else:
                parts = self.parse_jsonpath(field)
                self._field_getter[name] = functools.partial(
                    self._parse_jsonpath_field, parts)

    def parse_jsonpath(self, field):
        try:
            parts = self.JSONPATH_RW_PARSER.parse(field)
        except Exception as e:
            raise CeiloscaMappingDefinitionException(
                "Parse error in JSONPath specification "
                "'%(jsonpath)s': %(err)s"
                % dict(jsonpath=field, err=e), self.cfg)
        return parts

    def parse_fields(self, field, message, all_values=False):
        getter = self._field_getter.get(field)
        if not getter:
            return
        elif isinstance(getter, dict):
            dict_val = {}
            for key, val in getter.items():
                dict_val[key] = val(message, all_values)
            return dict_val
        elif callable(getter):
            return getter(message, all_values)
        else:
            return getter

    @staticmethod
    def _parse_jsonpath_field(parts, message, all_values):
        values = [match.value for match in parts.find(message)
                  if match.value is not None]
        if values:
            if not all_values:
                return values[0]
            return values


def get_config_file(conf):
    config_file = conf.monasca.ceilometer_monasca_metrics_mapping
    if not os.path.exists(config_file):
        config_file = conf.find_file(config_file)
    if not config_file:
        config_file = pkg_resources.resource_filename(
            __name__, "data/ceilosca_mapping.yaml")
    return config_file


def setup_ceilosca_mapping_config(conf):
    """Setup the meters definitions from yaml config file."""
    config_file = get_config_file(conf)
    if config_file is not None:
        LOG.debug("Ceilometer Monasca Mapping Definitions file: %s",
                  config_file)

        with open(config_file) as cf:
            config = cf.read()

        try:
            ceilosca_mapping_config = yaml.safe_load(config)
        except yaml.YAMLError as err:
            if hasattr(err, 'problem_mark'):
                mark = err.problem_mark
                errmsg = ("Invalid YAML syntax in Ceilometer Monasca "
                          "Mapping Definitions file %(file)s at line: "
                          "%(line)s, column: %(column)s."
                          % dict(file=config_file,
                                 line=mark.line + 1,
                                 column=mark.column + 1))
            else:
                errmsg = ("YAML error reading Ceilometer Monasca Mapping "
                          "Definitions file %(file)s" %
                          dict(file=config_file))

            LOG.error(errmsg)
            raise

    else:
        LOG.debug("No Ceilometer Monasca Definitions configuration file "
                  "found! using default config.")
        ceilosca_mapping_config = {}

    LOG.debug("Ceilometer Monasca Definitions: %s",
              ceilosca_mapping_config)

    return ceilosca_mapping_config


def load_definitions(config_def):
    if not config_def:
        return []
    ceilosca_mapping_defs = {}
    for meter_metric_map in reversed(config_def['meter_metric_map']):
        if meter_metric_map.get('name') in ceilosca_mapping_defs:
            # skip duplicate meters
            LOG.warning("Skipping duplicate Ceilometer Monasca Mapping"
                        " Definition %s" % meter_metric_map)
            continue

        try:
            md = CeiloscaMappingDefinition(meter_metric_map)
            ceilosca_mapping_defs[meter_metric_map['name']] = md
        except CeiloscaMappingDefinitionException as me:
            errmsg = ("Error loading Ceilometer Monasca Mapping "
                      "Definition : %(err)s" % dict(err=me.message))
            LOG.error(errmsg)
    return ceilosca_mapping_defs.values()


class ProcessMappedCeiloscaMetric(object):
    """Implentation for managing monasca mapped metrics to ceilometer meters

    The class will be responsible for managing mapped meters and their
    definition. You can use get functions for
    get_monasca_metric_name: get mapped monasca metric name for ceilometer
                             meter name
    get_list_monasca_metrics: get list of mapped metrics with their respective
                              definitions
    get_ceilosca_mapped_metric_definition: get definition of a provided monasca
                                           metric name
    get_ceilosca_mapped_definition_key_val: get respective value of a provided
                                            key from mapping definitions
    The class would be a singleton class
    """
    _inited = False
    _instance = None

    def __new__(cls, *args, **kwargs):
        """Singleton to avoid duplicated initialization."""
        if not cls._instance:
            cls._instance = super(ProcessMappedCeiloscaMetric, cls).__new__(
                cls, *args, **kwargs)
        return cls._instance

    def __init__(self, conf):
        if not (self._instance and self._inited):
            self.conf = conf
            self._inited = True
            self.__definitions = load_definitions(
                setup_ceilosca_mapping_config(self.conf))
            self.__mapped_metric_map = dict()
            self.__mon_metric_to_cm_meter_map = dict()
            for d in self.__definitions:
                self.__mapped_metric_map[d.cfg['monasca_metric_name']] = d
                self.__mon_metric_to_cm_meter_map[d.cfg['name']] = (
                    d.cfg['monasca_metric_name'])

    def get_monasca_metric_name(self, ceilometer_meter_name):
        return self.__mon_metric_to_cm_meter_map.get(ceilometer_meter_name)

    def get_list_monasca_metrics(self):
        return self.__mapped_metric_map

    def get_ceilosca_mapped_metric_definition(self, monasca_metric_name):
        return self.__mapped_metric_map.get(monasca_metric_name)

    def get_ceilosca_mapped_definition_key_val(self, monasca_metric_name, key):
        return self.__mapped_metric_map.get(monasca_metric_name).cfg[key]

    def reinitialize(self, conf):
        self.conf = conf
        self.__definitions = load_definitions(
            setup_ceilosca_mapping_config(self.conf))
        self.__mapped_metric_map = dict()
        self.__mon_metric_to_cm_meter_map = dict()
        for d in self.__definitions:
            self.__mapped_metric_map[d.cfg['monasca_metric_name']] = d
            self.__mon_metric_to_cm_meter_map[d.cfg['name']] = (
                d.cfg['monasca_metric_name'])


class PipelineReader(object):
    """Implentation for class to provide ceilometer meters enabled by pipeline

    The class will be responsible for providing the list of ceilometer meters
    enabled using pipeline.yaml configuration.
    get_pipeline_meters: is a get function which can be used to get list of
                         pipeline meters.
    """
    _inited = False
    _instance = None

    def __new__(cls, *args, **kwargs):
        """Singleton to avoid duplicated initialization."""
        if not cls._instance:
            cls._instance = super(PipelineReader, cls).__new__(
                cls, *args, **kwargs)
        return cls._instance

    def __init__(self, conf):
        if not (self._instance and self._inited):
            self._inited = True
            self.conf = conf
            self.__pipeline_manager = pipeline.setup_pipeline(self.conf)
            self.__meters_from_pipeline = set()
            for pipe in self.__pipeline_manager.pipelines:
                if not isinstance(pipe, pipeline.EventPipeline):
                    for meter in pipe.source.meters:
                        if meter not in self.__meters_from_pipeline:
                            self.__meters_from_pipeline.add(meter)

    def get_pipeline_meters(self):
        return self.__meters_from_pipeline

    def reinitialize(self):
        self.__pipeline_manager = pipeline.setup_pipeline(self.conf)
        self.__meters_from_pipeline = set()
        for pipe in self.__pipeline_manager.pipelines:
            if not isinstance(pipe, pipeline.EventPipeline):
                for meter in pipe.source.meters:
                    if meter not in self.__meters_from_pipeline:
                        self.__meters_from_pipeline.add(meter)
