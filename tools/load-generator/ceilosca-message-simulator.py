#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import eventlet
eventlet.monkey_patch()

import argparse
import datetime
import logging
import sys
import threading
import time

from oslo_config import cfg
import oslo_messaging as messaging
from oslo_messaging import notify  # noqa
from oslo_messaging import rpc  # noqa
from oslo_utils import timeutils

LOG = logging.getLogger()

USAGE = """ Usage: ./simulator.py [-h] [--url URL] [-d DEBUG]\
 {notify-server,notify-client,rpc-server,rpc-client} ...

Usage example:
 python tools/ceilosca-message-simulator.py\
 --url rabbit://stackrabbit:secretrabbit@localhost/ notify-client\
 -m 100 -s nova -a create - project_id, -r resource_id -d load_date"""


class LoggingNoParsingFilter(logging.Filter):
    def filter(self, record):
        msg = record.getMessage()
        for i in ['received {', 'MSG_ID is ']:
            if i in msg:
                return False
        return True


class NotifyEndpoint(object):
    def __init__(self):
        self.cache = []

    def info(self, ctxt, publisher_id, event_type, payload, metadata):
        LOG.info('msg rcv')
        LOG.info("%s %s %s %s" % (ctxt, publisher_id, event_type, payload))
        if payload not in self.cache:
            LOG.info('requeue msg')
            self.cache.append(payload)
            for i in range(15):
                eventlet.sleep(1)
            return messaging.NotificationResult.REQUEUE
        else:
            LOG.info('ack msg')
        return messaging.NotificationResult.HANDLED


def notify_server(transport):
    endpoints = [NotifyEndpoint()]
    target = messaging.Target(topic='notifications')
    server = notify.get_notification_listener(transport, [target],
                                              endpoints, executor='eventlet')
    server.start()
    server.wait()


class RpcEndpoint(object):
    def __init__(self, wait_before_answer):
        self.count = None
        self.wait_before_answer = wait_before_answer

    def info(self, ctxt, message):
        i = int(message.split(' ')[-1])
        if self.count is None:
            self.count = i
        elif i == 0:
            self.count = 0
        else:
            self.count += 1

        LOG.info("######## RCV: %s/%s" % (self.count, message))
        if self.wait_before_answer > 0:
            time.sleep(self.wait_before_answer)
        return "OK: %s" % message


class RpcEndpointMonitor(RpcEndpoint):
    def __init__(self, *args, **kwargs):
        super(RpcEndpointMonitor, self).__init__(*args, **kwargs)

        self._count = self._prev_count = 0
        self._monitor()

    def _monitor(self):
        threading.Timer(1.0, self._monitor).start()
        print("%d msg was received per second"
              % (self._count - self._prev_count))
        self._prev_count = self._count

    def info(self, *args, **kwargs):
        self._count += 1
        super(RpcEndpointMonitor, self).info(*args, **kwargs)


def rpc_server(transport, target, wait_before_answer, executor, show_stats):
    endpoint_cls = RpcEndpointMonitor if show_stats else RpcEndpoint
    endpoints = [endpoint_cls(wait_before_answer)]
    server = rpc.get_rpc_server(transport, target, endpoints,
                                executor=executor)
    server.start()
    server.wait()


def threads_spawner(threads, method, *args, **kwargs):
    p = eventlet.GreenPool(size=threads)
    for i in range(0, threads):
        p.spawn_n(method, i, *args, **kwargs)
    p.waitall()


def send_msg(_id, transport, target, messages, wait_after_msg, timeout,
             is_cast):
    client = rpc.RPCClient(transport, target)
    client = client.prepare(timeout=timeout)
    rpc_method = _rpc_cast if is_cast else _rpc_call

    for i in range(0, messages):
        msg = "test message %d" % i
        LOG.info("SEND: %s" % msg)
        rpc_method(client, msg)
        if wait_after_msg > 0:
            time.sleep(wait_after_msg)


def _rpc_call(client, msg):
    try:
        res = client.call({}, 'info', message=msg)
    except Exception as e:
        LOG.exception('Error %s on CALL for message %s' % (str(e), msg))
    else:
        LOG.info("SENT: %s, RCV: %s" % (msg, res))


def _rpc_cast(client, msg):
    try:
        client.cast({}, 'info', message=msg)
    except Exception as e:
        LOG.exception('Error %s on CAST for message %s' % (str(e), msg))
    else:
        LOG.info("SENT: %s" % msg)


