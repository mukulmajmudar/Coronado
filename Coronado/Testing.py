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
import argparse

import MySQLdb
from MySQLdb.cursors import DictCursor
import tornado.testing

from .HttpUtil import parseContentType
from .Exceptions import IllegalArgument

class TestEnvironmentError(Exception):
    pass


class Scaffold(object):
    app = None

    def __init__(self, config, appClass, *args, **kwargs):
        self._config = config

        # Create application
        self.app = appClass(config, *args, **kwargs)


    def setup(self):
        # Install test database and setup the app
        self._installTestDatabase()
        self.app.setup()


    def destroy(self):
        '''
        Destroy the test database
        '''
        cmd = 'mysql --user=%s --password="%s" %s --execute="%s"' \
                % (self._config['mysql']['user'],
                        self._config['mysql']['password'],
                        self._config['mysql']['dbName'],
                        'DROP DATABASE \\`' + self._config['mysql']['dbName'] 
                        + '\\`')
        rc = os.system(cmd)
        if rc != 0:
            raise TestEnvironmentError('Could not destroy database')


    def _installTestDatabase(self):
        mysql = self._config['mysql']

        # Drop database if exists
        cmd = ('mysql --user=%s --password="%s" --execute="DROP DATABASE IF ' + \
                'EXISTS \\`%s\\`"') % (mysql['user'], mysql['password'], 
                        mysql['dbName'])
        rc = os.system(cmd)
        if rc != 0:
            raise TestEnvironmentError('Failed to drop previous database')

        cmd = 'mysql --user=%s --password="%s" --execute="CREATE DATABASE \\`%s\\`"' \
                % (mysql['user'], mysql['password'], mysql['dbName'])
        rc = os.system(cmd)
        if rc != 0:
            raise TestEnvironmentError('Failed to create database')

        cmd = 'mysql --user=%s --password="%s" %s < %s' \
                % (mysql['user'], mysql['password'], mysql['dbName'], 
                        mysql['schemaFilePath'])
        rc = os.system(cmd)
        if rc != 0:
            raise TestEnvironmentError('Failed to install database schema')


    _config = None


class AppTester(Scaffold):

    def __init__(self, config, appClass, unitSuiteBuilder, integSuiteBuilder, 
            *args, **kwargs):
        super(AppTester, self).__init__(config, appClass, *args, **kwargs)
        self._unitSuiteBuilder = unitSuiteBuilder
        self._integSuiteBuilder = integSuiteBuilder


    def runTests(self):
        try:
            self.app.startListening()

            # Parse command-line args
            argParser = argparse.ArgumentParser()
            argParser.add_argument('-i', '--integration', action='store_true', 
                    help='Run integration tests')
            argParser.add_argument('--all', action='store_true',
                    help='Run both unit and integration tests')
            argParser.add_argument('--unit', action='store_true',
                    help='Run unit tests')
            args = argParser.parse_args()

            # Build the test suite
            suite = None
            if args.all:
                suite = unittest.TestSuite()
                suite.addTest(self._unitSuiteBuilder())
                suite.addTest(self._integSuiteBuilder())
            elif args.integration:
                suite = self._integSuiteBuilder(self.app.context)
            else:
                suite = self._unitSuiteBuilder(self.app.context)

            assert suite is not None

            # Run the suite
            result = unittest.TestResult()
            sys.stderr.write('Running ' + str(suite.countTestCases())
                    + ' test cases...\n')
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
            self.destroy()


    _suiteBuilder = None


class _TestRoot(tornado.testing.AsyncTestCase):
    '''
    Root class for TestCase and mixins. The purpose of this class is to 
    consume the "context" and "testType" constructor keyword args before 
    forwarding to AsyncTestCase.

    Inspired by: 
    http://rhettinger.wordpress.com/2011/05/26/super-considered-super/
    '''

    def __init__(self, *args, **kwargs):
        try:
            del kwargs['context']
        except KeyError:
            pass
        try:
            del kwargs['testType']
        except KeyError:
            pass
        super(_TestRoot, self).__init__(*args, **kwargs)


class TestCase(_TestRoot):

    def __init__(self, *args, **kwargs):
        '''
        A "context" keyword argument is required. It should be a dictionary
        containing at least the following mappings:

        ioloop => Tornado IOLoop to be used for this test case
        httpClient => AsyncHTTPClient to be used for this test case

        The context argument will be available to subclasses as self._context.

        An optional "testType" keyword argument ("unit" or "integration") can 
        be given which will be stored as self._testType for subclasses.
        '''
        self._context = kwargs['context']
        self._ioloop = self._context['ioloop']
        self._httpClient = self._context['httpClient']
        self._testType = kwargs.get('testType', 'unit')

        # Call parent constructor
        super(TestCase, self).__init__(*args, **kwargs)


    def get_new_ioloop(self):
        return self._ioloop


    def get_app(self):
        return self._context['tornadoApp']


    def _assertJsonResponse(self, httpResponse, charset='UTF-8'):
        contentType, reqCharset = parseContentType(
                httpResponse.headers.get('Content-Type'))
        self.assertEqual(contentType, 'application/json')
        self.assertEqual(reqCharset, charset)
        return json.loads(httpResponse.body)


    _context = None
    _ioloop = None


