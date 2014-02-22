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
from .MySQLMessageQueue import MySQLMessageQueue
from . import Email

class Application(object):
    config = None
    context = None
    tornadoApp = None

    def __init__(self, config):
        self.config = config


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
            self.context['httpClient'] = tornado.httpclient.AsyncHTTPClient(
                    self.context['ioloop'])
        if 'messageQueue' not in self.context:
            self.context['messageQueue'] = MySQLMessageQueue(
                    self.context['mysql'])
        if 'messageHandlers' not in self.context:
            self.context['messageHandlers'] = dict(
                    email=Coronado.Email.MessageHandler(self.context['smtp']))
        else:
            if 'email' not in self.context['messageHandlers']:
                self.context['messageQueue']['email'] \
                        = Coronado.Email.MessageHandler(self.context['smtp'])
        if 'errorEmailer' not in self.context:
            self.context['errorEmailer'] = functools.partial(
                    Email.send, self.context['messageQueue'])
        if 'getNewDbConnection' not in self.context:
            self.context['getNewDbConnection'] = self._getDbConnection

        # Define url handler
        self.tornadoApp = tornado.web.Application(self._getUrlHandlers())


    def startListening(self):
        # Start the message queue
        Coronado.startMessageQueue(
                messageQueue=self.context['messageQueue'],
                mysqlArgs=self.context['mysql'], 
                messageHandlers=self.context['messageHandlers'])

        self.tornadoApp.listen(self.context['port'])


    def startEventLoop(self):
        self.context['ioloop'].start()


    def stopEventLoop(self):
        self.context['ioloop'].stop()


    def destroy(self):
        Coronado.stopMessageQueue(self.context['messageQueue'])


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