def notifier(_id, transport, messages, wait_after_msg, timeout,
             service, action, project_id, resource_id, load_date):
    n1 = notify.Notifier(transport, topic="notifications").prepare(
        publisher_id='publisher-%d' % _id)
    # msg = 0
    for i in range(0, messages):
        # msg = 1 + msg
        ctxt = {}

        LOG.info("send msg")
        if service == 'nova':
            if action == 'create':
                n1.info(ctxt, 'compute.instance.create',
                        _instance_payload(project_id, resource_id, load_date))
            elif action == 'delete':
                n1.info(ctxt, 'compute.instance.delete',
                        _instance_payload(project_id, resource_id, load_date))
            else:
                LOG.exception('Action %s not create or delete' % (action))
                break
        elif service == 'cinder':
            if action == 'create':
                n1.info(ctxt, 'volume.create',
                        _volume_payload(project_id, resource_id, load_date))
            elif action == 'delete':
                n1.info(ctxt, 'volume.delete',
                        _volume_payload(project_id, resource_id, load_date))
            else:
                LOG.exception('Action %s not create or delete' % (action))
                break
        elif service == 'glance':
            if action == 'create':
                n1.info(ctxt, 'image.upload',
                        _image_payload(project_id, resource_id, load_date))
            elif action == 'delete':
                n1.info(ctxt, 'image.delete',
                        _image_payload(project_id, resource_id, load_date))
            else:
                LOG.exception('Action %s not create or delete' % (action))
                break
        else:
            LOG.exception('Service %s not nova, cinder or glance' % (action))
            break

        if wait_after_msg > 0:
            time.sleep(wait_after_msg)


def _volume_payload(project_id, resource_id, load_date):
    return {'user_id': u'abcd_01234_dcba',
            'tenant_id': unicode(project_id),
            'volume_id': unicode(resource_id),
            'size': 1024,
            'availablity_zone': u'nova',
            'display_name': u'simulator',
            'replication_status': u'disabled',
            'status': u'active',
            'created_at': load_date + str(timeutils.utcnow())[-15:-7]
            }


def _instance_payload(project_id, resource_id, load_date):
    return {'created_at': load_date + str(timeutils.utcnow())[-15:-7],
            'deleted_at': u'',
            'disk_gb': 50,
            'display_name': u'testme',
            'fixed_ips': [{'address': u'10.0.0.2',
                           'floating_ips': [],
                           'meta': {},
                            'type': u'fixed',
                            'version': 4}],
            'image_ref_url': u'http://10.0.2.15:9292/images/UUID',
            'instance_id': unicode(resource_id),
            'instance_type': u'm1.xlarge',
            'instance_type_id': 2,
            'launched_at': load_date + str(timeutils.utcnow())[-15:-7],
            'memory_mb': 512,
            'state': u'active',
            'state_description': u'',
            'tenant_id': unicode(project_id),
            'user_id': u'abcd_01234_dcba',
            'reservation_id': u'1e3ce043029547f1a61c1996d1a531a3',
            'vcpus': 10,
            'root_gb': 10,
            'ephemeral_gb': 10,
            'host': u'compute-host-name',
            'availability_zone': u'1e3ce043029547f1a61c1996d1a531a4',
            'os_type': u'linux?',
            'architecture': u'x86',
            'image_ref': u'UUID',
            'kernel_id': u'1e3ce043029547f1a61c1996d1a531a5',
            'ramdisk_id': u'1e3ce043029547f1a61c1996d1a531a6'
            }


def _image_payload(project_id, resource_id, load_date):
    return {'id': unicode(resource_id),
            'name': u'myImage',
            'status': u'active',
            'created_at': load_date + str(timeutils.utcnow())[-15:-7],
            'updated_at': load_date + str(timeutils.utcnow())[-15:-7],
            'min_disk': 100,
            'min_ram': 4096,
            'protected': u'',
            'checksum': u'',
            'owner': unicode(project_id),
            'disk_format': u'',
            'container_format': u'',
            'size': 1000000,
            'is_public': u'public',
            'deleted_at': ''
            }


def _setup_logging(is_debug):
    log_level = logging.DEBUG if is_debug else logging.WARN
    logging.basicConfig(stream=sys.stdout, level=log_level)
    logging.getLogger().handlers[0].addFilter(LoggingNoParsingFilter())
    for i in ['kombu', 'amqp', 'stevedore', 'qpid.messaging'
              'oslo.messaging._drivers.amqp', ]:
        logging.getLogger(i).setLevel(logging.WARN)


