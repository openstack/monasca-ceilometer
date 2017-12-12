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

"""Static mapping for Ceilometer static info like unit and type information
"""

import os
import pkg_resources
import yaml

from oslo_log import log

from ceilometer import sample

LOG = log.getLogger(__name__)


class CeilometerStaticMappingDefinitionException(Exception):
    def __init__(self, message, definition_cfg):
        super(CeilometerStaticMappingDefinitionException,
              self).__init__(message)
        self.message = message
        self.definition_cfg = definition_cfg

    def __str__(self):
        return '%s %s: %s' % (self.__class__.__name__,
                              self.definition_cfg, self.message)


class CeilometerStaticMappingDefinition(object):
    REQUIRED_FIELDS = ['name', 'type', 'unit']

    def __init__(self, definition_cfg):
        self.cfg = definition_cfg
        missing = [field for field in self.REQUIRED_FIELDS
                   if not self.cfg.get(field)]
        if missing:
            raise CeilometerStaticMappingDefinitionException(
                "Required fields %s not specified" % missing, self.cfg)

        if ('type' not in self.cfg.get('lookup', []) and
                self.cfg['type'] not in sample.TYPES):
            raise CeilometerStaticMappingDefinitionException(
                "Invalid type %s specified" % self.cfg['type'], self.cfg)


def get_config_file(conf):
    config_file = conf.monasca.ceilometer_static_info_mapping
    if not os.path.exists(config_file):
        config_file = conf.find_file(config_file)
    if not config_file:
        config_file = pkg_resources.resource_filename(
            __name__, "data/ceilometer_static_info_mapping.yaml")
    return config_file


def setup_ceilometer_static_mapping_config(conf):
    """Setup the meters definitions from yaml config file."""
    config_file = get_config_file(conf)
    if config_file is not None:
        LOG.debug("Static Ceilometer mapping file to map static info: %s",
                  config_file)

        with open(config_file) as cf:
            config = cf.read()

        try:
            ceilometer_static_mapping_config = yaml.safe_load(config)
        except yaml.YAMLError as err:
            if hasattr(err, 'problem_mark'):
                mark = err.problem_mark
                errmsg = ("Invalid YAML syntax in static Ceilometer "
                          "Mapping Definitions file %(file)s at line: "
                          "%(line)s, column: %(column)s."
                          % dict(file=config_file,
                                 line=mark.line + 1,
                                 column=mark.column + 1))
            else:
                errmsg = ("YAML error reading static Ceilometer Mapping "
                          "Definitions file %(file)s" %
                          dict(file=config_file))

            LOG.error(errmsg)
            raise

    else:
        LOG.debug("No static Ceilometer Definitions configuration file "
                  "found! using default config.")
        ceilometer_static_mapping_config = {}

    LOG.debug("Ceilometer Monasca Definitions: %s",
              ceilometer_static_mapping_config)

    return ceilometer_static_mapping_config


def load_definitions(config_def):
    if not config_def:
        return []
    ceilometer_static_mapping_defs = {}
    for meter_info_static_map in reversed(config_def['meter_info_static_map']):
        if meter_info_static_map.get('name') in ceilometer_static_mapping_defs:
            # skip duplicate meters
            LOG.warning("Skipping duplicate Ceilometer Monasca Mapping"
                        " Definition %s" % meter_info_static_map)
            continue

        try:
            md = CeilometerStaticMappingDefinition(meter_info_static_map)
            ceilometer_static_mapping_defs[meter_info_static_map['name']] = md
        except CeilometerStaticMappingDefinitionException as me:
            errmsg = ("Error loading Ceilometer Static Mapping "
                      "Definition : %(err)s" % dict(err=me.message))
            LOG.error(errmsg)
    return ceilometer_static_mapping_defs.values()


class ProcessMappedCeilometerStaticInfo(object):
    """Implentation for class to provide static info for ceilometer meters

    The class will be responsible for providing the static information of
    ceilometer meters enabled using pipeline.yaml configuration.
    get_list_supported_meters: is a get function which can be used to get
                               list of pipeline meters.
    get_ceilometer_meter_static_definition: returns entire definition for
                                            provided meter name
    get_meter_static_info_key_val: returns specific value for provided meter
                                   name and a particular key from definition
    """
    _inited = False
    _instance = None

    def __new__(cls, *args, **kwargs):
        """Singleton to avoid duplicated initialization."""
        if not cls._instance:
            cls._instance = super(ProcessMappedCeilometerStaticInfo, cls).\
                __new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self, conf):
        if not (self._instance and self._inited):
            self.conf = conf
            self._inited = True
            self.__definitions = load_definitions(
                setup_ceilometer_static_mapping_config(self.conf))
            self.__mapped_meter_info_map = dict()
            for d in self.__definitions:
                self.__mapped_meter_info_map[d.cfg['name']] = d

    def get_list_supported_meters(self):
        return self.__mapped_meter_info_map

    def get_ceilometer_meter_static_definition(self, meter_name):
        return self.__mapped_meter_info_map.get(meter_name)

    def get_meter_static_info_key_val(self, meter_name, key):
        return self.__mapped_meter_info_map.get(meter_name).cfg[key]

    def reinitialize(self, conf):
        self.conf = conf
        self.__definitions = load_definitions(
            setup_ceilometer_static_mapping_config(self.conf))
        self.__mapped_meter_info_map = dict()
        for d in self.__definitions:
            self.__mapped_meter_info_map[d.cfg['name']] = d
