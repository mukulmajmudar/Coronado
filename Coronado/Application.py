import logging
import time

import importlib
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

class DatabaseError(Exception):
    pass

class SchemaVersionMismatch(Exception):
    pass


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
    httpServer = None
    urlHandlers = None
    workHandlers = None
    xheaders = None
    started = False

    def __init__(self, config, workerMode=False, xheaders=True):
        self.config = config
        self._workerMode = workerMode
        self._destroyed = False
        self.urlHandlers = {}
        self.workHandlers = {}
        self.xheaders = xheaders


    def prepare(self, context=None):
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

        # Assign defaults for any context arguments that are not already there
        if 'ioloop' not in self.context:
            self.context['ioloop'] = tornado.ioloop.IOLoop.instance()

        # Set up app plugins
        for plugin in self.context['plugins']:
            appPluginClass = getattr(plugin, 'AppPlugin', False)
            if not appPluginClass:
                continue
            appPlugin = appPluginClass()
            appPlugin.setup(self, self.context)

        self.addToContextFlatten(
        {
            'public':
            [
                'ioloop',
                'database',
                'httpClient',
                'getNewDbConnection'
            ],
            # Some old clients need non-public versions too
            'non-public': ['ioloop', 'database', 'httpClient']
        })

        # Check Database schema version matches what is expected
        self.checkDbSchemaVersion()

        # Setup eventManager if configured
        self.setupEventManager()

        # Call API-specific setup functions
        self.setup()

        # Setup worker if configured
        self.setupWorker()

        # Define url handlers
        urls = {}
        for i, apiVersion in enumerate(self.urlHandlers):
            # If no API version is specified, we will use the oldest one
            if i == 0:
                urls.update(self.urlHandlers[apiVersion])

            versionUrls = self.urlHandlers[apiVersion]
            for url, handlerClass in list(versionUrls.items()):
                urls['/v' + str(apiVersion) + url] = handlerClass
        logger.debug('URL mappings: %s', str(urls))
        urlHandlers = [mapping + (self.context,)
                for mapping in zip(list(urls.keys()), list(urls.values()))]

        if urlHandlers:
            self.tornadoApp = tornado.web.Application(urlHandlers)

        self.context['tornadoApp'] = self.tornadoApp

    def getCurrDbSchemaVersion(self):
        '''
        Get currently installed database schema version.
        '''
        currentVersion = None
        with closing(self.context['database'].cursor()) as cursor:
            try:
                cursor.execute('SELECT * FROM metadata WHERE attribute = %s',
                        ('version',))
            except pymysql.ProgrammingError as e:
                # 1146 == table does not exist
                if e.args[0] == 1146:
                    # Version 1 tables don't exist either, so it is most
                    # likely that no schema is installed
                    return None
                else:
                    raise
            else:
                row = cursor.fetchone()
                if not row:
                    raise DatabaseError('Could not read current ' +
                        'database version')
                currentVersion = row['value']

        return currentVersion


    def checkDbSchemaVersion(self):
        currentVersion = self.getCurrDbSchemaVersion()

        # Get most recent version from context
        expectedVersion = self.context['databasePkg'].versions[-1]

        if currentVersion != expectedVersion:
            raise SchemaVersionMismatch(
                ('Installed database schema version {} does '
                'not match expected version {}').format(
                    currentVersion, expectedVersion))


    def setup(self):
        pass


    def setupWorker(self):
        worker = self.context.get('worker')
        if not worker:
            return

        workerType = worker.pop('type')
        classes = workerClasses[workerType]

        # Setup a worker or proxy based on mode
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


    def setupEventManager(self):
        eventManager = self.context.get('eventManager')
        if not eventManager:
            return

        # Create an event manager
        eventManagerType = eventManager.pop('type')
        eventManager = self.context['eventManager'] = \
                EventManager.make(eventManagerType, **eventManager)

        self.context['ioloop'].run_sync(eventManager.setup)

        self.addToContextFlatten(
        {
            'public': ['eventManager'],
        })


    def startListening(self):
        if self._workerMode:
            return

        # Create a new HTTPServer
        from tornado.httpserver import HTTPServer
        self.httpServer = HTTPServer(self.tornadoApp, xheaders=self.xheaders)

        # Start listening
        self.httpServer.listen(self.context['port'])


    def startEventLoop(self):
        '''
        # Start plugins
        for plugin in self.context['plugins']:
            if hasattr(plugin, 'start'):
                getattr(plugin, 'start')(self, self.context)
        '''

        self._callApiSpecific('start', self, self.context)
        self.started = True
        self.context['ioloop'].start()


    def stopEventLoop(self):
        self.context['ioloop'].stop()


    def addUrlHandlers(self, version, urlHandlers):
        if version in self.urlHandlers:
            self.urlHandlers[version].update(urlHandlers)
        else:
            self.urlHandlers[version] = urlHandlers


    def addWorkHandlers(self, handlers):
        self.workHandlers.update(handlers)


    def addWorkUrlHandlers(self, handlers):
        '''
        Deprecated. Use addWorkHandlers() instead.
        '''
        return self.addWorkHandlers(handlers)


    def destroy(self):
        # If already destroyed, do nothing
        if not self.started or self._destroyed:
            return

        self._callApiSpecific('destroy', self, self.context)

        # Stop accepting new HTTP connections, then shutdown server after a
        # delay. This pattern is suggested by Ben Darnell (a maintainer of
        # Tornado):
        # https://groups.google.com/d/msg/python-tornado/NTJfzETaxeI/MaJ-hvTw4_4J

        if not self._workerMode:
            # Stop accepting new connections
            self.httpServer.stop()

            if self.context['worker'] is not None:
                # Stop worker proxy
                logger.info('Stopping worker proxy')
        else:
            if self.context['worker'] is not None:
                logger.info('Stopping worker')

        if self.context['worker'] is not None:
            workerStopFuture = self.context['worker'].stop()

            def onWorkerStopped(workerStopFuture):
                try:
                    workerStopFuture.result()
                finally:
                    # Stop event loop after a delay
                    delaySeconds = self.context['shutdownDelay']

                    label = self._workerMode and 'Worker application' \
                            or 'Server application'

                    def stop():
                        self.stopEventLoop()
                        self._destroyed = True
                        logger.info('%s has been shut down.', label)

                    logger.info('%s will be shut down in %d seconds', label,
                            delaySeconds)
                    self.context['ioloop'].add_timeout(
                            time.time() + delaySeconds, stop)

            self.context['ioloop'].add_future(workerStopFuture, onWorkerStopped)


    def _callApiSpecific(self, functionName, *args, **kwargs):
        for apiVersion in self.context.get('apiVersions', ['1']):
            versionMod = importlib.import_module(
                    self.context['appPackage'].__name__
                    + '.v' + apiVersion)
            if hasattr(versionMod, functionName):
                getattr(versionMod, functionName)(*args, **kwargs)


    def addToContextFlatten(self, attrKeys):
        for attrType, keys in list(attrKeys.items()):
            for key in keys:
                self.context.addFlattenedAttr(attrType, key)


    _workerMode = None
    _destroyed = None
