import json

from ..EventManager import EventManager as BaseEventManager
from ..Concurrent import when, transform
from .Client import Client

class EventManager(BaseEventManager):
    topicExName = None
    directExName = None
    client = None
    triggerCapable = None

    # pylint: disable=too-many-arguments
    def __init__(self, host, port, name, trigger=True, ioloop=None):
        # Call parent
        super(EventManager, self).__init__(name, ioloop)

        self.topicExName = self.name + '-topic'
        self.directExName = self.name + '-direct'
        self.triggerCapable = trigger

        # Create a client
        self.client = Client(host, port, self._onMessage, ioloop)


    def setup(self):
        if self.triggerCapable:
            # Declare direct and topic exchanges
            return when(self.client.declareExchange(self.topicExName, 'topic'),
                self.client.declareExchange(self.directExName, 'direct'))


    def on(self, sourceId, eventType, listener, listenerId=None):
        # Figure out the exchange and queue names based on whether
        # event type corresponds to a topic or direct exchange
        exchangeType = '.' in eventType and 'topic' or 'direct'
        exchangeName = '%s-%s' % (sourceId, exchangeType)
        if listenerId is None:
            listenerId = ''
        queueName = listenerId

        # Declare exchange
        declareXFuture = self.client.declareExchange(exchangeName, exchangeType)

        # Declare queue
        declareQFuture = self.client.declareQueue(queueName)

        def onDeclared(future):
            # Trap exceptions, if any
            declareXFuture, declareQFuture = future.result()
            declareXFuture.result()
            declareQFuture.result()

            # Bind the queue
            queueBindFuture = self.client.bindQueue(
                    queueName, exchangeName, eventType)

            return transform(queueBindFuture, onQueueBound, ioloop=self.ioloop)

        def onQueueBound(queueBindFuture):
            # Trap exceptions, if any
            queueBindFuture.result()

            # Start consuming from the subscriber queue
            consumeFuture = self.client.startConsuming(queueName)

            return transform(when(consumeFuture), onStartedConsuming)

        def onStartedConsuming(consumeFuture):
            consumerTag = consumeFuture.result()

            # Associate message handler with consumer tag
            self._saveHandler(consumerTag, listener)

            return consumerTag

        return transform(when(declareXFuture, declareQFuture),
                onDeclared, ioloop=self.ioloop)


    def trigger(self, eventType, **kwargs):
        body = json.dumps(kwargs)

        # If the key contains dots, publish to the topic exchange, otherwise
        # publish to the direct exchange
        exchangeName = '.' in eventType and self.topicExName \
                or self.directExName
        self.client.publish(exchangeName, eventType, body,
                'application/json', 'utf-8')


    def off(self, listenerId):
        # Stop consuming
        return self.client.stopConsuming(listenerId)


    # pylint: disable=unused-argument
    def _onMessage(self, consumerTag, properties, body):
        # Assume body is a JSON string
        kwargs = json.loads(body)

        # Call onEvent
        self._onEvent(consumerTag, **kwargs)
