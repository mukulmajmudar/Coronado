import socket
import ssl
import struct
import binascii
from random import random
import json
import time
from datetime import datetime, timedelta
import logging
from queue import Queue, Empty

import tornado.iostream
from tornado.iostream import StreamClosedError
from tornado.concurrent import Future
from tornado.ioloop import IOLoop
import dateutil.tz
import dateutil.parser

from .WebSocketHandler import WebSocketHandler
from .Concurrent import transform
from .NetUtil import exponentialBackoff

logger = logging.getLogger(__name__)

class PayloadTooLong(Exception):
    pass

class RequestError(Exception):
    code = None

    def __init__(self, *args, **kwargs):
        super(RequestError, self).__init__(*args)
        self.code = kwargs.get('code')


class BadRequest(Exception):
    pass

class AuthenticationError(Exception):
    pass

class ResponseError(Exception):
    pass

class InvalidDataKey(Exception):
    pass

class InvalidTtl(Exception):
    pass

class MissingRegistration(Exception):
    pass

class Notifier(object):

    def send(self, notification):
        raise NotImplementedError()


class APNsConnector(object):
    apnsArgs = None
    sslArgs = None
    connected = False
    ioloop = None


    def __init__(self, apnsArgs, sslArgs, ioloop=None):
        self.apnsArgs = apnsArgs
        self.sslArgs = sslArgs
        self.ioloop = ioloop is not None and ioloop or IOLoop.current()


    def connect(self):
        if self._connecting:
            return self._connectFuture

        self._connecting = True
        self._connectFuture = Future()

        # Create a non-blocking SSL socket
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setblocking(0)

        # Make tornado iostream
        sslOptions = \
        {
            'certfile': self.apnsArgs['certFilePath'],
            'ca_certs': self.sslArgs['caCertsFilePath'],
            'cert_reqs': ssl.CERT_REQUIRED
        }
        self._iostream = tornado.iostream.SSLIOStream(
                s, ssl_options=sslOptions, io_loop=self.ioloop)

        def onConnected():
            logger.info('Connected to %s:%d', self.apnsArgs['host'],
                    self.apnsArgs['port'])
            self._connectFuture.set_result(None)
            self._connecting = False
            self.connected = True

            # Change connected flag on close
            def onClosed():
                logger.info('APNs connection closed.')
                self.connected = False
            self._iostream.set_close_callback(onClosed)

            # Read until connection closed
            self._iostream.read_until_close(self.onDataReceived)

        # Connect
        logger.info('Connecting to %s:%d', self.apnsArgs['host'],
                self.apnsArgs['port'])
        self._iostream.connect((self.apnsArgs['host'], self.apnsArgs['port']),
                onConnected)

        return self._connectFuture


    def shutdown(self):
        if self._iostream is not None:
            self._iostream.close()


    def onDataReceived(self, data):
        raise NotImplementedError()


    _iostream = None
    _connecting = False
    _connectFuture = None