def main():
    parser = argparse.ArgumentParser(
        description='Tools to play with oslo.messaging\'s RPC',
        usage=USAGE,
    )
    parser.add_argument('--url', dest='url',
                        default='rabbit://guest:password@localhost/',
                        help="oslo.messaging transport url")
    parser.add_argument('-d', '--debug', dest='debug', type=bool,
                        default=False,
                        help="Turn on DEBUG logging level instead of WARN")
    subparsers = parser.add_subparsers(dest='mode',
                                       help='notify/rpc server/client mode')

    server = subparsers.add_parser('notify-server')
    client = subparsers.add_parser('notify-client')
    client.add_argument('-p', dest='threads', type=int, default=1,
                        help='number of client threads')
    client.add_argument('-m', dest='messages', type=int, default=1,
                        help='number of call per threads')
    client.add_argument('-w', dest='wait_after_msg', type=int, default=-1,
                        help='sleep time between two messages')
    client.add_argument('-t', dest='timeout', type=int, default=3,
                        help='client timeout')
    client.add_argument('-s', dest='service', default='nova',
                        help='nova, cinder or glance')
    client.add_argument('-a', dest='action', default='create',
                        help='create or delete')
    client.add_argument('-x', dest='project_id', default='tenant_abc',
                        help='project_id')
    client.add_argument('-r', dest='resource_id', default='resource_abc',
                        help='resource_id')
    client.add_argument('-d', dest='load_date', default='2015-10-01',
                        help='date in format yyyy-mm-dd')

    server = subparsers.add_parser('rpc-server')
    server.add_argument('-w', dest='wait_before_answer', type=int, default=-1)
    server.add_argument('--show-stats', dest='show_stats',
                        type=bool, default=True)
    server.add_argument('-e', '--executor', dest='executor',
                        type=str, default='eventlet',
                        help='name of a message executor')

    client = subparsers.add_parser('rpc-client')
    client.add_argument('-p', dest='threads', type=int, default=1,
                        help='number of client threads')
    client.add_argument('-m', dest='messages', type=int, default=1,
                        help='number of call per threads')
    client.add_argument('-w', dest='wait_after_msg', type=int, default=-1,
                        help='sleep time between two messages')
    client.add_argument('-t', dest='timeout', type=int, default=3,
                        help='client timeout')
    client.add_argument('--exit-wait', dest='exit_wait', type=int, default=0,
                        help='Keep connections open N seconds after calls '
                        'have been done')
    client.add_argument('--is-cast', dest='is_cast', type=bool, default=False,
                        help='Use `call` or `cast` RPC methods')

    args = parser.parse_args()

    _setup_logging(is_debug=args.debug)

    # oslo.config defaults
    cfg.CONF.heartbeat_interval = 5
    cfg.CONF.notification_topics = "notif"
    cfg.CONF.notification_driver = "messaging"

    transport = messaging.get_transport(cfg.CONF, url=args.url)
    target = messaging.Target(topic='profiler_topic', server='profiler_server')

    if args.mode == 'rpc-server':
        if args.url.startswith('zmq'):
            cfg.CONF.rpc_zmq_matchmaker = "redis"
            transport._driver.matchmaker._redis.flushdb()
        rpc_server(transport, target, args.wait_before_answer, args.executor,
                   args.show_stats)
    elif args.mode == 'notify-server':
        notify_server(transport)
    elif args.mode == 'notify-client':
        threads_spawner(args.threads, notifier, transport, args.messages,
                        args.wait_after_msg, args.timeout, args.service,
                        args.action, args.project_id, args.resource_id,
                        args.load_date)
    elif args.mode == 'rpc-client':
        start = datetime.datetime.now()
        threads_spawner(args.threads, send_msg, transport, target,
                        args.messages, args.wait_after_msg, args.timeout,
                        args.is_cast)
        time_ellapsed = (datetime.datetime.now() - start).total_seconds()
        msg_count = args.messages * args.threads
        print('%d messages was sent for %s seconds. Bandwight is %s msg/sec'
              % (msg_count, time_ellapsed, (msg_count / time_ellapsed)))
        LOG.info("calls finished, wait %d seconds" % args.exit_wait)
        time.sleep(args.exit_wait)


if __name__ == '__main__':
    main()
