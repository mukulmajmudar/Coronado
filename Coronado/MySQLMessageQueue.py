import multiprocessing
from contextlib import closing
import sys
import traceback

import MySQLdb

class MySQLMessageQueue(object):
    condition = None
    mysqlArgs = None
    database = None
    name = None

    def __init__(self, mysqlArgs, name='messageQueue'):
        self.condition = multiprocessing.Condition()
        self.mysqlArgs = mysqlArgs
        self.name = name

        # Connect to MySQL
        self.database = MySQLdb.connect(host=mysqlArgs['host'],
                user=mysqlArgs['user'], passwd=mysqlArgs['password'], 
                db=mysqlArgs['dbName'], use_unicode=True, charset='utf8')

        # Turn on autocommit
        self.database.autocommit(True)

        with closing(self.database.cursor()) as cursor:
            # Set wait_timeout to its largest value (365 days): connection will be
            # disconnected only if it is idle for 365 days.
            cursor.execute("SET wait_timeout=31536000")

            # Create message queue table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS `''' + name + '''`(
                    position INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
                    class VARCHAR(100) CHARACTER SET utf8,
                    value TEXT) ENGINE=INNODB''')


    def put(self, msgClass, msgValue):
        cursor = None
        try:
            self.condition.acquire()
            cursor = self.database.cursor()
            cursor.execute(
                '''INSERT INTO `''' + self.name + '''` (class, value) 
                   VALUES(%s, %s)''', (msgClass, msgValue))
            self.database.commit()

            # Notify any waiting processes
            self.condition.notify()

        finally:
            self.condition.release()
            if cursor is not None:
                cursor.close()


    def get(self):
        cursor = None
        try:
            self.condition.acquire()
            cursor = self.database.cursor()

            def getNextRow():
                cursor.execute(
                    '''SELECT position, class, value FROM `''' + self.name 
                    + '''` ORDER BY position LIMIT 1''')
                self.database.commit()
                return cursor.fetchone()

            # Get the next row from the database. If no rows, wait
            # till a row is available
            row = getNextRow()
            while not row:
                self.condition.wait()
                row = getNextRow()

            # Delete the row from the database
            cursor.execute(
                    '''DELETE FROM `''' + self.name + 
                    '''` WHERE position = %s''', (row[0],))
            self.database.commit()

            # A row is available, so return it as a message
            message = {'class' : row[1], 'value' : row[2]}
            return message

        finally:
            self.condition.release()
            if cursor is not None:
                cursor.close()
         

class MessageDispatcher(object):
    handlers = None
    messageQueue = None

    def __init__(self, messageQueue):
        self.handlers = dict()
        self.messageQueue = messageQueue


    def register(self, msgClass, handler):
        # Get list of handlers for the message class
        handlerList = None
        if msgClass not in self.handlers:
            self.handlers[msgClass] = handlerList = []
        else:
            handlerList = self.handlers[msgClass]

        # Add given handler to the list
        handlerList.append(handler)


    def start(self):
        while True:
            try:
                # Wait for a message
                message = self.messageQueue.get()
            except KeyboardInterrupt:
                break

            # Give it to registered handlers, if any
            if message['class'] in self.handlers:
                handlerList = self.handlers[message['class']]
                for handler in handlerList:
                    try:
                        handler(message['value'])
                    except Exception as e:
                        sys.stderr.write('Exception occurred while handling '
                                + 'message: \n')
                        sys.stderr.write(traceback.format_exc() + '\n')
