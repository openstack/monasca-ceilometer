import calendar
import time

from ceilometer.monclient import client
from ceilometer.openstack.common import log
from ceilometer import publisher


LOG = log.getLogger(__name__)


class monclient(publisher.PublisherBase):
    """Publisher to publish samples to monclient.

    Example URL to place in pipeline.yaml:
        - monclient://http://192.168.10.4:8080/v2.0?username=xxxx&password=yyyy
    """
    def __init__(self, parsed_url):
        super(monclient, self).__init__(parsed_url)

        query_parms = parsed_url[3]
        for query_parm in query_parms.split('&'):
            name = query_parm.split('=')[0]
            value = query_parm.split('=')[1]
            if (name == 'username'):
                username = value
                LOG.debug(_('found username in query parameters'))
            if (name == 'password'):
                password = value
                LOG.debug(_('found password in query parameters'))

        endpoint = "http:" + parsed_url.path
        LOG.debug(_('publishing samples to endpoint %s') % endpoint)

        api_version = '2_0'
        kwargs = {
            'username': username,
            'password': password,
            'token': '82510970543135',
            'tenant_id': '82510970543135',
            'tenant_name': '',
            'auth_url': '',
            'service_type': '',
            'endpoint_type': '',
            'insecure': False
        }

        mon_client = client.Client(api_version, endpoint, **kwargs)
        self.metrics = mon_client.metrics

    def publish_samples(self, context, samples):
        """Main method called to publish samples."""

        for sample in samples:
            dimensions = {}
            dimensions['project_id'] = sample.project_id
            dimensions['resource_id'] = sample.resource_id
            dimensions['source'] = sample.source
            dimensions['type'] = sample.type
            dimensions['unit'] = sample.unit
            dimensions['user_id'] = sample.user_id
            self._traverse_dict(dimensions, 'meta', sample.resource_metadata)
            timeWithoutFractionalSeconds = sample.timestamp[0:19]
            try:
                seconds = \
                    calendar.timegm(time.strptime(timeWithoutFractionalSeconds,
                                                  "%Y-%m-%dT%H:%M:%S"))
            except ValueError:
                seconds = \
                    calendar.timegm(time.strptime(timeWithoutFractionalSeconds,
                                                  "%Y-%m-%d %H:%M:%S"))

            self.metrics.create(**{'name': sample.name, 'dimensions':
                                dimensions, 'timestamp': seconds, 'value':
                                sample.volume})

    def _traverse_dict(self, dimensions, name_prefix, meta_dict):
        """Method to add values of a dictionary to another dictionary.

        Nested dictionaries are handled.
        """

        for name, value in meta_dict.iteritems():
            if isinstance(value, basestring) and value:
                dimensions[name_prefix + '.' + name] = value
            elif isinstance(value, dict):
                self._traverse_dict(dimensions, name_prefix + '.' + name,
                                    value)
