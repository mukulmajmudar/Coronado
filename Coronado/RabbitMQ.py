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


#logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.WARNING)


class Worker(BaseWorker):

    def __init__(self, handlers, host, port, queueName, ioloop=None):
        # Call parent
        super(Worker, self).__init__(handlers)

        self._host = host
        self._port = port
        self._queueName = queueName
        self._connected = False
        self._ioloop = ioloop is not None and ioloop or IOLoop.current()


    def setup(self):
        # Use a blocking connection to declare the app's queue
        params = pika.ConnectionParameters(host=self._host, port=self._port)
        connection = pika.BlockingConnection(params)
        with closing(connection.channel()) as channel:
            # Close connection once channel is closed
            def closeConnection(channel, replyCode, replyText):
                connection.close()
            channel.add_on_close_callback(closeConnection)

            # Declare a durable queue; we will use the default exchange for
            # simple key-based routing
            channel.queue_declare(queue=self._queueName, durable=True)


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


    def queue(self, key, message, contentType='application/json',
            contentEncoding='utf-8', persistent=False):
        '''
        Publish a message to the configured queue. 
        
        If not connected to the RabbitMQ server yet, makes a connection and then 
        publishes.
        '''

        queueFuture = tornado.concurrent.Future()

        # If already connected to RabbitMQ server, publish immediately
        if self._connected:
            self._publish(key, message, contentType, 
                    contentEncoding, persistent)

            queueFuture.set_result(None)
        else:
            #
            # Publish when connected
            # 

            def onConnected(connectFuture):
                try:
                    # Trap connection exceptions, if any
                    connectFuture.result()
                except Exception as e:
                    queueFuture.set_exception(e)
                else:
                    assert(self._connected)

                    # Connected, so publish
                    self._publish(key, message, contentType, 
                            contentEncoding, persistent)

                    # Resolve the future
                    queueFuture.set_result(None)

            # Wait for connection, then publish
            self._ioloop.add_future(self.connect(), onConnected)

        return queueFuture 


    def start(self):
        # Connect, bind, then start consuming
        def onConnected(connectFuture):
            connectFuture.result()
            assert(self._connected)

            # Start consuming
            self._channel.basic_consume(self._onMessage,
                    self._queueName)

        self._ioloop.add_future(self.connect(), onConnected)


    def _publish(self, key, message, contentType, 
            contentEncoding, persistent):
        # Define properties
        properties = BasicProperties(
                content_type=contentType,
                content_encoding=contentEncoding,
                type=key,
                delivery_mode=persistent and 2 or None)

        # Convert dictionaries and lists to JSON if content type is JSON
        if (isinstance(message, dict) or isinstance(message, list)) \
                and contentType == 'application/json':
            message = json.dumps(message, encoding=contentEncoding)

        # Publish to RabbitMQ server
        self._channel.basic_publish(exchange='', 
                routing_key=self._queueName, body=message, 
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


    def _onMessage(self, channel, basicDeliver, properties, body):
        # Execute route with message's key
        self._execute(properties.type, body, properties.content_type,
                properties.content_encoding)

        # Acknowledge message
        self._channel.basic_ack(basicDeliver.delivery_tag)
         

    _host = None
    _port = None
    _connectFuture = None
    _connection = None
    _channel = None
    _connected = None
    _ioloop = None
