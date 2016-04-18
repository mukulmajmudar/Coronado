import logging
import time

import tornado.ioloop

from . import RabbitMQ, EventManager
from .Email import SendEmail
from .Context import Context

logger = logging.getLogger(__name__)

workerClasses = \
{
    'RabbitMQ':
    {
        'worker': RabbitMQ.Worker,
        'proxy': RabbitMQ.WorkerProxy
    }
}

class Application(object):
    '''
    Coronado Application base class.

    Subclass this and add application startup code. Enables easier testability.
    See testing pattern recommended by Bret Taylor (creator of Tornado) at:
    https://groups.google.com/d/msg/python-tornado/hnz7JmXqEKk/S2zkl6L9ctEJ
    '''

    config = None
    context = None
    tornadoApp = None
    workHandlers = None
    started = False

    def __init__(self, config, workerMode=False):
        self.config = config
        self._workerMode = workerMode
        self._destroyed = False
        self.workHandlers = {}


    def _start(self, context=None):
        if context is None:
            context = {}

        context['workerMode'] = self._workerMode

        # Initialize context to be a copy of the configuration
        self.context = Context(self.config.copy())

        # Deep copy worker and event manager params (copy.deepcopy doesn't
        # work presumably because config contains classes)
        if self.context.get('worker'):
            self.context['worker'] = self.context['worker'].copy()
        if self.context.get('eventManager'):
            self.context['eventManager'] = self.context['eventManager'].copy()

        # Override with passed in arguments (customization)
        self.context.update(context)

        # Assign default IOLoop instance
        if 'ioloop' not in self.context:
            self.context['ioloop'] = tornado.ioloop.IOLoop.instance()

        # Start eventManager if configured
        self.startEventManager()

        # Start app plugins
        self.context['appPlugins'] = {}
        for plugin in self.context['plugins']:
            appPluginClass = getattr(plugin, 'AppPlugin', False)
            if not appPluginClass:
                continue
            appPlugin = appPluginClass()
            appPlugin.start(self, self.context)
            self.context['appPlugins'][appPlugin.pluginId] = appPlugin

        self.addToContextFlatten(
        {
            'public': ['ioloop']
        })

        # Start worker if configured
        self.startWorker()

        # Call sub-class specific start()
        self.start()

        self.started = True

        # Start event loop
        self.context['ioloop'].start()


    def startWorker(self):
        worker = self.context.get('worker')
        if not worker:
            return

        workerType = worker.pop('type')
        classes = workerClasses[workerType]

        # Start a worker or proxy based on mode
        if self._workerMode:
            # Get app-specific work handlers
            handlers = self.workHandlers

            # If an email work tag is configured, add an email work handler
            emailWorkTag = self.context.get('emailWorkTag')
            if emailWorkTag is not None:
                handlers[emailWorkTag] = SendEmail

            # Convert to Tornado-style tuple
            workHandlers = [mapping + (self.context,)
                    for mapping in zip(list(handlers.keys()),
                        list(handlers.values()))]

            # Create a worker
            worker = self.context['worker'] = classes['worker'](
                    handlers=workHandlers,
                    shutdownDelay=self.context['shutdownDelay'], **worker)
        else:
            # Create a worker proxy
            worker = self.context['worker'] = classes['proxy'](
                    shutdownDelay=self.context['shutdownDelay'], **worker)

        worker.setup()
        self.context['ioloop'].run_sync(worker.start)

        self.addToContextFlatten(
        {
            'non-public': ['worker'],
            'public': ['worker']
        })


    def startEventManager(self):
        eventManager = self.context.get('eventManager')
        if not eventManager:
            return

        # Create an event manager
        eventManagerType = eventManager.pop('type')
        eventManager = self.context['eventManager'] = \
                EventManager.make(eventManagerType, **eventManager)

        self.context['ioloop'].run_sync(eventManager.start)

        self.addToContextFlatten(
        {
            'public': ['eventManager']
        })


    def start(self):
        '''
        Start-time hook for sub-classes.
        '''
        pass


    def addWorkHandlers(self, handlers):
        self.workHandlers.update(handlers)


    def addWorkUrlHandlers(self, handlers):
        '''
        Deprecated. Use addWorkHandlers() instead.
        '''
        return self.addWorkHandlers(handlers)


    def _destroy(self):
        # If already destroyed, do nothing
        if not self.started or self._destroyed:
            return

        # Sub-class destroy
        self.destroy()

        # Destroy app plugins
        for appPlugin in self.context['appPlugins'].values():
            appPlugin.destroy(self, self.context)

        if not self._workerMode:
            if self.context['worker'] is not None:
                # Stop worker proxy
                logger.info('Stopping worker proxy')
        else:
            if self.context['worker'] is not None:
                logger.info('Stopping worker')

        def stopEvtLoop():
            # Stop event loop after a delay
            delaySeconds = self.context['shutdownDelay']

            label = self._workerMode and 'Worker application' \
                    or 'Server application'

            def stop():
                self.context['ioloop'].stop()
                self._destroyed = True
                logger.info('%s has been shut down.', label)

            logger.info('%s will be shut down in %d seconds', label,
                    delaySeconds)
            self.context['ioloop'].add_timeout(
                    time.time() + delaySeconds, stop)

        if self.context['worker'] is not None:
            workerStopFuture = self.context['worker'].stop()

            def onWorkerStopped(workerStopFuture):
                try:
                    workerStopFuture.result()
                finally:
                    stopEvtLoop()

            self.context['ioloop'].add_future(workerStopFuture, onWorkerStopped)
        else:
            stopEvtLoop()


    def destroy(self):
        '''
        Destroy-time hook for sub-classes.
        '''
        pass


    def addToContextFlatten(self, attrKeys):
        for attrType, keys in list(attrKeys.items()):
            for key in keys:
                self.context.addFlattenedAttr(attrType, key)


    _workerMode = None
    _destroyed = None
