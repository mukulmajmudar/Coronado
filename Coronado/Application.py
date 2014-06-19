import sys
import functools
from contextlib import closing
import argparse
import json
import traceback

import tornado.ioloop
import tornado.httpclient
import MySQLdb
from MySQLdb.cursors import DictCursor

import Coronado
import Coronado.Testing
from . import Email
import RabbitMQ

workerClasses = \
{
    'RabbitMQ': RabbitMQ.Worker
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

    def __init__(self, config, workerMode=False):
        self.config = config
        self._workerMode = workerMode


    def setup(self, context=None):
        if context is None:
            context = {}

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

        # Define url handler
        self.tornadoApp = tornado.web.Application(self._getUrlHandlers())

        self.context['tornadoApp'] = self.tornadoApp

        # Setup a worker if configured
        worker = self.context.get('worker')
        if worker:
            # Get app-specific work handlers
            handlers = self._getWorkHandlers()

            # If an email work key is configured, add an email work handler
            emailWorkKey = self.context.get('emailWorkKey')
            if emailWorkKey is not None:
                handlers.append(
                    (emailWorkKey, Coronado.Email.SendEmail, self.context))

            # Setup a worker
            workerType = worker['type']
            del worker['type']
            worker = self.context['worker'] = workerClasses[workerType](
                    handlers=handlers, **worker)
            worker.setup()

            self._addToContextFlatten(
            {
                'non-public': ['worker']
            })

            if self._workerMode:
                worker.start()


    def startListening(self):
        if self._workerMode:
            return

        self.tornadoApp.listen(self.context['port'])


    def startEventLoop(self):
        self.context['ioloop'].start()


    def stopEventLoop(self):
        self.context['ioloop'].stop()


    def destroy(self):
        pass


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


    def _getUrlHandlers(self):
        return []


    def _getWorkHandlers(self):
        return []


    def _addToContextFlatten(self, attrKeys):
        flatten = self.context.get('flatten', {})
        for attrType, keys in attrKeys.iteritems():
            if attrType in flatten:
                for key in keys:
                    flatten[attrType].append(key)
            else:
                flatten[attrType] = keys[:]
        self.context['flatten'] = flatten



    _workerMode = None


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
