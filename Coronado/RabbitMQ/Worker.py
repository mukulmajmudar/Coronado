import time
import logging

import tornado.concurrent

from .SimpleClient import SimpleClient
from ..Worker import Worker as BaseWorker
from ..Worker import WorkerProxy as BaseWorkerProxy
from ..Concurrent import when

# Logger for this module
logger = logging.getLogger(__name__)

class WorkerProxy(BaseWorkerProxy):

    # pylint: disable=too-many-arguments
    def __init__(self, host, port, requestQueueName, responseQueueName,
            ioloop=None, shutdownDelay=10.0):
        # Call parent
        super(WorkerProxy, self).__init__(ioloop)

        self._requestQueueName = requestQueueName
        self._responseQueueName = responseQueueName
        self._shutdownDelay = shutdownDelay

        # Create a client
        self._client = SimpleClient(host, port, self._onMessage, ioloop)


    def setup(self):
        return self._client.setup(
                self._requestQueueName, self._responseQueueName)


    def asyncSetup(self):
        return when(self._client.declare(self._requestQueueName, durable=True),
                self._client.declare(self._responseQueueName, durable=True))


    def start(self):
        # Start consuming from the response queue
        return self._client.startConsuming(self._responseQueueName)


    def stop(self):
        future = tornado.concurrent.Future()
        def onStopped(stopFuture):
            try:
                stopFuture.result()
            finally:
                def disconnect():
                    disconnFuture = self._client.disconnect()
                    def onDisconnected(disconnFuture):
                        try:
                            disconnFuture.result()
                        finally:
                            future.set_result(None)

                    self._ioloop.add_future(disconnFuture, onDisconnected)

                # Disconnect after a delay
                logger.info('WorkerProxy will be stopped in %d seconds',
                        self._shutdownDelay)
                self._ioloop.add_timeout(time.time() + self._shutdownDelay,
                        disconnect)

        self._ioloop.add_future(self._client.stopConsuming(), onStopped)

        return future


    def _request(self, requestId, tag, body, contentType, contentEncoding):
        '''
        Publish a request to a worker.
        '''

        return self._client.publish(
                queueName=self._requestQueueName,
                messageType=tag,
                body=body,
                contentType=contentType,
                contentEncoding=contentEncoding,
                correlationId=requestId,
                persistent=True,
                replyTo=self._responseQueueName)


    def _onMessage(self, properties, body):
        # Pass to parent
        self._onResponse(properties.correlation_id, body,
                properties.content_type, properties.content_encoding)


    _requestQueueName = None
    _responseQueueName = None
    _client = None
    _shutdownDelay = None


class Worker(BaseWorker):

    # pylint: disable=too-many-arguments
    def __init__(self, handlers, host, port, requestQueueName,
            ioloop=None, shutdownDelay=10.0, **kwargs):
        # Call parent
        super(Worker, self).__init__(handlers, ioloop)

        self._requestQueueName = requestQueueName
        self._shutdownDelay = shutdownDelay

        # Create a client
        self._client = SimpleClient(host, port, self._onMessage, ioloop)


    def setup(self):
        return self._client.setup(self._requestQueueName)


    def start(self):
        # Start consuming from the request queue
        return self._client.startConsuming(self._requestQueueName)


    def stop(self):
        future = tornado.concurrent.Future()
        def onStopped(stopFuture):
            try:
                stopFuture.result()
            finally:
                def disconnect():
                    disconnFuture = self._client.disconnect()
                    def onDisconnected(disconnFuture):
                        try:
                            disconnFuture.result()
                        finally:
                            future.set_result(None)

                    self._ioloop.add_future(disconnFuture, onDisconnected)

                # Disconnect after a delay
                logger.info('Worker will be stopped in %d seconds',
                        self._shutdownDelay)
                self._ioloop.add_timeout(time.time() + self._shutdownDelay,
                        disconnect)

        self._ioloop.add_future(self._client.stopConsuming(), onStopped)

        return future


    # pylint: disable=too-many-arguments
    def respond(self, requestId, replyTo, body, contentType, contentEncoding):
        '''
        Publish a message to the response queue.
        '''
        return self._client.publish(
                queueName=replyTo,
                messageType=None,
                body=body,
                contentType=contentType,
                contentEncoding=contentEncoding,
                correlationId=requestId,
                persistent=True)


    def _onMessage(self, properties, body):
        # Pass to parent
        self._onRequest(
                requestId=properties.correlation_id,
                tag=properties.type,
                body=body,
                contentType=properties.content_type,
                contentEncoding=properties.content_encoding,
                replyTo=properties.reply_to)


    _requestQueueName = None
    _client = None
    _shutdownDelay = None
