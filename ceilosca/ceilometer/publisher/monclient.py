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

import os
import time

from oslo_config import cfg
from oslo_log import log
from oslo_service import loopingcall

import ceilometer
from ceilometer.i18n import _
from ceilometer import monasca_client as mon_client
from ceilometer import publisher
from ceilometer.publisher.monasca_data_filter import MonascaDataFilter

from monascaclient import exc


monpub_opts = [
    cfg.BoolOpt('batch_mode',
                default=True,
                help='Indicates whether samples are'
                     ' published in a batch.'),
    cfg.IntOpt('batch_count',
               default=1000,
               help='Maximum number of samples in a batch.'),
    cfg.IntOpt('batch_timeout',
               default=15,
               help='Maximum time interval(seconds) after which '
                    'samples are published in a batch.'),
    cfg.IntOpt('batch_polling_interval',
               default=5,
               help='Frequency of checking if batch criteria is met.'),
    cfg.BoolOpt('retry_on_failure',
                default=False,
                help='Indicates whether publisher retries publishing'
                     'sample in case of failure. Only a few error cases'
                     'are queued for a retry.'),
    cfg.IntOpt('retry_interval',
               default=60,
               help='Frequency of attempting a retry.'),
    cfg.IntOpt('max_retries',
               default=3,
               help='Maximum number of retry attempts on a publishing '
                    'failure.'),
    cfg.BoolOpt('archive_on_failure',
                default=False,
                help='When turned on, archives metrics in file system when'
                     'publish to Monasca fails or metric publish maxes out'
                     'retry attempts.'),
    cfg.StrOpt('archive_path',
               default='mon_pub_failures.txt',
               help='File of metrics that failed to publish to '
                    'Monasca. These include metrics that failed to '
                    'publish on first attempt and failed metrics that'
                    ' maxed out their retries.'),
]

cfg.CONF.register_opts(monpub_opts, group='monasca')
cfg.CONF.import_group('service_credentials', 'ceilometer.service')

LOG = log.getLogger(__name__)


