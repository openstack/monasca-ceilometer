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
"""Test api with Monasca driver
"""

import mock
import pkg_resources

from oslo_config import cfg
from oslo_config import fixture as fixture_config
from oslotest import mockpatch
from stevedore import driver
from stevedore import extension

from ceilometer import storage
from ceilometer.tests import base as test_base
from oslo_policy import opts

import pecan
import pecan.testing

OPT_GROUP_NAME = 'keystone_authtoken'
cfg.CONF.import_group(OPT_GROUP_NAME, "keystonemiddleware.auth_token")


class TestApi(test_base.BaseTestCase):

    # TODO(Unresolved comment from git review: Can we include CM-api test
    # cases for get_samples in
    # ceilometer/tests/api/v2/test_api_with_monasca_driver.py?)

    def _get_driver_from_entry_point(self, entry_point, namespace):
        ep = pkg_resources.EntryPoint.parse(entry_point)
        a_driver = extension.Extension('con_driver', ep,
                                       ep.load(require=False), None)

        mgr = driver.DriverManager.make_test_instance(
            a_driver, namespace=namespace
        )
        mgr._init_plugins([a_driver])
        return mgr

    def get_connection_with_mock_driver_manager(self, url, namespace):
        mgr = self._get_driver_from_entry_point(
            entry_point='monasca = ceilometer.storage.impl_monasca:Connection',
            namespace='ceilometer.metering.storage')
        return mgr.driver(url)

    def get_publisher_with_mock_driver_manager(self, url, namespace):
        mgr = self._get_driver_from_entry_point(
            entry_point='monasca = ceilometer.publisher.monclient:'
                        'MonascaPublisher',
            namespace='ceilometer.publisher')
        return mgr.driver(url)

    def setUp(self):
        super(TestApi, self).setUp()
        self.PATH_PREFIX = '/v2'

        self.CONF = self.useFixture(fixture_config.Config()).conf
        self.CONF([], project='ceilometer', validate_default_values=True)

        self.setup_messaging(self.CONF)
        opts.set_defaults(self.CONF)

        self.CONF.set_override("auth_version", "v2.0",
                               group=OPT_GROUP_NAME)
        self.CONF.set_override("policy_file",
                               self.path_get('etc/ceilometer/policy.json'),
                               group='oslo_policy')

        self.CONF.import_opt('pipeline_cfg_file', 'ceilometer.pipeline')
        self.CONF.set_override(
            'pipeline_cfg_file',
            self.path_get('etc/ceilometer/pipeline.yaml')
        )

        self.CONF.import_opt('monasca_mappings',
                             'ceilometer.publisher.monasca_data_filter',
                             group='monasca')

        self.CONF.set_override(
            'monasca_mappings',
            self.path_get('etc/ceilometer/monasca_field_definitions.yaml'),
            group='monasca'
        )

        with mock.patch("ceilometer.monasca_client.Client") as mock_client,\
                mock.patch('ceilometer.storage.get_connection') as \
                get_storage_conn, \
                mock.patch('ceilometer.publisher.get_publisher') as get_pub:

            get_storage_conn.side_effect = (
                self.get_connection_with_mock_driver_manager)
            get_pub.side_effect = self.get_publisher_with_mock_driver_manager
            self.mock_mon_client = mock_client
            self.conn = storage.get_connection('monasca://127.0.0.1:8080',
                                               'ceilometer.metering.storage')

            self.useFixture(mockpatch.Patch(
                'ceilometer.storage.get_connection',
                return_value=self.conn))

            self.app = self._make_app()

    def _make_app(self, enable_acl=False):
        self.config = {
            'app': {
                'root': 'ceilometer.api.controllers.root.RootController',
                'modules': ['ceilometer.api'],
                'enable_acl': enable_acl,
            },
            'wsme': {
                'debug': True,
            },
        }

        return pecan.testing.load_test_app(self.config)

    def get_json(self, path, expect_errors=False, headers=None,
                 extra_environ=None, q=None, groupby=None, status=None,
                 override_params=None, **params):
        """Sends simulated HTTP GET request to Pecan test app.

        :param path: url path of target service
        :param expect_errors: boolean value whether an error is expected based
                              on request
        :param headers: A dictionary of headers to send along with the request
        :param extra_environ: A dictionary of environ variables to send along
                              with the request
        :param q: list of queries consisting of: field, value, op, and type
                  keys
        :param groupby: list of fields to group by
        :param status: Expected status code of response
        :param override_params: literally encoded query param string
        :param params: content for wsgi.input of request
        """
        q = q or []
        groupby = groupby or []
        full_path = self.PATH_PREFIX + path
        if override_params:
            all_params = override_params
        else:
            query_params = {'q.field': [],
                            'q.value': [],
                            'q.op': [],
                            'q.type': [],
                            }
            for query in q:
                for name in ['field', 'op', 'value', 'type']:
                    query_params['q.%s' % name].append(query.get(name, ''))
            all_params = {}
            all_params.update(params)
            if q:
                all_params.update(query_params)
            if groupby:
                all_params.update({'groupby': groupby})
        response = self.app.get(full_path,
                                params=all_params,
                                headers=headers,
                                extra_environ=extra_environ,
                                expect_errors=expect_errors,
                                status=status)
        if not expect_errors:
            response = response.json
        return response


class TestListMeters(TestApi):

    def setUp(self):
        super(TestListMeters, self).setUp()

        self.meter_payload = [{'name': 'm1',
                               'dimensions': {
                                   'type': 'gauge',
                                   'unit': 'any',
                                   'resource_id': 'resource-1',
                                   'project_id': 'project-1',
                                   'user_id': 'user-1',
                                   'source': 'source'}},
                              {'name': 'm2',
                               'dimensions': {
                                   'type': 'delta',
                                   'unit': 'any',
                                   'resource_id': 'resource-1',
                                   'project_id': 'project-1',
                                   'user_id': 'user-1',
                                   'source': 'source'}}]

    def test_empty(self):
        data = self.get_json('/meters')
        self.assertEqual([], data)

    def test_get_meters(self):

        mnl_mock = self.mock_mon_client().metrics_list
        mnl_mock.return_value = self.meter_payload

        data = self.get_json('/meters')
        self.assertEqual(True, mnl_mock.called)
        self.assertEqual(1, mnl_mock.call_count)
        self.assertEqual(2, len(data))

        (self.assertIn(meter['name'],
                       [payload.get('name') for payload in
                        self.meter_payload]) for meter in data)

    def test_get_meters_query_with_project_resource(self):
        mnl_mock = self.mock_mon_client().metrics_list
        mnl_mock.return_value = self.meter_payload

        self.get_json('/meters',
                      q=[{'field': 'resource_id',
                          'value': 'resource-1'},
                         {'field': 'project_id',
                          'value': 'project-1'}])
        self.assertEqual(True, mnl_mock.called)
        self.assertEqual(1, mnl_mock.call_count)
        self.assertEqual(dict(dimensions=dict(resource_id=u'resource-1',
                                              project_id=u'project-1'),
                              limit=100),
                         mnl_mock.call_args[1])

    def test_get_meters_query_with_user(self):
        mnl_mock = self.mock_mon_client().metrics_list
        mnl_mock.return_value = self.meter_payload

        self.get_json('/meters',
                      q=[{'field': 'user_id',
                          'value': 'user-1'}])
        self.assertEqual(True, mnl_mock.called)
        self.assertEqual(1, mnl_mock.call_count)
        self.assertEqual(dict(dimensions=dict(user_id=u'user-1'),
                              limit=100),
                         mnl_mock.call_args[1])
