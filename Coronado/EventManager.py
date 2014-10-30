from tornado.ioloop import IOLoop
import pdb

class EventManager(object):

    def __init__(self, name, ioloop):
        self.name = name
        self.ioloop = ioloop is not None and ioloop or IOLoop.current()
        self.messageHandlers = {}

    def setup(self):
        pass


    def on(self, sourceId, eventType, handler, listenerId=None):
        '''
        Listen for an event on the given source.

        sourceId: ID of the event source
        eventType: type of event for which to listen
        handler: function to call when the specified event occurs
        listenerId: ID of this event listening request (default None 
            means listener ID will be auto-generated)
        '''
        raise NotImplementedError()


    def trigger(self, eventType, **kwargs):
        raise NotImplementedError()


    def off(self, listenerId):
        raise NotImplementedError()


    def _onEvent(self, listenerId, **kwargs):
        # Call message handler associated with the binding ID, if any
        try:
            self.messageHandlers[listenerId](**kwargs)
        except KeyError:
            pass


    def _saveHandler(self, listenerId, messageHandler):
        self.messageHandlers[listenerId] = messageHandler


def make(type, *args, **kwargs):
    if type == 'RabbitMQ':
        # Import here to avoid circular dependency
        from .RabbitMQ import EventManager as RMQEventManager
        return RMQEventManager(*args, **kwargs)