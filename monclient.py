from ceilometer.monclient import client
from ceilometer import publisher
import time
import calendar

class monclient (publisher.PublisherBase):

    def __init__(self, parsed_url):
        super(monclient, self).__init__(parsed_url)


        username_password_part = parsed_url[3]
        username_part = username_password_part.split('&')[0]
        username = username_part.split('=')[1]
        password_part = username_password_part.split('&')[1]
        password = password_part.split('=')[1]

        endpoint = "http:" + parsed_url.path
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
            'insecure': False,
            'runlocal': True
        }

        mon_client = client.Client(api_version, endpoint, **kwargs)
        self.metrics = mon_client.metrics

    def publish_samples(self, context, samples):

        for sample in samples:
            dimensions = {}
            dimensions['project_id'] = sample.project_id
            dimensions['resource_id'] = sample.resource_id
            dimensions['source'] = sample.source
            dimensions['type'] = sample.type
            dimensions['unit'] = sample.unit
            dimensions['user_id'] = sample.user_id
            for name, value in sample.resource_metadata:
                dimensions['meta.' + name] = value

            timeWithoutFractionalSeconds = sample.timestamp[0:19]
            seconds = calendar.timegm(time.strptime(timeWithoutFractionalSeconds, "%Y-%m-%dT%H:%M:%S"))

            self.metrics.create(**{'name':sample.name, 'dimensions': dimensions, 'timestamp': seconds, 'value': sample.volume})

