import multiprocessing

from .CoronadoError import CoronadoError
from .MySQLMessageQueue import MySQLMessageQueue, MessageDispatcher

def startMessageQueue(messageQueue=None, name='messageQueue',
        mysqlArgs=None, messageHandlers=None,
        numProcesses=multiprocessing.cpu_count()):
    if messageHandlers is None:
        messageHandlers = {}

    if messageQueue is None:
        if mysqlArgs is None:
            raise CoronadoError(
                'Either messageQueue or mysqlArgs argument is required')
        messageQueue = MySQLMessageQueue(mysqlArgs, name)

    def startMessageDispatcher():
        dispatcher = MessageDispatcher(messageQueue)

        # Register handlers
        for key, handler in messageHandlers.items():
            dispatcher.register(key, handler)

        # Start the dispatcher
        dispatcher.start()


    for x in xrange(numProcesses):
        multiprocessing.Process(target=startMessageDispatcher).start()

    messageQueue._numDispatchers = numProcesses

    return messageQueue


def stopMessageQueue(messageQueue):
    for x in xrange(messageQueue._numDispatchers):
        messageQueue.put('__STOP__', '')
