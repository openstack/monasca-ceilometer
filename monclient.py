import calendar
import time

from ceilometer.openstack.common.gettextutils import _
from ceilometer.openstack.common import log
from ceilometer import publisher
from monascaclient import client
from monascaclient import ksclient


LOG = log.getLogger(__name__)


class monclient(publisher.PublisherBase):
    """Publisher to publish samples to monclient.

    Example URL to place in pipeline.yaml:
        - monclient://http://192.168.10.4:8080/v2.0?username=xxxx&password=yyyy
    """
    def __init__(self, parsed_url):
        super(monclient, self).__init__(parsed_url)

        # Set these if they are not passed as part of the URL
        self.token = None
        self.username = None
        self.password = None
        # auth_url must be a v3 endpoint, e.g.
        # http://192.168.10.5:35357/v3/
        self.auth_url = "http://20.20.20.76:35357/v3/"
        query_parms = parsed_url[3]
        for query_parm in query_parms.split('&'):
            name = query_parm.split('=')[0]
            value = query_parm.split('=')[1]
            if (name == 'username'):
                self.username = value
                LOG.debug(_('found username in query parameters'))
            if (name == 'password'):
                self.password = str(value)
                LOG.debug(_('found password in query parameters'))
            if (name == 'token'):
                self.token = value
                LOG.debug(_('found token in query parameters'))
        if not self.token:
            if not self.username or not self.password:
                LOG.error(_('username and password must be '
                            'specified if no token is given'))
            if not self.auth_url:
                LOG.error(_('auth_url must be '
                            'specified if no token is given'))
        self.endpoint = "http:" + parsed_url.path
        LOG.debug(_('publishing samples to endpoint %s') % self.endpoint)

    def publish_samples(self, context, samples):
        """Main method called to publish samples."""

        if not self.token:
            kwargs = {
                'username': self.username,
                'password': self.password,
                'auth_url': self.auth_url
            }

            _ksclient = ksclient.KSClient(**kwargs)
            self.token = _ksclient.token
        kwargs = {'token': self.token}
        api_version = '2_0'
        mon_client = client.Client(api_version, self.endpoint, **kwargs)
        self.metrics = mon_client.metrics
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
