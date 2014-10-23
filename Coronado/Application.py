import sys
import functools
from contextlib import closing
import argparse
import json
import traceback
import logging
import time

import importlib
import tornado.ioloop
import tornado.httpclient
import MySQLdb
from MySQLdb.cursors import DictCursor

import Coronado
import Coronado.Testing
from . import Email
import RabbitMQ

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
    httpServer = None
    urlHandlers = None
    workUrlHandlers = None
    started = False

    def __init__(self, config, workerMode=False):
        self.config = config
        self._workerMode = workerMode
        self._destroyed = False
        self.urlHandlers = {}
        self.workUrlHandlers = {}


    def setup(self, context=None):
        if context is None:
            context = {}

        context['workerMode'] = self._workerMode

        # Initialize context to be a copy of the configuration
        self.context = self.config.copy()

        # Override with passed in arguments (customization)
        self.context.update(context)

        # Assign defaults for any context arguments that are not already there
        if 'ioloop' not in self.context:
            self.context['ioloop'] = tornado.ioloop.IOLoop.instance()
        if 'database' not in self.context:
            self.context['database'] = self._getDbConnection()
        if 'httpClient' not in self.context:
            '''
            # Configure AsyncHTTPClient to use cURL implementation
            tornado.httpclient.AsyncHTTPClient.configure(
                    "tornado.curl_httpclient.CurlAsyncHTTPClient",
                    max_clients=5000)
            '''
            self.context['httpClient'] = tornado.httpclient.AsyncHTTPClient(
                    self.context['ioloop'])

        if 'getNewDbConnection' not in self.context:
            self.context['getNewDbConnection'] = self._getDbConnection

        # Call API-specific setup functions
        self._callApiSpecific('setup', self, self.context)

        # Setup a worker if configured
        worker = self.context.get('worker')
        if worker:
            workerType = worker['type']
            del worker['type']
            classes = workerClasses[workerType]

            # Setup a worker or proxy based on mode
            if self._workerMode:
                # Get app-specific work handlers
                handlers = self.workUrlHandlers

                # If an email work tag is configured, add an email work handler
                emailWorkTag = self.context.get('emailWorkTag')
                if emailWorkTag is not None:
                    handlers[emailWorkTag] = Coronado.Email.SendEmail

                # Convert to Tornado-style tuple
                workUrlHandlers = [mapping + (self.context,) 
                        for mapping in zip(handlers.keys(), handlers.values())]

                # Create a worker
                worker = self.context['worker'] = classes['worker'](
                        handlers=workUrlHandlers, **worker)
            else:
                # Create a worker proxy
                worker = self.context['worker'] = classes['proxy'](**worker)

            worker.setup()
            worker.start()

            self.addToContextFlatten(
            {
                'non-public': ['worker'],
                'public': ['getNewDbConnection']
            })

        # Define url handlers
        urls = {}
        for i, apiVersion in enumerate(self.urlHandlers):
            # If no API version is specified, we will use the oldest one
            if i == 0:
                urls.update(self.urlHandlers[apiVersion])

            versionUrls = self.urlHandlers[apiVersion]
            for url, handlerClass in versionUrls.iteritems():
                urls['/v' + str(apiVersion) + url] = handlerClass
        logger.debug('URL mappings: %s', str(urls))
        urlHandlers = [mapping + (self.context,) 
                for mapping in zip(urls.keys(), urls.values())]

        self.tornadoApp = tornado.web.Application(urlHandlers)

        self.context['tornadoApp'] = self.tornadoApp


    def startListening(self):
        if self._workerMode:
            return

        # Create a new HTTPServer
        from tornado.httpserver import HTTPServer
        self.httpServer = HTTPServer(self.tornadoApp)

        # Start listening
        self.httpServer.listen(self.context['port'])


    def startEventLoop(self):
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


    def addWorkUrlHandlers(self, urlHandlers):
        self.workUrlHandlers.update(urlHandlers)


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

            # Stop worker proxy
            logger.info('Stopping worker proxy')
        else:
            logger.info('Stopping worker')

        workerStopFuture = self.context['worker'].stop()

        def onWorkerStopped(workerStopFuture):
            try:
                workerStopFuture.result()
            finally:
                # Stop event loop after a delay
                delaySeconds = self.context.get('shutdownDelay', 5.0)

                label = self._workerMode and 'Worker' or 'Application'

                def stop():
                    self.stopEventLoop()
                    self._destroyed = True
                    logger.info('%s has been shut down.', label)

                logger.info('%s will be shut down in %d seconds', label,
                        delaySeconds)
                self.context['ioloop'].add_timeout(
                        time.time() + delaySeconds, stop)

        self.context['ioloop'].add_future(workerStopFuture, onWorkerStopped)


    def _getDbConnection(self):
        # Connect to MySQL
        mysqlArgs = self.context['mysql']
        database = MySQLdb.connect(host=mysqlArgs['host'], 
                user=mysqlArgs['user'], passwd=mysqlArgs['password'], 
                db=mysqlArgs['dbName'], use_unicode=True, charset='utf8',
                cursorclass=DictCursor)

        # Turn on autocommit
        database.autocommit(True)

        # Set wait_timeout to its largest value (365 days): connection will be
        # disconnected only if it is idle for 365 days.
        with closing(database.cursor()) as cursor:
            cursor.execute("SET wait_timeout=31536000")

        return database


    def _callApiSpecific(self, functionName, *args, **kwargs):
        for apiVersion in self.context.get('apiVersions', ['1']):
            versionMod = importlib.import_module(
                    self.context['appPackage'].__name__
                    + '.v' + apiVersion)
            if hasattr(versionMod, functionName):
                getattr(versionMod, functionName)(*args, **kwargs)


    def addToContextFlatten(self, attrKeys):
        flatten = self.context.get('flatten', {})
        for attrType, keys in attrKeys.iteritems():
            if attrType in flatten:
                for key in keys:
                    flatten[attrType].append(key)
            else:
                flatten[attrType] = keys[:]
        self.context['flatten'] = flatten



    _workerMode = None
    _destroyed = None


