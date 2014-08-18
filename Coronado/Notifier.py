import socket
import ssl
import struct
import binascii
from random import random
import json
import time
from datetime import datetime, timedelta
import logging
from Queue import Queue, Empty

import tornado.iostream
from tornado.iostream import StreamClosedError
from tornado.concurrent import Future
from tornado.ioloop import IOLoop
from Coronado.Concurrent import transform

logger = logging.getLogger(__name__)

class PayloadTooLong(Exception):
    pass

class RequestError(Exception):
    code = None

    def __init__(self, *args, **kwargs):
        super(RequestError, self).__init__(*args)
        self.code = kwargs.get('code')


class Notifier(object):

    def send(self, notification):
        raise NotImplementedError()


class APNsNotifier(Notifier):
    sentQueue = None
    ioloop = None
    timeoutHandles = None

    def __init__(self, apnsArgs, sslArgs, ioloop=None):
        self._apnsArgs = apnsArgs
        self._sslArgs = sslArgs
        self._connected = False
        self.sentQueue = Queue()
        self.ioloop = ioloop is not None and ioloop or IOLoop.current()
        self.timeoutHandles = {}


    def connect(self):
        self._connecting = True
        self._connectFuture = Future()

        # Create a non-blocking SSL socket
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setblocking(0)

        # Make tornado iostream
        sslOptions = \
        {
            'certfile': self._apnsArgs['certFilePath'],
            'ca_certs': self._sslArgs['caCertsFilePath'],
            'cert_reqs': ssl.CERT_REQUIRED
        }
        self._iostream = tornado.iostream.SSLIOStream(s, ssl_options=sslOptions)

        def onConnected():
            logger.info('APNs connected')
            self._connectFuture.set_result(None)
            self._connecting = False
            self._connected = True

        # Connect
        self._iostream.connect((self._apnsArgs['host'], self._apnsArgs['port']),
                onConnected)

        # Perform read for error packets
        self._iostream.read_bytes(6, self._onError)

        return self._connectFuture


    def send(self, notification):
        def _send():
            # Make sure payload is not too long
            payload = json.dumps(notification['payload'])
            if len(payload) > 256:
                raise PayloadTooLong()

            # Pack device token item
            tokenItem = struct.pack('!BH32s', 1, 32, 
                    binascii.unhexlify(notification['token']))

            # Pack payload item
            payloadItem = struct.pack('!BH' + str(len(payload)) + 's',
                    2, len(payload), payload)

            # Pack identifier item
            id = None
            if '_id' not in notification:
                id = int(random() * 10000)
                notification['_id'] = id
            else:
                id = notification['_id']
            identifierItem = struct.pack('!BHi', 3, 4, id)

            # Pack expiry item
            tomorrow = int(time.mktime(datetime.now().timetuple()))
            expiryItem = struct.pack('!BHi', 4, 4, tomorrow)

            # Pack priority item
            priorityItem = struct.pack('!BHB', 5, 1, 10)

            # Assemble notification packet from items
            frameData = tokenItem + payloadItem + identifierItem + expiryItem \
                    + priorityItem
            packet = struct.pack('!BI' + str(len(frameData)) + 's', 2, len(frameData),
                    frameData)

            logger.info('Sending push notification...')

            try:
                self._iostream.write(packet)
            except StreamClosedError:
                logger.warning('Stream closed, reconnecting...')

                def retry():
                    self.connect()
                    def onReconnected(future):
                        future.result()
                        _send()
                    self.ioloop.add_future(self._connectFuture, onReconnected)

                self.ioloop.add_timeout(timedelta(seconds=2), retry)
            else:
                # Save sent notification in queue. We may have to resend it if
                # a preceding notification fails.
                logger.info('Sent notification.')
                self.sentQueue.put(notification)

                # Pop item after some time
                def popItem():
                    logger.info('Popping item from sent queue')

                    # Remove an item from the queue
                    notifcn = self.sentQueue.get()

                    # Delete its timeout, if any
                    try:
                        del self.timeoutHandles[notifcn['_id']]
                    except KeyError:
                        pass

                handle = self.ioloop.add_timeout(timedelta(seconds=2), popItem)
                self.timeoutHandles[notification['_id']] = handle


        def onConnected(future):
            future.result()
            _send()

        if self._connected:
            _send()
        else:
            if not self._connecting:
                self.connect()
            self.ioloop.add_future(self._connectFuture, onConnected)


    def shutdown(self):
        if self._iostream is not None:
            self._iostream.close()

        self._connected = False


    def _onError(self, response):
        command, status, notifId = struct.unpack('!BBi', response)
        logger.error('APNs ERROR: %s %s %s', str(command), str(status), str(notifId))

        # Connection is closed by APNs on error
        self._connected = False

        # Pop sent-queue until we get the erroneous notification.
        # Items before the erroneous one were successful
        poppedNotifcns = []
        while True:
            try:
                notifcn = self.sentQueue.get(False)
            except Empty:
                break
            else:
                # Remove timeout to pop item from the queue
                try:
                    timeoutHandle = self.timeoutHandles[notifId]
                except KeyError:
                    pass
                else:
                    self.ioloop.remove_timeout(timeoutHandle)

                if notifcn['_id'] == notifId:
                    break

                poppedNotifcns.append(notifcn)

        # Resend all remaining notifications in the queue
        resendList = []
        while True:
            try:
                notifcn = self.sentQueue.get(False)
            except Empty:
                break
            else:
                resendList.append(notifcn)

        if resendList:
            logger.info('Resending notifications after erroneous one.')
            for n in resendList:
                self.send(n)
        else:
            logger.info('Resending remaining known notifications after ' + \
                    'erroneous one.')

            # Resend list was empty, which means that the erroneous notification
            # was assumed by us to be successful, and so all the popped 
            # notifications need to be resent. Some notifications may be
            # permanently lost. This is unavoidable since APNs doesn't
            # acknowledge successful notifications.
            for n in poppedNotifcns:
                self.send(n)


    _apnsArgs = None
    _sslArgs = None
    _sslSocket = None
    _iostream = None
    _connectFuture = None
    _connected = None
    _connecting = False


class GCMNotifier(Notifier):
    gcmArgs = None
    httpClient = None
    ioloop = None

    def __init__(self, gcmArgs, httpClient, ioloop=None):
        self.gcmArgs = gcmArgs
        self.httpClient = httpClient
        self.ioloop = ioloop is not None and ioloop or IOLoop.current()


    def send(self, notification):
        responseFuture = self.httpClient.fetch(
                request=self.gcmArgs['uri'],
                method='POST',
                headers=
                {
                    'Content-Type': 'application/json; charset=UTF-8',
                    'Authorization': 'key=' + self.gcmArgs['apiKey']
                },
                body=json.dumps(notification))

        def onResponse(responseFuture):
            try:
                response = responseFuture.result()
            except tornado.httpclient.HTTPError as e:
                raise RequestError(code=e.code)
            else:
                return json.loads(response.body)

        return transform(responseFuture, onResponse, ioloop=self.ioloop)
