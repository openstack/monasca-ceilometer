# Copyright 2015 Hewlett-Packard Company
# (c) Copyright 2018 SUSE LLC
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

import copy

from monascaclient import client
from monascaclient import exc
from oslo_log import log
import tenacity

from ceilometer.i18n import _

LOG = log.getLogger(__name__)


class MonascaException(Exception):
    def __init__(self, message=''):
        msg = 'An exception is raised from Monasca: ' + message
        super(MonascaException, self).__init__(msg)


class MonascaServiceException(Exception):
    def __init__(self, message=''):
        msg = 'Monasca service is unavailable: ' + message
        super(MonascaServiceException, self).__init__(msg)


class MonascaInvalidServiceCredentialsException(Exception):
    pass


class MonascaInvalidParametersException(Exception):
    code = 400

    def __init__(self, message=''):
        msg = 'Request cannot be handled by Monasca: ' + message
        super(MonascaInvalidParametersException, self).__init__(msg)


class Client(object):
    """A client which gets information via python-monascaclient."""

    def __init__(self, conf, parsed_url):
        self.conf = conf
        self._retry_interval = self.conf.database.retry_interval
        self._max_retries = self.conf.database.max_retries or 1
        # enable monasca api pagination
        self._enable_api_pagination = self.conf.monasca.enable_api_pagination
        # NOTE(zqfan): There are many concurrency requests while using
        # Ceilosca, to save system resource, we don't retry too many times.
        if self._max_retries < 0 or self._max_retries > 10:
            LOG.warning('Reduce max retries from %s to 10',
                        self._max_retries)
            self._max_retries = 10

        # self.conf.log_opt_values(LOG, logging.INFO)

        conf = self.conf.service_credentials
        monasca_conf = self.conf.monasca
        # because our ansible script are in another repo, the old setting
        # of auth_type is password-ceilometer-legacy which doesn't register
        # os_xxx options, so here we need to provide a compatible way to
        # avoid circle dependency
        if conf.auth_type == 'password-ceilometer-legacy':
            username = conf.os_username
            password = conf.os_password
            auth_url = conf.os_auth_url
            # project_id = conf.os_tenant_id
            project_name = conf.os_tenant_name
        else:
            username = monasca_conf.service_username
            password = monasca_conf.service_password
            auth_url = monasca_conf.service_auth_url
            # project_id = monasca_conf.service_project_id
            project_name = monasca_conf.service_project_name
            default_domain_name = monasca_conf.service_domain_name
            region_name = monasca_conf.service_region_name
            service_verify = monasca_conf.service_verify

        if not username or not password or not auth_url:
            err_msg = _("No user name or password or auth_url "
                        "found in service_credentials")
            LOG.error(err_msg)
            raise MonascaInvalidServiceCredentialsException(err_msg)

        kwargs = {
            'username': username,
            'password': password,
            'auth_url': auth_url.replace("v2.0", "v3"),
            # 'project_id': project_id,
            'project_name': project_name,
            'region_name': region_name,
            'default_domain_name': default_domain_name,
            'project_domain_name': default_domain_name,
            'user_domain_name': default_domain_name,
            'read_timeout': self.conf.http_timeout,
            'write_timeout': self.conf.http_timeout,
            'keystone_timeout': self.conf.http_timeout,
            'verify': service_verify
        }
        self._kwargs = kwargs
        self._endpoint = parsed_url.netloc + parsed_url.path
        LOG.info(_("monasca_client: using %s as monasca end point") %
                 self._endpoint)
        self._refresh_client()

    def _refresh_client(self):
        self._mon_client = client.Client(self.conf.monasca.clientapi_version,
                                         self._endpoint, **self._kwargs)

    def call_func(self, func, **kwargs):
        @tenacity.retry(
            wait=tenacity.wait_fixed(self._retry_interval),
            stop=tenacity.stop_after_attempt(self._max_retries),
            retry=(tenacity.retry_if_exception_type(MonascaServiceException) |
                   tenacity.retry_if_exception_type(MonascaException)))
        def _inner():
            try:
                return func(**kwargs)
            except (exc.http.InternalServerError,
                    exc.http.ServiceUnavailable,
                    exc.http.BadGateway,
                    exc.connection.ConnectionError) as e:
                LOG.exception(e)
                msg = '%s: %s' % (e.__class__.__name__, e)
                raise MonascaServiceException(msg)
            except exc.http.HttpError as e:
                LOG.exception(e)
                msg = '%s: %s' % (e.__class__.__name__, e)
                status_code = e.http_status
                if not isinstance(status_code, int):
                    status_code = 500
                if 400 <= status_code < 500:
                    raise MonascaInvalidParametersException(msg)
                else:
                    raise MonascaException(msg)
            except Exception as e:
                LOG.exception(e)
                msg = '%s: %s' % (e.__class__.__name__, e)
                raise MonascaException(msg)

        return _inner()

    def metrics_create(self, **kwargs):
        return self.call_func(self._mon_client.metrics.create,
                              **kwargs)

    def metrics_list(self, **kwargs):
        """Using monasca pagination to get all metrics.

        We yield endless metrics till caller doesn't want more or
        no more is left.
        """
        search_args = copy.deepcopy(kwargs)
        metrics = self.call_func(self._mon_client.metrics.list, **search_args)
        # check if api pagination is enabled
        if self._enable_api_pagination:
            # page through monasca results
            while metrics:
                for metric in metrics:
                    yield metric
                # offset for metrics is the last metric's id
                search_args['offset'] = metric['id']
                metrics = self.call_func(self._mon_client.metrics.list,
                                         **search_args)
        else:
            for metric in metrics:
                yield metric

    def metric_names_list(self, **kwargs):
        return self.call_func(self._mon_client.metrics.list_names,
                              **kwargs)

    def measurements_list(self, **kwargs):
        """Using monasca pagination to get all measurements.

        We yield endless measurements till caller doesn't want more or
        no more is left.
        """
        search_args = copy.deepcopy(kwargs)
        measurements = self.call_func(
            self._mon_client.metrics.list_measurements,
            **search_args)
        # check if api pagination is enabled
        if self._enable_api_pagination:
            while measurements and len(measurements[0]["measurements"]) > 0:
                for measurement in measurements:
                    if measurement["measurements"] is not None and \
                       len(measurement["measurements"]) > 0:
                        # offset for measurements is measurement id composited
                        # with the last measurement's timestamp
                        last_good_offset = '%s_%s' % (
                            measurement['id'],
                            measurement['measurements'][-1][0])
                    yield measurement
                search_args['offset'] = last_good_offset
                measurements = self.call_func(
                    self._mon_client.metrics.list_measurements,
                    **search_args)
        else:
            for measurement in measurements:
                yield measurement

    def statistics_list(self, **kwargs):
        """Using monasca pagination to get all statistics.

        We yield endless statistics till caller doesn't want more or
        no more is left.
        """
        search_args = copy.deepcopy(kwargs)
        statistics = self.call_func(self._mon_client.metrics.list_statistics,
                                    **search_args)
        # check if api pagination is enabled
        if self._enable_api_pagination:
            while statistics and len(statistics[0]["statistics"]) > 0:
                for statistic in statistics:
                    if statistic["statistics"] is not None and \
                       len(statistic["statistics"]) > 0:
                        # offset for statistics is statistic id composited with
                        # the last statistic's timestamp
                        last_good_offset = '%s_%s' % (
                            statistic['id'], statistic['statistics'][-1][0])
                    yield statistic

                # with groupby, the offset is unpredictable to me, we don't
                # support pagination for it now.
                if kwargs.get('group_by'):
                    break
                search_args['offset'] = last_good_offset
                statistics = self.call_func(
                    self._mon_client.metrics.list_statistics,
                    **search_args)
                # unlike metrics.list and metrics.list_measurements
                # return whole new data, metrics.list_statistics
                # next page will use last page's final statistic
                # data as the first one, so we need to pop it here.
                # I think Monasca should treat this as a bug and fix it.
                if statistics:
                    statistics[0]['statistics'].pop(0)
                    if len(statistics[0]['statistics']) == 0:
                        statistics.pop(0)
        else:
            for statistic in statistics:
                yield statistic
