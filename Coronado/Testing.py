import sys
# Import unittest2 for Python < 2.7, unittest otherwise
if sys.version_info[0] <= 2 and sys.version_info[1] < 7:
    import unittest2 as unittest
else:
    import unittest
import os
import json
import tempfile

import MySQLdb
from MySQLdb.cursors import DictCursor

from .Exceptions import IllegalArgument

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

        cmd = 'mysql --user=%s --password="%s" %s < %s' \
                % (mysql['user'], mysql['password'], mysql['dbName'], 
                        self.config['dbSchemaFileName'])
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


class DbFixtureTestCase(unittest.TestCase):
    fixture = None
    database = None

    def __init__(self, *args, **kwargs):
        # Call super
        super(DbFixtureTestCase, self).__init__(*args)
        self.context = kwargs['context']
        self.database = self.context['database']
        self.fixture = kwargs['fixture']

        # If fixture is a file path, load it as a path relative to 
        if isinstance(self.fixture, str):
            self.fixture = json.load(open(self.fixture))

        # Fixture must be a dictionary
        if not isinstance(self.fixture, dict):
            raise IllegalArgument('fixture must be a dictionary')


    def setUp(self):
        # If there is no "self" key in self.fixture, that means the
        # entire fixture dict is the self fixture
        if 'self' not in self.fixture:
            self._installSelfFixture(self.fixture)
        else:
            # Fixtures for multiple apps are given
            for appName, fixture in self.fixture.items():
                if appName == 'self':
                    self._installSelfFixture(fixture)
                else:
                    # Output fixture into a JSON file and wait for confirmation
                    # from user that it has been loaded into the correct app
                    f = tempfile.NamedTemporaryFile(prefix=appName + '-', suffix='.json',
                            delete=False)
                    json.dump(fixture, f)
                    raw_input(('Please load the file "%s" into a test ' +
                        'instance of "%s". Press ENTER to continue.') 
                        % (f.name, appName))


    def tearDown(self):
        '''
        Truncate all tables.
        '''
        # Credit: http://stackoverflow.com/a/8912749/1196816
        cmd = ("mysql -u %s -p'%s' -Nse 'show tables' %s " \
                + "| while read table; do mysql -u %s -p'%s' -e \"truncate table $table\" " \
                + "%s; done") % (
                        self.context['mysql']['user'], 
                        self.context['mysql']['password'],
                        self.context['mysql']['dbName'], 
                        self.context['mysql']['user'], 
                        self.context['mysql']['password'],
                        self.context['mysql']['dbName'])

        rc = os.system(cmd)
        if rc != 0:
            raise TestEnvironmentError('Failed to reset database')


    def _installSelfFixture(self, fixture):
        # Install fixture into database
        for tableName in fixture['tableOrder']:
            for row in fixture[tableName]:
                query = 'INSERT INTO ' + tableName + ' (' \
                        + ','.join(row.keys()) \
                        + ') VALUES (' + '%s' + ',%s' * (len(row) -1) + ')'
                with closing(self.database.cursor()) as cursor:
                    cursor.execute(query, tuple(row.values()))