class AppStarter(object):

    def __init__(self, config):
        self._config = config


    def start(self, *args, **kwargs):
        app = None
        scaffold = None
        try:
            # Parse command-line args
            parser = argparse.ArgumentParser(description='Server starter')
            parser.add_argument('-t', '--test', action='store_true', 
                    help='Whether to start the application in test mode')
            parser.add_argument('-f', '--fixture', type=file,
                    help='Fixture file path, only applicable in test mode')
            clArgs = parser.parse_args()
            
            if clArgs.test:
                testsMod = __import__(self._config['testPkg'].__name__ + '.config')
                config = testsMod.config.config

                # Setup a testing scaffold
                scaffold = Coronado.Testing.Scaffold(config, config['appClass'],
                        *args, **kwargs)
                scaffold.setup()
                app = scaffold.app

                # Load test fixture if any
                if clArgs.fixture is not None:
                    fixture = json.load(clArgs.fixture)
                    Coronado.Testing.installFixture(
                            app.context['database'], fixture)

                # Start listening for requests
                scaffold.app.startListening()

                # Start async event loop
                scaffold.app.startEventLoop()

            else:
                # Create an application object and set it up.
                #
                # Startup code is placed into an "Application" class
                # for easier testability. See testing pattern recommended by
                # Bret Taylor (creator of Tornado) at:
                # https://groups.google.com/d/msg/python-tornado/hnz7JmXqEKk/S2zkl6L9ctEJ
                app = self._config['appClass'](self._config, *args, **kwargs)
                app.setup()

                # Start listening for requests
                app.startListening()

                # Start async event loop
                app.startEventLoop()
        except KeyboardInterrupt:
            pass
        except Exception as e:
            sys.stderr.write(traceback.format_exc() + '\n')
        finally:
            if app is not None:
                app.destroy()

            if scaffold is not None:
                scaffold.destroy()


    _config = None
