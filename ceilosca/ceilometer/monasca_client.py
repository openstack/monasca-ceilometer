# Copyright 2015 Hewlett-Packard Company
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

from ceilometer.i18n import _
from monascaclient import client
from monascaclient import exc
from monascaclient import ksclient
from oslo_config import cfg
from oslo_log import log

monclient_opts = [
    cfg.StrOpt('clientapi_version',
               default='2_0',
               help='Version of Monasca client to use while publishing.'),
]

cfg.CONF.register_opts(monclient_opts, group='monasca')
cfg.CONF.import_group('service_credentials', 'ceilometer.keystone_client')

LOG = log.getLogger(__name__)


class MonascaServiceException(Exception):
    pass


class MonascaInvalidServiceCredentialsException(Exception):
    pass


class MonascaInvalidParametersException(Exception):
    code = 400


class Client(object):
    """A client which gets information via python-monascaclient."""

    def __init__(self, parsed_url):
        conf = cfg.CONF.service_credentials
        if not conf.username or not conf.password or \
                not conf.auth_url:
            err_msg = _("No user name or password or auth_url "
                        "found in service_credentials")
            LOG.error(err_msg)
            raise MonascaInvalidServiceCredentialsException(err_msg)

        kwargs = {
            'username': conf.username,
            'password': conf.password,
            'auth_url': conf.auth_url + "/v3",
            'project_id': conf.project_id,
            'project_name': conf.project_name,
            'region_name': conf.region_name,
        }

        self._kwargs = kwargs
        self._endpoint = "http:" + parsed_url.path
        LOG.info(_("monasca_client: using %s as monasca end point") %
                 self._endpoint)
        self._refresh_client()

    def _refresh_client(self):
        _ksclient = ksclient.KSClient(**self._kwargs)

        self._kwargs['token'] = _ksclient.token
        self._mon_client = client.Client(cfg.CONF.monasca.clientapi_version,
                                         self._endpoint, **self._kwargs)

    def call_func(self, func, **kwargs):
        try:
            return func(**kwargs)
        except (exc.HTTPInternalServerError,
                exc.HTTPServiceUnavailable,
                exc.HTTPBadGateway,
                exc.CommunicationError) as e:
            LOG.exception(e)
            raise MonascaServiceException(e.message)
        except exc.HTTPUnProcessable as e:
            LOG.exception(e)
            raise MonascaInvalidParametersException(e.message)
        except Exception as e:
            LOG.exception(e)
            raise

    def metrics_create(self, **kwargs):
        return self.call_func(self._mon_client.metrics.create,
                              **kwargs)

    def metrics_list(self, **kwargs):
        return self.call_func(self._mon_client.metrics.list,
                              **kwargs)

    def metric_names_list(self, **kwargs):
        return self.call_func(self._mon_client.metrics.list_names,
                              **kwargs)

    def measurements_list(self, **kwargs):
        return self.call_func(self._mon_client.metrics.list_measurements,
                              **kwargs)

    def statistics_list(self, **kwargs):
        return self.call_func(self._mon_client.metrics.list_statistics,
                              **kwargs)