class APNsNotifier(APNsConnector):
    sentQueue = None
    timeoutHandles = None
    removeToken = None

    def __init__(self, *args, **kwargs):
        self.removeToken = kwargs.pop('removeToken')
        super(APNsNotifier, self).__init__(*args, **kwargs)
        self.sentQueue = Queue()
        self.timeoutHandles = {}


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
            idn = None
            if '_id' not in notification:
                idn = int(random() * 10000)
                notification['_id'] = idn
            else:
                idn = notification['_id']
            identifierItem = struct.pack('!BHi', 3, 4, idn)

            # Pack expiry item
            tomorrow = int(time.mktime(datetime.now().timetuple()))
            expiryItem = struct.pack('!BHi', 4, 4, tomorrow)

            # Pack priority item
            priorityItem = struct.pack('!BHB', 5, 1, 10)

            # Assemble notification packet from items
            frameData = tokenItem + payloadItem + identifierItem + expiryItem \
                    + priorityItem
            packet = struct.pack('!BI' + str(len(frameData)) + 's', 2,
                    len(frameData), frameData)

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

                self.ioloop.add_timeout(timedelta(seconds=5), retry)
            else:
                # Save sent notification in queue. We may have to resend it if
                # a preceding notification fails.
                logger.info('Sent notification.')
                self.sentQueue.put(notification)

                # Pop item after some time
                def popItem():
                    logger.info('Popping item from sent queue')

                    # Remove an item from the queue
                    try:
                        notifcn = self.sentQueue.get(False)
                    except Empty:
                        pass
                    else:
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

        if self.connected:
            _send()
        else:
            logger.info('Not connected to APNs.')
            if not self._connecting:
                self.connect()
            self.ioloop.add_future(self._connectFuture, onConnected)


    # pylint: disable=too-many-branches
    def onDataReceived(self, data):
        # Empty data means connection closed without error
        if len(data) == 0:
            return

        command, status, notifId = struct.unpack('!BBi', data)
        logger.error('APNs ERROR: %s %s %s', str(command),
                str(status), str(notifId))

        # Pop sent-queue until we get the erroneous notification.
        # Items before the erroneous one were successful
        poppedNotifcns = []
        notifcn = None
        foundNotification = False
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
                    foundNotification = True
                    break

                poppedNotifcns.append(notifcn)

        # If error is invalid-token, remove the token
        if status == 8 and foundNotification:
            logger.info('Removing invalid iOS token %s...', notifcn['token'])
            self.removeToken(notifcn['token'])

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
            if not foundNotification and len(poppedNotifcns) > 0:
                logger.info('Resending remaining known notifications after ' + \
                        'erroneous one.')

                # Resend list was empty, which means that the erroneous
                # notification was assumed by us to be successful, and so all
                # the popped notifications need to be resent. Some
                # notifications may be permanently lost. This is unavoidable
                # since APNs doesn't acknowledge successful notifications.
                for n in poppedNotifcns:
                    self.send(n)


class APNsFeedbackHandler(APNsConnector):
    removeToken = None

    def __init__(self, *args, **kwargs):
        self.removeToken = kwargs.pop('removeToken')
        super(APNsFeedbackHandler, self).__init__(*args, **kwargs)


    def start(self):
        return self.connect()


    def onDataReceived(self, data):
        if len(data) > 0:
            logger.info('Feedback handler received data.')
        else:
            logger.info('Feedback handler connection closed, no data received.')
        while len(data) > 0:
            timestamp, tokenLength = struct.unpack('!iH', data[:6])
            data = data[6:]
            token = data[:tokenLength]

            # Call remove function
            logger.info('Removing token %s', token)
            self.removeToken(token, timestamp)

            data = data[tokenLength:]

        # Schedule next feedback service query
        logger.info('Will connect to APNs feedback service again in %s',
                self.apnsArgs['queryInterval'])
        self.ioloop.add_timeout(self.apnsArgs['queryInterval'], self.connect)



