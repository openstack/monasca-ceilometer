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

import mock
from oslo_config import cfg
from oslo_utils import netutils
from oslotest import base

from ceilometer import monasca_client
from monascaclient import exc

cfg.CONF.import_group('service_credentials', 'ceilometer.service')


class TestMonascaClient(base.BaseTestCase):
    def setUp(self):
        super(TestMonascaClient, self).setUp()

        self.mc = self._get_client()

    @mock.patch('monascaclient.client.Client')
    @mock.patch('monascaclient.ksclient.KSClient')
    def _get_client(self, ksclass_mock, monclient_mock):
        ksclient_mock = ksclass_mock.return_value
        ksclient_mock.token.return_value = "token123"
        return monasca_client.Client(
            netutils.urlsplit("http://127.0.0.1:8080"))

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
                self.username = conf.os_username
                conf.os_username = ""

            def __exit__(self, exc_type, exc_val, exc_tb):
                conf.os_username = self.username

        with SetOpt():
            self.assertRaises(
                monasca_client.MonascaInvalidServiceCredentialsException,
                self._get_client)

        self.assertIsNotNone(True, conf.os_username)
