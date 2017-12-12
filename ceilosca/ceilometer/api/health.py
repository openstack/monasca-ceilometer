#
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

from oslo_log import log
LOG = log.getLogger(__name__)


def filter_factory(global_config, **local_conf):
    """Returns a WSGI Filter."""
    conf = global_config.copy()
    conf.update(local_conf)
    LOG.debug('Filter Factory')

    def health_filter(app):
        return HealthFilterApi(app, conf)
    return health_filter


class HealthFilterApi(object):

    def __init__(self, app, conf):
        self.conf = conf
        self.app = app
        self.db = None

    def __call__(self, environ, start_response):
        """Handle the incoming request and filters it.

        Interjects the request and acts on it only if
        it is related to the filter functionality, otherwise
        it just let the request pass through to the app.

        """

        LOG.debug('Health Check Filter')

        if environ['PATH_INFO'].startswith('/v2/health'):
            response_code = '204 No Content'
            if environ['REQUEST_METHOD'] != 'HEAD':
                response_code = '200 OK'
# Commenting out healthcheck behavior when request method
# is not of type HEAD.# As it creates load on monasca vertica
# FIXME: fix this when monasca creates get versions api in
# in Monascaclient. USe that instead
#                try:
#                    if not self.db:
#                        self.db = storage.get_connection_from_config(cfg.CONF)
#                    meters = self.db.get_meters(unique=True, limit=1)
#                    if not meters:
#                        response_code = '503 Backend Unavailable'
#                except Exception as e:
#                    response_code = '503 Backend Unavailable'
#                    LOG.warning('DB health check connection failed: %s', e)
#                    self.db = None
            resp = MiniResp(response_code, environ)
            start_response(response_code, resp.headers)
            return resp.body
        else:
            return self.app(environ, start_response)


class MiniResp(object):

    def __init__(self, message, env, headers=[]):
        if env['REQUEST_METHOD'] == 'HEAD':
            self.body = ['']
        else:
            self.body = [message]
        self.headers = list(headers)