def _installFixture(database, fixture, ignoreConflicts):
    if 'tableOrder' not in fixture:
        return

    # Install fixture into database
    for tableName in fixture['tableOrder']:
        for row in fixture[tableName]:
            query = 'INSERT INTO ' + tableName + ' (' \
                    + ','.join(row.keys()) \
                    + ') VALUES (' + '%s' + ',%s' * (len(row) -1) + ')'
            with closing(database.cursor()) as cursor:
                try:
                    cursor.execute(query, tuple(row.values()))
                except MySQLdb.IntegrityError:
                    if ignoreConflicts:
                        continue
                    else:
                        raise


def installFixture(database, fixture, ignoreConflicts=False):
    # If there is no "self" key in self.fixture, that means the
    # entire fixture dict is the self fixture
    if 'self' not in fixture:
        _installFixture(database, fixture, ignoreConflicts)
    else:
        # Fixtures for multiple apps are given
        for appName, fix in fixture.items():
            if appName == 'self':
                _installFixture(database, fix, ignoreConflicts)
            else:
                # Output fixture into a JSON file and wait for confirmation
                # from user that it has been loaded into the correct app
                f = tempfile.NamedTemporaryFile(
                        prefix=appName + '-', suffix='.json',
                        delete=False)
                json.dump(fix, f)
                f.flush()
                raw_input(('Please load the file "%s" into a test ' +
                    'instance of "%s". Press ENTER to continue.') 
                    % (f.name, appName))


class FixtureMixin(_TestRoot):
    '''
    Database fixture mixin for TestCase.

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
        '''
        context = kwargs['context']
        self._database = context['database']
        self._mysqlArgs = context['mysql']

        # Call parent constructor
        super(FixtureMixin, self).__init__(*args, **kwargs)


    def setUp(self):
        # Call parent version
        super(FixtureMixin, self).setUp()

        # Get the fixture
        fixture = self._getFixture() 

        # If fixture is a file path, load it as JSON
        if isinstance(fixture, str):
            fixture = json.load(open(fixture))

        # Fixture must be a dictionary
        if not isinstance(fixture, dict):
            raise IllegalArgument('fixture must be a dictionary')

        # Install the fixture
        installFixture(self._database, fixture)


    def tearDown(self):
        '''
        Truncate all tables.
        '''
        # Call parent version
        super(FixtureMixin, self).tearDown()

        if self._mysqlArgs is None:
            return

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


    _database = None
    _mysqlArgs = None


def getInputSets(inputValues):
    '''
    Returns a generator for (isValid, inputSet, invalidKeys) triples, one for 
    each combination of valid/invalid key-value pairs in the given input 
    dictionary.
    '''

    keys = inputValues.keys()

    def buildInputSet(keyIdx, inputSet, invalidKeys, isValid):
        '''
        Recursive function for building an input set.

        Returns a generator.
        '''

        # Break recursion if all keys have been processed. A complete
        # input set has been generated.
        if keyIdx == len(keys):
            yield isValid, inputSet, invalidKeys
            return

        # Read key at the given index
        key = keys[keyIdx]

        # For each valid value of the key
        validValues = inputValues[key]['validValues']
        for validValue in validValues:
            # Set key's value in the input set
            inputSet[key] = validValue

            # Remove this key from the set of invalid keys if present
            try:
                invalidKeys.remove(key)
            except KeyError:
                pass

            # Recurse for the next key. Each recursive call returns a 
            # generator so we need to iterate through it.
            for i, s, ik in buildInputSet(keyIdx + 1, inputSet, 
                    invalidKeys, isValid):
                yield i, s, ik

        # For each invalid value of the key
        invalidValues = inputValues[key]['invalidValues']
        for invalidValue in invalidValues:
            # Set this key's value in the input
            inputSet[key] = invalidValue

            # Add this key to the set of invalid keys
            invalidKeys.add(key)

            # Recurse for the next key. Each recursive call returns a 
            # generator so we need to iterate through it.
            for i, s, ik in buildInputSet(keyIdx + 1, inputSet, 
                    invalidKeys, False):
                yield i, s, ik


    # Need as many for-loops as there are keys. 
    # Solution: use recursion. For each input set to return, there will
    # be one recursive call for each key. 
    return buildInputSet(0, {}, set(), True)


class InputSetsMixin(_TestRoot):

    def setUp(self):
        # Call parent version
        super(InputSetsMixin, self).setUp()

        # Load input values
        self._inputValues = self._getInputValues()

        # Get input values
        inputValues = self._getInputValues()

        # If return value is a file path, load it as JSON
        if isinstance(inputValues, str):
            inputValues = json.load(open(inputValues))

        # inputValues must be a dictionary
        if not isinstance(inputValues, dict):
            raise IllegalArgument('input values description must be a '
                + 'dictionary')

        self._inputValues = inputValues


    def testInputSets(self):
        # Execute test function for each input set
        for isValid, inputSet, invalidKeys in getInputSets(self._inputValues):
            self._testInputSet(isValid, inputSet, invalidKeys)


    def _testInputSet(self, isValid, inputSet, invalidKeys):
        raise NotImplementedError()
         

    def _getInputValues(self):
        raise NotImplementedError()


    _inputValues = None
