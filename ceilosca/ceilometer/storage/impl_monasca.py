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

"""Simple monasca storage backend.
"""

import datetime
from monascaclient import exc as monasca_exc
from oslo_config import cfg
from oslo_log import log
from oslo_service import service as os_service
from oslo_utils import netutils
from oslo_utils import timeutils

import eventlet
from eventlet.queue import Empty

import ceilometer
from ceilometer.i18n import _
from ceilometer import monasca_client
from ceilometer.publisher.monasca_data_filter import MonascaDataFilter
from ceilometer.storage import base
from ceilometer.storage import models as api_models
from ceilometer import utils


OPTS = [
    cfg.IntOpt('default_stats_period',
               default=300,
               help='Default period (in seconds) to use for querying stats '
                    'in case no period specified in the stats API call.'),
    cfg.IntOpt('query_concurrency_limit',
               default=30,
               help='Number of concurrent queries to use for querying '
                    'Monasca API'),
]

cfg.CONF.register_opts(OPTS, group='monasca')

LOG = log.getLogger(__name__)

AVAILABLE_CAPABILITIES = {
    'meters': {'query': {'simple': True,
                         'metadata': False}},
    'resources': {'query': {'simple': True,
                            'metadata': True}},
    'samples': {'pagination': False,
                'groupby': False,
                'query': {'simple': True,
                          'metadata': True,
                          'complex': False}},
    'statistics': {'groupby': False,
                   'query': {'simple': True,
                             'metadata': False},
                   'aggregation': {'standard': True,
                                   'selectable': {
                                       'max': True,
                                       'min': True,
                                       'sum': True,
                                       'avg': True,
                                       'count': True,
                                       'stddev': False,
                                       'cardinality': False}}
                   },
}


AVAILABLE_STORAGE_CAPABILITIES = {
    'storage': {'production_ready': True},
}


