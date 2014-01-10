import multiprocessing

from CoronadoError import CoronadoError
from MySQLMessageQueue import MySQLMessageQueue, MessageDispatcher

def startMessageQueue(messageQueue=None, mysqlArgs=None, messageHandlers={},
        numProcesses=multiprocessing.cpu_count()):

    if messageQueue is None:
        if mysqlArgs is None:
            raise CoronadoError(
                'Either messageQueue or mysqlArgs argument is required')
        messageQueue = MySQLMessageQueue(mysqlArgs)

    def startMessageDispatcher():
        dispatcher = MessageDispatcher(messageQueue)

        # Register handlers
        for key, handler in messageHandlers.items():
            dispatcher.register(key, handler)

        # Start the dispatcher
        dispatcher.start()


    for x in xrange(numProcesses):
        multiprocessing.Process(target=startMessageDispatcher).start()

    return messageQueue
