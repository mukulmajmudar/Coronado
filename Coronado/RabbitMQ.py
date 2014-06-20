from contextlib import closing
import pdb
import sys
import logging
import json
import logging

import pika
from pika.adapters import TornadoConnection
from pika.spec import BasicProperties
import tornado.concurrent
from tornado.ioloop import IOLoop

from Worker import Worker as BaseWorker
from Worker import WorkerProxy as BaseWorkerProxy

# Logger for this module
logger = logging.getLogger(__name__)

class ConnectionError(Exception):
    pass


class SimpleClient(object):

    def __init__(self, host, port, messageHandler, ioloop=None):
        self._host = host
        self._port = port
        self._messageHandler = messageHandler
        self._ioloop = ioloop is not None and ioloop or IOLoop.current()
        self._connected = False


    def setup(self, *queueNames):
        # Use a blocking connection to declare the app's queues
        params = pika.ConnectionParameters(host=self._host, port=self._port)
        connection = pika.BlockingConnection(params)
        with closing(connection.channel()) as channel:
            # Close connection once channel is closed
            def closeConnection(channel, replyCode, replyText):
                connection.close()
            channel.add_on_close_callback(closeConnection)

            # Declare durable queues; we will use the 
            # default exchange for simple tag-based routing
            for queueName in queueNames:
                logger.info('Declaring RabbitMQ queue %s', queueName)
                channel.queue_declare(queue=queueName, durable=True)
                logger.info('Declared RabbitMQ queue %s', queueName)


    def connect(self):
        logger.info('Connecting to RabbitMQ server')

        # Make connection
        self._connectFuture = tornado.concurrent.Future()
        params = pika.ConnectionParameters(host=self._host, port=self._port)
        self._connection = pika.adapters.TornadoConnection(params, 
                on_open_callback=self._onConnected, 
                on_open_error_callback=self._onConnectError, 
                on_close_callback=self._onConnectionClosed,
                custom_ioloop=self._ioloop)

        return self._connectFuture


    def publish(self, queueName, type, body, contentType, 
            contentEncoding, correlationId, persistent):
        # If already connected to RabbitMQ server, publish immediately
        if self._connected:
            self._publish(
                    queueName=queueName, 
                    type=type, 
                    body=body, 
                    contentType=contentType, 
                    contentEncoding=contentEncoding, 
                    correlationId=correlationId,
                    persistent=persistent)
            return

        #
        # Not connected, so connect and then publish
        #

        queueFuture = tornado.concurrent.Future()

        def onConnected(connectFuture):
            try:
                # Trap connection exceptions, if any
                connectFuture.result()
            except Exception as e:
                queueFuture.set_exception(e)
            else:
                assert(self._connected)

                # Connected, so publish
                self._publish(
                        queueName=queueName,
                        type=type, 
                        body=body,
                        contentType=contentType, 
                        contentEncoding=contentEncoding, 
                        correlationId=correlationId,
                        persistent=persistent)

                # Resolve the future
                queueFuture.set_result(None)

        self._ioloop.add_future(self.connect(), onConnected)

        return queueFuture


    def startConsuming(self, queueName):
        # Connect, then start consuming
        def onConnected(connectFuture):
            connectFuture.result()
            assert(self._connected)

            # Start consuming
            self._channel.basic_consume(self._onMessage, queueName)
            logger.info('Started consuming from queue %s', queueName)

        self._ioloop.add_future(self.connect(), onConnected)


    def _publish(self, queueName, type, body, contentType, 
            contentEncoding, correlationId, persistent):

        # Define properties
        properties = BasicProperties(
                content_type=contentType,
                content_encoding=contentEncoding,
                type=type,
                delivery_mode=persistent and 2 or None,
                correlation_id=correlationId)

        # Publish to RabbitMQ server
        self._channel.basic_publish(exchange='', 
                routing_key=queueName, body=body, 
                properties=properties)


    def _onConnected(self, connection):
        # Open a channel in the connection
        self._channel = connection.channel(self._onChannel)


    def _onConnectError(self):
        self._connectFuture.set_exception(ConnectionError())


    def _onConnectionClosed(self, connection, replyCode, replyText):
        logger.info('RabbitMQ server connection closed')


    def _onChannel(self, channel):
        # Add channel-close callback
        channel.add_on_close_callback(self._onChannelClosed)
        self._connected = True
        logger.info('Connected to RabbitMQ server')
        self._connectFuture.set_result(None)


    def _onChannelClosed(self, channel, replyCode, replyText):
        self._connected = False
        logger.info('RabbitMQ channel closed')
        self._connection.close()


    def _onMessage(self, channel, basicDeliver, properties, body):
        logger.info('Message received (may be partial): %s', body[0:50])
        logger.debug('Message body (may be partial): %s', body[0:1000])
        self._messageHandler(properties, body)

        # Acknowledge message
        self._channel.basic_ack(basicDeliver.delivery_tag)


    _host = None
    _port = None
    _messageHandler = None
    _ioloop = None
    _connected = None
    _connectFuture = None
    _connection = None
    _channel = None


class WorkerProxy(BaseWorkerProxy):

    def __init__(self, host, port, requestQueueName, responseQueueName, 
            ioloop=None):
        # Call parent
        super(WorkerProxy, self).__init__(ioloop)

        self._requestQueueName = requestQueueName
        self._responseQueueName = responseQueueName

        # Create a client
        self._client = SimpleClient(host, port, self._onMessage, ioloop)


    def setup(self):
        self._client.setup(self._requestQueueName, self._responseQueueName)


    def start(self):
        # Start consuming from the response queue
        self._client.startConsuming(self._responseQueueName)


    def _request(self, id, tag, body, contentType, contentEncoding):
        '''
        Publish a request to a worker.
        '''

        return self._client.publish(
                queueName=self._requestQueueName,
                type=tag,
                body=body,
                contentType=contentType,
                contentEncoding=contentEncoding,
                correlationId=id,
                persistent=True)


    def _onMessage(self, properties, body):
        # Pass to parent
        self._onResponse(properties.correlation_id, body, 
                properties.content_type, properties.content_encoding)


    _requestQueueName = None
    _responseQueueName = None
    _client = None


class Worker(BaseWorker):

    def __init__(self, handlers, host, port, requestQueueName,
            responseQueueName, ioloop=None):
        # Call parent
        super(Worker, self).__init__(handlers, ioloop)

        self._requestQueueName = requestQueueName
        self._responseQueueName = responseQueueName

        # Create a client
        self._client = SimpleClient(host, port, self._onMessage, ioloop)


    def setup(self):
        self._client.setup(self._requestQueueName, self._responseQueueName)


    def start(self):
        # Start consuming from the request queue
        self._client.startConsuming(self._requestQueueName)


    def respond(self, requestId, body, contentType, contentEncoding):
        '''
        Publish a message to the response queue. 
        '''
        return self._client.publish(
                queueName=self._responseQueueName,
                type=None,
                body=body,
                contentType=contentType,
                contentEncoding=contentEncoding,
                correlationId=requestId,
                persistent=True)


    def _onMessage(self, properties, body):
        # Pass to parent
        self._onRequest(
                id=properties.correlation_id, 
                tag=properties.type, 
                body=body, 
                contentType=properties.content_type,
                contentEncoding=properties.content_encoding)


    _requestQueueName = None
    _responseQueueName = None
    _client = None