class Connection(base.Connection):
    CAPABILITIES = utils.update_nested(base.Connection.CAPABILITIES,
                                       AVAILABLE_CAPABILITIES)
    STORAGE_CAPABILITIES = utils.update_nested(
        base.Connection.STORAGE_CAPABILITIES,
        AVAILABLE_STORAGE_CAPABILITIES,
    )

    def __init__(self, url):
        self.mc = monasca_client.Client(netutils.urlsplit(url))
        self.mon_filter = MonascaDataFilter()

    @staticmethod
    def _convert_to_dict(stats, cols):
        return {c: stats[i] for i, c in enumerate(cols)}

    def _convert_metaquery(self, metaquery):
        """Strip "metadata." from key and convert value to string

        :param metaquery:  { 'metadata.KEY': VALUE, ... }
        :returns: converted metaquery
        """
        query = {}
        for k, v in metaquery.items():
            key = k.split('.')[1]
            if isinstance(v, basestring):
                query[key] = v
            else:
                query[key] = str(int(v))
        return query

    def _match_metaquery_to_value_meta(self, query, value_meta):
        """Check if metaquery matches value_meta

        :param query: metaquery with converted format
        :param value_meta: metadata from monasca
        :returns: True for matched, False for not matched
        """
        if (len(query) > 0 and
           (len(value_meta) == 0 or
           not set(query.items()).issubset(set(value_meta.items())))):
            return False
        else:
            return True

    def upgrade(self):
        pass

    def clear(self):
        pass

    def record_metering_data(self, data):
        """Write the data to the backend storage system.

        :param data: a dictionary such as returned by
                     ceilometer.meter.meter_message_from_counter.
        """
        LOG.info(_('metering data %(counter_name)s for %(resource_id)s: '
                   '%(counter_volume)s')
                 % ({'counter_name': data['counter_name'],
                     'resource_id': data['resource_id'],
                     'counter_volume': data['counter_volume']}))

        metric = self.mon_filter.process_sample_for_monasca(data)
        self.mc.metrics_create(**metric)

    def clear_expired_metering_data(self, ttl):
        """Clear expired data from the backend storage system.

        Clearing occurs according to the time-to-live.
        :param ttl: Number of seconds to keep records for.
        """
        LOG.info(_("Dropping data with TTL %d"), ttl)

    def get_resources(self, user=None, project=None, source=None,
                      start_timestamp=None, start_timestamp_op=None,
                      end_timestamp=None, end_timestamp_op=None,
                      metaquery=None, resource=None, limit=None):
        """Return an iterable of dictionaries containing resource information.

        { 'resource_id': UUID of the resource,
          'project_id': UUID of project owning the resource,
          'user_id': UUID of user owning the resource,
          'timestamp': UTC datetime of last update to the resource,
          'metadata': most current metadata for the resource,
          'meter': list of the meters reporting data for the resource,
          }

        :param user: Optional ID for user that owns the resource.
        :param project: Optional ID for project that owns the resource.
        :param source: Optional source filter.
        :param start_timestamp: Optional modified timestamp start range.
        :param start_timestamp_op: Optional start time operator, like gt, ge.
        :param end_timestamp: Optional modified timestamp end range.
        :param end_timestamp_op: Optional end time operator, like lt, le.
        :param metaquery: Optional dict with metadata to match on.
        :param resource: Optional resource filter.
        :param limit: Maximum number of results to return.
        """
        if limit == 0:
            return
        # TODO(Implement limit correctly)

        q = {}
        if metaquery:
            q = self._convert_metaquery(metaquery)

        if start_timestamp_op and start_timestamp_op != 'ge':
            raise ceilometer.NotImplementedError(('Start time op %s '
                                                  'not implemented') %
                                                 start_timestamp_op)

        if end_timestamp_op and end_timestamp_op != 'le':
            raise ceilometer.NotImplementedError(('End time op %s '
                                                  'not implemented') %
                                                 end_timestamp_op)

        if not start_timestamp:
            start_timestamp = timeutils.isotime(datetime.datetime(1970, 1, 1))
        else:
            start_timestamp = timeutils.isotime(start_timestamp)

        if end_timestamp:
            end_timestamp = timeutils.isotime(end_timestamp)

        dims_filter = dict(user_id=user,
                           project_id=project,
                           source=source,
                           resource_id=resource
                           )
        dims_filter = {k: v for k, v in dims_filter.items() if v is not None}

        _search_args = dict(
            start_time=start_timestamp,
            end_time=end_timestamp,
            limit=1)

        _search_args = {k: v for k, v in _search_args.items()
                        if v is not None}

        for metric in self.mc.metrics_list(
                **dict(dimensions=dims_filter)):
            _search_args['name'] = metric['name']
            _search_args['dimensions'] = metric['dimensions']
            try:
                for sample in self.mc.measurements_list(**_search_args):
                    d = sample['dimensions']
                    m = self._convert_to_dict(
                        sample['measurements'][0], sample['columns'])
                    vm = m['value_meta']
                    if not self._match_metaquery_to_value_meta(q, vm):
                        continue
                    if d.get('resource_id'):
                        yield api_models.Resource(
                            resource_id=d.get('resource_id'),
                            first_sample_timestamp=(
                                timeutils.parse_isotime(m['timestamp'])),
                            last_sample_timestamp=timeutils.utcnow(),
                            project_id=d.get('project_id'),
                            source=d.get('source'),
                            user_id=d.get('user_id'),
                            metadata=m['value_meta'],
                        )
            except monasca_exc.HTTPConflict:
                pass

    def get_meters(self, user=None, project=None, resource=None, source=None,
                   metaquery=None, limit=None):
        """Return an iterable of dictionaries containing meter information.

        { 'name': name of the meter,
          'type': type of the meter (gauge, delta, cumulative),
          'resource_id': UUID of the resource,
          'project_id': UUID of project owning the resource,
          'user_id': UUID of user owning the resource,
          }

        :param user: Optional ID for user that owns the resource.
        :param project: Optional ID for project that owns the resource.
        :param resource: Optional resource filter.
        :param source: Optional source filter.
        :param metaquery: Optional dict with metadata to match on.
        :param limit: Maximum number of results to return.
        """
        if limit == 0:
            return

        if metaquery:
            raise ceilometer.NotImplementedError('Metaquery not implemented')

        _dimensions = dict(
            user_id=user,
            project_id=project,
            resource_id=resource,
            source=source
        )

        _dimensions = {k: v for k, v in _dimensions.items() if v is not None}

        _search_kwargs = {'dimensions': _dimensions}

        if limit:
            _search_kwargs['limit'] = limit

        for metric in self.mc.metrics_list(**_search_kwargs):
            yield api_models.Meter(
                name=metric['name'],
                type=metric['dimensions'].get('type') or 'cumulative',
                unit=metric['dimensions'].get('unit'),
                resource_id=metric['dimensions'].get('resource_id'),
                project_id=metric['dimensions'].get('project_id'),
                source=metric['dimensions'].get('source'),
                user_id=metric['dimensions'].get('user_id'))

    def get_measurements(self, result_queue, metric_name, metric_dimensions,
                         meta_q, start_ts, end_ts, start_op, end_op, limit):

        start_ts = timeutils.isotime(start_ts)
        end_ts = timeutils.isotime(end_ts)

        _search_args = dict(name=metric_name,
                            start_time=start_ts,
                            start_timestamp_op=start_op,
                            end_time=end_ts,
                            end_timestamp_op=end_op,
                            merge_metrics=False,
                            limit=limit,
                            dimensions=metric_dimensions)

        _search_args = {k: v for k, v in _search_args.items()
                        if v is not None}

        for sample in self.mc.measurements_list(**_search_args):
            LOG.debug(_('Retrieved sample: %s'), sample)

            d = sample['dimensions']
            for measurement in sample['measurements']:
                meas_dict = self._convert_to_dict(measurement,
                                                  sample['columns'])
                vm = meas_dict['value_meta']
                if not self._match_metaquery_to_value_meta(meta_q, vm):
                    continue
                result_queue.put(api_models.Sample(
                    source=d.get('source'),
                    counter_name=sample['name'],
                    counter_type=d.get('type'),
                    counter_unit=d.get('unit'),
                    counter_volume=meas_dict['value'],
                    user_id=d.get('user_id'),
                    project_id=d.get('project_id'),
                    resource_id=d.get('resource_id'),
                    timestamp=timeutils.parse_isotime(meas_dict['timestamp']),
                    resource_metadata=meas_dict['value_meta'],
                    message_id=sample['id'],
                    message_signature='',
                    recorded_at=(
                        timeutils.parse_isotime(meas_dict['timestamp']))))

    def get_next_time_delta(self, start, end, delta):
        # Gets next time window
        curr = start
        while curr < end:
            next = curr + delta
            yield curr, next
            curr = next

    def get_next_task_args(self, sample_filter, delta, **kwargs):
        # Yields next set of measurement related args
        metrics = self.mc.metrics_list(**kwargs)
        for start, end in self.get_next_time_delta(
                sample_filter.start_timestamp,
                sample_filter.end_timestamp,
                delta):
            for metric in metrics:
                task = {'metric': metric['name'],
                        'dimension': metric['dimensions'],
                        'start_ts': start,
                        'end_ts': end}
                LOG.debug(_('next task is : %s'), task)
                yield task

    def has_more_results(self, result_queue, t_pool):
        if result_queue.empty() and t_pool.pool.running() == 0:
            return False
        return True

    def fetch_from_queue(self, result_queue, t_pool):
        # Fetches result from queue in non-blocking way
        try:
            result = result_queue.get_nowait()
            LOG.debug(_('Retrieved result : %s'), result)
            return result
        except Empty:
            # if no data in queue, yield to work threads
            # to give them a chance
            if t_pool.pool.running() > 0:
                eventlet.sleep(0)

    def get_results(self, result_queue, t_pool, limit=None, result_count=None):
        # Inspect and yield results
        if limit:
            while result_count < limit:
                if not self.has_more_results(result_queue, t_pool):
                    break
                result = self.fetch_from_queue(result_queue, t_pool)
                if result:
                    yield result
                    result_count += 1
        else:
            while True:
                if not self.has_more_results(result_queue, t_pool):
                    break
                result = self.fetch_from_queue(result_queue, t_pool)
                if result:
                    yield result

    def get_samples(self, sample_filter, limit=None):
        """Return an iterable of dictionaries containing sample information.

        {
          'source': source of the resource,
          'counter_name': name of the resource,
          'counter_type': type of the sample (gauge, delta, cumulative),
          'counter_unit': unit of the sample,
          'counter_volume': volume of the sample,
          'user_id': UUID of user owning the resource,
          'project_id': UUID of project owning the resource,
          'resource_id': UUID of the resource,
          'timestamp': timestamp of the sample,
          'resource_metadata': metadata of the sample,
          'message_id': message ID of the sample,
          'message_signature': message signature of the sample,
          'recorded_at': time the sample was recorded
          }

        :param sample_filter: constraints for the sample search.
        :param limit: Maximum number of results to return.
        """
        # Initialize pool of green work threads and queue to handle results
        thread_pool = os_service.threadgroup.ThreadGroup(
            thread_pool_size=cfg.CONF.monasca.query_concurrency_limit)
        result_queue = eventlet.queue.Queue()

        if not sample_filter or not sample_filter.meter:
            raise ceilometer.NotImplementedError(
                "Supply meter name at the least")

        if (sample_filter.start_timestamp_op and
                sample_filter.start_timestamp_op != 'ge'):
            raise ceilometer.NotImplementedError(('Start time op %s '
                                                  'not implemented') %
                                                 sample_filter.
                                                 start_timestamp_op)

        if (sample_filter.end_timestamp_op and
                sample_filter.end_timestamp_op != 'le'):
            raise ceilometer.NotImplementedError(('End time op %s '
                                                  'not implemented') %
                                                 sample_filter.
                                                 end_timestamp_op)

        q = {}
        if sample_filter.metaquery:
            q = self._convert_metaquery(sample_filter.metaquery)

        if sample_filter.message_id:
            raise ceilometer.NotImplementedError('message_id not '
                                                 'implemented '
                                                 'in get_samples')

        if not sample_filter.start_timestamp:
            sample_filter.start_timestamp = datetime.datetime(1970, 1, 1)

        if not sample_filter.end_timestamp:
            sample_filter.end_timestamp = datetime.datetime.utcnow()

        delta = sample_filter.end_timestamp - sample_filter.start_timestamp
        delta = delta / cfg.CONF.monasca.query_concurrency_limit

        _dimensions = dict(
            user_id=sample_filter.user,
            project_id=sample_filter.project,
            resource_id=sample_filter.resource,
            source=sample_filter.source
        )

        _dimensions = {k: v for k, v in _dimensions.items() if v is not None}

        _metric_args = dict(name=sample_filter.meter,
                            dimensions=_dimensions)

        if limit:
            result_count = 0

        for task_cnt, task in enumerate(self.get_next_task_args(
                sample_filter, delta, **_metric_args)):
            # Spawn query_concurrency_limit number of green threads
            # simultaneously to fetch measurements
            thread_pool.add_thread(self.get_measurements,
                                   result_queue,
                                   task['metric'],
                                   task['dimension'],
                                   q,
                                   task['start_ts'],
                                   task['end_ts'],
                                   sample_filter.start_timestamp_op,
                                   sample_filter.end_timestamp_op,
                                   limit)
            # For every query_conncurrency_limit set of tasks,
            # consume data from queue and yield before moving on to
            # next set of tasks.
            if (task_cnt + 1) % cfg.CONF.monasca.query_concurrency_limit == 0:
                for result in self.get_results(result_queue, thread_pool,
                                               limit,
                                               result_count=result_count if
                                               limit else None):
                    yield result

        # Shutdown threadpool
        thread_pool.stop()

    def get_meter_statistics(self, filter, period=None, groupby=None,
                             aggregate=None):
        """Return a dictionary containing meter statistics.

        Meter statistics is described by the query parameters.
        The filter must have a meter value set.

        { 'min':
          'max':
          'avg':
          'sum':
          'count':
          'period':
          'period_start':
          'period_end':
          'duration':
          'duration_start':
          'duration_end':
          }
        """
        if filter:
            if not filter.meter:
                raise ceilometer.NotImplementedError('Query without meter '
                                                     'not implemented')
        else:
            raise ceilometer.NotImplementedError('Query without filter '
                                                 'not implemented')

        if groupby:
            raise ceilometer.NotImplementedError('Groupby not implemented')

        if filter.metaquery:
            raise ceilometer.NotImplementedError('Metaquery not implemented')

        if filter.message_id:
            raise ceilometer.NotImplementedError('Message_id query '
                                                 'not implemented')

        if filter.start_timestamp_op and filter.start_timestamp_op != 'ge':
            raise ceilometer.NotImplementedError(('Start time op %s '
                                                  'not implemented') %
                                                 filter.start_timestamp_op)

        if filter.end_timestamp_op and filter.end_timestamp_op != 'le':
            raise ceilometer.NotImplementedError(('End time op %s '
                                                  'not implemented') %
                                                 filter.end_timestamp_op)

        if not filter.start_timestamp:
            filter.start_timestamp = timeutils.isotime(
                datetime.datetime(1970, 1, 1))

        # TODO(monasca): Add this a config parameter
        allowed_stats = ['avg', 'min', 'max', 'sum', 'count']
        if aggregate:
            not_allowed_stats = [a.func for a in aggregate
                                 if a.func not in allowed_stats]
            if not_allowed_stats:
                raise ceilometer.NotImplementedError(('Aggregate function(s) '
                                                      '%s not implemented') %
                                                     not_allowed_stats)

            statistics = [a.func for a in aggregate
                          if a.func in allowed_stats]
        else:
            statistics = allowed_stats

        dims_filter = dict(user_id=filter.user,
                           project_id=filter.project,
                           source=filter.source,
                           resource_id=filter.resource
                           )
        dims_filter = {k: v for k, v in dims_filter.items() if v is not None}

        period = period if period \
            else cfg.CONF.monasca.default_stats_period

        _search_args = dict(
            name=filter.meter,
            dimensions=dims_filter,
            start_time=filter.start_timestamp,
            end_time=filter.end_timestamp,
            period=period,
            statistics=','.join(statistics),
            merge_metrics=True)

        _search_args = {k: v for k, v in _search_args.items()
                        if v is not None}

        stats_list = self.mc.statistics_list(**_search_args)
        for stats in stats_list:
            for s in stats['statistics']:
                stats_dict = self._convert_to_dict(s, stats['columns'])
                ts_start = timeutils.parse_isotime(stats_dict['timestamp'])
                ts_end = ts_start + datetime.timedelta(0, period)
                del stats_dict['timestamp']
                if 'count' in stats_dict:
                    stats_dict['count'] = int(stats_dict['count'])
                yield api_models.Statistics(
                    unit=stats['dimensions'].get('unit'),
                    period=period,
                    period_start=ts_start,
                    period_end=ts_end,
                    duration=period,
                    duration_start=ts_start,
                    duration_end=ts_end,
                    groupby={u'': u''},
                    **stats_dict
                )
