from .Application import Application

class Config(dict):

    def __init__(self, keys):
        keys = \
        [
            'admin',
            'allowedCORSOrigins',
            'allowedWSOrigins',
            'apiVersions',
            'appClass',
            'appName',
            'appPackage',
            'appRoot',
            'errorEmailRecipient',
            'errorEmailSubject',
            'emailSender',
            'emailWorkTag',
            'eventManager',
            'mysql',
            'port',
            'sendEmailOnError',
            'shutdownDelay',
            'smtp',
            'testPkg',
            'uri',
            'worker',
        ] + keys
        for key in keys:
            self[key] = getattr(self, '_get' + key[0].upper() + key[1:])()

        super(Config, self).__init__()


    def _getAdmin(self):
        return \
        {
            'name': self._getAdminName(),
            'email': self._getAdminEmail()
        }


    def _getAdminName(self):
        return None


    def _getAdminEmail(self):
        return None


    def _getAllowedCORSOrigins(self):
        '''
        List of origins allowed to access this server.
        '''
        return []


    def _getAllowedWSOrigins(self):
        '''
        List of origins allowed to access this server using WebSocket protocol.
        '''
        return []


    def _getApiVersions(self):
        return ['1']


    def _getAppClass(self):
        return Application


    def _getAppName(self):
        '''
        A descriptive name for the application.
        '''
        return 'Coronado Application'


    def _getAppPackage(self):
        raise NotImplementedError()


    def _getAppRoot(self):
        '''
        Root directory of the Coronado application.
        '''
        raise NotImplementedError()


    def _getErrorEmailRecipient(self):
        return self['admin']['email']


    def _getErrorEmailSubject(self):
        return '[ERROR][%s] Server Error Occurred' % (self['appName'],)


    def _getEmailWorkTag(self):
        return 'sendEmail'


    def _getEventManager(self):
        return None


    def _getMysql(self):
        '''
        MySQL parameters
        '''
        return \
        {
            'host': self._getMysqlHost(),
            'port': self._getMysqlPort(),
            'user': self._getMysqlUser(),
            'password': self._getMysqlPassword(),
            'dbName': self._getMysqlDbName(),
            'schemaFilePath': self._getMySchemaFilePath()
        }


    def _getMysqlHost(self):
        raise NotImplementedError()


    def _getMysqlPort(self):
        return 3306


    def _getMysqlUser(self):
        raise NotImplementedError()


    def _getMysqlPassword(self):
        raise NotImplementedError()


    def _getMysqlDbName(self):
        raise NotImplementedError()

    def _getMySchemaFilePath(self):
        raise NotImplementedError()

    def _getEmailSender(self):
        return ''

    def _getPort(self):
        '''
        Port on which to listen for requests.
        '''
        raise NotImplementedError()


    def _getSendEmail(self):
        '''
        Return True to enable SMTP-based email sending.
        '''
        return False


    def _getSendEmailOnError(self):
        return True


    def _getShutdownDelay(self):
        return 5.0


    def _getSmtp(self):
        '''
        SMTP parameters
        '''
        return \
        {
            'host': self._getSmtpHost(),
            'port': self._getSmtpPort(),
            'email': self._getSmtpEmail(),
            'password': self._getSmtpPassword()
        }


    def _getSmtpHost(self):
        raise NotImplementedError()


    def _getSmtpPort(self):
        raise NotImplementedError()


    def _getSmtpEmail(self):
        raise NotImplementedError()


    def _getSmtpPassword(self):
        raise NotImplementedError()


    def _getTestPkg(self):
        '''
        Package containing tests and test config.
        '''
        return None


    def _getUri(self):
        '''
        URI of this application.
        '''
        return 'http://127.0.0.1:%d' % (self['port'],)


    def _getWorker(self):
        return None
