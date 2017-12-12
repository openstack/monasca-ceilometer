# Copyright 2015 Hewlett-Packard Company
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
import mock

from oslo_utils import netutils
from oslotest import base

from ceilometer import monasca_ceilometer_opts
from ceilometer import monasca_client
from ceilometer import service

from monascaclient import exc
import tenacity


class TestMonascaClient(base.BaseTestCase):
    def setUp(self):
        super(TestMonascaClient, self).setUp()

        self.CONF = service.prepare_service([], [])
        self.CONF.register_opts(list(monasca_ceilometer_opts.OPTS),
                                'monasca')
        self.CONF.set_override('service_username', 'ceilometer', 'monasca')
        self.CONF.set_override('service_password', 'admin', 'monasca')
        self.CONF.set_override('service_auth_url',
                               'http://localhost:5000/v2.0',
                               'monasca')

        self.CONF.set_override('max_retries', 0, 'database')
        self.mc = self._get_client()

    def tearDown(self):
        # For some reason, cfg.CONF is registered a required option named
        # auth_url after these tests run, which occasionally blocks test
        # case test_event_pipeline_endpoint_requeue_on_failure, so we
        # unregister it here.
        self.CONF.reset()
        # self.CONF.unregister_opt(cfg.StrOpt('service_auth_url'),
        #                          group='monasca')
        super(TestMonascaClient, self).tearDown()

    @mock.patch('monascaclient.client.Client')
    def _get_client(self, monclient_mock):
        return monasca_client.Client(
            self.CONF,
            netutils.urlsplit("http://127.0.0.1:8080"))

    @mock.patch('monascaclient.client.Client')
    def test_client_url_correctness(self, monclient_mock):
        mon_client = monasca_client.Client(
            self.CONF,
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
                side_effect=[exc.http.InternalServerError, True])\
                as create_patch:
            e = self.assertRaises(tenacity.RetryError,
                                  self.mc.metrics_create)
            (original_ex, traceobj) = e.last_attempt.exception_info()
            self.assertIsInstance(original_ex,
                                  monasca_client.MonascaServiceException)
            self.assertEqual(1, create_patch.call_count)

    def test_metrics_create_unprocessable_exception(self):
        with mock.patch.object(
                self.mc._mon_client.metrics, 'create',
                side_effect=[exc.http.UnprocessableEntity, True])\
                as create_patch:
            self.assertRaises(monasca_client.MonascaInvalidParametersException,
                              self.mc.metrics_create)
            self.assertEqual(1, create_patch.call_count)

    def test_invalid_service_creds(self):
        conf = self.CONF.monasca

        class SetOpt(object):
            def __enter__(self):
                self.username = conf.service_username
                conf.service_username = ""

            def __exit__(self, exc_type, exc_val, exc_tb):
                conf.service_username = self.username

        with SetOpt():
            self.assertRaises(
                monasca_client.MonascaInvalidServiceCredentialsException,
                self._get_client)

        self.assertIsNotNone(True, conf.service_username)

    def test_retry_on_key_error(self):
        self.CONF.set_override('max_retries', 2, 'database')
        self.CONF.set_override('retry_interval', 1, 'database')
        self.mc = self._get_client()
        with mock.patch.object(
                self.mc._mon_client.metrics, 'list',
                side_effect=[KeyError, []]) as mocked_metrics_list:
            list(self.mc.metrics_list())
            self.assertEqual(2, mocked_metrics_list.call_count)

    def test_no_retry_on_invalid_parameter(self):
        self.CONF.set_override('max_retries', 2, 'database')
        self.CONF.set_override('retry_interval', 1, 'database')
        self.mc = self._get_client()

        def _check(exception):
            expected_exc = monasca_client.MonascaInvalidParametersException
            with mock.patch.object(
                    self.mc._mon_client.metrics, 'list',
                    side_effect=[exception, []]
            ) as mocked_metrics_list:
                self.assertRaises(expected_exc, list, self.mc.metrics_list())
                self.assertEqual(1, mocked_metrics_list.call_count)

        _check(exc.http.UnprocessableEntity)
        _check(exc.http.BadRequest)

    def test_max_retris_not_too_much(self):
        def _check(configured, expected):
            self.CONF.set_override('max_retries', configured, 'database')
            self.mc = self._get_client()
            self.assertEqual(expected, self.mc._max_retries)

        _check(-1, 10)
        _check(11, 10)
        _check(5, 5)
        _check(None, 1)

    def test_meaningful_exception_message(self):
        with mock.patch.object(
                self.mc._mon_client.metrics, 'list',
                side_effect=[exc.http.InternalServerError,
                             exc.http.UnprocessableEntity,
                             KeyError]):
            e = self.assertRaises(
                tenacity.RetryError,
                list, self.mc.metrics_list())
            (original_ex, traceobj) = e.last_attempt.exception_info()
            self.assertIn('Monasca service is unavailable',
                          str(original_ex))
            e = self.assertRaises(
                monasca_client.MonascaInvalidParametersException,
                list, self.mc.metrics_list())
            self.assertIn('Request cannot be handled by Monasca',
                          str(e))
            e = self.assertRaises(
                tenacity.RetryError,
                list, self.mc.metrics_list())
            (original_ex, traceobj) = e.last_attempt.exception_info()
            self.assertIn('An exception is raised from Monasca',
                          str(original_ex))

    @mock.patch.object(monasca_client.Client, '_refresh_client')
    def test_metrics_create_with_401(self, rc_patch):
        with mock.patch.object(
                self.mc._mon_client.metrics, 'create',
                side_effect=[exc.http.Unauthorized, True]):
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

        self.CONF.set_override('enable_api_pagination',
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

        self.CONF.set_override('enable_api_pagination',
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

        self.CONF.set_override('enable_api_pagination',
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

        self.CONF.set_override('enable_api_pagination',
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

        self.CONF.set_override('enable_api_pagination',
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

        self.CONF.set_override('enable_api_pagination',
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