class GCMNotifier(Notifier):
    gcmArgs = None
    httpClient = None
    removeRegId = None
    updateRegId = None
    ioloop = None

    # pylint: disable=too-many-arguments
    def __init__(self, gcmArgs, httpClient, removeRegId,
            updateRegId, ioloop=None):
        self.gcmArgs = gcmArgs
        self.httpClient = httpClient
        self.removeRegId = removeRegId
        self.updateRegId = updateRegId
        self.ioloop = ioloop is not None and ioloop or IOLoop.current()


    @exponentialBackoff(maxDelay=60)
    # pylint: disable=too-many-statements
    def send(self, notification, retry):
        '''
        Send a notification to the GCM server.

        Remove and update functions are passed in as arguments due to
        a Coronado API versioning limitation. They will be moved to the
        constructor when the limitation is removed.
        '''

        logger.debug('GCM notification = %s',
                json.dumps(notification, indent=4))

        # Send to GCM server
        responseFuture = self.httpClient.fetch(
                request=self.gcmArgs['uri'],
                method='POST',
                headers=
                {
                    'Content-Type': 'application/json; charset=UTF-8',
                    'Authorization': 'key=' + self.gcmArgs['apiKey']
                },
                body=json.dumps(notification))

        # pylint: disable=too-many-branches,too-many-statements
        def onResponse(responseFuture):
            try:
                response = responseFuture.result()
            except tornado.httpclient.HTTPError as e:
                logger.info('HTTP status code = %d', e.code)
                if e.code == 400:
                    logger.error(e.response.body)
                    raise BadRequest()
                elif e.code == 401:
                    raise AuthenticationError()
                elif e.code >= 500:
                    return retry(self, notification)
                else:
                    raise RequestError(code=e.code)
            else:
                jsonResponse = json.loads(response.body)

                # If both failure and canonical_ids are 0, then the
                # request was successful
                if jsonResponse.get('failure') == 0 and \
                        jsonResponse.get('canonical_ids') == 0:
                    logger.info('GCM notification sent successfully')
                    return

                logger.info('One or GCM notifications may not have been sent.')

                results = jsonResponse.get('results')
                if not results or not isinstance(results, list):
                    raise ResponseError()

                retryAfter = response.headers.get('Retry-After', None)
                if retryAfter is not None:
                    # Parse header value: it could be seconds as an integer or
                    # an HTTP date
                    try:
                        retryAfter = int(retryAfter)
                    except ValueError:
                        # Value is in HTTP date format
                        httpDate = dateutil.parser.parse(retryAfter)
                        now = datetime.now(dateutil.tz.tzutc())
                        retryAfter = (httpDate - now).seconds

                        # Safeguard: if bad header value, ignore it
                        if retryAfter <= 0:
                            retryAfter = None

                for i, result in enumerate(results):
                    regId = result.get('registration_id')
                    if 'message_id' in result and regId is not None:
                        origRegId = notification['registration_ids'][i]
                        logger.info('Updating stale registration ID...')
                        logger.debug('Replacing %s with %s', origRegId, regId)
                        self.updateRegId(origRegId, regId)
                    else:
                        error = result.get('error')
                        if error is None:
                            continue

                        logger.error('GCM Error: %s', error)
                        if error == 'MissingRegistration':
                            raise MissingRegistration()
                        elif error in ('Unavailable', 'InternalServerError'):
                            return retry(self, notification,
                                    minDelay=retryAfter)
                        elif error in ('NotRegistered', 'InvalidRegistration',
                                'MismatchSenderId', 'InvalidPackageName'):
                            origRegId = notification['registration_ids'][i]
                            logger.info('Removing registration ID %s...',
                                    origRegId)
                            self.removeRegId(origRegId)
                        elif error == 'MessageTooBig':
                            raise PayloadTooLong()
                        elif error == 'InvalidDataKey':
                            raise InvalidDataKey()
                        elif error == 'InvalidTtl':
                            raise InvalidTtl()

        return transform(responseFuture, onResponse, ioloop=self.ioloop)


class WebSocketNotifier(Notifier):

    def send(self, notification):
        for token in notification.pop('tokens'):
            try:
                handler = WSNotifierHandler.handlers[token]
            except KeyError:
                pass
            else:
                handler.write_message(notification)


class WSNotifierHandler(WebSocketHandler):

    token = None

    # Class-shared map
    handlers = {}

    def open(self):
        self.token = self.get_argument('deviceToken')

        # Save token-handler mapping
        WSNotifierHandler.handlers[self.token] = self

        # Max connection age = 7 days, after which client must reconnect
        ioloop = IOLoop.current()
        duration = timedelta(days=7)
        ioloop.add_timeout(duration, self.close)


    def on_close(self):
        # Remove handler
        try:
            del WSNotifierHandler.handlers[self.token]
        except KeyError:
            pass

        # Trigger expired event
        eventManager = self.context.get('eventManager')
        if eventManager:
            eventManager.trigger('webDeviceToken.expired', token=self.token)


    def on_message(self, message):
        pass
