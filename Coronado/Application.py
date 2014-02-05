import functools
from contextlib import closing

import tornado.ioloop
import tornado.httpclient
import MySQLdb
from MySQLdb.cursors import DictCursor

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
            self.context['httpClient'] = tornado.httpclient.AsyncHTTPClient()
        if 'messageQueue' not in self.context:
            self.context['messageQueue'] = MySQLMessageQueue(
                    self.context['mysql'])
        if 'messageHandlers' not in self.context:
            self.context['messageHandlers'] = {}
        if 'errorEmailer' not in self.context:
            self.context['errorEmailer'] = functools.partial(
                    Email.send, self.context['messageQueue'])

        # Define url handler
        self.tornadoApp = tornado.web.Application(self._getUrlHandlers())


    def startListening(self):
        # Start the message queue
        """Coronado.startMessageQueue(
                messageQueue=self.context['messageQueue'],
                mysqlArgs=self.context['mysql'], 
                messageHandlers=self.context['messageHandlers'])
        """

        self.tornadoApp.listen(self.context['tornado']['port'])


    def startEventLoop(self):
        self.context['ioloop'].start()


    def destroy(self):
        self.context['ioloop'].stop()

        # TODO: destroy message queue


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
