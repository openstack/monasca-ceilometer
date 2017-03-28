# Copyright 2015 Hewlett-Packard Company
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

from keystoneauth1 import loading as ka_loading
import mock
from oslo_config import cfg
from oslo_config import fixture as fixture_config
from oslo_utils import fileutils
from oslo_utils import netutils
from oslotest import base

from ceilometer import monasca_client
from monascaclient import exc

cfg.CONF.import_group('service_credentials', 'ceilometer.service')


class TestMonascaClient(base.BaseTestCase):
    def setUp(self):
        super(TestMonascaClient, self).setUp()
        content = ("[service_credentials]\n"
                   "auth_type = password\n"
                   "username = ceilometer\n"
                   "password = admin\n"
                   "auth_url = http://localhost:5000/v2.0\n")
        tempfile = fileutils.write_to_tempfile(content=content,
                                               prefix='ceilometer',
                                               suffix='.conf')
        self.addCleanup(os.remove, tempfile)
        self.conf = self.useFixture(fixture_config.Config()).conf
        self.conf([], default_config_files=[tempfile])
        ka_loading.load_auth_from_conf_options(self.conf,
                                               "service_credentials")
        self.conf.set_override('max_retries', 0, 'database')
        self.mc = self._get_client()

    def tearDown(self):
        # For some reason, cfg.CONF is registered a required option named
        # auth_url after these tests run, which occasionally blocks test
        # case test_event_pipeline_endpoint_requeue_on_failure, so we
        # unregister it here.
        self.conf.reset()
        self.conf.unregister_opt(cfg.StrOpt('auth_url'),
                                 group='service_credentials')
        super(TestMonascaClient, self).tearDown()

    @mock.patch('monascaclient.client.Client')
    @mock.patch('monascaclient.ksclient.KSClient')
    def _get_client(self, ksclass_mock, monclient_mock):
        ksclient_mock = ksclass_mock.return_value
        ksclient_mock.token.return_value = "token123"
        return monasca_client.Client(
            netutils.urlsplit("http://127.0.0.1:8080"))

    @mock.patch('monascaclient.client.Client')
    @mock.patch('monascaclient.ksclient.KSClient')
    def test_client_url_correctness(self, ksclass_mock, monclient_mock):
        ksclient_mock = ksclass_mock.return_value
        ksclient_mock.token.return_value = "token123"
        mon_client = monasca_client.Client(
            netutils.urlsplit("monasca://https://127.0.0.1:8080"))
        self.assertEqual("https://127.0.0.1:8080", mon_client._endpoint)

    def test_metrics_create(self):
        with mock.patch.object(self.mc._mon_client.metrics, 'create',
                               side_effect=[True]) as create_patch:
            self.mc.metrics_create()

            self.assertEqual(1, create_patch.call_count)

    def test_metrics_create_exception(self):
        with mock.patch.object(
                self.mc._mon_client.metrics, 'create',
                side_effect=[exc.HTTPInternalServerError, True])\
                as create_patch:
            self.assertRaises(monasca_client.MonascaServiceException,
                              self.mc.metrics_create)
            self.assertEqual(1, create_patch.call_count)

    def test_metrics_create_unprocessable_exception(self):
        with mock.patch.object(
                self.mc._mon_client.metrics, 'create',
                side_effect=[exc.HTTPUnProcessable, True])\
                as create_patch:
            self.assertRaises(monasca_client.MonascaInvalidParametersException,
                              self.mc.metrics_create)
            self.assertEqual(1, create_patch.call_count)

    def test_invalid_service_creds(self):
        conf = cfg.CONF.service_credentials

        class SetOpt(object):
            def __enter__(self):
                self.username = conf.username
                conf.username = ""

            def __exit__(self, exc_type, exc_val, exc_tb):
                conf.username = self.username

        with SetOpt():
            self.assertRaises(
                monasca_client.MonascaInvalidServiceCredentialsException,
                self._get_client)

        self.assertIsNotNone(True, conf.username)

    def test_retry_on_key_error(self):
        self.conf.set_override('max_retries', 2, 'database')
        self.conf.set_override('retry_interval', 1, 'database')
        self.mc = self._get_client()

        with mock.patch.object(
                self.mc._mon_client.metrics, 'list',
                side_effect=[KeyError, []]) as mocked_metrics_list:
            list(self.mc.metrics_list())
            self.assertEqual(2, mocked_metrics_list.call_count)

    def test_no_retry_on_invalid_parameter(self):
        self.conf.set_override('max_retries', 2, 'database')
        self.conf.set_override('retry_interval', 1, 'database')
        self.mc = self._get_client()

        def _check(exception):
            expected_exc = monasca_client.MonascaInvalidParametersException
            with mock.patch.object(
                    self.mc._mon_client.metrics, 'list',
                    side_effect=[exception, []]
            ) as mocked_metrics_list:
                self.assertRaises(expected_exc, list, self.mc.metrics_list())
                self.assertEqual(1, mocked_metrics_list.call_count)

        _check(exc.HTTPUnProcessable)
        _check(exc.HTTPBadRequest)

    def test_max_retris_not_too_much(self):
        def _check(configured, expected):
            self.conf.set_override('max_retries', configured, 'database')
            self.mc = self._get_client()
            self.assertEqual(expected, self.mc._max_retries)

        _check(-1, 10)
        _check(11, 10)
        _check(5, 5)
        _check(None, 1)

    def test_meaningful_exception_message(self):
        with mock.patch.object(
                self.mc._mon_client.metrics, 'list',
                side_effect=[exc.HTTPInternalServerError,
                             exc.HTTPUnProcessable,
                             KeyError]):
            e = self.assertRaises(
                monasca_client.MonascaServiceException,
                list, self.mc.metrics_list())
            self.assertIn('Monasca service is unavailable', str(e))
            e = self.assertRaises(
                monasca_client.MonascaInvalidParametersException,
                list, self.mc.metrics_list())
            self.assertIn('Request cannot be handled by Monasca', str(e))
            e = self.assertRaises(
                monasca_client.MonascaException,
                list, self.mc.metrics_list())
            self.assertIn('An exception is raised from Monasca', str(e))

    @mock.patch.object(monasca_client.Client, '_refresh_client')
    def test_metrics_create_with_401(self, rc_patch):
        with mock.patch.object(
                self.mc._mon_client.metrics, 'create',
                side_effect=[exc.HTTPUnauthorized, True]):
            self.assertRaises(
                monasca_client.MonascaInvalidParametersException,
                self.mc.metrics_create)

    def test_metrics_list_with_pagination(self):

        metric_list_pages = [[{u'dimensions': {},
                               u'measurements': [
                                   [u'2015-04-14T17:52:31Z',
                                    1.0, {}]],
                               u'id': u'2015-04-14T18:42:31Z',
                               u'columns': [u'timestamp', u'value',
                                            u'value_meta'],
                               u'name': u'test1'}],
                             [{u'dimensions': {},
                               u'measurements': [
                                   [u'2015-04-15T17:52:31Z',
                                    2.0, {}]],
                               u'id': u'2015-04-15T18:42:31Z',
                               u'columns': [u'timestamp', u'value',
                                            u'value_meta'],
                               u'name': u'test2'}], None]

        expected_page_count = len(metric_list_pages)
        expected_metric_names = ["test1", "test2"]

        self.conf.set_override('enable_api_pagination',
                               True, group='monasca')
        # get a new ceilosca mc
        mc = self._get_client()
        with mock.patch.object(
                mc._mon_client.metrics, 'list',
                side_effect=metric_list_pages) as mocked_metrics_list:
            returned_metrics = mc.metrics_list()
            returned_metric_names_list = [metric["name"]
                                          for metric in returned_metrics]
            self.assertListEqual(expected_metric_names,
                                 returned_metric_names_list)
            self.assertEqual(expected_page_count,
                             mocked_metrics_list.call_count)
            self.assertEqual(True, mocked_metrics_list.called)

    def test_metrics_list_without_pagination(self):

        metric_list_pages = [[{u'dimensions': {},
                               u'measurements': [
                                   [u'2015-04-14T17:52:31Z',
                                    1.0, {}]],
                               u'id': u'2015-04-14T18:42:31Z',
                               u'columns': [u'timestamp', u'value',
                                            u'value_meta'],
                               u'name': u'test1'}],
                             [{u'dimensions': {},
                               u'measurements': [
                                   [u'2015-04-15T17:52:31Z',
                                    2.0, {}]],
                               u'id': u'2015-04-15T18:42:31Z',
                               u'columns': [u'timestamp', u'value',
                                            u'value_meta'],
                               u'name': u'test2'}], None]

        # first page only
        expected_page_count = 1
        expected_metric_names = ["test1"]

        self.conf.set_override('enable_api_pagination',
                               False, group='monasca')
        # get a new ceilosca mc
        mc = self._get_client()
        with mock.patch.object(
                mc._mon_client.metrics, 'list',
                side_effect=metric_list_pages) as mocked_metrics_list:
            returned_metrics = mc.metrics_list()
            returned_metric_names_list = [metric["name"]
                                          for metric in returned_metrics]
            self.assertListEqual(expected_metric_names,
                                 returned_metric_names_list)
            self.assertEqual(expected_page_count,
                             mocked_metrics_list.call_count)
            self.assertEqual(True, mocked_metrics_list.called)

    def test_measurement_list_with_pagination(self):

        measurement_list_pages = [[{u'dimensions': {},
                                    u'measurements': [
                                        [u'2015-04-14T17:52:31Z',
                                         1.0, {}]],
                                    u'id': u'2015-04-14T18:42:31Z',
                                    u'columns': [u'timestamp', u'value',
                                                 u'value_meta'],
                                    u'name': u'test1'}],
                                  [{u'dimensions': {},
                                    u'measurements': [
                                        [u'2015-04-15T17:52:31Z',
                                         2.0, {}]],
                                    u'id': u'2015-04-15T18:42:31Z',
                                    u'columns': [u'timestamp', u'value',
                                                 u'value_meta'],
                                    u'name': u'test2'}], None]

        expected_page_count = len(measurement_list_pages)
        expected_metric_names = ["test1", "test2"]

        self.conf.set_override('enable_api_pagination',
                               True, group='monasca')
        # get a new ceilosca mc
        mc = self._get_client()
        with mock.patch.object(
                mc._mon_client.metrics, 'list_measurements',
                side_effect=measurement_list_pages) as mocked_metrics_list:
            returned_metrics = mc.measurements_list()
            returned_metric_names_list = [metric["name"]
                                          for metric in returned_metrics]
            self.assertListEqual(expected_metric_names,
                                 returned_metric_names_list)
            self.assertEqual(expected_page_count,
                             mocked_metrics_list.call_count)
            self.assertEqual(True, mocked_metrics_list.called)

    def test_measurement_list_without_pagination(self):

        measurement_list_pages = [[{u'dimensions': {},
                                    u'measurements': [
                                        [u'2015-04-14T17:52:31Z',
                                         1.0, {}]],
                                    u'id': u'2015-04-14T18:42:31Z',
                                    u'columns': [u'timestamp', u'value',
                                                 u'value_meta'],
                                    u'name': u'test1'}],
                                  [{u'dimensions': {},
                                    u'measurements': [
                                    [u'2015-04-15T17:52:31Z',
                                     2.0, {}]],
                                    u'id': u'2015-04-15T18:42:31Z',
                                    u'columns': [u'timestamp', u'value',
                                                 u'value_meta'],
                                    u'name': u'test2'}], None]

        # first page only
        expected_page_count = 1
        expected_metric_names = ["test1"]

        self.conf.set_override('enable_api_pagination',
                               False, group='monasca')
        # get a new ceilosca mc
        mc = self._get_client()
        with mock.patch.object(
                mc._mon_client.metrics, 'list_measurements',
                side_effect=measurement_list_pages) as mocked_metrics_list:
            returned_metrics = mc.measurements_list()
            returned_metric_names_list = [metric["name"]
                                          for metric in returned_metrics]
            self.assertListEqual(expected_metric_names,
                                 returned_metric_names_list)
            self.assertEqual(expected_page_count,
                             mocked_metrics_list.call_count)
            self.assertEqual(True, mocked_metrics_list.called)

    def test_statistics_list_with_pagination(self):

        statistics_list_pages = [[{u'dimensions': {},
                                   u'statistics': [
                                       [u'2015-04-14T17:52:31Z',
                                        1.0, 10.0],
                                       [u'2015-04-15T17:52:31Z',
                                        1.0, 10.0]],
                                   u'id': u'2015-04-14T18:42:31Z',
                                   u'columns': [u'timestamp', u'avg',
                                                u'max'],
                                   u'name': u'test1'}],
                                 [{u'dimensions': {},
                                   u'statistics': [
                                       [u'2015-04-16T17:52:31Z',
                                        2.0, 20.0],
                                       [u'2015-04-17T17:52:31Z',
                                        2.0, 20.0]],
                                   u'id': u'2015-04-15T18:42:31Z',
                                   u'columns': [u'timestamp', u'avg',
                                                u'max'],
                                   u'name': u'test2'}], None]

        expected_page_count = len(statistics_list_pages)
        expected_metric_names = ["test1", "test2"]

        self.conf.set_override('enable_api_pagination',
                               True, group='monasca')
        # get a new ceilosca mc
        mc = self._get_client()
        with mock.patch.object(
                mc._mon_client.metrics, 'list_statistics',
                side_effect=statistics_list_pages) as mocked_metrics_list:

            returned_metrics = mc.statistics_list()
            returned_metric_names_list = [metric["name"]
                                          for metric in returned_metrics]
            self.assertListEqual(expected_metric_names,
                                 returned_metric_names_list)
            self.assertEqual(expected_page_count,
                             mocked_metrics_list.call_count)
            self.assertEqual(True, mocked_metrics_list.called)

    def test_statistics_list_without_pagination(self):

        statistics_list_pages = [[{u'dimensions': {},
                                   u'statistics': [
                                       [u'2015-04-14T17:52:31Z',
                                        1.0, 10.0]],
                                   u'id': u'2015-04-14T18:42:31Z',
                                   u'columns': [u'timestamp', u'avg',
                                                u'max'],
                                   u'name': u'test1'}],
                                 [{u'dimensions': {},
                                   u'statistics': [
                                       [u'2015-04-15T17:52:31Z',
                                        2.0, 20.0]],
                                   u'id': u'2015-04-15T18:42:31Z',
                                   u'columns': [u'timestamp', u'avg',
                                                u'max'],
                                   u'name': u'test2'}], None]
        # first page only
        expected_page_count = 1
        expected_metric_names = ["test1"]

        self.conf.set_override('enable_api_pagination',
                               False, group='monasca')
        # get a new ceilosca mc
        mc = self._get_client()
        with mock.patch.object(
                mc._mon_client.metrics, 'list_statistics',
                side_effect=statistics_list_pages) as mocked_metrics_list:
            returned_metrics = mc.statistics_list()
            returned_metric_names_list = [metric["name"]
                                          for metric in returned_metrics]
            self.assertListEqual(expected_metric_names,
                                 returned_metric_names_list)
            self.assertEqual(expected_page_count,
                             mocked_metrics_list.call_count)
            self.assertEqual(True, mocked_metrics_list.called)