class MonascaPublisher(publisher.PublisherBase):
    """Publisher to publish samples to monasca using monasca-client.

    Example URL to place in pipeline.yaml:
        - monclient://http://192.168.10.4:8070/v2.0
    """
    def __init__(self, parsed_url):
        super(MonascaPublisher, self).__init__(parsed_url)

        # list to hold metrics to be published in batch (behaves like queue)
        self.metric_queue = []
        self.time_of_last_batch_run = time.time()

        self.mon_client = mon_client.Client(parsed_url)
        self.mon_filter = MonascaDataFilter()

        batch_timer = loopingcall.FixedIntervalLoopingCall(self.flush_batch)
        batch_timer.start(interval=cfg.CONF.monasca.batch_polling_interval)

        if cfg.CONF.monasca.retry_on_failure:
            # list to hold metrics to be re-tried (behaves like queue)
            self.retry_queue = []
            # list to store retry attempts for metrics in retry_queue
            self.retry_counter = []
            retry_timer = loopingcall.FixedIntervalLoopingCall(
                self.retry_batch)
            retry_timer.start(
                interval=cfg.CONF.monasca.retry_interval,
                initial_delay=cfg.CONF.monasca.batch_polling_interval)

        if cfg.CONF.monasca.archive_on_failure:
            archive_path = cfg.CONF.monasca.archive_path
            if not os.path.exists(archive_path):
                archive_path = cfg.CONF.find_file(archive_path)

            self.archive_handler = publisher.get_publisher('file://' +
                                                           str(archive_path))

    def _publish_handler(self, func, metrics, batch=False):
        """Handles publishing and exceptions that arise."""

        try:
            metric_count = len(metrics)
            if batch:
                func(**{'jsonbody': metrics})
            else:
                func(**metrics[0])
            LOG.debug(_('Successfully published %d metric(s)') % metric_count)
        except mon_client.MonascaServiceException:
            # Assuming atomicity of create or failure - meaning
            # either all succeed or all fail in a batch
            LOG.error(_('Metric create failed for %(count)d metric(s) with'
                        ' name(s) %(names)s ') %
                      ({'count': len(metrics),
                        'names': ','.join([metric['name']
                                           for metric in metrics])}))
            if cfg.CONF.monasca.retry_on_failure:
                # retry payload in case of internal server error(500),
                # service unavailable error(503),bad gateway (502) or
                # Communication Error

                # append failed metrics to retry_queue
                LOG.debug(_('Adding metrics to retry queue.'))
                self.retry_queue.extend(metrics)
                # initialize the retry_attempt for the each failed
                # metric in retry_counter
                self.retry_counter.extend(
                    [0 * i for i in range(metric_count)])
            else:
                if hasattr(self, 'archive_handler'):
                    self.archive_handler.publish_samples(None, metrics)
        except Exception:
            if hasattr(self, 'archive_handler'):
                    self.archive_handler.publish_samples(None, metrics)

    def publish_samples(self, samples):
        """Main method called to publish samples."""

        for sample in samples:
            metric = self.mon_filter.process_sample_for_monasca(sample)
            # In batch mode, push metric to queue,
            # else publish the metric
            if cfg.CONF.monasca.batch_mode:
                LOG.debug(_('Adding metric to queue.'))
                self.metric_queue.append(metric)
            else:
                LOG.debug(_('Publishing metric with name %(name)s and'
                            ' timestamp %(ts)s to endpoint.') %
                          ({'name': metric['name'],
                            'ts': metric['timestamp']}))

                self._publish_handler(self.mon_client.metrics_create, [metric])

    def is_batch_ready(self):
        """Method to check if batch is ready to trigger."""

        previous_time = self.time_of_last_batch_run
        current_time = time.time()
        elapsed_time = current_time - previous_time

        if elapsed_time >= cfg.CONF.monasca.batch_timeout and len(self.
           metric_queue) > 0:
            LOG.debug(_('Batch timeout exceeded, triggering batch publish.'))
            return True
        else:
            if len(self.metric_queue) >= cfg.CONF.monasca.batch_count:
                LOG.debug(_('Batch queue full, triggering batch publish.'))
                return True
            else:
                return False

    def flush_batch(self):
        """Method to flush the queued metrics."""

        if self.is_batch_ready():
            # publish all metrics in queue at this point
            batch_count = len(self.metric_queue)

            self._publish_handler(self.mon_client.metrics_create,
                                  self.metric_queue[:batch_count],
                                  batch=True)

            self.time_of_last_batch_run = time.time()
            # slice queue to remove metrics that
            # published with success or failed and got queued on
            # retry queue
            self.metric_queue = self.metric_queue[batch_count:]

    def is_retry_ready(self):
        """Method to check if retry batch is ready to trigger."""

        if len(self.retry_queue) > 0:
            LOG.debug(_('Retry queue has items, triggering retry.'))
            return True
        else:
            return False

    def retry_batch(self):
        """Method to retry the failed metrics."""

        if self.is_retry_ready():
            retry_count = len(self.retry_queue)

            # Iterate over the retry_queue to eliminate
            # metrics that have maxed out their retry attempts
            for ctr in xrange(retry_count):
                if self.retry_counter[ctr] > cfg.CONF.monasca.max_retries:
                    if hasattr(self, 'archive_handler'):
                        self.archive_handler.publish_samples(
                            None,
                            [self.retry_queue[ctr]])
                    LOG.debug(_('Removing metric %s from retry queue.'
                                ' Metric retry maxed out retry attempts') %
                              self.retry_queue[ctr]['name'])
                    del self.retry_queue[ctr]
                    del self.retry_counter[ctr]

            # Iterate over the retry_queue to retry the
            # publish for each metric.
            # If an exception occurs, the retry count for
            # the failed metric is incremented.
            # If the retry succeeds, remove the metric and
            # the retry count from the retry_queue and retry_counter resp.
            ctr = 0
            while ctr < len(self.retry_queue):
                try:
                    LOG.debug(_('Retrying metric publish from retry queue.'))
                    self.mon_client.metrics_create(**self.retry_queue[ctr])
                    # remove from retry queue if publish was success
                    LOG.debug(_('Retrying metric %s successful,'
                                ' removing metric from retry queue.') %
                              self.retry_queue[ctr]['name'])
                    del self.retry_queue[ctr]
                    del self.retry_counter[ctr]
                except exc.BaseException:
                    LOG.error(_('Exception encountered in retry. '
                                'Batch will be retried in next attempt.'))
                    # if retry failed, increment the retry counter
                    self.retry_counter[ctr] += 1
                    ctr += 1

    def publish_events(self, events):
        """Send an event message for publishing

        :param events: events from pipeline after transformation
        """
        raise ceilometer.NotImplementedError
