import logging
from functools import wraps

import pika
from pika.adapters import TornadoConnection
from pika.spec import BasicProperties
import tornado.concurrent
from tornado.ioloop import IOLoop

from ..Concurrent import transform

# Logger for this module
logger = logging.getLogger(__name__)

class ConnectionError(Exception):
    pass


def connected(method):
    '''
    Decorator to ensure that the Client is connected to the RabbitMQ server.
    '''

    @wraps(method)
    def wrapper(self, *args, **kwargs):
        # If already connected, call method immediately
        if self._connected:
            return method(self, *args, **kwargs)

        # Not connected, so connect and then call method

        def onConnected(connectFuture):
            # Trap connection exceptions if any
            connectFuture.result()

            # Call actual method
            method(self, *args, **kwargs)

        connectFuture = self.connect()

        return transform(connectFuture, onConnected, ioloop=self._ioloop)

    return wrapper


class Client(object):
    '''
    A RabbitMQ client.

    This client use pika internally but returns futures for asynchronous
    operations.
    '''

    def __init__(self, host, port, messageHandler=None, ioloop=None):
        self._host = host
        self._port = port
        self._messageHandler = messageHandler
        self._ioloop = ioloop is not None and ioloop or IOLoop.current()
        self._connected = False


    @connected
    def declareExchange(self, name, exchangeType):
        declareFuture = tornado.concurrent.Future()
        def onExchangeDeclared(frame):  # pylint: disable=unused-argument
            logger.info('Declared RabbitMQ exchange %s of type %s',
                    name, exchangeType)
            declareFuture.set_result(None)

        logger.info('Declaring RabbitMQ exchange %s of type %s',
                name, exchangeType)
        self._channel.exchange_declare(
                callback=onExchangeDeclared,
                exchange=name,
                exchange_type=exchangeType,
                durable=True)

        return declareFuture


    @connected
    def declareQueue(self, name):
        declareFuture = tornado.concurrent.Future()

        def onQueueDeclared(methodFrame):   # pylint: disable=unused-argument
            logger.info('Declared RabbitMQ queue %s', name)
            declareFuture.set_result(None)

        logger.info('Declaring RabbitMQ queue %s', name)

        # If no queue name, declare a temporary queue
        if name == '':
            self._channel.queue_declare(onQueueDeclared, auto_delete=True,
                    exclusive=True)
        else:
            # Declare a durable queue
            self._channel.queue_declare(onQueueDeclared, name, durable=True)

        return declareFuture


    @connected
    def bindQueue(self, queueName, exchangeName, key):
        bindFuture = tornado.concurrent.Future()

        def onQueueBound(frame):    # pylint: disable=unused-argument
            logger.info('Bound queue %s to exchange %s',
                    queueName, exchangeName)
            bindFuture.set_result(None)

        logger.info('Binding queue %s to exchange %s',
                queueName, exchangeName)
        self._channel.queue_bind(onQueueBound, queueName, exchangeName,
                key)

        return bindFuture


    def connect(self):
        logger.info('Connecting to RabbitMQ server')

        if self._connectFuture is not None:
            return self._connectFuture

        # Make connection
        self._connectFuture = tornado.concurrent.Future()
        params = pika.ConnectionParameters(host=self._host, port=self._port)
        self._connection = TornadoConnection(params,
                on_open_callback=self._onConnected,
                on_open_error_callback=self._onConnectError,
                on_close_callback=self._onConnectionClosed,
                custom_ioloop=self._ioloop)

        return self._connectFuture


    def disconnect(self):
        if not self._connected:
            return
        self._disconnectFuture = tornado.concurrent.Future()
        self._connection.close()
        return self._disconnectFuture


    @connected
    # pylint: disable=too-many-arguments
    def publish(self, exchangeName, routingKey, body,
            contentType, contentEncoding):
        # Define properties
        properties = BasicProperties(
                content_type=contentType,
                content_encoding=contentEncoding,
                delivery_mode=2)

        # Publish to RabbitMQ server
        self._channel.basic_publish(exchange=exchangeName,
                routing_key=routingKey, body=body,
                properties=properties)


    @connected
    def startConsuming(self, queueName):
        # Add on-cancel callback
        def onCancel(frame):    # pylint: disable=unused-argument
            self._channel.close()
        self._channel.add_on_cancel_callback(onCancel)

        # Start consuming
        consumerTag = self._channel.basic_consume(
                self._onMessage, queueName)
        logger.info('Started consuming from queue %s', queueName)

        return consumerTag


    def stopConsuming(self, consumerTag):
        logger.info('Stopping RabbitMQ consumer')
        stopFuture = tornado.concurrent.Future()
        def onCanceled(unused): # pylint: disable=unused-argument
            logger.info('Canceled RabbitMQ consumer')
            stopFuture.set_result(None)
        self._channel.basic_cancel(onCanceled, consumerTag)
        return stopFuture


    def _onConnected(self, connection):
        # Open a channel in the connection
        self._channel = connection.channel(self._onChannel)


    def _onConnectError(self):
        self._connectFuture.set_exception(ConnectionError())
        self._connectFuture = None


    # pylint: disable=unused-argument
    def _onConnectionClosed(self, connection, replyCode, replyText):
        logger.info('RabbitMQ server connection closed')
        self._connected = False
        if self._disconnectFuture is not None:
            self._disconnectFuture.set_result(None)
            self._disconnectFuture = None


    def _onChannel(self, channel):
        # Add channel-close callback
        channel.add_on_close_callback(self._onChannelClosed)
        self._connected = True
        logger.info('Connected to RabbitMQ server')
        self._connectFuture.set_result(None)
        self._connectFuture = None


    # pylint: disable=unused-argument
    def _onChannelClosed(self, channel, replyCode, replyText):
        self._connected = False
        logger.info('RabbitMQ channel closed')
        self._connection.close()


    def _onMessage(self, channel, basicDeliver, properties, body):
        logger.info('Message received (may be partial): %s', body[0:50])
        logger.debug('Message body (may be partial): %s', body[0:1000])
        self._messageHandler(basicDeliver.consumer_tag, properties, body)

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
    _disconnectFuture = None
