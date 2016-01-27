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
import operator

from monascaclient import exc as monasca_exc
from oslo_config import cfg
from oslo_log import log
from oslo_utils import netutils
from oslo_utils import timeutils

import ceilometer
from ceilometer.i18n import _
from ceilometer import monasca_client
from ceilometer.publisher.monasca_data_filter import MonascaDataFilter
from ceilometer import storage
from ceilometer.storage import base
from ceilometer.storage import models as api_models
from ceilometer import utils


OPTS = [
    cfg.IntOpt('default_stats_period',
               default=300,
               help='Default period (in seconds) to use for querying stats '
                    'in case no period specified in the stats API call.'),
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
                          'complex': True}},
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
        if (query and (len(value_meta) == 0 or
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

        result_count = 0
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
                        result_count += 1

                        yield api_models.Resource(
                            resource_id=d.get('resource_id'),
                            first_sample_timestamp=(
                                timeutils.parse_isotime(m['timestamp'])),
                            last_sample_timestamp=timeutils.utcnow(),
                            project_id=d.get('project_id'),
                            source=d.get('source'),
                            user_id=d.get('user_id'),
                            metadata=m['value_meta']
                        )

                        if result_count == limit:
                            return

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

    def get_samples(self, sample_filter, limit=None):
        """Return an iterable of dictionaries containing sample information.

        {
          'source': source of the resource,
          'counter_name': name of the resource,if groupby:
            raise ceilometer.NotImplementedError('Groupby not implemented')
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

        if limit == 0:
            return

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

        _dimensions = dict(
            user_id=sample_filter.user,
            project_id=sample_filter.project,
            resource_id=sample_filter.resource,
            source=sample_filter.source,
            # Dynamic sample filter attributes, these fields are useful for
            # filtering result.
            unit=getattr(sample_filter, 'unit', None),
            type=getattr(sample_filter, 'type', None),
        )

        _dimensions = {k: v for k, v in _dimensions.items() if v is not None}

        _metric_args = dict(name=sample_filter.meter,
                            dimensions=_dimensions)

        start_ts = timeutils.isotime(sample_filter.start_timestamp)
        end_ts = timeutils.isotime(sample_filter.end_timestamp)

        _search_args = dict(
            start_time=start_ts,
            start_timestamp_op=sample_filter.start_timestamp_op,
            end_time=end_ts,
            end_timestamp_op=sample_filter.end_timestamp_op,
            merge_metrics=False
        )

        result_count = 0
        for metric in self.mc.metrics_list(
                **_metric_args):
            _search_args['name'] = metric['name']
            _search_args['dimensions'] = metric['dimensions']
            _search_args = {k: v for k, v in _search_args.items()
                            if v is not None}

            for sample in self.mc.measurements_list(**_search_args):
                d = sample['dimensions']
                for meas in sample['measurements']:
                    m = self._convert_to_dict(
                        meas, sample['columns'])
                    vm = m['value_meta']
                    if not self._match_metaquery_to_value_meta(q, vm):
                        continue
                    result_count += 1
                    yield api_models.Sample(
                        source=d.get('source'),
                        counter_name=sample['name'],
                        counter_type=d.get('type'),
                        counter_unit=d.get('unit'),
                        counter_volume=m['value'],
                        user_id=d.get('user_id'),
                        project_id=d.get('project_id'),
                        resource_id=d.get('resource_id'),
                        timestamp=timeutils.parse_isotime(m['timestamp']),
                        resource_metadata=m['value_meta'],
                        message_id=sample['id'],
                        message_signature='',
                        recorded_at=(timeutils.parse_isotime(m['timestamp'])))

                    if result_count == limit:
                        return

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

        allowed_groupby = ['user_id', 'project_id', 'resource_id', 'source']

        if groupby:
            if len(groupby) > 1:
                raise ceilometer.NotImplementedError('Only one groupby '
                                                     'supported')

            groupby = groupby[0]
            if groupby not in allowed_groupby:
                raise ceilometer.NotImplementedError('Groupby %s not'
                                                     ' implemented' % groupby)

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
        else:
            filter.start_timestamp = timeutils.isotime(filter.start_timestamp)

        if filter.end_timestamp:
            filter.end_timestamp = timeutils.isotime(filter.end_timestamp)

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

        if groupby:
            _metric_args = dict(name=filter.meter,
                                dimensions=dims_filter)
            group_stats_list = []

            for metric in self.mc.metrics_list(**_metric_args):
                _search_args = dict(
                    name=metric['name'],
                    dimensions=metric['dimensions'],
                    start_time=filter.start_timestamp,
                    end_time=filter.end_timestamp,
                    period=period,
                    statistics=','.join(statistics),
                    merge_metrics=False)

                _search_args = {k: v for k, v in _search_args.items()
                                if v is not None}
                stats_list = self.mc.statistics_list(**_search_args)
                group_stats_list.extend(stats_list)

            group_stats_dict = {}

            for stats in group_stats_list:
                groupby_val = stats['dimensions'].get(groupby)
                stats_list = group_stats_dict.get(groupby_val)
                if stats_list:
                    stats_list.append(stats)
                else:
                    group_stats_dict[groupby_val] = [stats]

            def get_max(items):
                return max(items)

            def get_min(items):
                return min(items)

            def get_avg(items):
                return sum(items)/len(items)

            def get_sum(items):
                return sum(items)

            def get_count(items):
                count = 0
                for item in items:
                    count = count + item
                return count

            for group_key, stats_group in group_stats_dict.iteritems():
                max_list = []
                min_list = []
                avg_list = []
                sum_list = []
                count_list = []
                ts_list = []
                group_statistics = {}
                for stats in stats_group:
                    for s in stats['statistics']:
                        stats_dict = self._convert_to_dict(s, stats['columns'])

                        if 'max' in stats['columns']:
                            max_list.append(stats_dict['max'])
                        if 'min' in stats['columns']:
                            min_list.append(stats_dict['min'])
                        if 'avg' in stats['columns']:
                            avg_list.append(stats_dict['avg'])
                        if 'sum' in stats['columns']:
                            sum_list.append(stats_dict['sum'])
                        if 'count' in stats['columns']:
                            count_list.append(stats_dict['count'])

                        ts_list.append(stats_dict['timestamp'])

                        group_statistics['unit'] = (stats['dimensions'].
                                                    get('unit'))

                if len(max_list):
                    group_statistics['max'] = get_max(max_list)
                if len(min_list):
                    group_statistics['min'] = get_min(min_list)
                if len(avg_list):
                    group_statistics['avg'] = get_avg(avg_list)
                if len(sum_list):
                    group_statistics['sum'] = get_sum(sum_list)
                if len(count_list):
                    group_statistics['count'] = get_count(count_list)

                group_statistics['end_timestamp'] = get_max(ts_list)
                group_statistics['timestamp'] = get_min(ts_list)

                ts_start = timeutils.parse_isotime(
                    group_statistics['timestamp']).replace(tzinfo=None)

                ts_end = timeutils.parse_isotime(
                    group_statistics['end_timestamp']).replace(tzinfo=None)

                del group_statistics['end_timestamp']

                if 'count' in group_statistics:
                    group_statistics['count'] = int(group_statistics['count'])
                unit = group_statistics['unit']
                del group_statistics['unit']
                if aggregate:
                        group_statistics['aggregate'] = {}
                        for a in aggregate:
                            key = '%s%s' % (a.func, '/%s' % a.param if a.param
                                            else '')
                            group_statistics['aggregate'][key] = (
                                group_statistics.get(key))
                yield api_models.Statistics(
                    unit=unit,
                    period=period,
                    period_start=ts_start,
                    period_end=ts_end,
                    duration=period,
                    duration_start=ts_start,
                    duration_end=ts_end,
                    groupby={groupby: group_key},
                    **group_statistics
                )
        else:
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
                    ts_start = timeutils.parse_isotime(
                        stats_dict['timestamp']).replace(tzinfo=None)
                    ts_end = (ts_start + datetime.timedelta(
                        0, period)).replace(tzinfo=None)
                    del stats_dict['timestamp']
                    if 'count' in stats_dict:
                        stats_dict['count'] = int(stats_dict['count'])

                    if aggregate:
                        stats_dict['aggregate'] = {}
                        for a in aggregate:
                            key = '%s%s' % (a.func, '/%s' % a.param if a.param
                                            else '')
                            stats_dict['aggregate'][key] = stats_dict.get(key)

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

    def _parse_to_filter_list(self, filter_expr):
        """Parse complex query expression to simple filter list.

        For i.e. parse:
            {"or":[{"=":{"meter":"cpu"}},{"=":{"meter":"memory"}}]}
        to
            [[{"=":{"counter_name":"cpu"}}],
             [{"=":{"counter_name":"memory"}}]]
        """
        op, nodes = filter_expr.items()[0]
        msg = "%s operand is not supported" % op

        if op == 'or':
            filter_list = []
            for node in nodes:
                filter_list.extend(self._parse_to_filter_list(node))
            return filter_list
        elif op == 'and':
            filter_list_subtree = []
            for node in nodes:
                filter_list_subtree.append(self._parse_to_filter_list(node))
            filter_list = [[]]
            for filters in filter_list_subtree:
                tmp = []
                for filter in filters:
                    for f in filter_list:
                        tmp.append(f + filter)
                filter_list = tmp
            return filter_list
        elif op == 'not':
            raise ceilometer.NotImplementedError(msg)
        elif op in ("<", "<=", "=", ">=", ">", '!='):
            return [[filter_expr]]
        else:
            raise ceilometer.NotImplementedError(msg)

    def _parse_to_sample_filter(self, simple_filters):
        """Parse to simple filters to sample filter.

        For i.e.: parse
            [{"=":{"counter_name":"cpu"}},{"=":{"counter_volume": 1}}]
        to
            SampleFilter(counter_name="cpu", counter_volume=1)
        """
        equal_only_fields = (
            'counter_name',
            'counter_unit',
            'counter_type',
            'project_id',
            'user_id',
            'source',
            'resource_id',
            # These fields are supported by Ceilometer but cannot supported
            # by Monasca.
            # 'message_id',
            # 'message_signature',
            # 'recorded_at',
        )
        field_map = {
            "project_id": "project",
            "user_id": "user",
            "resource_id": "resource",
            "counter_name": "meter",
            "counter_type": "type",
            "counter_unit": "unit",
        }
        msg = "operand %s cannot be applied to field %s"
        kwargs = {'metaquery': {}}
        for sf in simple_filters:
            op = sf.keys()[0]
            field, value = sf.values()[0].items()[0]
            if field in equal_only_fields:
                if op != '=':
                    raise ceilometer.NotImplementedError(msg % (op, field))
                field = field_map.get(field, field)
                kwargs[field] = value
            elif field == 'timestamp':
                if op == '>=':
                    kwargs['start_timestamp'] = value
                    kwargs['start_timestamp_op'] = 'ge'
                elif op == '<=':
                    kwargs['end_timestamp'] = value
                    kwargs['end_timestamp_op'] = 'le'
                else:
                    raise ceilometer.NotImplementedError(msg % (op, field))
            elif field == 'counter_volume':
                kwargs['volume'] = value
                kwargs['volume_op'] = op
            elif (field.startswith('resource_metadata.') or
                  field.startswith('metadata.')):
                kwargs['metaquery'][field] = value
            else:
                ra_msg = "field %s is not supported" % field
                raise ceilometer.NotImplementedError(ra_msg)
        sample_type = kwargs.pop('type', None)
        sample_unit = kwargs.pop('unit', None)
        sample_volume = kwargs.pop('volume', None)
        sample_volume_op = kwargs.pop('volume_op', None)
        sample_filter = storage.SampleFilter(**kwargs)
        # Add some dynamic attributes, type and unit attributes can be used
        # when query Monasca API, volume and volime_op attributes can
        # be used for volume comparison.
        sample_filter.type = sample_type
        sample_filter.unit = sample_unit
        sample_filter.volume = sample_volume
        sample_filter.volume_op = sample_volume_op
        return sample_filter

    def _parse_to_sample_filters(self, filter_expr):
        """Parse complex query expression to sample filter list."""
        filter_list = self._parse_to_filter_list(filter_expr)
        sample_filters = []
        for filters in filter_list:
            sf = self._parse_to_sample_filter(filters)
            if sf:
                sample_filters.append(sf)
        return sample_filters

    def _validate_samples_by_volume(self, samples, sf):
        if not sf.volume:
            return samples

        op_func_map = {
            '<': operator.lt,
            '<=': operator.le,
            '=': operator.eq,
            '>=': operator.ge,
            '>': operator.gt,
            '!=': operator.ne,
        }

        ret = []
        for s in samples:
            op_func = op_func_map[sf.volume_op]
            volume = getattr(s, 'volume', getattr(s, 'counter_volume', None))
            if op_func(volume, sf.volume):
                ret.append(s)
        return ret

    def query_samples(self, filter_expr=None, orderby=None, limit=None):
        if not filter_expr:
            msg = "fitler must be specified"
            raise ceilometer.NotImplementedError(msg)
        if orderby:
            msg = "orderby is not supported"
            raise ceilometer.NotImplementedError(msg)
        if not limit:
            msg = "limit must be specified"
            raise ceilometer.NotImplementedError(msg)

        LOG.debug("filter_expr = %s", filter_expr)
        sample_filters = self._parse_to_sample_filters(filter_expr)
        LOG.debug("sample_filters = %s", sample_filters)

        ret = []
        for sf in sample_filters:
            if not sf.volume:
                samples = list(self.get_samples(sf, limit))
            else:
                samples = self.get_samples(sf)
                samples = list(self._validate_samples_by_volume(samples, sf))

            if limit <= len(samples):
                ret.extend(samples[0:limit])
                break
            else:
                ret.extend(samples)
                limit -= len(samples)

        return ret
