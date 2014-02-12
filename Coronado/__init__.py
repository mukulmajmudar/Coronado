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


    messageQueue._processes = []
    for x in xrange(numProcesses):
        process = multiprocessing.Process(target=startMessageDispatcher)
        messageQueue._processes.append(process)
        process.start()

    return messageQueue


def stopMessageQueue(messageQueue):
    for x in xrange(len(messageQueue._processes)):
        messageQueue.put('__STOP__', '')

    for process in messageQueue._processes:
        process.join()
