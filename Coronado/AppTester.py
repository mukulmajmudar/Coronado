import os
import sys
# Import unittest2 for Python < 2.7, unittest otherwise
if sys.version_info[0] <= 2 and sys.version_info[1] < 7:
    import unittest2 as unittest
else:
    import unittest

class TestEnvironmentError(Exception):
    pass


class AppTester(object):
    config = None
    suiteBuilder = None
    app = None

    def __init__(self, config, appClass, suiteBuilder, *args, **kwargs):
        self.config = config
        self.suiteBuilder = suiteBuilder

        # Create application
        self.app = appClass(config, *args, **kwargs)


    def setup(self):
        # Install test database and setup the app
        self._installTestDatabase()
        self.app.setup()


    def runTests(self):
        try:
            self.app.startListening()

            self._run()

            # Start the application's event loop
            self.app.startEventLoop()
        finally:
            self._destroyTestDatabase()


    def _installTestDatabase(self):
        mysql = self.config['mysql']

        # Drop database if exists
        cmd = ('mysql --user=%s --password="%s" --execute="DROP DATABASE IF ' + \
                'EXISTS %s"') % (mysql['user'], mysql['password'], 
                        mysql['dbName'])
        rc = os.system(cmd)
        if rc != 0:
            raise TestEnvironmentError('Failed to drop previous database')

        cmd = 'mysql --user=%s --password="%s" --execute="CREATE DATABASE %s"' \
                % (mysql['user'], mysql['password'], mysql['dbName'])
        rc = os.system(cmd)
        if rc != 0:
            raise TestEnvironmentError('Failed to create database')

        cmd = 'mysql --user=%s --password="%s" %s < dbSchema.sql' \
                % (mysql['user'], mysql['password'], mysql['dbName'])
        rc = os.system(cmd)
        if rc != 0:
            raise TestEnvironmentError('Failed to install database schema')


    def _destroyTestDatabase(self):
        '''
        Destroy the test database
        '''
        context = self.app.context
        cmd = 'mysql --user=%s --password="%s" %s --execute="%s"' \
                % (context['mysql']['user'],
                        context['mysql']['password'],
                        context['mysql']['dbName'],
                        'DROP DATABASE ' + context['mysql']['dbName'])
        rc = os.system(cmd)
        if rc != 0:
            raise TestEnvironmentError('Could not destroy database')


    def _run(self):
        # Build the test suite
        suite = self.suiteBuilder(self.app.context)

        # Run the suite
        result = unittest.TestResult()
        suite.run(result)

        # Check for errors and failures
        if result.errors:
            for error in result.errors:
                print 'Error:\n' + error[1]
        if result.failures:
            for failure in result.failures:
                print 'Failure:\n' + failure[1]
        if not result.errors and not result.failures:
            print 'All tests passed successfully. Congratulations!'

        # Destroy the app
        self.app.destroy()
