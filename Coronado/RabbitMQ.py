from contextlib import closing
import pdb
import sys
import logging
import json

import pika
from pika.adapters import TornadoConnection
from pika.spec import BasicProperties
import tornado.concurrent
from tornado.ioloop import IOLoop

from Worker import Worker as BaseWorker

class ConnectionError(Exception):
    pass


class Worker(BaseWorker):

    def __init__(self, handlers, type, host, port, requestQueueName,
            responseQueueName, ioloop=None):
        # Call parent
        super(Worker, self).__init__(handlers, type, ioloop)

        self._host = host
        self._port = port
        self._requestQueueName = requestQueueName
        self._responseQueueName = responseQueueName
        self._connected = False
        self._ioloop = ioloop is not None and ioloop or IOLoop.current()


    def setup(self):
        # Use a blocking connection to declare the app's queues
        params = pika.ConnectionParameters(host=self._host, port=self._port)
        connection = pika.BlockingConnection(params)
        with closing(connection.channel()) as channel:
            # Close connection once channel is closed
            def closeConnection(channel, replyCode, replyText):
                connection.close()
            channel.add_on_close_callback(closeConnection)

            # Declare durable request and response queues; we will use the 
            # default exchange for simple key-based routing
            channel.queue_declare(queue=self._requestQueueName, durable=True)
            channel.queue_declare(queue=self._responseQueueName, durable=True)


    def connect(self):
        # Make connection
        self._connectFuture = tornado.concurrent.Future()
        params = pika.ConnectionParameters(host=self._host, port=self._port)
        self._connection = pika.adapters.TornadoConnection(params, 
                on_open_callback=self._onConnected, 
                on_open_error_callback=self._onConnectError, 
                on_close_callback=self._onConnectionClosed,
                custom_ioloop=self._ioloop)

        return self._connectFuture


    def start(self):
        # Connect, then start consuming
        def onConnected(connectFuture):
            connectFuture.result()
            assert(self._connected)

            # Queue from which to consume depends on whether this is
            # a worker or a worker proxy
            queueName = self._type == 'worker' \
                    and self._requestQueueName \
                    or self._responseQueueName

            # Start consuming
            self._channel.basic_consume(self._handleMessage, queueName)

        self._ioloop.add_future(self.connect(), onConnected)


    def _queue(self, key, message, contentType, contentEncoding, 
            correlationId, persistent=False):
        '''
        Publish a message to the configured queue. 
        
        If not connected to the RabbitMQ server yet, makes a connection and then
        publishes.
        '''

        # If already connected to RabbitMQ server, publish immediately
        if self._connected:
            self._publish(key=key, message=message, 
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
                self._publish(key=key, message=message, 
                        contentType=contentType, 
                        contentEncoding=contentEncoding, 
                        correlationId=correlationId,
                        persistent=persistent)

                # Resolve the future
                queueFuture.set_result(None)

        self._ioloop.add_future(self.connect(), onConnected)

        return queueFuture


    def _publish(self, key, message, contentType, 
            contentEncoding, correlationId, persistent):


        # Define properties
        properties = BasicProperties(
                content_type=contentType,
                content_encoding=contentEncoding,
                type=key,
                delivery_mode=persistent and 2 or None,
                correlation_id=correlationId)

        # Queue on which to publish depends on whether this is a worker
        # or a worker proxy
        queueName = self._type == 'worker' \
                and self._responseQueueName \
                or self._requestQueueName

        # Publish to RabbitMQ server
        self._channel.basic_publish(exchange='', 
                routing_key=queueName, body=message, 
                properties=properties)


    def _onConnected(self, connection):
        # Open a channel in the connection
        self._channel = connection.channel(self._onChannel)


    def _onConnectError(self):
        self._connectFuture.set_exception(ConnectionError())


    def _onConnectionClosed(self, connection, replyCode, replyText):
        pass


    def _onChannel(self, channel):
        # Add channel-close callback
        channel.add_on_close_callback(self._onChannelClosed)
        self._connected = True
        self._connectFuture.set_result(None)


    def _onChannelClosed(self, channel, replyCode, replyText):
        self._connected = False
        self._connection.close()


    def _handleMessage(self, channel, basicDeliver, properties, body):
        # Pass to parent
        self._onMessage(properties.key, body, properties.content_type,
                properties.content_encoding, properties.correlation_id)

        # Acknowledge message
        self._channel.basic_ack(basicDeliver.delivery_tag)
         

    _host = None
    _port = None
    _connectFuture = None
    _connection = None
    _channel = None
    _connected = None
    _ioloop = None
