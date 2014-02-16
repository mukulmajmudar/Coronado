import sys
# Import unittest2 for Python < 2.7, unittest otherwise
if sys.version_info[0] <= 2 and sys.version_info[1] < 7:
    import unittest2 as unittest
else:
    import unittest
import os
import json
import tempfile
from contextlib import closing

import MySQLdb
from MySQLdb.cursors import DictCursor
import tornado.testing

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

        finally:
            # Destroy the app
            self.app.destroy()

            # Destroy the test database
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
        cmd = 'mysql --user=%s --password="%s" %s --execute="%s"' \
                % (self.config['mysql']['user'],
                        self.config['mysql']['password'],
                        self.config['mysql']['dbName'],
                        'DROP DATABASE ' + self.config['mysql']['dbName'])
        rc = os.system(cmd)
        if rc != 0:
            raise TestEnvironmentError('Could not destroy database')

class TestCase(tornado.testing.AsyncTestCase):

    def __init__(self, *args, **kwargs):
        '''
        A "context" keyword argument is required. It should be a dictionary
        containing at least the following mappings:

        ioloop => Tornado IOLoop to be used for this test case

        The context argument will be available to subclasses as self._context.
        '''
        self._context = kwargs['context']
        self._ioloop = self._context['ioloop']
        del kwargs['context']

        # Call parent constructor
        super(TestCase, self).__init__(*args, **kwargs)


    def get_new_ioloop(self):
        return self._ioloop


    _ioloop = None


class DbFixtureTestCase(TestCase):
    '''
    Test case with a database fixture.

    Implement _getFixture() to return either a dictionary or a 
    JSON file path containing a fixture. The fixture should be
    a dictionary mapping table names to rows.
    '''

    def __init__(self, *args, **kwargs):
        '''
        A "context" keyword argument is required. It should be a dictionary
        containing at least the following mappings:

        database => MySQL database connection
        mysql => dictionary of MySQL connection arguments: must contain at least
                 user, password, dbName
        ioloop => Tornado IOLoop to be used for this test case
        '''
        context = kwargs['context']
        self._database = context['database']
        self._mysqlArgs = context['mysql']

        # Call parent constructor
        super(DbFixtureTestCase, self).__init__(*args, **kwargs)


    def setUp(self):
        # Call parent version
        super(DbFixtureTestCase, self).setUp()

        # Get the fixture
        fixture = self._getFixture()

        # If fixture is a file path, load it as JSON
        if isinstance(fixture, str):
            fixture = json.load(open(fixture))

        # Fixture must be a dictionary
        if not isinstance(fixture, dict):
            raise IllegalArgument('fixture must be a dictionary')

        # If there is no "self" key in self.fixture, that means the
        # entire fixture dict is the self fixture
        if 'self' not in fixture:
            self._installSelfFixture(fixture)
        else:
            # Fixtures for multiple apps are given
            for appName, fix in fixture.items():
                if appName == 'self':
                    self._installSelfFixture(fix)
                else:
                    # Output fixture into a JSON file and wait for confirmation
                    # from user that it has been loaded into the correct app
                    f = tempfile.NamedTemporaryFile(prefix=appName + '-', suffix='.json',
                            delete=False)
                    json.dump(fix, f)
                    raw_input(('Please load the file "%s" into a test ' +
                        'instance of "%s". Press ENTER to continue.') 
                        % (f.name, appName))


    def tearDown(self):
        '''
        Truncate all tables.
        '''
        # Call parent version
        super(DbFixtureTestCase, self).tearDown()

        # Credit: http://stackoverflow.com/a/8912749/1196816
        cmd = ("mysql -u %s -p'%s' -Nse 'show tables' %s " \
                + "| while read table; do mysql -u %s -p'%s' -e \"truncate table $table\" " \
                + "%s; done") % (
                        self._mysqlArgs['user'], 
                        self._mysqlArgs['password'],
                        self._mysqlArgs['dbName'], 
                        self._mysqlArgs['user'], 
                        self._mysqlArgs['password'],
                        self._mysqlArgs['dbName'])

        rc = os.system(cmd)
        if rc != 0:
            raise TestEnvironmentError('Failed to reset database')


    def _getFixture(self):
        return {}


    def _installSelfFixture(self, fixture):
        # Install fixture into database
        for tableName in fixture['tableOrder']:
            for row in fixture[tableName]:
                query = 'INSERT INTO ' + tableName + ' (' \
                        + ','.join(row.keys()) \
                        + ') VALUES (' + '%s' + ',%s' * (len(row) -1) + ')'
                with closing(self._database.cursor()) as cursor:
                    cursor.execute(query, tuple(row.values()))

    _context = None
    _database = None
    _mysqlArgs = None
